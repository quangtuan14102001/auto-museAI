from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QMenu
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction


from core.version import APP_VERSION


class HeaderRibbon(QFrame):
    script_rewriter_requested = pyqtSignal()
    video_merge_requested = pyqtSignal()
    tts_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    film_requested = pyqtSignal()
    update_requested = pyqtSignal()
    theme_changed_signal = pyqtSignal(str) # theme_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "ribbon")
        self.setFixedHeight(58)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 6, 18, 6)
        layout.setSpacing(10)

        # Brand Logo & Title
        lbl_logo = QLabel("⚡ AUTO MUSE AI")
        lbl_logo.setProperty("class", "brand-title")
        lbl_sub = QLabel(f"STUDIO BATCH v{APP_VERSION}")
        lbl_sub.setStyleSheet("color: #64748b; font-size: 11px; font-weight: bold; margin-left: -4px;")
        layout.addWidget(lbl_logo)
        layout.addWidget(lbl_sub)

        layout.addSpacing(25)

        # 1. Viết lại kịch bản
        self.btn_script = QPushButton("📝 Kịch bản")
        self.btn_script.setProperty("class", "btn-ribbon")
        self.btn_script.setToolTip("Dùng LLM API (Gemini/OpenAI/Claude) chuyển kịch bản thô thành danh sách prompt")
        self.btn_script.clicked.connect(self.script_rewriter_requested.emit)
        layout.addWidget(self.btn_script)

        # 2. Ghép
        self.btn_merge = QPushButton("🎬 Ghép")
        self.btn_merge.setProperty("class", "btn-ribbon")
        self.btn_merge.setToolTip("Ghép nối các file video clip hoàn thành thành video dài hoàn chỉnh (FFmpeg)")
        self.btn_merge.clicked.connect(self.video_merge_requested.emit)
        layout.addWidget(self.btn_merge)
        self.btn_film = QPushButton("🎞 Phim dài")
        self.btn_film.setProperty("class", "btn-ribbon")
        self.btn_film.setToolTip("Chia phim thành clip tiếp nối, duyệt khung hình và ghép phim dài")
        self.btn_film.clicked.connect(self.film_requested.emit)
        layout.addWidget(self.btn_film)

        # 3. Đọc Audio Nội Dung Cảm Xúc
        self.btn_tts = QPushButton("🎙 Audio")
        self.btn_tts.setProperty("class", "btn-ribbon")
        self.btn_tts.setToolTip("Tích hợp TTS (Edge-TTS / ElevenLabs / FPT) chuyển văn bản thành giọng đọc")
        self.btn_tts.clicked.connect(self.tts_requested.emit)
        layout.addWidget(self.btn_tts)

        layout.addStretch()

        self.btn_update = QPushButton("↻ Cập nhật")
        self.btn_update.setProperty("class", "btn-ribbon")
        self.btn_update.clicked.connect(self.update_requested.emit)
        layout.addWidget(self.btn_update)

        # 5. Cài đặt
        self.btn_settings = QPushButton("⚙ Cài đặt")
        self.btn_settings.setProperty("class", "btn-ribbon")
        self.btn_settings.setToolTip("Cấu hình thư mục lưu, API keys, nhắc chờ, proxy, selectors")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.btn_settings)

        # 5. Giao diện (Theme switcher)
        self.btn_theme = QPushButton("🎨 Giao diện ▾")
        self.btn_theme.setProperty("class", "btn-ribbon")
        self.btn_theme.setToolTip("Đổi theme màu sắc giao diện")
        
        theme_menu = QMenu(self)
        action_obsidian = QAction("Obsidian Studio (Mặc định)", self)
        action_obsidian.triggered.connect(lambda: self.theme_changed_signal.emit("obsidian_dark"))
        action_cyber = QAction("Cyberpunk Dark", self)
        action_cyber.triggered.connect(lambda: self.theme_changed_signal.emit("cyberpunk"))

        theme_menu.addAction(action_obsidian)
        theme_menu.addAction(action_cyber)
        self.btn_theme.setMenu(theme_menu)

        layout.addWidget(self.btn_theme)
