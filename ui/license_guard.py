"""Revalidate while open; disable UI and request safe worker stops on loss."""
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QApplication, QDialog
from ui.dialogs.license_dialog import LicenseCheck, LicenseDialog


class LicenseGuard(QObject):
    def __init__(self, session, window):
        super().__init__(window)
        self.session, self.window = session, window
        self.worker = None
        self.locked = False
        self.closing = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60000)
        self.expiry = QTimer(self)
        self.expiry.timeout.connect(self.check_expiry)
        self.expiry.start(1000)
        window.status_bar.showMessage(session.description)

    def refresh(self):
        if self.locked or (self.worker and self.worker.isRunning()):
            return
        self.worker = LicenseCheck(self.session, parent=self)
        self.worker.finished.connect(lambda: self.completed(self.worker.error))
        self.worker.start()

    def completed(self, error):
        if self.closing:
            QTimer.singleShot(0, self.window.close)
            return
        if error:
            self.lock()

    def closing_is_pending(self):
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.timer.stop()
            self.expiry.stop()
            return True
        return False

    def check_expiry(self):
        if not self.session.valid:
            self.lock()

    def lock(self):
        if self.locked:
            return
        self.locked = True
        if self.window.automation_worker and self.window.automation_worker.isRunning():
            self.window.automation_worker.stop()
        if self.window.film_dialog:
            self.window.film_dialog._stop()
        self.window.status_bar.showMessage('Bản quyền cần kiểm tra lại. Đang dừng tác vụ và giữ dữ liệu.')
        self.disabled = []
        for widget in QApplication.topLevelWidgets():
            if widget.isEnabled():
                widget.setEnabled(False)
                self.disabled.append(widget)
        QTimer.singleShot(0, self.reactivate)

    def reactivate(self):
        # Do not overlap credential writes with an in-flight heartbeat request.
        if self.worker and self.worker.isRunning():
            QTimer.singleShot(100, self.reactivate)
            return
        dialog = LicenseDialog(self.session)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            # Allow workers to checkpoint before exiting; never force-kill them.
            QTimer.singleShot(500, self.shutdown)
            return
        for widget in self.disabled:
            try:
                widget.setEnabled(True)
            except RuntimeError:
                pass
        self.locked = False
        self.window.status_bar.showMessage(self.session.description)

    def shutdown(self):
        if self.window._update_busy():
            QTimer.singleShot(500, self.shutdown)
            return
        if self.window.close():
            QApplication.quit()
        else:
            QTimer.singleShot(500, self.shutdown)
