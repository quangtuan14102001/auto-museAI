import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QPushButton, QFileDialog, QMessageBox, QProgressBar, QLineEdit
)
from config.settings import SettingsManager
from workers.video_merger import VideoMergerWorker
from utils.file_utils import open_in_explorer


class VideoMergeDialog(QDialog):
    def __init__(self, initial_videos=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ghép Nối Video Clips (FFmpeg Engine)")
        self.resize(650, 500)
        self.settings = SettingsManager.get_instance()
        self.worker: VideoMergerWorker = None
        self.initial_videos = initial_videos or []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Danh sách các đoạn video cần ghép nối theo thứ tự:"))

        h_list = QHBoxLayout()
        self.list_videos = QListWidget()
        for v in self.initial_videos:
            if os.path.exists(v):
                self.list_videos.addItem(v)

        h_list.addWidget(self.list_videos)

        v_order = QVBoxLayout()
        btn_add = QPushButton("+ Thêm video...")
        btn_add.clicked.connect(self._add_videos)
        btn_up = QPushButton("▲ Lên")
        btn_up.clicked.connect(self._move_up)
        btn_down = QPushButton("▼ Xuống")
        btn_down.clicked.connect(self._move_down)
        btn_del = QPushButton("Xóa")
        btn_del.clicked.connect(self._delete_selected)
        btn_clear = QPushButton("Xóa hết")
        btn_clear.clicked.connect(self.list_videos.clear)

        v_order.addWidget(btn_add)
        v_order.addWidget(btn_up)
        v_order.addWidget(btn_down)
        v_order.addWidget(btn_del)
        v_order.addWidget(btn_clear)
        v_order.addStretch()
        h_list.addLayout(v_order)

        layout.addLayout(h_list)

        # Output video file path
        layout.addWidget(QLabel("Đường dẫn video xuất ra:"))
        h_out = QHBoxLayout()
        default_out = os.path.join(
            self.settings.app_config.get("output_dir", "output"), "merged_long_video.mp4"
        )
        self.txt_out = QLineEdit(default_out)
        btn_browse_out = QPushButton("Chọn nơi lưu...")
        btn_browse_out.clicked.connect(self._browse_output)
        h_out.addWidget(self.txt_out)
        h_out.addWidget(btn_browse_out)
        layout.addLayout(h_out)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Sẵn sàng ghép nối video bằng FFmpeg.")
        self.lbl_status.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.lbl_status)

        # Buttons
        h_action = QHBoxLayout()
        h_action.addStretch()
        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.reject)

        self.btn_merge = QPushButton("🎬 Bắt Đầu Ghép Video")
        self.btn_merge.setProperty("class", "btn-run")
        self.btn_merge.clicked.connect(self._start_merge)

        h_action.addWidget(btn_close)
        h_action.addWidget(self.btn_merge)
        layout.addLayout(h_action)

    def _add_videos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Chọn các file video cần ghép", "", "Video Files (*.mp4 *.webm *.mov *.mkv)"
        )
        for f in files:
            self.list_videos.addItem(f)

    def _move_up(self):
        row = self.list_videos.currentRow()
        if row > 0:
            item = self.list_videos.takeItem(row)
            self.list_videos.insertItem(row - 1, item)
            self.list_videos.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_videos.currentRow()
        if row < self.list_videos.count() - 1 and row >= 0:
            item = self.list_videos.takeItem(row)
            self.list_videos.insertItem(row + 1, item)
            self.list_videos.setCurrentRow(row + 1)

    def _delete_selected(self):
        row = self.list_videos.currentRow()
        if row >= 0:
            self.list_videos.takeItem(row)

    def _browse_output(self):
        out_f, _ = QFileDialog.getSaveFileName(
            self, "Lưu video hoàn chỉnh", self.txt_out.text(), "MP4 Video (*.mp4)"
        )
        if out_f:
            self.txt_out.setText(out_f)

    def _start_merge(self):
        items = [self.list_videos.item(i).text() for i in range(self.list_videos.count())]
        if not items:
            QMessageBox.warning(self, "Lỗi", "Danh sách video để ghép rỗng!")
            return

        out_path = self.txt_out.text().strip()
        if not out_path:
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn đường dẫn video xuất ra!")
            return

        self.btn_merge.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)

        self.worker = VideoMergerWorker(video_files=items, output_path=out_path)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_progress(self, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(msg)

    def _on_finished(self, out_file: str):
        self.btn_merge.setEnabled(True)
        self.progress_bar.setValue(100)
        self.lbl_status.setText(f"✓ Ghép video hoàn tất: {os.path.basename(out_file)}")
        reply = QMessageBox.information(
            self, "Thành công", f"Đã ghép hoàn tất video!\nĐường dẫn:\n{out_file}\n\nBạn có muốn mở file không?",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok
        )
        if reply == QMessageBox.StandardButton.Open:
            open_in_explorer(out_file)

    def _on_error(self, err: str):
        self.btn_merge.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"✗ Lỗi: {err}")
        QMessageBox.warning(self, "Lỗi", err)
