import os
import uuid
import datetime
from typing import List, Dict

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QCheckBox, QAbstractItemView,
    QMessageBox, QWidget, QScrollArea, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QCursor

from config.settings import SettingsManager
from core.models import AliasItem, TaskItem, TaskStatus, JobMode
from core.prompt_parser import PromptParser
from core.media_output import validate_output
from ui.dialogs.alias_dialog import AliasDialog
from utils.file_utils import open_in_explorer, sanitize_filename
from utils.logger import log_event


class RightPanel(QFrame):
    task_retry_signal = pyqtSignal(str) # task_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.settings = SettingsManager.get_instance()
        self._running = False
        self._audit_saved_outputs()
        self._init_ui()
        self._load_aliases()
        self._load_tasks()

    def _audit_saved_outputs(self):
        changed = False
        for task in self.settings.tasks:
            if not task.status.startswith("OK"):
                continue
            try:
                validate_output(task.output_file, task.mode, probe_video=False)
            except (ValueError, OSError) as exc:
                task.status = TaskStatus.FAIL.value
                task.error_message = f"Kết quả cũ không hợp lệ: {exc} File được giữ tại: {task.output_file}"
                task.output_file = ""
                changed = True
        if changed:
            self.settings.save()

    def set_running(self, running: bool):
        self._running = running
        for widget_type in (QComboBox, QSpinBox, QPushButton):
            for widget in self.findChildren(widget_type):
                widget.setEnabled(not running)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # 1. THANH THAM SỐ TRÊN CÙNG
        # -------------------------------------------------------------
        frame_top_params = QFrame()
        frame_top_params.setStyleSheet("background-color: #161922; border-radius: 8px; padding: 4px;")
        h_params = QHBoxLayout(frame_top_params)
        h_params.setContentsMargins(10, 8, 10, 8)
        h_params.setSpacing(16)

        # CHỨC NĂNG
        h_params.addWidget(QLabel("CHỨC NĂNG:"))
        self.combo_mode = QComboBox()
        self.combo_mode.setMinimumWidth(220)
        if self.combo_mode.view():
            self.combo_mode.view().setMinimumWidth(230)
        self.combo_mode.addItems([
            JobMode.TEXT_TO_IMAGE.value,
            JobMode.TEXT_TO_VIDEO.value,
            JobMode.REFERENCE_IMAGE_TO_VIDEO.value,
            JobMode.TEXT_TO_IMAGE_TO_VIDEO.value
        ])
        self.combo_mode.setCurrentText(self.settings.app_config.get("default_mode", JobMode.TEXT_TO_VIDEO.value))
        self.combo_mode.currentTextChanged.connect(self._on_param_changed)
        h_params.addWidget(self.combo_mode)

        # Khung hình
        h_params.addWidget(QLabel("Khung hình:"))
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems(["AUTO", "9:16", "16:9", "1:1"])
        self.combo_aspect.setCurrentText(self.settings.app_config.get("default_aspect_ratio", "16:9"))
        self.combo_aspect.currentTextChanged.connect(self._on_param_changed)
        h_params.addWidget(self.combo_aspect)

        # A reminder interval, not a generation deadline.
        h_params.addWidget(QLabel("Nhắc chờ (s):"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(30, 999)
        self.spin_timeout.setValue(self.settings.app_config.get("default_timeout", 210))
        self.spin_timeout.setMinimumWidth(110)
        self.spin_timeout.setToolTip("Mốc nhắc đang chờ; app tiếp tục đợi kết quả, không tự báo FAIL khi hết mốc này.")
        self.spin_timeout.valueChanged.connect(self._on_param_changed)
        h_params.addWidget(self.spin_timeout)

        # Video (s)
        h_params.addWidget(QLabel("Video (s):"))
        self.spin_video_duration = QSpinBox()
        self.spin_video_duration.setRange(2, 60)
        self.spin_video_duration.setValue(self.settings.app_config.get("default_video_duration", 5))
        self.spin_video_duration.setMinimumWidth(85)
        self.spin_video_duration.valueChanged.connect(self._on_param_changed)
        h_params.addWidget(self.spin_video_duration)

        # Số luồng song song (Concurrency)
        h_params.addWidget(QLabel("Số luồng:"))
        self.spin_concurrency = QSpinBox()
        self.spin_concurrency.setRange(1, 8)
        self.spin_concurrency.setValue(self.settings.app_config.get("max_concurrent_tabs", 2))
        self.spin_concurrency.setMinimumWidth(75)
        self.spin_concurrency.setToolTip("Số tài khoản/luồng chạy song song cùng một thời điểm")
        self.spin_concurrency.valueChanged.connect(self._on_param_changed)
        h_params.addWidget(self.spin_concurrency)

        h_params.addStretch()
        main_layout.addWidget(frame_top_params)

        # -------------------------------------------------------------
        # 2. BẢNG QUẢN LÝ THAM CHIẾU ĐẶT TÊN (REFERENCE ALIAS MANAGER)
        # -------------------------------------------------------------
        h_alias_header = QHBoxLayout()
        lbl_alias_title = QLabel("🏷 QUẢN LÝ THAM CHIẾU ĐẶT TÊN (REFERENCE ALIASES)")
        lbl_alias_title.setProperty("class", "section-title")
        h_alias_header.addWidget(lbl_alias_title)
        h_alias_header.addStretch()

        btn_add_alias = QPushButton("+ Thêm ảnh...")
        btn_add_alias.clicked.connect(self._add_alias)
        btn_edit_alias = QPushButton("Sửa")
        btn_edit_alias.clicked.connect(self._edit_alias)
        btn_del_alias = QPushButton("Xóa")
        btn_del_alias.clicked.connect(self._delete_alias)

        h_alias_header.addWidget(btn_add_alias)
        h_alias_header.addWidget(btn_edit_alias)
        h_alias_header.addWidget(btn_del_alias)
        main_layout.addLayout(h_alias_header)

        # Alias Table
        self.table_aliases = QTableWidget()
        self.table_aliases.setColumnCount(3)
        self.table_aliases.setHorizontalHeaderLabels(["THUMBNAIL", "@TÊN", "ĐƯỜNG DẪN ẢNH"])
        self.table_aliases.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_aliases.setColumnWidth(0, 75)
        self.table_aliases.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_aliases.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_aliases.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_aliases.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_aliases.verticalHeader().setVisible(False)
        self.table_aliases.setFixedHeight(120)
        main_layout.addWidget(self.table_aliases)

        # Chips Container: DANH SÁCH @THAM CHIẾU
        h_chip_bar = QHBoxLayout()
        lbl_chips_label = QLabel("DANH SÁCH @THAM CHIẾU:")
        lbl_chips_label.setStyleSheet("font-weight: bold; color: #a5b4fc; font-size: 11px;")
        h_chip_bar.addWidget(lbl_chips_label)

        self.scroll_chips = QScrollArea()
        self.scroll_chips.setFixedHeight(34)
        self.scroll_chips.setWidgetResizable(True)
        self.scroll_chips.setStyleSheet("background: transparent; border: none;")
        self.widget_chips = QWidget()
        self.layout_chips = QHBoxLayout(self.widget_chips)
        self.layout_chips.setContentsMargins(0, 0, 0, 0)
        self.layout_chips.setSpacing(6)
        self.scroll_chips.setWidget(self.widget_chips)
        h_chip_bar.addWidget(self.scroll_chips, stretch=1)
        main_layout.addLayout(h_chip_bar)

        # -------------------------------------------------------------
        # 3. MULTI-REFERENCE PROMPT PIPELINE (KHUNG 1 - PROMPT LIST GỐC)
        # -------------------------------------------------------------
        h_raw_head = QHBoxLayout()
        lbl_raw = QLabel("✍ KHUNG 1 - PROMPT LIST GỐC (Nhập kịch bản phân cách theo dòng trống):")
        lbl_raw.setProperty("class", "section-title")
        h_raw_head.addWidget(lbl_raw)
        h_raw_head.addStretch()

        self.chk_auto_attach = QCheckBox("Tự động gắn ảnh tham chiếu - không cần @alias")
        self.chk_auto_attach.setToolTip("Nếu bật, tự động đính kèm tất cả các ảnh tham chiếu ngay cả khi câu prompt không có @alias")
        h_raw_head.addWidget(self.chk_auto_attach)
        main_layout.addLayout(h_raw_head)

        h_prompt_box = QHBoxLayout()
        self.txt_raw_prompts = QTextEdit()
        self.txt_raw_prompts.setPlaceholderText(
            "Nhập prompt mỗi cảnh phân tách bằng dòng trống, ví dụ:\n\n"
            "Cảnh quay cận cảnh @anh1 đang nở nụ cười tươi trong ánh nắng hoàng hôn\n\n"
            "Góc quay sản phẩm @anh3 trên bàn, người mẫu mặc @anhaohong cầm sản phẩm..."
        )
        self.txt_raw_prompts.setFixedHeight(85)
        h_prompt_box.addWidget(self.txt_raw_prompts)

        btn_parse_feed = QPushButton("Phân tích & Nạp vào\nHàng Đợi ➔")
        btn_parse_feed.setProperty("class", "btn-accent")
        btn_parse_feed.setFixedWidth(150)
        btn_parse_feed.clicked.connect(self._parse_and_feed_prompts)
        h_prompt_box.addWidget(btn_parse_feed)
        main_layout.addLayout(h_prompt_box)

        # -------------------------------------------------------------
        # 4. KHUNG 2, 3, 4 - HÀNG ĐỢI TIẾN TRÌNH THEO HÀNG (TASK ROW)
        # -------------------------------------------------------------
        h_queue_head = QHBoxLayout()
        lbl_queue = QLabel("📋 HÀNG ĐỢI TIẾN TRÌNH THEO HÀNG (MULTI-REFERENCE PROMPT PIPELINE)")
        lbl_queue.setProperty("class", "section-title")
        h_queue_head.addWidget(lbl_queue)
        h_queue_head.addStretch()

        btn_add_row = QPushButton("+ Thêm dòng")
        btn_add_row.clicked.connect(self._add_single_task_row)
        btn_rerun_all = QPushButton("🔄 Chạy lại tất cả")
        btn_rerun_all.setToolTip("Đặt lại toàn bộ các task sang READY theo chế độ hiện tại trên thanh công cụ")
        btn_rerun_all.clicked.connect(self._rerun_all_tasks)
        btn_retry_fails = QPushButton("🔄 Retry all FAIL")
        btn_retry_fails.clicked.connect(self._retry_all_fails)
        btn_open_output = QPushButton("📁 Output thư mục")
        btn_open_output.clicked.connect(self._open_output_folder)
        btn_clear_tasks = QPushButton("Xóa hết")
        btn_clear_tasks.clicked.connect(self._clear_all_tasks)

        h_queue_head.addWidget(btn_add_row)
        h_queue_head.addWidget(btn_rerun_all)
        h_queue_head.addWidget(btn_retry_fails)
        h_queue_head.addWidget(btn_open_output)
        h_queue_head.addWidget(btn_clear_tasks)
        main_layout.addLayout(h_queue_head)

        # Task Queue Table
        self.table_tasks = QTableWidget()
        self.table_tasks.setColumnCount(4)
        self.table_tasks.setHorizontalHeaderLabels(["#", "PROMPT / RETRY", "THAM CHIẾU (Multi-tag)", "KẾT QUẢ / PREVIEW"])
        self.table_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_tasks.setColumnWidth(0, 45)
        self.table_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_tasks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.verticalHeader().setDefaultSectionSize(75)
        self.table_tasks.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_tasks.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_tasks.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table_tasks, stretch=1)

    # -------------------------------------------------------------
    # ALIAS METHODS
    # -------------------------------------------------------------
    def _load_aliases(self):
        self.table_aliases.setRowCount(0)
        # Clear chip layout
        while self.layout_chips.count():
            item = self.layout_chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for a in self.settings.aliases:
            row = self.table_aliases.rowCount()
            self.table_aliases.insertRow(row)

            # Col 0: Thumbnail
            lbl_thumb = QLabel()
            lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if os.path.exists(a.file_path):
                pix = QPixmap(a.file_path)
                if not pix.isNull():
                    lbl_thumb.setPixmap(pix.scaled(55, 55, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    lbl_thumb.setText("No IMG")
            else:
                lbl_thumb.setText("N/A")
            self.table_aliases.setCellWidget(row, 0, lbl_thumb)

            # Col 1: Tag & Name
            item_tag = QTableWidgetItem(f"{a.tag} ({a.name})")
            item_tag.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table_aliases.setItem(row, 1, item_tag)

            # Col 2: Path
            item_path = QTableWidgetItem(a.file_path)
            item_path.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table_aliases.setItem(row, 2, item_path)

            # Add to Chips bar
            btn_chip = QPushButton(f"{a.tag}")
            btn_chip.setProperty("class", "chip-btn")
            btn_chip.setToolTip(f"Nhấp để chèn {a.tag} vào prompt")
            btn_chip.clicked.connect(lambda checked, t=a.tag: self._insert_tag_to_prompt(t))
            self.layout_chips.addWidget(btn_chip)

        self.layout_chips.addStretch()

    def _insert_tag_to_prompt(self, tag: str):
        cursor = self.txt_raw_prompts.textCursor()
        cursor.insertText(f" {tag} ")
        self.txt_raw_prompts.setFocus()

    def _add_alias(self):
        dlg = AliasDialog(parent=self)
        if dlg.exec():
            new_a = dlg.result_alias
            # check duplicate
            self.settings.aliases = [a for a in self.settings.aliases if a.tag.lower() != new_a.tag.lower()]
            self.settings.aliases.append(new_a)
            self.settings.save()
            self._load_aliases()
            self._refresh_all_task_references()
            log_event(f"Đã thêm tham chiếu mới: {new_a.tag} -> {new_a.file_path}")

    def _edit_alias(self):
        row = self.table_aliases.currentRow()
        if 0 <= row < len(self.settings.aliases):
            item = self.settings.aliases[row]
            dlg = AliasDialog(alias_item=item, parent=self)
            if dlg.exec():
                self.settings.aliases[row] = dlg.result_alias
                self.settings.save()
                self._load_aliases()
                self._refresh_all_task_references()
                log_event(f"Đã cập nhật tham chiếu: {dlg.result_alias.tag}")
        else:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một tham chiếu để sửa!")

    def _delete_alias(self):
        row = self.table_aliases.currentRow()
        if 0 <= row < len(self.settings.aliases):
            item = self.settings.aliases[row]
            reply = QMessageBox.question(
                self, "Xác nhận", f"Bạn có chắc muốn xóa tham chiếu '{item.tag}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.settings.aliases.pop(row)
                self.settings.save()
                self._load_aliases()
                self._refresh_all_task_references()
                log_event(f"Đã xóa tham chiếu: {item.tag}")
        else:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một tham chiếu để xóa!")

    # -------------------------------------------------------------
    # TASK QUEUE PIPELINE METHODS
    # -------------------------------------------------------------
    def _load_tasks(self):
        self.table_tasks.setRowCount(0)
        for idx, task in enumerate(self.settings.tasks, 1):
            self._insert_task_row_widget(task, idx)

    def _insert_task_row_widget(self, task: TaskItem, index_num: int):
        row = self.table_tasks.rowCount()
        self.table_tasks.insertRow(row)

        # Col 0: Index
        item_idx = QTableWidgetItem(f"#{index_num}")
        item_idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item_idx.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table_tasks.setItem(row, 0, item_idx)

        # Col 1: PROMPT / RETRY widget
        w_prompt = QWidget()
        v_p = QVBoxLayout(w_prompt)
        v_p.setContentsMargins(6, 6, 6, 6)
        v_p.setSpacing(4)

        lbl_text = QLabel(task.prompt)
        lbl_text.setWordWrap(True)
        lbl_text.setStyleSheet("color: #f1f5f9; font-weight: 500;")
        v_p.addWidget(lbl_text)

        h_act = QHBoxLayout()
        lbl_mode_badge = QLabel(f"[{task.mode}]")
        lbl_mode_badge.setStyleSheet(
            "color: #38bdf8; font-size: 10px; font-weight: bold; background-color: #0f172a; "
            "padding: 1px 5px; border: 1px solid #1e293b; border-radius: 4px;"
        )
        btn_retry = QPushButton("↺ Retry")
        btn_retry.setEnabled(not self._running)
        btn_retry.setFixedHeight(22)
        btn_retry.clicked.connect(lambda _, t_id=task.id: self._retry_single_task(t_id))

        btn_del = QPushButton("✕ Xóa")
        btn_del.setEnabled(not self._running)
        btn_del.setFixedHeight(22)
        btn_del.clicked.connect(lambda _, t_id=task.id: self._delete_single_task(t_id))

        h_act.addWidget(lbl_mode_badge)
        h_act.addWidget(btn_retry)
        h_act.addWidget(btn_del)
        h_act.addStretch()
        v_p.addLayout(h_act)
        self.table_tasks.setCellWidget(row, 1, w_prompt)

        # Col 2: THAM CHIẾU (Multi-tag parsing) widget
        w_ref = self._create_multi_reference_widget(task.prompt, task)
        self.table_tasks.setCellWidget(row, 2, w_ref)

        # Col 3: KẾT QUẢ / PREVIEW widget
        w_res = self._create_result_preview_widget(task)
        self.table_tasks.setCellWidget(row, 3, w_res)

    def _create_multi_reference_widget(self, prompt_text: str, task: TaskItem = None) -> QWidget:
        """
        Extracts ALL @tags in prompt and direct task references. Renders thumbnail + name chip for EACH!
        """
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 6, 6, 6)
        h.setSpacing(8)

        # 1. Direct task references (e.g. image from previous TEXT -> IMAGE)
        has_direct_refs = False
        if task and hasattr(task, "references") and task.references:
            for ref_path in task.references:
                if os.path.exists(ref_path):
                    has_direct_refs = True
                    card_ref = QFrame()
                    card_ref.setStyleSheet("background-color: #1a1e2b; border: 1px solid #38bdf8; border-radius: 6px; padding: 2px;")
                    v_cr = QVBoxLayout(card_ref)
                    v_cr.setContentsMargins(4, 4, 4, 4)
                    v_cr.setSpacing(2)

                    lbl_cr_img = QLabel()
                    lbl_cr_img.setFixedSize(48, 48)
                    lbl_cr_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    pix = QPixmap(ref_path)
                    if not pix.isNull():
                        lbl_cr_img.setPixmap(pix.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    else:
                        lbl_cr_img.setText("IMG")

                    lbl_cr_tag = QLabel("📸 Ảnh gốc")
                    lbl_cr_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl_cr_tag.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 10px;")

                    v_cr.addWidget(lbl_cr_img, alignment=Qt.AlignmentFlag.AlignCenter)
                    v_cr.addWidget(lbl_cr_tag, alignment=Qt.AlignmentFlag.AlignCenter)
                    h.addWidget(card_ref)

        alias_dict = self.settings.get_alias_dict()
        matched_aliases, missing_tags = PromptParser.resolve_aliases(
            prompt_text, alias_dict, auto_attach_all_if_none=self.chk_auto_attach.isChecked()
        )

        if not matched_aliases and not missing_tags and not has_direct_refs:
            lbl_none = QLabel("Không có @alias")
            lbl_none.setStyleSheet("color: #64748b; font-style: italic;")
            h.addWidget(lbl_none)
            h.addStretch()
            return w

        # Render each matched alias with thumbnail and badge!
        for a in matched_aliases:
            card = QFrame()
            card.setStyleSheet("background-color: #1a1e2b; border: 1px solid #2e354a; border-radius: 6px; padding: 2px;")
            v_card = QVBoxLayout(card)
            v_card.setContentsMargins(4, 4, 4, 4)
            v_card.setSpacing(2)

            lbl_img = QLabel()
            lbl_img.setFixedSize(48, 48)
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if os.path.exists(a.file_path):
                pix = QPixmap(a.file_path)
                if not pix.isNull():
                    lbl_img.setPixmap(pix.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    lbl_img.setText("IMG")
            else:
                lbl_img.setText("N/A")

            lbl_tag = QLabel(a.tag)
            lbl_tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_tag.setStyleSheet("color: #c7d2fe; font-weight: bold; font-size: 10px;")

            v_card.addWidget(lbl_img, alignment=Qt.AlignmentFlag.AlignCenter)
            v_card.addWidget(lbl_tag, alignment=Qt.AlignmentFlag.AlignCenter)
            h.addWidget(card)

        # If any unknown tags were detected
        for tag in missing_tags:
            card_miss = QFrame()
            card_miss.setStyleSheet("background-color: #291a1a; border: 1px dashed #ef4444; border-radius: 6px; padding: 4px;")
            v_m = QVBoxLayout(card_miss)
            lbl_m = QLabel(f"⚠️ {tag}\n(Chưa gán ảnh)")
            lbl_m.setStyleSheet("color: #fca5a5; font-size: 10px;")
            v_m.addWidget(lbl_m)
            h.addWidget(card_miss)

        h.addStretch()
        return w

    def _create_result_preview_widget(self, task: TaskItem) -> QWidget:
        """
        Renders status pill, output filename, and thumbnail preview of result.
        """
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 6, 6, 6)
        h.setSpacing(8)

        v_info = QVBoxLayout()
        v_info.setSpacing(4)

        # Status badge
        lbl_status = QLabel("CHỜ KẾT QUẢ" if task.status == TaskStatus.WAITING.value else task.status)
        lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_status.setFixedWidth(90)
        lbl_status.setFixedHeight(22)
        if task.status == TaskStatus.OK.value or "OK" in task.status:
            lbl_status.setStyleSheet("background-color: #065f46; color: #34d399; border-radius: 4px; font-weight: bold; font-size: 11px;")
        elif task.status == TaskStatus.FAIL.value:
            lbl_status.setStyleSheet("background-color: #7f1d1d; color: #f87171; border-radius: 4px; font-weight: bold; font-size: 11px;")
        elif task.status == TaskStatus.PROCESSING.value:
            lbl_status.setStyleSheet("background-color: #78350f; color: #fbbf24; border-radius: 4px; font-weight: bold; font-size: 11px;")
        elif task.status in [TaskStatus.QUEUED.value, TaskStatus.WAITING.value]:
            lbl_status.setStyleSheet("background-color: #1e3a8a; color: #60a5fa; border-radius: 4px; font-weight: bold; font-size: 11px;")
        else:
            lbl_status.setStyleSheet("background-color: #374151; color: #9ca3af; border-radius: 4px; font-weight: bold; font-size: 11px;")
        v_info.addWidget(lbl_status)
        if task.status in [TaskStatus.PROCESSING.value, TaskStatus.WAITING.value] and task.progress_message:
            progress = QLabel(task.progress_message)
            progress.setWordWrap(True)
            progress.setStyleSheet("color: #fbbf24; font-size: 10px;")
            progress.setToolTip(task.progress_message)
            v_info.addWidget(progress)

        # Filename & Action
        if task.output_file:
            fname = os.path.basename(task.output_file)
            lbl_f = QLabel(fname)
            lbl_f.setStyleSheet("color: #94a3b8; font-size: 10px;")
            lbl_f.setToolTip(task.output_file)
            v_info.addWidget(lbl_f)

            # Nút tạo Video nhanh từ ảnh đã tạo (TEXT -> IMAGE => IMAGE -> VIDEO)
            is_image_output = any(task.output_file.lower().endswith(ext) for ext in [".webp", ".png", ".jpg", ".jpeg"])
            if is_image_output and os.path.exists(task.output_file):
                btn_create_vid = QPushButton("🎬 Tạo Video")
                btn_create_vid.setEnabled(not self._running)
                btn_create_vid.setToolTip("Dùng ngay ảnh này kèm prompt chuyển động để tạo Video")
                btn_create_vid.setStyleSheet("""
                    QPushButton {
                        background-color: #7c3aed;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 10px;
                        font-weight: bold;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        background-color: #6d28d9;
                    }
                """)
                btn_create_vid.clicked.connect(lambda _, t=task: self._open_image_to_video_dialog(t))
                v_info.addWidget(btn_create_vid)
        if task.error_message:
            lbl_err = QLabel(task.error_message[:40])
            lbl_err.setStyleSheet("color: #ef4444; font-size: 10px;")
            lbl_err.setToolTip(task.error_message)
            v_info.addWidget(lbl_err)

        v_info.addStretch()
        h.addLayout(v_info)

        # Thumbnail Preview of Generated Media
        lbl_thumb = QLabel()
        lbl_thumb.setFixedSize(54, 54)
        lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_thumb.setStyleSheet("border: 1px solid #2e354a; border-radius: 6px; background-color: #12141c;")

        if task.output_file and os.path.exists(task.output_file):
            pix = QPixmap(task.output_file)
            if not pix.isNull():
                lbl_thumb.setPixmap(pix.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                lbl_thumb.setText("🎬 VIDEO")
                lbl_thumb.setStyleSheet("border: 1px solid #10b981; border-radius: 6px; background-color: #064e3b; color: #34d399; font-weight: bold; font-size: 9px;")
            lbl_thumb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            lbl_thumb.setToolTip("Nhấp để mở file trong hệ điều hành")
            lbl_thumb.mousePressEvent = lambda e, p=task.output_file: open_in_explorer(p)
        else:
            lbl_thumb.setText("No File")
            lbl_thumb.setStyleSheet("border: 1px dashed #262c3e; border-radius: 6px; color: #475569; font-size: 10px;")

        h.addWidget(lbl_thumb)
        return w

    def _open_image_to_video_dialog(self, task: TaskItem):
        """Mở hộp thoại tạo video từ ảnh đã render."""
        if self._running:
            return
        try:
            validate_output(task.output_file, JobMode.TEXT_TO_IMAGE.value)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Ảnh không hợp lệ", str(exc))
            return
        from ui.dialogs.create_video_dialog import ImageToVideoDialog
        dlg = ImageToVideoDialog(
            image_path=task.output_file,
            initial_prompt=task.prompt,
            default_aspect=task.aspect_ratio or self.combo_aspect.currentText(),
            default_duration=self.spin_video_duration.value(),
            parent=self
        )
        if dlg.exec():
            res = dlg.result_data
            if res:
                new_task = TaskItem(
                    id=f"task_{uuid.uuid4().hex[:8]}",
                    prompt=res["prompt"],
                    mode=JobMode.REFERENCE_IMAGE_TO_VIDEO.value,
                    aspect_ratio=res["aspect_ratio"],
                    video_duration=res["video_duration"],
                    status=TaskStatus.READY.value,
                    created_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    references=[res["image_path"]]
                )
                self.settings.tasks.append(new_task)
                self.settings.save()
                self._load_tasks()
                log_event(f"Đã tạo task mới biến Ảnh thành Video: {new_task.prompt[:60]}...", "SUCCESS")
                QMessageBox.information(
                    self, "Thành công",
                    f"✓ Đã thêm Task tạo Video từ ảnh thành công vào hàng đợi!\n\n"
                    f"Prompt: {new_task.prompt[:75]}...\n"
                    f"Ảnh gốc: {os.path.basename(res['image_path'])}\n\n"
                    "Bấm 'CHẠY / LUÂN CHUYỂN' để bắt đầu render video!"
                )

    def _refresh_all_task_references(self):
        """Re-render reference column across all task rows."""
        for row in range(self.table_tasks.rowCount()):
            if row < len(self.settings.tasks):
                task = self.settings.tasks[row]
                w_ref = self._create_multi_reference_widget(task.prompt, task)
                self.table_tasks.setCellWidget(row, 2, w_ref)

    def _parse_and_feed_prompts(self):
        raw_text = self.txt_raw_prompts.toPlainText().strip()
        if not raw_text:
            QMessageBox.warning(self, "Thông báo", "Vui lòng nhập nội dung prompt!")
            return

        prompts = PromptParser.split_raw_prompt_list(raw_text)
        if not prompts:
            return

        for p in prompts:
            task = TaskItem(
                id=f"task_{uuid.uuid4().hex[:8]}",
                prompt=p,
                mode=self.combo_mode.currentText(),
                aspect_ratio=self.combo_aspect.currentText(),
                video_duration=self.spin_video_duration.value(),
                status=TaskStatus.READY.value,
                created_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            self.settings.tasks.append(task)

        self.settings.save()
        self._load_tasks()
        log_event(f"Đã phân tích và thêm {len(prompts)} prompt mới vào Hàng Đợi.", "SUCCESS")
        self.txt_raw_prompts.clear()

    def feed_external_prompts(self, prompts: List[str]):
        """Receives prompts from LLM Dialog and injects them."""
        for p in prompts:
            task = TaskItem(
                id=f"task_{uuid.uuid4().hex[:8]}",
                prompt=p,
                mode=self.combo_mode.currentText(),
                aspect_ratio=self.combo_aspect.currentText(),
                video_duration=self.spin_video_duration.value(),
                status=TaskStatus.READY.value,
                created_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            self.settings.tasks.append(task)
        self.settings.save()
        self._load_tasks()

    def _add_single_task_row(self):
        task = TaskItem(
            id=f"task_{uuid.uuid4().hex[:8]}",
            prompt="Prompt phân cảnh mới...",
            mode=self.combo_mode.currentText(),
            aspect_ratio=self.combo_aspect.currentText(),
            video_duration=self.spin_video_duration.value(),
            status=TaskStatus.READY.value,
            created_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.settings.tasks.append(task)
        self.settings.save()
        self._load_tasks()

    def _retry_single_task(self, task_id: str):
        if self._running:
            return
        for idx, t in enumerate(self.settings.tasks):
            if t.id == task_id:
                t.status = TaskStatus.READY.value
                t.error_message = ""
                t.output_file = ""
                t.generated_image_file = ""
                # Cập nhật theo tham số hiện tại trên thanh công cụ
                t.mode = self.combo_mode.currentText()
                t.aspect_ratio = self.combo_aspect.currentText()
                t.video_duration = self.spin_video_duration.value()
                self.settings.save()
                self._load_tasks()
                log_event(f"Đã đặt lại task #{idx+1} sang chế độ '{t.mode}' (READY).", "SUCCESS")
                self.task_retry_signal.emit(task_id)
                break

    def _delete_single_task(self, task_id: str):
        if self._running:
            return
        self.settings.tasks = [t for t in self.settings.tasks if t.id != task_id]
        self.settings.save()
        self._load_tasks()

    def _retry_all_fails(self):
        if self._running:
            return
        count = 0
        current_mode = self.combo_mode.currentText()
        current_aspect = self.combo_aspect.currentText()
        current_dur = self.spin_video_duration.value()
        for idx, t in enumerate(self.settings.tasks):
            if t.status == TaskStatus.FAIL.value or "FAIL" in t.status:
                t.status = TaskStatus.READY.value
                t.error_message = ""
                t.output_file = ""
                t.generated_image_file = ""
                t.mode = current_mode
                t.aspect_ratio = current_aspect
                t.video_duration = current_dur
                count += 1
        self.settings.save()
        self._load_tasks()
        if count > 0:
            log_event(f"Đã cập nhật {count} task lỗi sang chế độ '{current_mode}' và sẵn sàng chạy lại.", "SUCCESS")
        else:
            log_event("Không có task nào bị FAIL để retry.")

    def _rerun_all_tasks(self):
        if self._running:
            return
        current_mode = self.combo_mode.currentText()
        current_aspect = self.combo_aspect.currentText()
        current_dur = self.spin_video_duration.value()
        count = 0
        for t in self.settings.tasks:
            t.status = TaskStatus.READY.value
            t.error_message = ""
            t.output_file = ""
            t.generated_image_file = ""
            t.mode = current_mode
            t.aspect_ratio = current_aspect
            t.video_duration = current_dur
            count += 1
        self.settings.save()
        self._load_tasks()
        log_event(f"Đã làm mới toàn bộ {count} task sang chế độ '{current_mode}' (READY) sẵn sàng chạy lại.", "SUCCESS")

    def _clear_all_tasks(self):
        if self._running:
            return
        if not self.settings.tasks:
            return
        reply = QMessageBox.question(
            self, "Xác nhận", "Bạn có chắc muốn xóa tất cả tasks trong hàng đợi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings.tasks.clear()
            self.settings.save()
            self._load_tasks()
            log_event("Đã xóa sạch hàng đợi tasks.")

    def _open_output_folder(self):
        out_dir = self.settings.app_config.get("output_dir", "output")
        open_in_explorer(out_dir)

    def _on_param_changed(self):
        if self._running:
            return
        curr_mode = self.combo_mode.currentText()
        curr_aspect = self.combo_aspect.currentText()
        curr_dur = self.spin_video_duration.value()
        self.settings.app_config["default_mode"] = curr_mode
        self.settings.app_config["default_aspect_ratio"] = curr_aspect
        self.settings.app_config["default_timeout"] = self.spin_timeout.value()
        self.settings.app_config["default_video_duration"] = curr_dur
        self.settings.app_config["max_concurrent_tabs"] = self.spin_concurrency.value()

        # Đồng bộ chế độ mới cho tất cả các task chưa hoàn tất hoặc đang sẵn sàng
        updated = 0
        for t in self.settings.tasks:
            if t.status in [TaskStatus.READY.value, TaskStatus.QUEUED.value]:
                t.mode = curr_mode
                t.aspect_ratio = curr_aspect
                t.video_duration = curr_dur
                t.output_file = ""
                t.generated_image_file = ""
                t.error_message = ""
                updated += 1

        self.settings.save()
        if updated > 0:
            self._load_tasks()
            log_event(f"Đã tự động cập nhật {updated} task trong hàng đợi sang chế độ: {curr_mode} ({curr_aspect}).")

    def _update_task_row_ui(self, row_idx: int, task: TaskItem):
        if row_idx < self.table_tasks.rowCount():
            w_res = self._create_result_preview_widget(task)
            self.table_tasks.setCellWidget(row_idx, 3, w_res)

    def on_task_started(self, task_id: str, profile_name: str):
        for idx, t in enumerate(self.settings.tasks):
            if t.id == task_id:
                t.status = TaskStatus.PROCESSING.value
                t.profile_assigned = profile_name
                t.output_file = ""
                t.error_message = ""
                t.progress_message = "Đang chuẩn bị tác vụ"
                self._update_task_row_ui(idx, t)
                break

    def on_task_completed(self, task_id: str, profile_name: str, output_file: str):
        for idx, t in enumerate(self.settings.tasks):
            if t.id == task_id:
                try:
                    validate_output(output_file, t.mode, probe_video=False)
                except (ValueError, OSError) as exc:
                    t.status = TaskStatus.FAIL.value
                    t.output_file = ""
                    t.error_message = str(exc)
                else:
                    t.status = f"OK - [{profile_name}]"
                    t.output_file = output_file
                    t.error_message = ""
                self._update_task_row_ui(idx, t)
                break
        self.settings.save()

    def on_task_progress(self, task_id: str, message: str):
        for index, task in enumerate(self.settings.tasks):
            if task.id == task_id:
                task.progress_message = message
                self._update_task_row_ui(index, task)
                break

    def on_task_waiting(self, task_id: str, profile_name: str, message: str):
        for index, task in enumerate(self.settings.tasks):
            if task.id == task_id:
                task.status = TaskStatus.WAITING.value
                task.output_file = ""
                task.error_message = ""
                task.progress_message = message
                self._update_task_row_ui(index, task)
                break
        self.settings.save()

    def on_task_failed(self, task_id: str, profile_name: str, error_msg: str):
        for idx, t in enumerate(self.settings.tasks):
            if t.id == task_id:
                t.status = TaskStatus.FAIL.value
                t.error_message = error_msg
                t.output_file = ""
                self._update_task_row_ui(idx, t)
                break
        self.settings.save()
