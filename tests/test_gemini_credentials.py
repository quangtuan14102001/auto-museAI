import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer
from config.settings import SettingsManager
from core.gemini_api import normalize_gemini_key, gemini_error
from ui.dialogs.film_dialog import FilmDialog
from ui.dialogs.settings_dialog import SettingsDialog
from workers.gemini_key_worker import GeminiKeyWorker
from workers.llm_rewriter import LLMRewriterWorker


class GeminiCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.previous = SettingsManager._instance
        self.settings = SettingsManager(str(self.root/'config/project_config.json'))
        SettingsManager._instance = self.settings
        self.settings.app_config['output_dir'] = str(self.root/'output')

    def tearDown(self):
        SettingsManager._instance = self.previous
        self.temp.cleanup()

    def test_key_roundtrip_normalizes_quotes_and_resets_retired_model(self):
        self.settings.llm_config.update(gemini_model='gemini-1.5-flash', provider='openai')
        self.assertEqual(self.settings.save_gemini_key('  "fixture-key"\n'), 'fixture-key')
        loaded = SettingsManager(self.settings.config_path)
        self.assertEqual(loaded.llm_config['gemini_api_key'], 'fixture-key')
        self.assertEqual(loaded.llm_config['gemini_model'], 'auto')
        self.assertEqual(loaded.llm_config['provider'], 'openai')

    def test_disk_error_keeps_previous_key_and_file(self):
        self.settings.save_gemini_key('old-key')
        before = Path(self.settings.config_path).read_bytes()
        with patch('config.settings.os.replace', side_effect=PermissionError('read-only')), self.assertLogs('AutoMuse.Settings', level='ERROR'):
            with self.assertRaisesRegex(ValueError, 'Không lưu được'):
                self.settings.save_gemini_key('new-key')
        self.assertEqual(self.settings.llm_config['gemini_api_key'], 'old-key')
        self.assertEqual(Path(self.settings.config_path).read_bytes(), before)
        self.assertFalse(list(Path(self.settings.config_path).parent.glob('*.tmp')))

    def test_invalid_paste_is_not_saved(self):
        for value in ['https://example.com/key', 'key with whitespace', 'key\nother']:
            with self.assertRaises(ValueError):
                normalize_gemini_key(value)

    def test_film_has_exactly_muse_and_gemini_and_uses_explicit_gemini_key(self):
        self.settings.llm_config.update(provider='openai', openai_api_key='openai-secret')
        dialog = FilmDialog()
        try:
            self.assertEqual([dialog.script_source.itemText(i) for i in range(dialog.script_source.count())], ['Muse','Gemini'])
            dialog.script_source.setCurrentIndex(1)
            dialog.gemini_panel.key.setText(' "gemini-fixture" ')
            dialog.idea.setPlainText('Robot tìm khu vườn')
            fake = Mock()
            fake.isRunning.return_value = False
            with patch('ui.dialogs.film_dialog.FilmStoryboardWorker', return_value=fake) as factory:
                dialog._generate_script()
            self.assertEqual(factory.call_args.args[4:7], ('gemini','gemini-fixture','auto'))
            self.assertEqual(self.settings.llm_config['provider'], 'openai')
            saved = json.loads(Path(self.settings.config_path).read_text(encoding='utf-8'))
            self.assertEqual(saved['llm']['gemini_api_key'], 'gemini-fixture')
            self.assertFalse(dialog.gemini_panel.key.isEnabled())
            dialog._script_finished()
        finally:
            dialog.close()

    def test_missing_key_prevents_gemini_worker_and_points_to_inline_field(self):
        dialog=FilmDialog()
        try:
            dialog.script_source.setCurrentIndex(1)
            dialog.idea.setPlainText('Robot')
            with patch('ui.dialogs.film_dialog.FilmStoryboardWorker') as factory:
                dialog._generate_script()
            factory.assert_not_called()
            self.assertIn('Nhập API key Gemini ngay bên dưới', dialog.status.text())
        finally:
            dialog.close()

    def test_key_test_runs_generate_not_only_list_and_saves_on_success(self):
        dialog=FilmDialog()
        try:
            dialog.script_source.setCurrentIndex(1)
            panel=dialog.gemini_panel
            panel.key.setText('fixture-key')
            listing=Mock(status_code=200)
            listing.json.return_value={'models':[{'name':'models/gemini-flash-test','supportedGenerationMethods':['generateContent']}]}
            response=Mock(status_code=200)
            response.json.return_value={'candidates':[{'content':{'parts':[{'text':'["OK"]'}]}}]}
            with patch('workers.llm_rewriter.requests.get', return_value=listing), patch('workers.llm_rewriter.requests.post', return_value=response) as post:
                panel.check()
                loop=QEventLoop()
                panel.worker.finished.connect(loop.quit)
                QTimer.singleShot(4000,loop.quit)
                loop.exec()
                self.app.processEvents()
            self.assertFalse(panel.checking)
            self.assertEqual(post.call_count,1)
            self.assertIn('generateContent',post.call_args.args[0])
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'],'fixture-key')
            self.assertIn('Gemini đã trả lời',panel.message.text())
            self.assertEqual(SettingsManager(self.settings.config_path).llm_config['gemini_api_key'],'fixture-key')
        finally:
            dialog.close()

    def test_list_success_but_inference_denied_is_not_reported_as_working(self):
        worker=GeminiKeyWorker('fixture-key')
        listing=Mock(status_code=200)
        listing.json.return_value={'models':[{'name':'models/gemini-flash-test','supportedGenerationMethods':['generateContent']}]}
        with patch('workers.llm_rewriter.requests.get', return_value=listing), patch('workers.llm_rewriter.requests.post', return_value=Mock(status_code=403)):
            worker.run()
        self.assertIn('chưa được phép',worker.error)
        self.assertEqual(worker.model,'')

    def test_settings_uses_same_save_path_and_survives_restart(self):
        dialog=SettingsDialog()
        try:
            dialog.txt_gemini_key.setText(' "fixture-settings" ')
            with patch('ui.dialogs.settings_dialog.QMessageBox.information'):
                dialog._save_settings()
            self.assertEqual(SettingsManager(self.settings.config_path).llm_config['gemini_api_key'],'fixture-settings')
        finally:
            dialog.close()

    def test_provider_failure_never_silently_reports_local_output(self):
        worker=LLMRewriterWorker('robot',1,[],'gemini','fixture-key','chosen-model')
        outputs,errors=[],[]
        worker.finished_signal.connect(outputs.append)
        worker.error_signal.connect(errors.append)
        with patch.object(worker,'_call_gemini',side_effect=ValueError('Gemini hết hạn mức')):
            worker.run()
        self.assertFalse(outputs)
        self.assertIn('hạn mức',errors[0])

    def test_known_http_error_is_safe_and_does_not_echo_key(self):
        response=Mock(status_code=400)
        response.json.return_value={'error':{'message':'secret-fixture-key','details':[{'reason':'API_KEY_INVALID'}]}}
        message=gemini_error(response)
        self.assertIn('không hợp lệ',message)
        self.assertNotIn('secret-fixture-key',message)
        self.assertIn('503',gemini_error(Mock(status_code=503)))
