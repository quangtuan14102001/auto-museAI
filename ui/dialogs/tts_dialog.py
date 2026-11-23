import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QComboBox, QMessageBox, QProgressBar, QSlider
)
from PyQt6.QtCore import Qt
from config.settings import SettingsManager
from workers.tts_engine import TTSEngineWorker
from utils.file_utils import open_in_explorer


class TTSDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đọc Audio Nội Dung Cảm Xúc (TTS Studio)")
        self.resize(600, 480)
        self.settings = SettingsManager.get_instance()
        self.worker: TTSEngineWorker = None
        self.last_audio_file: str = ""
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Voice Selector
        h_voice = QHBoxLayout()
        h_voice.addWidget(QLabel("Giọng đọc:"))
        self.combo_voice = QComboBox()
        self.combo_voice.addItems([
            "vi-VN-HoaiMyNeural (Nữ, truyền cảm hứng)",
            "vi-VN-NamMinhNeural (Nam, tin tức trầm ấm)",
            "en-US-JennyNeural (Nữ, tiếng Anh tự nhiên)",
            "en-US-GuyNeural (Nam, tiếng Anh chuẩn)"
        ])
        h_voice.addWidget(self.combo_voice)
        layout.addLayout(h_voice)

        # Speed / Rate slider
        h_speed = QHBoxLayout()
        h_speed.addWidget(QLabel("Tốc độ đọc:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(-50, 50)
        self.slider_speed.setValue(0)
        self.lbl_speed_val = QLabel("+0%")
        self.slider_speed.valueChanged.connect(lambda v: self.lbl_speed_val.setText(f"{v:+d}%"))
        h_speed.addWidget(self.slider_speed)
        h_speed.addWidget(self.lbl_speed_val)
        layout.addLayout(h_speed)

        # Text input
        layout.addWidget(QLabel("Nội dung kịch bản văn bản cần lồng tiếng:"))
        self.txt_content = QTextEdit()
        self.txt_content.setPlaceholderText(
            "Nhập nội dung bạn muốn AI đọc lồng tiếng...\n"
            "Ví dụ: Chào mừng bạn đến với thế giới sáng tạo hình ảnh và video không giới hạn cùng Muse AI!"
        )
        layout.addWidget(self.txt_content)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Sẵn sàng tạo giọng đọc.")
        self.lbl_status.setStyleSheet("color: #94a3b8;")
        layout.addWidget(self.lbl_status)

        # Buttons
        h_btns = QHBoxLayout()
        self.btn_open_file = QPushButton("▶ Mở File Audio")
        self.btn_open_file.setEnabled(False)
        self.btn_open_file.clicked.connect(self._open_audio)

        self.btn_open_folder = QPushButton("Thư mục Audio")
        self.btn_open_folder.clicked.connect(self._open_folder)

        self.btn_generate = QPushButton("🎙 Tạo Giọng Nói Audio")
        self.btn_generate.setProperty("class", "btn-primary")
        self.btn_generate.clicked.connect(self._start_tts)

        h_btns.addWidget(self.btn_open_file)
        h_btns.addWidget(self.btn_open_folder)
        h_btns.addStretch()
        h_btns.addWidget(self.btn_generate)
        layout.addLayout(h_btns)

    def _start_tts(self):
        text = self.txt_content.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập nội dung cần đọc!")
            return

        raw_voice = self.combo_voice.currentText().split()[0]
        rate_val = f"{self.slider_speed.value():+d}%"
        output_dir = os.path.join(self.settings.app_config.get("output_dir", "output"), "audio")
        provider = self.settings.tts_config.get("provider", "edge-tts")
        api_key = self.settings.tts_config.get("fpt_api_key" if provider == "fpt" else "elevenlabs_api_key", "")
        if provider == "fpt":
            raw_voice = self.settings.tts_config.get("fpt_voice", "banmai")
        self.last_audio_file = ""
        self.btn_open_file.setEnabled(False)

        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_status.setText("Đang kết nối TTS engine và tạo audio...")

        self.worker = TTSEngineWorker(
            text=text,
            output_dir=output_dir,
            provider=provider,
            voice=raw_voice,
            rate=rate_val,
            api_key=api_key,
            voice_id=self.settings.tts_config.get("elevenlabs_voice_id", "")
        )
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, out_file: str):
        self.last_audio_file = out_file
        self.btn_generate.setEnabled(True)
        self.btn_open_file.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"✓ Đã tạo thành công: {os.path.basename(out_file)}")
        QMessageBox.information(self, "Thành công", f"Đã lưu file audio tại:\n{out_file}")

    def _on_error(self, err: str):
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText(f"✗ Lỗi: {err}")
        QMessageBox.warning(self, "Lỗi", err)

    def _open_audio(self):
        if self.last_audio_file and os.path.exists(self.last_audio_file):
            open_in_explorer(self.last_audio_file)

    def _open_folder(self):
        audio_dir = os.path.join(self.settings.app_config.get("output_dir", "output"), "audio")
        open_in_explorer(audio_dir)
