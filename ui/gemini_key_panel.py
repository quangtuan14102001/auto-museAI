"""Shared Gemini credential entry with explicit persistence and inference test."""
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel
from core.gemini_api import normalize_gemini_key
from workers.gemini_key_worker import GeminiKeyWorker


class GeminiKeyPanel(QWidget):
    busy_changed = pyqtSignal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings, self.worker = settings, None
        self.workflow_busy = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.key = QLineEdit(settings.llm_config.get('gemini_api_key', ''))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Dán API key Gemini của bạn')
        row.addWidget(self.key, 1)
        self.save_button = QPushButton('Lưu key')
        self.save_button.clicked.connect(self.save)
        self.check_button = QPushButton('Kiểm tra key')
        self.check_button.setToolTip('Gửi một yêu cầu văn bản rất ngắn tới Gemini; có dùng quota/chi phí API. Không tạo ảnh/video.')
        self.check_button.clicked.connect(self.check)
        row.addWidget(self.save_button)
        row.addWidget(self.check_button)
        layout.addLayout(row)
        self.message = QLabel('Dùng key Google AI Studio; không phải key bản quyền app. Phép thử có dùng quota API.')
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

    @property
    def checking(self):
        return bool(self.worker and self.worker.isRunning())

    def candidate(self):
        # Refresh a clean, empty field if Settings was changed elsewhere.
        value = self.key.text()
        if not value and not self.key.isModified():
            value = self.settings.llm_config.get('gemini_api_key', '')
        return normalize_gemini_key(value)

    def save(self):
        try:
            value = self.settings.save_gemini_key(self.key.text())
            self.key.setText(value)
            self.message.setText('Đã lưu key. Bấm Kiểm tra key để xác nhận Gemini trả lời được.' if value else 'Đã xóa key Gemini đã lưu.')
            return True
        except ValueError as exc:
            self.message.setText(str(exc))
            return False

    def set_workflow_busy(self, busy):
        self.workflow_busy = busy
        enabled = not busy and not self.checking
        for item in (self.key, self.save_button, self.check_button):
            item.setEnabled(enabled)

    def check(self):
        if self.checking or self.workflow_busy:
            return
        try:
            key = self.candidate()
            if not key:
                raise ValueError('Nhập API key Gemini trước khi kiểm tra.')
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self.worker = GeminiKeyWorker(key, self)
        self.worker.finished.connect(self.checked)
        self.message.setText('Đang kiểm tra quyền tạo văn bản với Gemini…')
        self.busy_changed.emit(True)
        self.worker.start()
        self.set_workflow_busy(False)

    def checked(self):
        self.set_workflow_busy(self.workflow_busy)
        if self.worker.error:
            self.message.setText(self.worker.error)
        else:
            try:
                value = self.settings.save_gemini_key(self.worker.key)
                self.key.setText(value)
                self.message.setText(f'Gemini đã trả lời phép thử. Key đã lưu. Model: {self.worker.model}.')
            except ValueError as exc:
                self.message.setText('Gemini đã trả lời nhưng chưa lưu được key. ' + str(exc))
        self.busy_changed.emit(False)
