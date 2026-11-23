"""Activation runs off the UI thread and never logs license keys."""
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton


class LicenseCheck(QThread):
    done = pyqtSignal(str)

    def __init__(self, session, key=None, parent=None):
        super().__init__(parent)
        self.session, self.key = session, key
        self.error = ''

    def run(self):
        try:
            self.session.check(self.key)
            self.done.emit('')
        except Exception as exc:
            self.error = str(exc) if isinstance(exc, ValueError) else 'Chưa kiểm tra được bản quyền. Thử lại sau.'
            self.done.emit(self.error)


class LicenseDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session, self.worker = session, None
        self.setWindowTitle('Kích hoạt AutoMuseAI')
        self.resize(490, 200)
        layout = QVBoxLayout(self)
        self.message = QLabel('Nhập key do người bán cung cấp. Cần kết nối Internet để kiểm tra bản quyền.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.key = QLineEdit(session.key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('AM-…')
        layout.addWidget(self.key)
        self.activate = QPushButton('Kích hoạt / kiểm tra key')
        self.activate.clicked.connect(self.check)
        layout.addWidget(self.activate)
        self.key.returnPressed.connect(self.check)

    def check(self):
        if self.worker and self.worker.isRunning():
            return
        self.activate.setEnabled(False)
        self.key.setEnabled(False)
        self.message.setText('Đang kiểm tra bản quyền…')
        self.worker = LicenseCheck(self.session, self.key.text(), self)
        self.worker.finished.connect(lambda: self.completed(self.worker.error))
        self.worker.start()

    def completed(self, error):
        self.activate.setEnabled(True)
        self.key.setEnabled(True)
        self.message.setText(error or self.session.description)
        if not error:
            self.accept()

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
