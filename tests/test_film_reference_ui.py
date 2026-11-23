import json
import os
import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import patch, Mock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from config.settings import SettingsManager
from core.film_project import FilmStore, plan_film
from ui.dialogs.film_dialog import FilmDialog


class FilmReferenceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_settings = SettingsManager._instance
        config = self.root / "config.json"
        config.write_text("{}")
        SettingsManager._instance = SettingsManager(str(config))
        self.dialog = FilmDialog()

    def tearDown(self):
        self.dialog.close()
        SettingsManager._instance = self.old_settings
        self.temp.cleanup()

    def store(self):
        project = plan_film("UI", ["Nhặt bản đồ", "Qua cầu", "Cảnh khác"], 15, 5)
        project.shots[1].sequence, project.shots[1].continuation = 1, True
        project.shots[0].end_state = project.shots[1].start_state = "Cầm bản đồ"
        project.shots[1].end_state = "Đứng trên cầu"
        store = FilmStore(self.root / "film/project.film.json", project)
        store.save()
        self.dialog.load_project(str(store.manifest))
        return self.dialog.store

    def test_disabling_pause_does_not_auto_approve_visual_findings(self):
        store = self.store()
        shot = store.project.shots[0]
        shot.status, shot.error, shot.visual_review = "REVIEW", "Trang phục khác", {"verdict": "review"}
        self.dialog._review_mode(False)
        self.assertEqual(shot.status, "REVIEW")
        self.assertFalse(store.project.ready_to_export)

    def test_reference_thumbnail_keeps_color_while_editing_is_locked(self):
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon, QImage, QColor
        from core.film_project import FilmReference
        store = self.store()
        source = self.root / 'red-reference.png'
        image = QImage(80, 60, QImage.Format.Format_RGB32)
        image.fill(QColor('#ec2211'))
        image.save(str(source))
        relative = store.snapshot(str(source), 'canonical')
        store.project.references = [FilmReference('cat', 'character', 'Cat', 'Red coat', images=[relative])]
        before = store.digest(store.asset(relative))
        self.dialog.references_panel.refresh()
        self.dialog._set_busy(True)
        self.assertFalse(self.dialog.references_panel.isEnabled())
        icon = self.dialog.references_panel.table.item(0, 1).icon()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
            pixel = icon.pixmap(QSize(80, 60), mode).toImage().pixelColor(40, 30)
            self.assertGreater(pixel.red(), 200)
            self.assertLess(pixel.green(), 60)
            self.assertLess(pixel.blue(), 60)
        self.assertEqual(store.digest(store.asset(relative)), before)

    def test_muse_needs_input_shows_visible_warning_and_selects_clip(self):
        store = self.store()
        shot = store.project.shots[1]
        store.project.state = shot.status = "WAITING"
        shot.error = "Cần sửa mô tả hoặc trả lời Muse trước khi tiếp tục."
        shot.submitted_prompt = "Original submitted request"
        with patch("ui.dialogs.film_dialog.QMessageBox.warning") as warning:
            self.dialog._finished()
        warning.assert_called_once()
        self.assertIn(shot.error, warning.call_args.args[2])
        self.assertEqual(self.dialog.table.currentRow(), 1)
        self.assertEqual(shot.submitted_prompt, "Original submitted request")
        self.assertEqual(shot.status, "WAITING")

    def test_preflight_selects_risky_clip_without_launching_worker(self):
        store = self.store()
        store.project.shots[1].prompt = "Chuột cắn mạnh vào chân mèo"
        with patch("ui.dialogs.film_dialog.QMessageBox.warning") as warning, patch.object(self.dialog, "_launch") as launch:
            self.dialog._start()
        warning.assert_called_once()
        launch.assert_not_called()
        self.assertEqual(self.dialog.table.currentRow(), 1)

    def test_18_clip_worker_result_reaches_setup_ui_despite_ai_state_wording(self):
        from test_storyboard_completion import data
        from workers.film_storyboard_worker import FilmStoryboardWorker
        payload = data(18)
        payload['shots'][3]['start_state'] = 'AI described this boundary differently'
        self.dialog.minutes.setValue(3)
        self.dialog.seconds.setValue(0)
        self.dialog.idea.setPlainText('mèo và chuột')
        worker = FilmStoryboardWorker('mèo và chuột', 180, 10, '', 'gemini', 'test', 'model')
        worker.storyboard_ready.connect(self.dialog._storyboard_received)
        errors = []
        worker.error_signal.connect(errors.append)
        with patch.object(worker, '_call_gemini', return_value=payload):
            worker.run()
        self.assertFalse(errors)
        self.assertEqual(len(self.dialog.storyboard_draft['shots']), 18)
        self.assertTrue(self.dialog.script.toPlainText().strip())
        self.assertEqual(self.dialog.storyboard_draft['shots'][3]['start_state'],
                         self.dialog.storyboard_draft['shots'][2]['end_state'])

    def test_shot_edit_updates_only_dependent_state_and_keeps_actions(self):
        store = self.store()
        self.dialog.table.selectRow(0)
        shot = store.project.shots[0]
        changes = {key: getattr(shot, key) for key in ("prompt", "continuation", "character_ids", "location_id", "start_state", "end_state")}
        changes.update(prompt="Nhặt và gấp bản đồ", end_state="Cầm bản đồ đã gấp")
        with patch("ui.dialogs.film_dialog.edit_shot_dialog", return_value=changes), patch.object(self.dialog, "_invalidate", return_value=True):
            self.dialog._edit_shot()
        self.assertEqual(store.project.shots[1].start_state, "Cầm bản đồ đã gấp")
        self.assertEqual(store.project.shots[1].prompt, "Qua cầu")
        self.assertEqual(store.project.shots[2].start_state, "")
        self.assertEqual(store.project.shots[2].prompt, "Cảnh khác")

    def test_new_project_clears_reference_draft_and_review_options(self):
        self.store()
        self.dialog.visual_review_enabled.setChecked(True)
        self.dialog._new()
        self.assertEqual(self.dialog.reference_draft, [])
        self.assertIsNone(self.dialog.storyboard_draft)
        self.assertFalse(self.dialog.visual_review_enabled.isChecked())
        self.assertEqual(self.dialog.references_panel.table.rowCount(), 0)

    def test_generate_resumes_saved_partial_without_rewriting_prefix(self):
        from test_storyboard_completion import data
        self.dialog.idea.setPlainText("Robot")
        self.dialog.script_source.setCurrentIndex(1)
        self.dialog.settings.llm_config.update(provider="gemini", gemini_api_key="test-key")
        self.dialog.settings.app_config["output_dir"] = str(self.root / "output")
        signature = json.dumps(["Robot", 600, 10, ""], ensure_ascii=False)
        identifier = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
        checkpoint = self.root / "output/film_drafts" / (identifier + ".json")
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text(json.dumps(data(48)), encoding="utf-8")
        fake = Mock()
        fake.isRunning.return_value = False
        with patch("ui.dialogs.film_dialog.FilmStoryboardWorker", return_value=fake) as factory:
            self.dialog._generate_script()
        self.assertEqual(len(factory.call_args.kwargs["existing"]["shots"]), 48)
        self.assertEqual(factory.call_args.kwargs["checkpoint_path"], checkpoint)
        fake.start.assert_called_once()

    def test_muse_source_does_not_require_api_key_and_uses_selected_profile(self):
        from core.models import ProfileItem
        profile = ProfileItem(id='so1', name='so1', path=str(self.root/'profile'))
        self.dialog.settings.profiles = [profile]
        self.dialog.profile.addItem('so1', profile.id)
        self.dialog.profile.setCurrentIndex(self.dialog.profile.count()-1)
        self.dialog.idea.setPlainText('Mèo và chuột')
        self.dialog.settings.llm_config['gemini_api_key'] = ''
        fake = Mock()
        fake.isRunning.return_value = False
        with patch('ui.dialogs.film_dialog.MuseStoryboardWorker', return_value=fake) as factory:
            self.dialog._generate_script()
        fake.start.assert_called_once()
        self.assertEqual(factory.call_args.args[4].id, 'so1')
        self.assertTrue(self.dialog.stop_button.isEnabled())
        self.assertFalse(self.dialog.script_source.isEnabled())
