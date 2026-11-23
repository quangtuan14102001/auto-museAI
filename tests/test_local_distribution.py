import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer
from config.settings import SettingsManager


class LocalDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "config.json"
        self.config.write_text(json.dumps({
            "app": {"github_repo": "retired/repository", "auto_check_update": True,
                    "output_dir": "my-output"},
            "profiles": [{"id": "test", "name": "test", "path": "my-profile"}],
            "tasks": [{"id": "task", "prompt": "scene", "status": "READY"}],
            "llm": {"gemini_api_key": "test-sentinel"}
        }), encoding="utf-8")
        self.previous = SettingsManager._instance
        SettingsManager._instance = SettingsManager(str(self.config))

    def tearDown(self):
        SettingsManager._instance = self.previous
        self.temp.cleanup()

    def test_retired_settings_removed_without_changing_user_data(self):
        settings = SettingsManager._instance
        self.assertNotIn("github_repo", settings.app_config)
        self.assertNotIn("auto_check_update", settings.app_config)
        settings.save()
        data = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertNotIn("github_repo", data["app"])
        self.assertNotIn("auto_check_update", data["app"])
        self.assertEqual(data["app"]["output_dir"], "my-output")
        self.assertEqual(data["profiles"][0]["path"], str(self.config.parent / "my-profile"))
        self.assertEqual(data["tasks"][0]["prompt"], "scene")
        self.assertEqual(data["llm"]["gemini_api_key"], "test-sentinel")

    def test_window_has_no_update_controls_or_startup_request(self):
        from ui.main_window import MainWindow
        from ui.dialogs.settings_dialog import SettingsDialog
        with patch("requests.sessions.Session.request") as request:
            window = MainWindow()
            dialog = SettingsDialog()
            self.assertTrue(hasattr(window.ribbon, "btn_update"))
            self.assertFalse(hasattr(dialog, "txt_github_repo"))
            self.assertFalse(hasattr(dialog, "chk_auto_update"))
            loop = QEventLoop()
            QTimer.singleShot(2800, loop.quit)
            loop.exec()
            request.assert_not_called()
            self.assertNotIn("workers.updater_worker", sys.modules)
            self.assertNotIn("ui.dialogs.update_dialog", sys.modules)
            dialog.close()
            window.close()


if __name__ == "__main__":
    unittest.main()
