import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QEventLoop, QTimer
from ui.dialogs.license_dialog import LicenseDialog
from ui.license_guard import LicenseGuard


class LicenseUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, dialog):
        loop=QEventLoop()
        dialog.worker.finished.connect(loop.quit)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        self.assertFalse(dialog.worker.isRunning())
        self.app.processEvents()

    def test_activation_checks_on_worker_and_error_keeps_dialog_open(self):
        session=MagicMock(key='', description='test')
        session.check.side_effect=ValueError('Key đã hết hạn')
        dialog=LicenseDialog(session)
        dialog.key.setText('AM-test')
        dialog.check()
        self.wait(dialog)
        self.assertIn('hết hạn', dialog.message.text())
        self.assertEqual(dialog.result(), 0)
        self.assertTrue(dialog.activate.isEnabled())
        dialog.close()

    def test_success_unlocks_only_after_worker_finished(self):
        session=MagicMock(key='', description='test')
        dialog=LicenseDialog(session)
        dialog.key.setText('AM-test')
        dialog.check()
        self.wait(dialog)
        self.assertEqual(dialog.result(), 1)
        session.check.assert_called_once_with('AM-test')
        dialog.close()

    def test_revocation_stops_workers_and_disables_existing_windows(self):
        window=QWidget()
        window.automation_worker=MagicMock()
        window.automation_worker.isRunning.return_value=True
        window.film_dialog=MagicMock()
        window.status_bar=MagicMock()
        session=MagicMock(valid=False, description='test')
        guard=LicenseGuard(session, window)
        with patch('ui.license_guard.QTimer.singleShot'):
            guard.check_expiry()
        self.assertFalse(window.isEnabled())
        window.automation_worker.stop.assert_called_once()
        window.film_dialog._stop.assert_called_once()
        guard.timer.stop()
        guard.expiry.stop()
        window.close()
