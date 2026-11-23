import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QComboBox, QSpinBox, QPushButton, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class ImageToVideoDialog(QDialog):
    """
    Dialog cho phép người dùng dùng ảnh đã tạo từ TEXT -> IMAGE,
    nhập prompt chuyển động để tạo tiếp Video (IMAGE -> VIDEO).
    """
    def __init__(self, image_path: str, initial_prompt: str = "", default_aspect: str = "16:9", default_duration: int = 5, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎬 Tạo Video từ Ảnh Tham Chiếu (Image ➔ Video)")
        self.resize(600, 480)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f111a;
                color: #e2e8f0;
            }
            QLabel {
                color: #e2e8f0;
                font-size: 13px;
            }
            QTextEdit {
                background-color: #1a1e2e;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }
            QTextEdit:focus {
                border: 1px solid #38bdf8;
            }
            QComboBox, QSpinBox {
                background-color: #1a1e2e;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#btnCancel {
                background-color: #334155;
            }
            QPushButton#btnCancel:hover {
                background-color: #475569;
            }
        """)

        self.image_path = image_path
        self.result_data = None
        self._init_ui(initial_prompt, default_aspect, default_duration)

    def _init_ui(self, initial_prompt: str, default_aspect: str, default_duration: int):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 1. Header info with image preview
        h_preview = QHBoxLayout()
        h_preview.setSpacing(14)

        lbl_img = QLabel()
        lbl_img.setFixedSize(110, 110)
        lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_img.setStyleSheet("background-color: #1e293b; border: 2px solid #38bdf8; border-radius: 8px;")
        if os.path.exists(self.image_path):
            pix = QPixmap(self.image_path)
            if not pix.isNull():
                lbl_img.setPixmap(pix.scaled(106, 106, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                lbl_img.setText("IMG")
        else:
            lbl_img.setText("No Image")
        h_preview.addWidget(lbl_img)

        v_meta = QVBoxLayout()
        v_meta.setSpacing(4)
        lbl_title = QLabel("Tạo Video chuyển động từ Ảnh này:")
        lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #38bdf8;")
        v_meta.addWidget(lbl_title)

        lbl_path = QLabel(f"Ảnh nguồn: {os.path.basename(self.image_path)}")
        lbl_path.setStyleSheet("color: #94a3b8; font-size: 11px;")
        lbl_path.setToolTip(self.image_path)
        v_meta.addWidget(lbl_path)

        lbl_hint = QLabel("💡 Bạn có thể giữ nguyên prompt hoặc thêm mô tả chuyển động camera (zoom, pan, tracking, hiệu ứng gió/nước...).")
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        v_meta.addWidget(lbl_hint)
        v_meta.addStretch()

        h_preview.addLayout(v_meta, stretch=1)
        layout.addLayout(h_preview)

        # 2. Prompt input for Video
        layout.addWidget(QLabel("Prompt mô tả chuyển động video:"))
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setPlaceholderText("Ví dụ: Góc máy quay cận cảnh chuyển động chậm, tóc bay nhẹ trong gió, hiệu ứng ánh sáng điện ảnh mờ ảo...")
        # Clean or set initial prompt
        self.txt_prompt.setPlainText(initial_prompt.strip())
        self.txt_prompt.setFixedHeight(120)
        layout.addWidget(self.txt_prompt)

        # 3. Parameters (Duration, Aspect Ratio)
        h_params = QHBoxLayout()
        h_params.setSpacing(16)

        h_params.addWidget(QLabel("Khung hình:"))
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems(["16:9", "9:16", "1:1", "AUTO"])
        if default_aspect in ["16:9", "9:16", "1:1", "AUTO"]:
            self.combo_aspect.setCurrentText(default_aspect)
        h_params.addWidget(self.combo_aspect)

        h_params.addWidget(QLabel("Thời lượng Video (giây):"))
        self.spin_duration = QSpinBox()
        self.spin_duration.setRange(2, 60)
        self.spin_duration.setValue(default_duration)
        h_params.addWidget(self.spin_duration)

        h_params.addStretch()
        layout.addLayout(h_params)

        # 4. Action buttons
        layout.addStretch()
        h_actions = QHBoxLayout()
        h_actions.addStretch()

        btn_cancel = QPushButton("Hủy")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.clicked.connect(self.reject)
        h_actions.addWidget(btn_cancel)

        btn_submit = QPushButton("➕ Đưa vào Hàng Đợi Tạo Video")
        btn_submit.setStyleSheet("background-color: #10b981; color: white;")
        btn_submit.clicked.connect(self._on_submit)
        h_actions.addWidget(btn_submit)

        layout.addLayout(h_actions)

    def _on_submit(self):
        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Chưa nhập Prompt", "Vui lòng nhập prompt mô tả video cần tạo!")
            return

        self.result_data = {
            "prompt": prompt,
            "aspect_ratio": self.combo_aspect.currentText(),
            "video_duration": self.spin_duration.value(),
            "image_path": self.image_path
        }
        self.accept()
