import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from config.settings import SettingsManager
from ui.left_panel import LeftPanel


class LoginStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = SettingsManager._instance
        p = Path(self.temp.name) / "config.json"
        p.write_text("{}")
        SettingsManager._instance = SettingsManager(str(p))
        self.panel = LeftPanel()

    def tearDown(self):
        self.panel.close()
        SettingsManager._instance = self.old
        self.temp.cleanup()

    def test_disconnected_session_never_displays_login_success(self):
        self.panel.active_login_worker = Mock(authenticated=False, session_issue="Muse đã ngắt kết nối")
        with patch("ui.left_panel.QMessageBox.information") as success, patch("ui.left_panel.QMessageBox.warning") as warning:
            self.panel._on_login_finished("so1")
        success.assert_not_called()
        warning.assert_called_once()
        self.assertEqual(self.panel.settings.profiles[0].status, "Muse đã ngắt kết nối")

    def test_verified_chat_displays_success(self):
        self.panel.active_login_worker = Mock(authenticated=True, session_issue="")
        with patch("ui.left_panel.QMessageBox.information") as success, patch("ui.left_panel.QMessageBox.warning") as warning:
            self.panel._on_login_finished("so1")
        success.assert_called_once()
        warning.assert_not_called()
        self.assertEqual(self.panel.settings.profiles[0].status, "Đã đăng nhập ✓")
