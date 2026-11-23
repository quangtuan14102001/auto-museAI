from typing import List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QSpinBox, QComboBox, QMessageBox, QProgressBar
)
from PyQt6.QtCore import pyqtSignal
from config.settings import SettingsManager
from workers.llm_rewriter import LLMRewriterWorker


class LLMDictationDialog(QDialog):
    prompts_generated_signal = pyqtSignal(list) # Emits List[str]

    def __init__(self, available_tags: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Viết Lại Kịch Bản & Phân Cảnh Bằng AI (LLM Studio)")
        self.resize(720, 600)
        self.available_tags = available_tags
        self.settings = SettingsManager.get_instance()
        self.worker: LLMRewriterWorker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Instructions & Top bar
        h_top = QHBoxLayout()
        h_top.addWidget(QLabel("Nhà cung cấp LLM:"))
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["gemini", "openai", "anthropic", "offline_local"])
        self.combo_provider.setCurrentText(self.settings.llm_config.get("provider", "gemini"))
        h_top.addWidget(self.combo_provider)

        h_top.addWidget(QLabel("Số phân cảnh cần tạo:"))
        self.spin_scenes = QSpinBox()
        self.spin_scenes.setRange(1, 50)
        self.spin_scenes.setValue(5)
        h_top.addWidget(self.spin_scenes)
        h_top.addStretch()
        layout.addLayout(h_top)

        # Tags hint
        tags_str = ", ".join(self.available_tags) if self.available_tags else "(Chưa có thẻ nào)"
        lbl_tags = QLabel(f"Các thẻ tham chiếu sẵn có: <b>{tags_str}</b>")
        lbl_tags.setStyleSheet("color: #a5b4fc;")
        layout.addWidget(lbl_tags)

        # Raw Script Input
        layout.addWidget(QLabel("Nhập kịch bản thô hoặc ý tưởng câu chuyện:"))
        self.txt_script = QTextEdit()
        self.txt_script.setPlaceholderText(
            "Ví dụ:\nCô gái trẻ bước vào quán cà phê cổ kính trong một buổi chiều mưa. "
            "Cô ngồi bên cửa sổ, gọi một tách cappuccino và mở cuốn sổ tay. "
            "Một chú mèo tam thể tiến lại gần dụi đầu vào chân cô..."
        )
        layout.addWidget(self.txt_script)

        # Generate Button
        self.btn_generate = QPushButton("✨ Phân Tích & Viết Lại Kịch Bản Thành Prompts")
        self.btn_generate.setProperty("class", "btn-accent")
        self.btn_generate.clicked.connect(self._start_generation)
        layout.addWidget(self.btn_generate)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Output Box
        layout.addWidget(QLabel("Kết quả danh sách prompt các phân cảnh:"))
        self.txt_output = QTextEdit()
        self.txt_output.setPlaceholderText("Danh sách các phân cảnh prompt sẽ xuất hiện ở đây...")
        layout.addWidget(self.txt_output)

        # Action Buttons
        h_action = QHBoxLayout()
        h_action.addStretch()
        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.reject)
        
        self.btn_push_queue = QPushButton("🚀 Đẩy vào Hàng Đợi Prompt Studio")
        self.btn_push_queue.setProperty("class", "btn-run")
        self.btn_push_queue.clicked.connect(self._push_to_queue)
        
        h_action.addWidget(btn_close)
        h_action.addWidget(self.btn_push_queue)
        layout.addLayout(h_action)

    def _start_generation(self):
        script_text = self.txt_script.toPlainText().strip()
        if not script_text:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập kịch bản thô!")
            return

        provider = self.combo_provider.currentText()
        api_key = ""
        model_name = ""

        if provider == "gemini":
            api_key = self.settings.llm_config.get("gemini_api_key", "")
            model_name = self.settings.llm_config.get("gemini_model", "auto")
        elif provider == "openai":
            api_key = self.settings.llm_config.get("openai_api_key", "")
            model_name = self.settings.llm_config.get("openai_model", "gpt-4o")
        elif provider == "anthropic":
            api_key = self.settings.llm_config.get("anthropic_api_key", "")
            model_name = self.settings.llm_config.get("anthropic_model", "claude-3-5-sonnet-20241022")

        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.worker = LLMRewriterWorker(
            raw_script=script_text,
            num_scenes=self.spin_scenes.value(),
            alias_tags=self.available_tags,
            provider=provider,
            api_key=api_key,
            model_name=model_name
        )
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, prompts: List[str]):
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.txt_output.setPlainText("\n\n".join(prompts))
        QMessageBox.information(self, "Thành công", f"Đã sinh {len(prompts)} phân cảnh prompt!")

    def _on_error(self, err: str):
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.warning(self, "Thông báo", f"Lỗi: {err}")

    def _push_to_queue(self):
        content = self.txt_output.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "Lỗi", "Chưa có prompt nào để đẩy vào hàng đợi!")
            return
        
        prompts = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not prompts:
            prompts = [p.strip() for p in content.splitlines() if p.strip()]

        self.prompts_generated_signal.emit(prompts)
        QMessageBox.information(self, "Thành công", f"Đã nạp {len(prompts)} prompt vào Hàng Đợi!")
        self.accept()
