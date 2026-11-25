"""Editable canonical reference library and per-shot continuity inspector."""
import copy
import uuid
from dataclasses import asdict
from pathlib import Path
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QDialogButtonBox, QFileDialog, QMessageBox, QComboBox, QListWidget, QListWidgetItem, QScrollArea, QGridLayout)
from core.film_project import FilmReference
from core.media_output import validate_output
from core.models import JobMode


class FilmReferencesPanel(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        layout = QVBoxLayout(self)
        info = QLabel("Ảnh chuẩn được lưu riêng cho từng nhân vật và địa điểm. App chỉ gắn ảnh của các đối tượng có trong clip. "
                      "Nếu chưa chọn ảnh, Muse sẽ tạo ảnh chuẩn trước khi tạo phim. Ảnh AI vẫn cần được xem lại.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Loại", "Tên", "Mô tả cố định", "Ảnh chuẩn"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(72)
        self.table.setColumnWidth(1, 190)
        self.table.setIconSize(QSize(80, 60))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for title, action in [("Thêm nhân vật", lambda: self.edit(kind="character")),
                              ("Thêm bối cảnh", lambda: self.edit(kind="location")),
                              ("Sửa / chọn ảnh", self.edit), ("Xem ảnh chuẩn", self.preview),
                              ("Tạo lại ảnh chuẩn", self.reset_image), ("Xóa", self.remove)]:
            button = QPushButton(title)
            button.clicked.connect(action)
            actions.addWidget(button)
        layout.addLayout(actions)

    def refs(self):
        return self.owner.store.project.references if self.owner.store else self.owner.reference_draft

    def refresh(self):
        self.table.setRowCount(len(self.refs()))
        for i, ref in enumerate(self.refs()):
            values = ["Nhân vật" if ref.kind == "character" else "Bối cảnh", ref.name, ref.description,
                      f"{len(ref.images)} ảnh" if ref.images else ("Cần kiểm tra Muse" if ref.submitted_prompt else "Sẽ tạo bằng Muse")]
            for j, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(ref.error if j == 3 and ref.error else value)
                if j == 1 and ref.images:
                    source = self.owner.store.asset(ref.images[0]) if self.owner.store else ref.images[0]
                    icon = QIcon(source)
                    # Qt synthesizes a grayscale Disabled pixmap when the
                    # reference panel is locked during generation. Supply the
                    # original image for that mode; editing stays disabled.
                    icon.addFile(source, QSize(), QIcon.Mode.Disabled)
                    item.setIcon(icon)
                self.table.setItem(i, j, item)

    def selected(self):
        row = self.table.currentRow()
        return self.refs()[row] if 0 <= row < len(self.refs()) else None

    def edit(self, checked=False, kind=None):
        previous = None if kind else self.selected()
        if previous is None and kind is None:
            return
        ref = copy.deepcopy(previous) if previous else FilmReference(uuid.uuid4().hex[:12], kind, "", "")
        dialog = QDialog(self)
        dialog.setWindowTitle("Ảnh chuẩn nhân vật" if ref.kind == "character" else "Ảnh chuẩn bối cảnh")
        dialog.resize(620, 390)
        form = QFormLayout(dialog)
        name, description = QLineEdit(ref.name), QTextEdit(ref.description)
        description.setPlaceholderText("Ngoại hình, trang phục, phụ kiện cố định" if ref.kind == "character" else "Bố cục, vật mốc, ánh sáng và thời điểm")
        form.addRow("Tên:", name)
        form.addRow("Mô tả:", description)
        paths = list(ref.images)
        images = QLabel(f"{len(paths)} ảnh đã chọn. Không có ảnh: app tạo ảnh chuẩn bằng Muse.")
        images.setWordWrap(True)
        choose = QPushButton("Chọn ảnh chuẩn từ máy")
        def select():
            chosen, _ = QFileDialog.getOpenFileNames(dialog, "Ảnh chuẩn", "", "Ảnh (*.png *.jpg *.jpeg *.webp)")
            if chosen:
                paths[:] = chosen
                images.setText(f"Đã chọn {len(paths)} ảnh")
        choose.clicked.connect(select)
        form.addRow(images)
        form.addRow(choose)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not name.text().strip() or not description.toPlainText().strip():
            QMessageBox.warning(self, "Thiếu thông tin", "Nhập tên và mô tả ảnh chuẩn.")
            return
        try:
            normalized = []
            for path in paths:
                source = self.owner.store.asset(path) if self.owner.store and not Path(path).is_absolute() else path
                validate_output(source, JobMode.TEXT_TO_IMAGE.value)
                normalized.append(self.owner.store.snapshot(source, "canonical") if self.owner.store else source)
            ref.name, ref.description, ref.images = name.text().strip(), description.toPlainText().strip(), normalized
            if previous and asdict(previous) == asdict(ref):
                return
            if previous and not self.owner._invalidate_reference(previous.id):
                return
            ref.image_hashes = {p: self.owner.store.digest(self.owner.store.asset(p)) for p in normalized} if self.owner.store else {}
            if normalized:
                ref.generation_status, ref.error = "READY", ""
            elif previous and previous.submitted_prompt:
                # Editing text is not permission to duplicate an interrupted image job.
                ref.generation_status = "WAITING"
            if previous:
                self.refs()[self.refs().index(previous)] = ref
            else:
                self.refs().append(ref)
            if self.owner.store:
                self.owner.store.save()
                self.owner._refresh()
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Chưa lưu được ảnh chuẩn", str(exc))

    def preview(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        ref = self.selected()
        if ref and ref.images:
            source = self.owner.store.asset(ref.images[0]) if self.owner.store else ref.images[0]
            QDesktopServices.openUrl(QUrl.fromLocalFile(source))

    def remove(self):
        ref = self.selected()
        if ref is None:
            return
        if self.owner.store and any(ref.id in shot.character_ids or ref.id == shot.location_id for shot in self.owner.store.project.shots):
            QMessageBox.information(self, "Tham chiếu đang dùng", "Bỏ gán tham chiếu khỏi các clip trước khi xóa.")
            return
        self.refs().remove(ref)
        if self.owner.store:
            self.owner.store.save()
        self.refresh()

    def reset_image(self):
        ref = self.selected()
        if ref is None:
            return
        answer = QMessageBox.question(self, "Tạo lại ảnh chuẩn",
            "Ảnh cũ vẫn được lưu. Nếu Muse còn đang xử lý ảnh trước, hãy kiểm tra kết quả để tránh gửi trùng. Đặt ảnh này về chờ tạo lại?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes or not self.owner._invalidate_reference(ref.id):
            return
        ref.history.append({key: value for key, value in asdict(ref).items() if key != "history"})
        ref.images, ref.image_hashes = [], {}
        ref.generation_status, ref.submitted_prompt, ref.submission_url, ref.error = "PENDING", "", "", ""
        if self.owner.store:
            self.owner.store.save()
            self.owner._refresh()
        self.refresh()
        self.owner.status.setText("Đã đặt ảnh chuẩn về chờ tạo. Bấm Tiếp tục làm phim để Muse tạo ảnh mới.")


def edit_shot_dialog(owner, shot):
    dialog = QDialog(owner)
    dialog.setWindowTitle("Nội dung và tham chiếu clip")
    dialog.resize(690, 650)
    form = QFormLayout(dialog)
    action = QTextEdit(shot.prompt)
    action.setMaximumHeight(100)
    form.addRow("Hành động riêng của clip:", action)
    mode = QComboBox()
    mode.addItems(["Cảnh mới / chuyển góc", "Tiếp nối clip trước"])
    mode.setCurrentIndex(int(shot.continuation))
    form.addRow("Cách nối:", mode)
    characters = QListWidget()
    characters.setMaximumHeight(100)
    location = QComboBox()
    location.addItem("Không gán bối cảnh", "")
    for ref in owner.store.project.references:
        if ref.kind == "character":
            item = QListWidgetItem(ref.name)
            item.setData(Qt.ItemDataRole.UserRole, ref.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if ref.id in shot.character_ids else Qt.CheckState.Unchecked)
            characters.addItem(item)
        else:
            location.addItem(ref.name, ref.id)
    location.setCurrentIndex(max(0, location.findData(shot.location_id)))
    form.addRow("Nhân vật xuất hiện:", characters)
    form.addRow("Bối cảnh:", location)
    start, end = QTextEdit(shot.start_state), QTextEdit(shot.end_state)
    start.setMaximumHeight(80)
    end.setMaximumHeight(80)
    form.addRow("Trạng thái bắt đầu:", start)
    form.addRow("Trạng thái kết thúc:", end)
    note = QLabel("Tiếp nối: trạng thái đầu phải khớp kết thúc clip trước. Sửa clip sẽ đặt lại các clip nối phía sau; file cũ được giữ.")
    note.setWordWrap(True)
    form.addRow(note)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return {"prompt": action.toPlainText().strip(), "continuation": bool(mode.currentIndex()),
            "character_ids": [characters.item(i).data(Qt.ItemDataRole.UserRole) for i in range(characters.count())
                              if characters.item(i).checkState() == Qt.CheckState.Checked],
            "location_id": location.currentData(), "start_state": start.toPlainText().strip(), "end_state": end.toPlainText().strip()}


def compare_reference_dialog(owner):
    from PyQt6.QtGui import QPixmap
    _, shot = owner._selection()
    if shot is None:
        return
    dialog = QDialog(owner)
    dialog.setWindowTitle("Đối chiếu ảnh chuẩn và kết quả clip")
    dialog.resize(860, 630)
    layout = QVBoxLayout(dialog)
    note = QLabel("Đối chiếu ngoại hình, trang phục, đạo cụ và bố cục. Ảnh tham chiếu giúp giữ nhất quán nhưng không bảo đảm AI làm đúng. "
                  "Ảnh đã gửi là bản sao lưu tại thời điểm gửi Muse.")
    note.setWordWrap(True)
    layout.addWidget(note)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content.setStyleSheet("background: #111827;")
    grid = QGridLayout(content)
    grid.setAlignment(Qt.AlignmentFlag.AlignTop)
    entries = []
    for ref in owner.store.project.references:
        if ref.id in shot.character_ids or ref.id == shot.location_id:
            entries.extend((f"Ảnh chuẩn · {ref.name}", image) for image in ref.images)
    entries.extend((f"Ảnh đã gửi · {i+1}", image) for i, image in enumerate(shot.input_refs))
    entries.extend((title, image) for title, image in [("Kết quả · khung đầu", shot.first_frame),
                                                      ("Kết quả · khung cuối", shot.last_frame)] if image)
    shown = {image for _, image in entries}
    report = shot.visual_review
    previous = report.get('previous_frame')
    if previous and previous.get('path') not in shown:
        entries.append(('Bàn giao · khung cuối clip trước', previous['path']))
        shown.add(previous['path'])
    for sample in report.get('samples', []):
        if sample.get('path') and sample['path'] not in shown:
            entries.append((sample['label'], sample['path']))
            shown.add(sample['path'])
    for i, (title, image) in enumerate(entries):
        column = QVBoxLayout()
        column.setAlignment(Qt.AlignmentFlag.AlignTop)
        column.addWidget(QLabel(title))
        picture = QLabel()
        picture.setPixmap(QPixmap(owner.store.asset(image)).scaled(240, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                                                   Qt.TransformationMode.SmoothTransformation))
        picture.setToolTip(owner.store.asset(image))
        column.addWidget(picture)
        grid.addLayout(column, i // 3, i % 3)
    scroll.setWidget(content)
    layout.addWidget(scroll)
    state = QLabel(f"Đầu clip: {shot.start_state or 'chưa khai báo'}\nCuối clip: {shot.end_state or 'chưa khai báo'}")
    state.setWordWrap(True)
    layout.addWidget(state)
    if shot.visual_review:
        scope = '5 khung mẫu' if report.get('scope') == 'five_sampled_frames_only' else 'khung đầu/cuối'
        correction = {'none':'Không đề xuất sửa', 'reference':'Kiểm tra ảnh chuẩn', 'shot_plan':'Sửa kế hoạch cảnh',
                      'generation':'Kiểm tra lần tạo clip', 'capability':'Kiểm tra khả năng công cụ', 'manual':'Xem lại thủ công'}
        text = f"Gemini (chỉ {scope}): " + report.get('summary', '')
        if report.get('issues'):
            text += '\n' + '\n'.join(report['issues'])
        if report.get('correction') in correction:
            text += '\nĐề xuất: ' + correction[report['correction']]
        result = QLabel(text)
        result.setTextFormat(Qt.TextFormat.PlainText)
        result.setWordWrap(True)
        layout.addWidget(result)
    close = QPushButton("Đóng")
    close.clicked.connect(dialog.accept)
    layout.addWidget(close)
    dialog.exec()
