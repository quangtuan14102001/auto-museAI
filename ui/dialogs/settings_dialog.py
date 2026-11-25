import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QSpinBox, QComboBox, QPushButton,
    QFileDialog, QMessageBox, QFormLayout, QGroupBox, QCheckBox
)
from config.settings import SettingsManager
from core.gemini_api import normalize_gemini_key
from ui.gemini_key_panel import GeminiKeyPanel


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài Đặt Hệ Thống & Cấu Hình")
        self.resize(650, 520)
        self.settings = SettingsManager.get_instance()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Cài đặt chung
        tab_general = QWidget()
        form_gen = QFormLayout(tab_general)
        form_gen.setSpacing(12)

        # Output Dir
        h_out = QHBoxLayout()
        self.txt_output_dir = QLineEdit(self.settings.app_config.get("output_dir", "output"))
        btn_browse_out = QPushButton("Duyệt...")
        btn_browse_out.clicked.connect(self._browse_output_dir)
        h_out.addWidget(self.txt_output_dir)
        h_out.addWidget(btn_browse_out)
        form_gen.addRow("Thư mục lưu Output:", h_out)

        # Timeout
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(30, 1800)
        self.spin_timeout.setValue(self.settings.app_config.get("default_timeout", 210))
        self.spin_timeout.setSuffix(" giây")
        self.spin_timeout.setToolTip("Chỉ nhắc thời gian chờ; không giới hạn thời gian Muse tạo sản phẩm.")
        form_gen.addRow("Mốc nhắc chờ kết quả:", self.spin_timeout)

        # Default Aspect Ratio
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems(["16:9", "9:16", "1:1", "AUTO"])
        self.combo_aspect.setCurrentText(self.settings.app_config.get("default_aspect_ratio", "16:9"))
        form_gen.addRow("Tỷ lệ khung hình mặc định:", self.combo_aspect)

        # Max Concurrent Tabs
        self.spin_tabs = QSpinBox()
        self.spin_tabs.setRange(1, 10)
        self.spin_tabs.setValue(self.settings.app_config.get("max_concurrent_tabs", 2))
        form_gen.addRow("Số tab mở song song / Profile:", self.spin_tabs)

        # Auto New Chat
        self.chk_auto_new_chat = QCheckBox("Tự động mở phiên chat mới (+) cho mỗi task (Cách 1)")
        self.chk_auto_new_chat.setChecked(self.settings.app_config.get("auto_new_chat", True))
        form_gen.addRow("Chế độ chat:", self.chk_auto_new_chat)

        # Proxy
        self.txt_proxy = QLineEdit(self.settings.app_config.get("proxy", ""))
        self.txt_proxy.setPlaceholderText("http://user:pass@ip:port hoặc socks5://...")
        form_gen.addRow("Proxy (tùy chọn):", self.txt_proxy)
        self.txt_update_source = QLineEdit(self.settings.app_config.get("update_manifest_url", ""))
        self.txt_update_source.setPlaceholderText("Link thông tin cập nhật do nhà phát hành cung cấp")
        form_gen.addRow("Nguồn cập nhật:", self.txt_update_source)

        self.tabs.addTab(tab_general, "Chung")

        # Tab 2: Muse AI Selectors
        tab_selectors = QWidget()
        form_sel = QFormLayout(tab_selectors)
        form_sel.setSpacing(10)

        self.txt_sel_new_chat = QLineEdit(", ".join(self.settings.muse_selectors.new_chat_button))
        form_sel.addRow("Nút New Chat (+):", self.txt_sel_new_chat)

        self.txt_sel_composer = QLineEdit(", ".join(self.settings.muse_selectors.composer_textarea))
        form_sel.addRow("Composer Textarea:", self.txt_sel_composer)

        self.txt_sel_upload = QLineEdit(", ".join(self.settings.muse_selectors.file_input))
        form_sel.addRow("File Upload Input:", self.txt_sel_upload)

        self.txt_sel_submit = QLineEdit(", ".join(self.settings.muse_selectors.submit_button))
        form_sel.addRow("Submit / Generate Button:", self.txt_sel_submit)

        self.txt_sel_media = QLineEdit(", ".join(self.settings.muse_selectors.completed_media))
        form_sel.addRow("Media Result Item:", self.txt_sel_media)

        self.txt_sel_quota = QLineEdit(", ".join(self.settings.muse_selectors.quota_warning))
        form_sel.addRow("Quota / Rate Limit Warning:", self.txt_sel_quota)

        self.tabs.addTab(tab_selectors, "Muse AI Selectors")

        # Tab 3: LLM API Keys
        tab_llm = QWidget()
        form_llm = QFormLayout(tab_llm)
        form_llm.setSpacing(12)

        self.combo_llm_prov = QComboBox()
        self.combo_llm_prov.addItems(["gemini", "openai", "anthropic"])
        self.combo_llm_prov.setCurrentText(self.settings.llm_config.get("provider", "gemini"))
        form_llm.addRow("Nhà cung cấp LLM chính:", self.combo_llm_prov)

        self.gemini_panel = GeminiKeyPanel(self.settings)
        self.txt_gemini_key = self.gemini_panel.key
        form_llm.addRow("Google Gemini API Key:", self.gemini_panel)

        self.txt_openai_key = QLineEdit(self.settings.llm_config.get("openai_api_key", ""))
        self.txt_openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_llm.addRow("OpenAI API Key:", self.txt_openai_key)

        self.txt_anthropic_key = QLineEdit(self.settings.llm_config.get("anthropic_api_key", ""))
        self.txt_anthropic_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_llm.addRow("Claude (Anthropic) API Key:", self.txt_anthropic_key)

        self.tabs.addTab(tab_llm, "LLM AI API")

        # Tab 4: TTS Config
        tab_tts = QWidget()
        form_tts = QFormLayout(tab_tts)
        form_tts.setSpacing(12)

        self.combo_tts_prov = QComboBox()
        self.combo_tts_prov.addItems(["edge-tts", "elevenlabs", "fpt"])
        self.combo_tts_prov.setCurrentText(self.settings.tts_config.get("provider", "edge-tts"))
        form_tts.addRow("Engine TTS:", self.combo_tts_prov)

        self.combo_edge_voice = QComboBox()
        self.combo_edge_voice.addItems([
            "vi-VN-HoaiMyNeural (Nữ, truyền cảm)",
            "vi-VN-NamMinhNeural (Nam, trầm ấm)",
            "en-US-JennyNeural (Nữ, US)",
            "en-US-GuyNeural (Nam, US)"
        ])
        curr_voice = self.settings.tts_config.get("edge_voice", "vi-VN-HoaiMyNeural")
        idx = 0
        for i in range(self.combo_edge_voice.count()):
            if curr_voice in self.combo_edge_voice.itemText(i):
                idx = i
                break
        self.combo_edge_voice.setCurrentIndex(idx)
        form_tts.addRow("Giọng Edge-TTS:", self.combo_edge_voice)

        self.txt_eleven_key = QLineEdit(self.settings.tts_config.get("elevenlabs_api_key", ""))
        self.txt_eleven_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_tts.addRow("ElevenLabs API Key:", self.txt_eleven_key)

        self.txt_fpt_key = QLineEdit(self.settings.tts_config.get("fpt_api_key", ""))
        self.txt_fpt_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_tts.addRow("FPT.AI API Key:", self.txt_fpt_key)

        self.tabs.addTab(tab_tts, "TTS Giọng Nói")

        # Buttons
        h_actions = QHBoxLayout()
        h_actions.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Lưu Cấu Hình")
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self._save_settings)
        h_actions.addWidget(btn_cancel)
        h_actions.addWidget(btn_save)
        layout.addLayout(h_actions)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu output")
        if d:
            self.txt_output_dir.setText(d)

    def _save_settings(self):
        if self.gemini_panel.checking:
            QMessageBox.information(self, 'Đang kiểm tra key', 'Chờ kiểm tra key Gemini hoàn tất trước khi lưu.')
            return
        try:
            gemini_key = normalize_gemini_key(self.txt_gemini_key.text())
        except ValueError as exc:
            QMessageBox.warning(self, 'API key Gemini', str(exc))
            return
        # General
        self.settings.app_config["output_dir"] = self.txt_output_dir.text().strip()
        self.settings.app_config["default_timeout"] = self.spin_timeout.value()
        self.settings.app_config["default_aspect_ratio"] = self.combo_aspect.currentText()
        self.settings.app_config["max_concurrent_tabs"] = self.spin_tabs.value()
        self.settings.app_config["auto_new_chat"] = self.chk_auto_new_chat.isChecked()
        self.settings.app_config["proxy"] = self.txt_proxy.text().strip()
        self.settings.app_config["update_manifest_url"] = self.txt_update_source.text().strip()

        # Selectors
        self.settings.muse_selectors.new_chat_button = [s.strip() for s in self.txt_sel_new_chat.text().split(",") if s.strip()]
        self.settings.muse_selectors.composer_textarea = [s.strip() for s in self.txt_sel_composer.text().split(",") if s.strip()]
        self.settings.muse_selectors.file_input = [s.strip() for s in self.txt_sel_upload.text().split(",") if s.strip()]
        self.settings.muse_selectors.submit_button = [s.strip() for s in self.txt_sel_submit.text().split(",") if s.strip()]
        self.settings.muse_selectors.completed_media = [s.strip() for s in self.txt_sel_media.text().split(",") if s.strip()]
        self.settings.muse_selectors.quota_warning = [s.strip() for s in self.txt_sel_quota.text().split(",") if s.strip()]

        # LLM
        self.settings.llm_config["provider"] = self.combo_llm_prov.currentText()
        if self.settings.llm_config.get('gemini_api_key') != gemini_key:
            self.settings.llm_config['gemini_model'] = 'auto'
        self.settings.llm_config["gemini_api_key"] = gemini_key
        self.settings.llm_config["openai_api_key"] = self.txt_openai_key.text().strip()
        self.settings.llm_config["anthropic_api_key"] = self.txt_anthropic_key.text().strip()

        # TTS
        self.settings.tts_config["provider"] = self.combo_tts_prov.currentText()
        raw_v = self.combo_edge_voice.currentText()
        self.settings.tts_config["edge_voice"] = raw_v.split()[0]
        self.settings.tts_config["elevenlabs_api_key"] = self.txt_eleven_key.text().strip()
        self.settings.tts_config["fpt_api_key"] = self.txt_fpt_key.text().strip()

        if self.settings.save() is False:
            QMessageBox.warning(self, 'Không lưu được', 'Kiểm tra quyền ghi thư mục cấu hình. Chưa lưu thay đổi xuống máy.')
            return
        QMessageBox.information(self, "Thành công", "Đã lưu toàn bộ cấu hình hệ thống!")
        self.accept()

    def reject(self):
        if self.gemini_panel.checking:
            self.gemini_panel.message.setText('Đang kiểm tra key. Chờ hoàn tất trước khi đóng.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.gemini_panel.checking:
            self.gemini_panel.message.setText('Đang kiểm tra key. Chờ hoàn tất trước khi đóng.')
            event.ignore()
        else:
            super().closeEvent(event)
