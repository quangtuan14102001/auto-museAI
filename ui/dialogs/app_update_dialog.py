import sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
from core.app_update import install_release
from core.version import APP_VERSION
from workers.app_update_worker import AppUpdateWorker


class AppUpdateDialog(QDialog):
    def __init__(self, url, parent, busy_check):
        super().__init__(parent)
        self.setWindowTitle("Cập nhật AutoMuseAI")
        self.resize(470, 180)
        self.busy_check = busy_check
        layout = QVBoxLayout(self)
        self.message = QLabel(f"Đang kiểm tra bản mới… Hiện tại: v{APP_VERSION}")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.button = QPushButton("Hủy")
        self.button.clicked.connect(self.close)
        layout.addWidget(self.button)
        self.worker = None
        if not url:
            self.message.setText("Nhà phát hành chưa cấu hình nguồn cập nhật. Chưa có file nào được tải.")
            self.progress.hide()
            self.button.setText("Đóng")
        else:
            self.worker = AppUpdateWorker(url, self)
            self.worker.progress.connect(self._progress)
            self.worker.finished.connect(self._finished)
            QTimer.singleShot(0, self.worker.start)

    def _progress(self, percent):
        self.progress.setRange(0, 100)
        self.progress.setValue(percent)
        self.message.setText(f"Đang tải bản cập nhật… {percent}%")

    def _finished(self):
        self.button.setText("Đóng")
        self.button.setEnabled(True)
        self.progress.hide()
        if self.worker.error:
            self.message.setText(self.worker.error)
        elif self.worker.isInterruptionRequested():
            self.message.setText("Đã hủy cập nhật.")
        elif not self.worker.result:
            self.message.setText(f"Bạn đang dùng phiên bản mới nhất (v{APP_VERSION}).")
        elif self.busy_check():
            self.message.setText("Bộ cài đã tải xong. Dừng tác vụ đang chạy rồi bấm Cập nhật lại để cài đặt.")
        elif not getattr(sys, "frozen", False):
            self.message.setText("Đã tải và kiểm tra bộ cài. Cài tự động chỉ áp dụng khi chạy bản EXE.")
        else:
            try:
                self.parent().settings.save()
                install_release(self.worker.result[1], Path(sys.executable).parent)
                self.accept()
                self.parent().close()
            except Exception:
                self.message.setText("Chưa mở được bộ cài. Đóng ứng dụng và thử cập nhật lại.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.message.setText("Đang hủy tải bản cập nhật…")
            self.button.setEnabled(False)
            event.ignore()
        else:
            event.accept()
