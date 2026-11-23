import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QFrame
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
from core.models import AliasItem


class AliasDialog(QDialog):
    def __init__(self, alias_item: AliasItem = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm / Sửa Tham Chiếu Ảnh (@Alias)")
        self.resize(480, 420)
        self.alias_item = alias_item
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Tag
        layout.addWidget(QLabel("Tag Định Danh (Bắt đầu bằng @):"))
        self.txt_tag = QLineEdit()
        self.txt_tag.setPlaceholderText("Ví dụ: @anh1, @anhaohong, @sanpham...")
        layout.addWidget(self.txt_tag)

        # Name / Description
        layout.addWidget(QLabel("Tên Mô Tả / Nhận Diện:"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ví dụ: Nhân vật nữ chính tóc nâu, Chai serum 50ml...")
        layout.addWidget(self.txt_name)

        # File path
        layout.addWidget(QLabel("Đường Dẫn File Ảnh Tham Chiếu:"))
        h_file = QHBoxLayout()
        self.txt_file = QLineEdit()
        self.txt_file.setPlaceholderText("Chọn file ảnh .jpg, .png, .webp...")
        btn_browse = QPushButton("Chọn ảnh...")
        btn_browse.clicked.connect(self._browse_image)
        h_file.addWidget(self.txt_file)
        h_file.addWidget(btn_browse)
        layout.addLayout(h_file)

        # Preview Frame
        layout.addWidget(QLabel("Xem Trước Ảnh:"))
        self.lbl_preview = QLabel("Chưa chọn ảnh")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setFixedSize(140, 140)
        self.lbl_preview.setStyleSheet(
            "border: 1px dashed #3e4663; border-radius: 8px; background-color: #12141c; color: #64748b;"
        )
        layout.addWidget(self.lbl_preview, alignment=Qt.AlignmentFlag.AlignCenter)

        # Populate if editing
        if self.alias_item:
            self.txt_tag.setText(self.alias_item.tag)
            self.txt_name.setText(self.alias_item.name)
            self.txt_file.setText(self.alias_item.file_path)
            self._update_preview(self.alias_item.file_path)

        self.txt_file.textChanged.connect(self._update_preview)

        # Action Buttons
        h_btn = QHBoxLayout()
        h_btn.addStretch()
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Lưu Tham Chiếu")
        btn_save.setProperty("class", "btn-primary")
        btn_save.clicked.connect(self._save)
        h_btn.addWidget(btn_cancel)
        h_btn.addWidget(btn_save)
        layout.addLayout(h_btn)

    def _browse_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file ảnh tham chiếu", "", "Images (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if file_path:
            self.txt_file.setText(file_path)

    def _update_preview(self, path: str):
        if path and os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                self.lbl_preview.setPixmap(
                    pix.scaled(130, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
                return
        self.lbl_preview.setText("Chưa chọn ảnh")
        self.lbl_preview.setPixmap(QPixmap())

    def _save(self):
        tag = self.txt_tag.text().strip()
        if not tag:
            QMessageBox.warning(self, "Lỗi", "Vui lòng nhập tag định danh (ví dụ: @anh1)!")
            return
        if not tag.startswith("@"):
            tag = f"@{tag}"

        file_path = self.txt_file.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Lỗi", "Đường dẫn file ảnh không hợp lệ hoặc file không tồn tại!")
            return

        name = self.txt_name.text().strip() or tag

        self.result_alias = AliasItem(tag=tag, name=name, file_path=file_path)
        self.accept()
