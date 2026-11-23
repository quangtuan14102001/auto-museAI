from PyQt6.QtCore import QThread, pyqtSignal
from core.app_update import read_release, download_release


class AppUpdateWorker(QThread):
    progress = pyqtSignal(int)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.result = None
        self.error = ""

    def run(self):
        try:
            release = read_release(self.url)
            if release:
                installer = download_release(release, self.progress.emit, self.isInterruptionRequested)
                self.result = (release, installer)
        except Exception as exc:
            # Do not expose signed download URLs, query tokens or response bodies.
            if isinstance(exc, (ValueError, InterruptedError)):
                self.error = str(exc)
            else:
                self.error = "Chưa kết nối được nguồn cập nhật. Kiểm tra mạng hoặc thử lại sau."
