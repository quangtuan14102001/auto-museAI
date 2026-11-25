"""Storyboard, clip review and export for persistent long-film projects."""
import math
import copy
import json
import hashlib
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QTextEdit, QSpinBox, QComboBox, QPushButton, QFileDialog,
    QMessageBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QApplication,
    QAbstractItemView, QInputDialog, QProgressBar, QToolButton, QMenu, QScrollArea,
)

from config.settings import SettingsManager
from core.film_project import FilmStore, plan_film, validate_continuity
from core.media_output import validate_output
from core.models import ProfileItem, JobMode
from core.prompt_parser import PromptParser
from core.film_genres import DEFAULT_GENRE, FILM_GENRES
from core.film_content import inspect_project, describe_issues
from utils.file_utils import open_in_explorer
from workers.film_worker import FilmWorker, FilmImportWorker, FilmExportWorker
from workers.film_script_worker import FilmScriptWorker
from workers.film_storyboard_worker import FilmStoryboardWorker, apply_storyboard
from workers.muse_storyboard_worker import MuseStoryboardWorker
from ui.dialogs.film_references import FilmReferencesPanel, edit_shot_dialog, compare_reference_dialog


class FilmDialog(QDialog):
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None, busy_check=None):
        super().__init__(parent)
        self.setWindowTitle("Phim dài · Kịch bản → nối cảnh → duyệt → xuất phim")
        self.setStyleSheet("""
            * { font-family: 'Segoe UI'; color: #e2e8f0; }
            QDialog { background: #0c1220; }
            QWidget#filmSetup, QWidget#filmReview, QWidget#filmExport { background: #111827; }
            QTabWidget::pane { border: 1px solid #28364d; background: #111827; }
            QTabBar::tab { background: #172238; color: #94a3b8; padding: 9px 16px; }
            QTabBar::tab:selected { color: #38bdf8; background: #111827; border-bottom: 2px solid #38bdf8; }
            QLineEdit, QTextEdit, QSpinBox, QComboBox { background: #0c1424; border: 1px solid #334155; border-radius: 4px; padding: 5px; }
            QPushButton { background: #1e293b; border: 1px solid #3b4b66; border-radius: 5px; padding: 7px 12px; }
            QPushButton:hover { background: #263b56; }
            QPushButton:disabled { color: #64748b; border-color: #273449; }
            QToolButton { background: #1e293b; border: 1px solid #3b4b66; border-radius: 5px; padding: 7px 12px; }
            QMenu { background: #172238; color: #e2e8f0; }
            QMenu::item:selected { background: #263b56; }
            QProgressBar { background: #0c1424; border: 1px solid #334155; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background: #047857; }
            QTableWidget { background: #0f172a; gridline-color: #28364d; }
            QHeaderView::section { background: #172238; color: #94a3b8; padding: 6px; border: 0; }
        """)
        self.resize(1120, 850)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(1120, available.width() - 60), min(850, max(620, available.height() - 80)))
        self.settings = SettingsManager.get_instance()
        self.busy_check = busy_check or (lambda: False)
        self.store = None
        self.worker = None
        self.script_worker = None
        self.closing = False
        self.seed_source = ""
        self.anchor_sources = []
        self.reference_draft = []
        self.storyboard_draft = None
        self.storyboard_partial = None
        self.generated_genre = ""
        self.script_genre = ""
        self._init_ui()

    @property
    def working(self):
        return self.worker is not None and self.worker.isRunning()

    def _button(self, text, slot, layout):
        button = QPushButton(text)
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    def _init_ui(self):
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.new_button = self._button("Dự án mới", self._new, toolbar)
        self.open_button = self._button("Mở dự án", self._open, toolbar)
        self.folder_button = self._button("Thư mục dự án", self._folder, toolbar)
        self.project_label = QLabel("Chưa có dự án")
        self.project_label.setWordWrap(True)
        self.project_label.setMaximumWidth(600)
        toolbar.addWidget(self.project_label, 1)
        layout.addLayout(toolbar)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        setup = QWidget()
        setup.setObjectName("filmSetup")
        setup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        form = QFormLayout(setup)
        self.title = QLineEdit("Phim mới")
        form.addRow("Tên phim:", self.title)
        self.genre = QComboBox()
        self.genre.addItems(FILM_GENRES)
        self.genre.setEditable(True)
        self.genre.lineEdit().setMaxLength(120)
        self.genre.setToolTip("Mỗi thể loại có hướng dẫn riêng về cấu trúc, nhịp cảnh, hình ảnh và âm thanh. Có thể nhập kết hợp nhiều thể loại. Phong cách/nhận dạng cụ thể khai báo ở phần khóa nhân vật/phong cách.")
        form.addRow("Thể loại phim:", self.genre)
        self.skills_hint = QLabel("Đã bật hướng dẫn viết kịch bản, đạo diễn từng cảnh và giữ nhân vật/bối cảnh nhất quán.")
        self.skills_hint.setWordWrap(True)
        form.addRow('', self.skills_hint)
        self.idea = QTextEdit()
        self.idea.setMaximumHeight(70)
        self.idea.setPlaceholderText("Ví dụ: Một chú robot đi tìm khu vườn cuối cùng trên Trái Đất, kết thúc ấm áp.")
        form.addRow("Ý tưởng / prompt phim:", self.idea)
        self.script_source = QComboBox()
        self.script_source.addItem("Muse · dùng tài khoản đã đăng nhập", "muse")
        self.script_source.addItem("AI API · theo Cài đặt (Gemini / OpenAI / Claude)", "api")
        form.addRow("AI viết kịch bản:", self.script_source)
        self.generate_script = QPushButton("Tạo kịch bản từ ý tưởng bằng AI")
        self.generate_script.clicked.connect(self._generate_script)
        form.addRow(self.generate_script)
        timing = QHBoxLayout()
        self.minutes, self.seconds = QSpinBox(), QSpinBox()
        self.minutes.setRange(0, 120)
        self.minutes.setValue(10)
        self.minutes.setSuffix(" phút")
        self.seconds.setRange(0, 59)
        self.seconds.setSuffix(" giây")
        self.clip_length = QComboBox()
        self.clip_length.addItems(["10", "5"])
        self.aspect = QComboBox()
        self.aspect.addItems(["16:9", "9:16", "1:1"])
        for control in [self.minutes, self.seconds, QLabel("Mỗi clip:"), self.clip_length, QLabel("Khung hình:"), self.aspect]:
            timing.addWidget(control)
        form.addRow("Thời lượng phim:", timing)
        self.profile = QComboBox()
        for profile in self.settings.profiles:
            if profile.enabled:
                self.profile.addItem(profile.name, profile.id)
        form.addRow("Tài khoản tạo phim:", self.profile)
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(105)
        self.notes.setPlaceholderText("Quy tắc xuyên suốt: nhân vật, quần áo, màu sắc, ánh sáng, hướng đi và phong cách phim...")
        form.addRow("Khóa nhân vật/phong cách:", self.notes)
        refs = QHBoxLayout()
        self.seed_button = self._button("Chọn ảnh mở đầu", self._choose_seed, refs)
        self.anchors_button = self._button("Ảnh khóa nhận dạng", self._choose_anchors, refs)
        self.refs_label = QLabel("Chưa chọn ảnh. App sẽ tạo ảnh mở đầu cho mỗi cảnh lớn.")
        self.refs_label.setWordWrap(True)
        form.addRow(refs)
        form.addRow(self.refs_label)
        self.script = QTextEdit()
        self.script.setPlaceholderText(
            "Nhập các cảnh lớn, cách nhau một dòng trống.\n\n"
            "Ví dụ: Báo tuyết thức dậy trên mỏm đá, nhìn về thung lũng.\n\n"
            "Báo tuyết bước dọc sườn núi, camera theo từ bên trái.\n\n"
            "Mỗi cảnh lớn được chia thành các clip tiếp nối. 10 phút / clip 10 giây = 60 clip."
        )
        form.addRow("Kịch bản / danh sách cảnh:", self.script)
        self.estimate = QLabel()
        form.addRow(self.estimate)
        self.plan_button = QPushButton("Tạo kế hoạch và lưu dự án")
        self.plan_button.clicked.connect(self._create)
        form.addRow(self.plan_button)
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setWidget(setup)
        self.tabs.addTab(setup_scroll, "1 · Kịch bản & tham chiếu")

        review = QWidget()
        review.setObjectName("filmReview")
        review.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        review_layout = QVBoxLayout(review)
        self.progress_text = QLabel("Chưa có dự án")
        review_layout.addWidget(self.progress_text)
        self.progress = QProgressBar()
        review_layout.addWidget(self.progress)
        self.review_required = QCheckBox("Tôi muốn xem và duyệt từng clip trước khi chạy tiếp")
        self.review_required.setChecked(False)
        self.review_required.toggled.connect(self._review_mode)
        review_layout.addWidget(self.review_required)
        self.visual_review_enabled = QCheckBox("Gemini đối chiếu nhân vật/bối cảnh (dùng API, 5 khung mẫu mỗi clip)")
        self.visual_review_enabled.setToolTip("Tùy chọn dùng Gemini API riêng để so ảnh chuẩn và các khung mẫu, không kiểm tra toàn bộ chuyển động/âm thanh. Nếu thấy lỗi hoặc không kiểm tra được, app dừng để bạn duyệt; không tự tạo lại tốn lượt.")
        self.visual_review_enabled.toggled.connect(self._visual_review_mode)
        review_layout.addWidget(self.visual_review_enabled)
        hint = QLabel("Bấm nút màu xanh để tiếp tục từ clip chưa xong. Clip đã hoàn thành được giữ lại.")
        hint.setWordWrap(True)
        review_layout.addWidget(hint)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "Cảnh", "Cách nối", "Nội dung", "Dùng (s)", "Trạng thái"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setWordWrap(False)
        for column, width in [(0, 45), (1, 55), (2, 100), (4, 85), (5, 200)]:
            self.table.setColumnWidth(column, width)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.currentCellChanged.connect(lambda *_: self._show_frames())
        review_layout.addWidget(self.table, 1)
        frame_layout = QHBoxLayout()
        self.frame_labels = []
        for text in ["Khung cuối clip trước", "Khung đầu clip đang chọn", "Khung cuối clip đang chọn"]:
            column = QVBoxLayout()
            column.addWidget(QLabel(text))
            label = QLabel("Chưa có khung hình")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumSize(220, 125)
            label.setStyleSheet("background: #111827; color: #94a3b8; border: 1px solid #374151;")
            column.addWidget(label)
            frame_layout.addLayout(column)
            self.frame_labels.append(label)
        review_layout.addLayout(frame_layout)
        actions = QHBoxLayout()
        actions_secondary = QHBoxLayout()
        self.next_step = QLabel()
        self.next_step.setWordWrap(True)
        review_layout.addWidget(self.next_step)
        self.start_button = self._button("Bắt đầu làm phim", self._continue_film, actions)
        self.start_button.setStyleSheet("QPushButton { background: #047857; color: white; font-weight: bold; padding: 11px; } QPushButton:disabled { background: #263449; color: #94a3b8; }")
        self.approve_button = self._button("Duyệt & tiếp tục", self._approve, actions)
        self.import_button = self._button("Nhập clip có sẵn", self._import_clip, actions)
        self.edit_button = self._button("Sửa cảnh", self._edit_shot, actions_secondary)
        self.retry_button = self._button("Tạo lại clip", self._retry, actions_secondary)
        self.clip_button = self._button("Mở clip", self._open_clip, actions_secondary)
        self.compare_button = self._button("Đối chiếu ảnh chuẩn", lambda: compare_reference_dialog(self), actions_secondary)
        for button in [self.approve_button, self.import_button, self.edit_button, self.retry_button]:
            button.hide()
        # Keep less common operations accessible without six competing buttons.
        self.more_button = QToolButton()
        self.more_button.setText("Tùy chọn clip ▾")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.more_button)
        for text, slot in [("Sửa nội dung clip", self._edit_shot),
                           ("Tạo lại clip đang chọn", self._retry),
                           ("Nhập video có sẵn", self._import_clip)]:
            menu.addAction(text, slot)
        self.more_button.setMenu(menu)
        actions_secondary.addWidget(self.more_button)
        review_layout.addLayout(actions)
        review_layout.addLayout(actions_secondary)
        self.tabs.addTab(review, "2 · Tạo & duyệt clip")

        export = QWidget()
        export.setObjectName("filmExport")
        export.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        export_form = QFormLayout(export)
        self.music, self.narration = QLineEdit(), QLineEdit()
        self.music.setPlaceholderText("Tùy chọn; nhạc được lặp vừa đủ phim, âm lượng nền 15%")
        self.narration.setPlaceholderText("Tùy chọn; lời thoại chạy từ đầu phim, không bị lặp")
        for name, control in [("Nhạc nền xuyên suốt:", self.music), ("Lời thoại/lồng tiếng:", self.narration)]:
            row = QHBoxLayout()
            row.addWidget(control)
            button = QPushButton("Chọn file")
            button.clicked.connect(lambda _, field=control: self._audio(field))
            row.addWidget(button)
            export_form.addRow(name, row)
        self.keep_audio = QCheckBox("Giữ âm thanh từ các clip")
        self.keep_audio.setChecked(True)
        export_form.addRow(self.keep_audio)
        self.export_note = QLabel("Xuất MP4 H.264, 24 FPS; các clip được chuẩn hóa trước khi nối. Phim chỉ xuất khi tất cả clip đã được chấp nhận.")
        self.export_note.setWordWrap(True)
        export_form.addRow(self.export_note)
        self.export_button = QPushButton("Ghép và xuất phim")
        self.export_button.clicked.connect(self._export)
        export_form.addRow(self.export_button)
        self.movie_button = QPushButton("Mở phim đã xuất")
        self.movie_button.clicked.connect(self._open_movie)
        export_form.addRow(self.movie_button)
        self.tabs.addTab(export, "3 · Âm thanh & xuất phim")
        self.references_panel = FilmReferencesPanel(self)
        self.references_panel.setObjectName("filmReview")
        self.tabs.insertTab(1, self.references_panel, "2 · Nhân vật & bối cảnh")
        self.tabs.setTabText(2, "3 · Phân cảnh & tạo phim")
        self.tabs.setTabText(3, "4 · Âm thanh & xuất phim")
        bottom = QHBoxLayout()
        self.status = QLabel("Lập kế hoạch trước, sau đó tạo và duyệt từng clip.")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.stop_button = self._button("Dừng", self._stop, bottom)
        layout.addLayout(bottom)
        for signal in [self.minutes.valueChanged, self.seconds.valueChanged, self.clip_length.currentTextChanged, self.script.textChanged]:
            signal.connect(self._estimate)
        self._estimate()
        self._set_busy(False)

    def _estimate(self):
        seconds = self.minutes.value() * 60 + self.seconds.value()
        count = math.ceil(seconds / int(self.clip_length.currentText()))
        blocks = len([part for part in self.script.toPlainText().split("\n\n") if part.strip()])
        self.estimate.setText(f"Dự kiến {count} clip / {seconds} giây · {blocks} cảnh lớn. Cảnh lớn có thể cần thêm một lượt tạo ảnh mở đầu.")

    def _choose_seed(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ảnh mở đầu phim", "", "Ảnh (*.png *.jpg *.jpeg *.webp)")
        if path:
            self.seed_source = path
            self._refs_summary()

    def _choose_anchors(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Ảnh nhân vật / trang phục / phong cách", "", "Ảnh (*.png *.jpg *.jpeg *.webp)")
        if paths:
            self.anchor_sources = paths
            self._refs_summary()

    def _refs_summary(self):
        self.refs_label.setText(f"Ảnh mở đầu: {Path(self.seed_source).name if self.seed_source else 'tạo bằng Muse'} · {len(self.anchor_sources)} ảnh khóa nhận dạng")

    def _new(self):
        if self.working or (self.script_worker and self.script_worker.isRunning()):
            return
        self.store = None
        self.reference_draft, self.storyboard_draft = [], None
        self.storyboard_partial = None
        self.generate_script.setText("Tạo kịch bản từ ý tưởng bằng AI")
        self.references_panel.refresh()
        self.table.setRowCount(0)
        self.title.setReadOnly(False)
        self.notes.setReadOnly(False)
        self.script.setReadOnly(False)
        self.title.setText("Phim mới")
        self.genre.setCurrentText(DEFAULT_GENRE)
        self.generated_genre, self.script_genre = "", ""
        self.idea.clear()
        self.notes.clear()
        self.script.clear()
        self.review_required.setChecked(False)
        self.visual_review_enabled.setChecked(False)
        self.progress.setValue(0)
        self.progress_text.setText("Chưa có dự án")
        self.next_step.clear()
        self.seed_source, self.anchor_sources = "", []
        self.music.clear()
        self.narration.clear()
        self._refs_summary()
        self.project_label.setText("Chưa có dự án")
        self._set_busy(False)
        self.tabs.setCurrentIndex(0)

    def _generate_script(self):
        if self.store or self.working or (self.script_worker and self.script_worker.isRunning()):
            return
        idea = self.idea.toPlainText().strip()
        seconds = self.minutes.value() * 60 + self.seconds.value()
        if not idea or seconds <= 0:
            self.status.setText("Nhập ý tưởng phim và chọn thời lượng trước khi tạo kịch bản.")
            return
        config = self.settings.llm_config
        use_muse = self.script_source.currentData() == 'muse'
        provider = 'muse' if use_muse else config.get("provider", "gemini")
        key = config.get(f"{provider}_api_key", "")
        if not use_muse and (not key or provider not in ("gemini", "openai", "anthropic")):
            self.status.setText("Cần cấu hình AI: vào Cài đặt → AI/LLM, chọn nhà cung cấp và nhập API key. Bạn vẫn có thể nhập kịch bản thủ công.")
            return
        profile = None
        if use_muse:
            if self.busy_check():
                self.status.setText("Tài khoản đang được dùng. Dừng hàng đợi hoặc đóng cửa sổ đăng nhập trước khi viết kịch bản bằng Muse.")
                return
            profile = next((p for p in self.settings.profiles if p.id == self.profile.currentData()), None)
            if not profile:
                self.status.setText("Chọn tài khoản Muse đã đăng nhập ở mục Tài khoản tạo phim.")
                return
        clip_seconds = int(self.clip_length.currentText())
        count = math.ceil(seconds / clip_seconds)
        reference_notes = self.notes.toPlainText().strip()
        if self.reference_draft:
            reference_notes += "\nGiữ nguyên ID và mô tả các tham chiếu có sẵn: " + json.dumps(
                [{"id": ref.id, "kind": ref.kind, "name": ref.name, "description": ref.description}
                 for ref in self.reference_draft], ensure_ascii=False)
        selected_genre = self.genre.currentText().strip()
        signature_parts = [idea, seconds, clip_seconds, reference_notes]
        if selected_genre and selected_genre != DEFAULT_GENRE:
            signature_parts.append(selected_genre)
        if use_muse:
            signature_parts.append(['muse', profile.id])
        signature = json.dumps(signature_parts, ensure_ascii=False)
        draft_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:24]
        checkpoint = Path(self.settings.app_config.get("output_dir", "output")) / "film_drafts" / (draft_id + ".json")
        existing = None
        if checkpoint.exists():
            try:
                draft = json.loads(checkpoint.read_text(encoding="utf-8"))
                expected_text = "\n\n".join(row["action"].strip() for row in draft["shots"])
                current_text = self.script.toPlainText().strip()
                if 0 < len(draft["shots"]) < count and (not current_text or current_text == expected_text):
                    existing = draft
            except (ValueError, KeyError, TypeError, AttributeError, OSError):
                pass
        if use_muse:
            self.script_worker = MuseStoryboardWorker(idea, seconds, clip_seconds, reference_notes,
                ProfileItem.from_dict(profile.to_dict()), self.settings.muse_selectors,
                self.settings.app_config.get('proxy', ''), existing=existing, checkpoint_path=checkpoint, genre=selected_genre)
        else:
            self.script_worker = FilmStoryboardWorker(idea, seconds, clip_seconds, reference_notes,
                                              provider, key, config.get(f"{provider}_model", ""),
                                              existing=existing, checkpoint_path=checkpoint, genre=selected_genre)
        self.script_genre = selected_genre
        self.script_worker.storyboard_ready.connect(self._storyboard_received)
        self.script_worker.partial_ready.connect(self._partial_storyboard_received)
        self.script_worker.progress.connect(self.status.setText)
        self.script_worker.error_signal.connect(self.status.setText)
        self.script_worker.finished.connect(self._script_finished)
        self._set_busy(True)
        self.busy_changed.emit(True)
        self.stop_button.setEnabled(use_muse)
        self.status.setText(f"AI đang viết {count} clip riêng, nhân vật, bối cảnh và trạng thái nối cảnh…")
        self.script_worker.start()

    def _script_finished(self):
        self._set_busy(False)
        self.busy_changed.emit(False)

    def _partial_storyboard_received(self, data):
        self.storyboard_partial = data
        self.storyboard_draft = None
        self.script.setPlainText("\n\n".join(row["action"].strip() for row in data["shots"]))
        missing = math.ceil((self.minutes.value()*60+self.seconds.value()) / int(self.clip_length.currentText())) - len(data["shots"])
        self.generate_script.setText(f"Viết tiếp {missing} clip còn thiếu")

    def _storyboard_received(self, data):
        try:
            project = apply_storyboard(data, self.title.text(), self.minutes.value() * 60 + self.seconds.value(),
                                       int(self.clip_length.currentText()), self.aspect.currentText(),
                                       self.profile.currentData() or "", self.notes.toPlainText())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        old = {ref.id: ref for ref in self.reference_draft}
        project.references = [old.get(ref.id, ref) if old.get(ref.id, ref).kind == ref.kind else ref for ref in project.references]
        project.references.extend(ref for ref in self.reference_draft if ref.id not in {r.id for r in project.references})
        self.reference_draft = project.references
        self.generated_genre = self.script_genre or self.genre.currentText().strip()
        self.storyboard_partial = None
        self.generate_script.setText("Tạo kịch bản từ ý tưởng bằng AI")
        self.storyboard_draft = data
        self._script_received([shot.prompt for shot in project.shots])
        self.references_panel.refresh()
        self.status.setText(f"Đã lập {len(project.shots)} clip riêng. Xem Nhân vật & bối cảnh để chọn ảnh chuẩn, hoặc để Muse tự tạo khi chạy phim.")

    def _script_received(self, scenes):
        self.script.setPlainText("\n\n".join(scenes))
        idea = self.idea.toPlainText().strip()
        if idea and self.title.text().strip() in ("", "Phim mới"):
            self.title.setText(idea.splitlines()[0][:100])
        self.status.setText(f"Đã tạo {len(scenes)} cảnh. Bạn có thể chỉnh nội dung bên dưới rồi bấm Tạo kế hoạch và lưu dự án.")

    def _create(self):
        try:
            paragraphs = [part.strip() for part in self.script.toPlainText().split("\n\n") if part.strip()]
            timing = (self.minutes.value() * 60 + self.seconds.value(), int(self.clip_length.currentText()))
            if self.storyboard_draft:
                if self.genre.currentText().strip() != self.generated_genre:
                    raise ValueError("Thể loại đã thay đổi. Bấm tạo lại kịch bản để áp dụng thể loại mới trước khi lưu dự án.")
                data = copy.deepcopy(self.storyboard_draft)
                if len(data["shots"]) != len(paragraphs):
                    raise ValueError("Số clip đã thay đổi. Tạo lại storyboard để phân bổ tham chiếu và trạng thái đúng.")
                for row, action in zip(data["shots"], paragraphs):
                    row["action"] = action
                project = apply_storyboard(data, self.title.text(), *timing, self.aspect.currentText(),
                                           self.profile.currentData() or "", self.notes.toPlainText())
            else:
                required = math.ceil(timing[0] / timing[1])
                if len(paragraphs) < required:
                    raise ValueError(f"Cần {required} hành động riêng cho {required} clip, hiện có {len(paragraphs)}. Bấm Tạo kịch bản bằng AI để phân cảnh chi tiết; app không lặp prompt cho đủ thời lượng.")
                project = plan_film(self.title.text(), paragraphs, *timing, self.aspect.currentText(),
                                    self.profile.currentData() or "", self.notes.toPlainText())
            project.references = copy.deepcopy(self.reference_draft)
            selected_genre = self.genre.currentText().strip()
            project.genre = "" if selected_genre == DEFAULT_GENRE else selected_genre
            validate_continuity(project)
            project.review_required = self.review_required.isChecked()
            project.visual_review_enabled = self.visual_review_enabled.isChecked()
            directory = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu thư mục phim")
            if not directory:
                return
            root = Path(directory) / ("film_" + project.id[:12])
            store = FilmStore(root / "project.film.json", project)
            for path in [self.seed_source, *self.anchor_sources]:
                if path:
                    validate_output(path, JobMode.TEXT_TO_IMAGE.value)
            if self.seed_source:
                project.seed_image = store.snapshot(self.seed_source)
            project.anchor_images = [store.snapshot(path) for path in self.anchor_sources]
            for ref in project.references:
                ref.images = [store.snapshot(path, "canonical") for path in ref.images]
                ref.image_hashes = {path: store.digest(store.asset(path)) for path in ref.images}
            store.save()
            self.store = store
            self._refresh()
            self.tabs.setCurrentIndex(2)
        except Exception as exc:
            QMessageBox.warning(self, "Chưa tạo được dự án", str(exc))

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Mở dự án phim", "", "Dự án phim (*.film.json)")
        if path:
            try:
                self.load_project(path)
            except Exception as exc:
                QMessageBox.warning(self, "Không mở được dự án", str(exc))

    def load_project(self, path):
        if self.working:
            raise ValueError("Dừng tác vụ hiện tại trước khi mở dự án khác.")
        self.store = FilmStore.load(path)
        self.storyboard_draft = None
        self.music.setText(self.store.asset(self.store.project.music_file) if self.store.project.music_file else "")
        self.narration.setText(self.store.asset(self.store.project.narration_file) if self.store.project.narration_file else "")
        self.keep_audio.setChecked(self.store.project.keep_clip_audio)
        self._refresh()
        self.tabs.setCurrentIndex(2)
        self.status.setText("Đã mở dự án. Chọn clip để xem và duyệt; clip đã tạo được giữ lại khi tiếp tục.")

    def _refresh(self):
        if not self.store:
            return
        project = self.store.project
        self.references_panel.refresh()
        completed = [shot for shot in project.shots if shot.status == "APPROVED"]
        seconds = sum(shot.timeline_seconds for shot in completed)
        self.progress.setRange(0, len(project.shots))
        self.progress.setValue(len(completed))
        self.progress_text.setText(
            f"Đã xong {len(completed)}/{len(project.shots)} clip · "
            f"{int(seconds)//60:02d}:{int(seconds)%60:02d} / {project.target_seconds//60:02d}:{project.target_seconds%60:02d}")
        pending = next(((i, shot) for i, shot in enumerate(project.shots) if shot.status != "APPROVED"), None)
        if pending:
            i, next_shot = pending
            self.start_button.setText(f"Duyệt clip {i + 1} và tiếp tục" if next_shot.status == "REVIEW" else f"Tiếp tục làm phim · clip {i + 1}")
            self.next_step.setText(f"Bước tiếp theo: clip {i + 1}. " +
                (next_shot.error if next_shot.error else "App sẽ chạy Muse ẩn và tiếp tục từ đây."))
        else:
            self.start_button.setText("Tiếp tục → Xuất phim")
            self.next_step.setText("Các clip đã hoàn thành. Chuyển sang bước âm thanh và xuất phim.")
        self.project_label.setText(f"{project.title} · {project.target_seconds // 60:02d}:{project.target_seconds % 60:02d} · {len(project.shots)} clip")
        self.project_label.setToolTip(str(self.store.manifest))
        self.title.setText(project.title)
        self.genre.setCurrentText(project.genre or DEFAULT_GENRE)
        self.title.setReadOnly(True)
        self.notes.setPlainText(project.continuity_notes)
        self.notes.setReadOnly(True)
        self.script.setReadOnly(True)
        sequences = {}
        for shot in project.shots:
            sequences.setdefault(shot.sequence, shot.prompt)
        self.script.setPlainText("\n\n".join(sequences.values()))
        self.minutes.setValue(project.target_seconds // 60)
        self.seconds.setValue(project.target_seconds % 60)
        self.clip_length.setCurrentText(str(project.clip_seconds))
        self.aspect.setCurrentText(project.aspect)
        index = self.profile.findData(project.profile_id)
        if index >= 0:
            self.profile.setCurrentIndex(index)
        self.refs_label.setText(f"Ảnh mở đầu: {'có' if project.seed_image else 'tạo bằng Muse'} · {len(project.anchor_images)} ảnh khóa nhận dạng · tài sản đã sao chép vào dự án")
        self.review_required.blockSignals(True)
        self.review_required.setChecked(project.review_required)
        self.review_required.blockSignals(False)
        self.visual_review_enabled.blockSignals(True)
        self.visual_review_enabled.setChecked(project.visual_review_enabled)
        self.visual_review_enabled.blockSignals(False)
        selected = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(len(project.shots))
        names = {"PENDING": "Chưa tạo", "GENERATING": "Đang tạo", "WAITING": "Cần kiểm tra tác vụ cũ",
                 "REVIEW": "Chờ duyệt", "APPROVED": "Đã chấp nhận", "FAILED": "Cần xử lý"}
        for row, shot in enumerate(project.shots):
            label = names.get(shot.status, shot.status)
            if shot.approved_by == "automatic":
                label += " (tự động)"
            values = [row + 1, shot.sequence, "Tiếp nối" if shot.continuation else "Cảnh mới", shot.prompt,
                      f"{shot.timeline_seconds:g}", label]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(shot.error if column == 5 else str(value))
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        if selected < 0:
            selected = next((i for i, shot in enumerate(project.shots) if shot.status != "APPROVED"), 0)
        self.table.selectRow(min(selected, len(project.shots) - 1))
        self._show_frames()
        self._set_busy(self.working)

    def _selection(self):
        index = self.table.currentRow()
        return (index, self.store.project.shots[index]) if self.store and index >= 0 else (-1, None)

    def _show_frames(self):
        index, shot = self._selection()
        if not shot:
            return
        previous = self.store.project.shots[index - 1].last_frame if shot.continuation and index > 0 else ""
        for label, relative in zip(self.frame_labels, [previous, shot.first_frame, shot.last_frame]):
            pix = QPixmap(self.store.asset(relative)) if relative else QPixmap()
            if pix.isNull():
                label.clear()
                label.setText("Chưa có khung hình" if relative else
                    ("Đây là clip mở đầu\nKhông có clip trước" if label is self.frame_labels[0] and not shot.continuation else "Clip này chưa tạo xong"))
            else:
                label.setPixmap(pix.scaled(220, 124, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            label.setToolTip(self.store.asset(relative) if relative else "")
            label.setCursor(Qt.CursorShape.PointingHandCursor if relative else Qt.CursorShape.ArrowCursor)
            label.mousePressEvent = lambda _, asset=relative: QDesktopServices.openUrl(QUrl.fromLocalFile(self.store.asset(asset))) if asset else None
        if shot.error:
            self.status.setText(shot.error)

    def _set_busy(self, busy):
        has_project = self.store is not None
        for button in self.findChildren(QPushButton):
            button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.new_button.setEnabled(not busy)
        self.plan_button.setEnabled(not busy and not has_project)
        self.generate_script.setEnabled(not busy and not has_project)
        self.idea.setReadOnly(busy or has_project)
        self.script.setReadOnly(busy or has_project)
        self.notes.setReadOnly(busy or has_project)
        self.title.setReadOnly(busy or has_project)
        self.genre.setEnabled(not busy and not has_project)
        self.script_source.setEnabled(not busy and not has_project)
        self.seed_button.setEnabled(not busy and not has_project)
        self.anchors_button.setEnabled(not busy and not has_project)
        self.start_button.setEnabled(not busy and has_project)
        if busy:
            self.start_button.setText("Đang làm phim… xem thông báo bên dưới")
        self.approve_button.setEnabled(not busy and has_project)
        self.import_button.setEnabled(not busy and has_project)
        self.edit_button.setEnabled(not busy and has_project)
        self.retry_button.setEnabled(not busy and has_project)
        self.clip_button.setEnabled(not busy and has_project)
        self.compare_button.setEnabled(not busy and has_project)
        self.folder_button.setEnabled(has_project)
        self.export_button.setEnabled(not busy and has_project and self.store.project.ready_to_export)
        self.movie_button.setEnabled(has_project and bool(self.store.project.export_file))
        for widget in [self.minutes, self.seconds, self.clip_length, self.aspect]:
            widget.setEnabled(not busy and not has_project)
        self.profile.setEnabled(not busy)
        self.review_required.setEnabled(not busy and has_project)
        self.visual_review_enabled.setEnabled(not busy and has_project)
        self.references_panel.setEnabled(not busy)
        self.more_button.setEnabled(not busy and has_project)
        self.music.setEnabled(not busy)
        self.narration.setEnabled(not busy)
        self.keep_audio.setEnabled(not busy)

    def _launch(self, worker):
        if self.working:
            return
        self.worker = worker
        worker.changed.connect(self._refresh)
        worker.message.connect(self.status.setText)
        worker.failed.connect(lambda text: self.status.setText(text))
        worker.finished.connect(self._finished)
        self._set_busy(True)
        self.busy_changed.emit(True)
        worker.start()

    def _finished(self):
        self.busy_changed.emit(False)
        self._refresh()
        if self.store and self.store.project.state in ("WAITING", "FAILED", "ERROR") and not self.closing:
            index = next((i for i, shot in enumerate(self.store.project.shots)
                          if shot.status in ("WAITING", "FAILED") and shot.error), -1)
            if index >= 0:
                shot = self.store.project.shots[index]
                self.table.selectRow(index)
                self.status.setText(f"Clip {index + 1}: {shot.error}")
                QMessageBox.warning(self, f"Clip {index + 1} cần xử lý",
                                    shot.error + "\n\nVào Tùy chọn clip → Sửa cảnh để sửa hành động và trạng thái đầu/cuối. "
                                    "Sau đó chọn Tạo lại clip khi muốn gửi yêu cầu mới.")
        if self.store and self.store.project.state == "REVIEW":
            index = next((i for i, shot in enumerate(self.store.project.shots) if shot.status == "REVIEW"), -1)
            if index >= 0:
                self.table.selectRow(index)
            self.status.setText("Clip đã sẵn sàng. Xem clip và đối chiếu khung hình, rồi Duyệt & tiếp tục.")
        if self.closing:
            self.closing = False
            self.close()

    def _start(self):
        if not self.store or self.working:
            return
        try:
            validate_continuity(self.store.project)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        issues = inspect_project(self.store.project)
        if issues:
            index = next((item.shot_index for item in issues if item.shot_index is not None), None)
            if index is not None:
                self.table.selectRow(index)
            self.status.setText("Chưa gửi Muse: cần chỉnh mô tả. Xem các mục trong thông báo.")
            QMessageBox.warning(self, "Rà nội dung trước khi tạo phim", describe_issues(issues))
            return
        if self.store.project.visual_review_enabled and not self.settings.llm_config.get("gemini_api_key"):
            self.status.setText("Cần API key Gemini trong Cài đặt để bật đối chiếu hình ảnh.")
            return
        if self.busy_check():
            QMessageBox.information(self, "Tài khoản đang được sử dụng", "Dừng hàng đợi thường hoặc đóng cửa sổ đăng nhập trước khi tạo phim.")
            return
        profile = next((p for p in self.settings.profiles if p.id == self.profile.currentData()), None)
        if not profile:
            QMessageBox.warning(self, "Chưa chọn tài khoản", "Chọn một tài khoản đã đăng nhập để tạo clip.")
            return
        self.store.project.profile_id = profile.id
        self.store.save()
        self._launch(FilmWorker(self.store, ProfileItem.from_dict(profile.to_dict()), self.settings.muse_selectors,
                                self.settings.app_config.get("proxy", ""), self.settings.llm_config))

    def _continue_film(self):
        if not self.store or self.working:
            return
        pending = next(((i, shot) for i, shot in enumerate(self.store.project.shots)
                        if shot.status != "APPROVED"), None)
        if pending is None:
            self.tabs.setCurrentIndex(3)
            return
        index, shot = pending
        self.table.selectRow(index)
        if shot.status == "REVIEW":
            self._approve()
            return
        if shot.status in ("FAILED", "WAITING") and not shot.source_file:
            if shot.submitted_prompt:
                # A previous Send may still be processing. Preserve explicit
                # confirmation before resubmitting a potentially paid job.
                self._retry()
                return
            self.store.invalidate_from(index)  # Nothing was sent: safe to resume.
            self._refresh()
        self._start()

    def _approve(self):
        index, shot = self._selection()
        if shot is None or shot.status != "REVIEW":
            self.status.setText("Chọn clip ở trạng thái Chờ duyệt.")
            return
        try:
            self.store.check_integrity(shot)
            validate_output(self.store.asset(shot.clip), JobMode.TEXT_TO_VIDEO.value)
            shot.status, shot.approved_by = "APPROVED", "manual"
            shot.error = ""
            self.store.project.state = "READY_TO_EXPORT" if self.store.project.ready_to_export else "READY"
            self.store.save()
            self._refresh()
            if not self.store.project.ready_to_export:
                self.table.selectRow(min(index + 1, len(self.store.project.shots) - 1))
                self._start()
            else:
                self.status.setText("Tất cả clip đã được duyệt. Chuyển sang Âm thanh & xuất phim.")
        except Exception as exc:
            QMessageBox.warning(self, "Chưa duyệt được", str(exc))

    def _review_mode(self, required):
        if not self.store or self.working:
            return
        self.store.project.review_required = required
        if not required:
            for shot in self.store.project.shots:
                if shot.status == "REVIEW" and not shot.error and shot.visual_review.get("verdict") != "review":
                    shot.status, shot.approved_by = "APPROVED", "automatic"
        self.store.save()
        self._refresh()
        self.status.setText("Tự chấp nhận clip sau kiểm tra file; cần tự xem lại hình ảnh trước khi xuất." if not required else "Sẽ dừng để duyệt sau mỗi clip mới.")

    def _visual_review_mode(self, enabled):
        if self.store and not self.working:
            self.store.project.visual_review_enabled = enabled
            self.store.save()

    def _invalidate(self, index):
        affected = []
        for offset in range(index, len(self.store.project.shots)):
            shot = self.store.project.shots[offset]
            if offset > index and not shot.continuation:
                break
            affected.append(shot)
        if any(shot.status != "PENDING" for shot in affected):
            answer = QMessageBox.question(self, "Đặt lại chuỗi tiếp nối",
                f"Clip này và {len(affected) - 1} clip tiếp nối phía sau sẽ cần tạo/duyệt lại. File cũ vẫn được giữ.\n"
                "Nếu Muse còn đang xử lý, kiểm tra kết quả cũ trước để tránh gửi trùng. Tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self.store.invalidate_from(index)
        return True

    def _retry(self):
        index, shot = self._selection()
        if shot and self._invalidate(index):
            self._refresh()
            self._start()

    def _edit_shot(self):
        index, shot = self._selection()
        if shot is None:
            return
        changes = edit_shot_dialog(self, shot)
        if changes and changes["prompt"] and any(getattr(shot, key) != value for key, value in changes.items()):
            candidate = copy.deepcopy(self.store.project)
            for key, value in changes.items():
                setattr(candidate.shots[index], key, value)
            # Dependent clips keep their actions but must be generated/reviewed
            # again using the revised location and incoming state.
            for offset in range(index + 1, len(candidate.shots)):
                following = candidate.shots[offset]
                if not following.continuation:
                    break
                following.location_id = changes["location_id"]
                if offset == index + 1:
                    following.start_state = changes["end_state"]
            try:
                validate_continuity(candidate)
            except ValueError as exc:
                QMessageBox.warning(self, "Cần sửa cách nối", str(exc))
                return
            if not self._invalidate(index):
                return
            for offset in range(index, len(candidate.shots)):
                if offset > index and not candidate.shots[offset].continuation:
                    break
                for key in changes:
                    setattr(self.store.project.shots[offset], key, getattr(candidate.shots[offset], key))
            self.store.save()
            self._refresh()

    def _invalidate_reference(self, reference_id):
        if not self.store:
            return True
        indices = [i for i, shot in enumerate(self.store.project.shots)
                   if reference_id in shot.character_ids or reference_id == shot.location_id]
        if indices and any(self.store.project.shots[i].status != "PENDING" for i in indices):
            result = QMessageBox.question(self, "Thay đổi tham chiếu", "Các clip dùng tham chiếu này và clip nối tiếp sẽ cần tạo/duyệt lại. File cũ vẫn được giữ. Tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if result != QMessageBox.StandardButton.Yes:
                return False
        for index in indices:
            self.store.invalidate_from(index)
        return True

    def _import_clip(self):
        index, shot = self._selection()
        if shot is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Nhập video đã có từ Muse", "", "Video (*.mp4 *.webm)")
        if path and self._invalidate(index):
            self._launch(FilmImportWorker(self.store, index, path))

    def _audio(self, field):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn âm thanh", "", "Âm thanh (*.mp3 *.wav *.m4a *.aac *.ogg *.flac)")
        if path:
            field.setText(path)

    def _export(self):
        if self.store and not self.working:
            try:
                project = self.store.project
                project.music_file = self.store.snapshot(self.music.text().strip(), "audio") if self.music.text().strip() else ""
                project.narration_file = self.store.snapshot(self.narration.text().strip(), "audio") if self.narration.text().strip() else ""
                project.keep_clip_audio = self.keep_audio.isChecked()
                self.store.save()
                self._launch(FilmExportWorker(self.store,
                    self.store.asset(project.music_file) if project.music_file else "",
                    self.store.asset(project.narration_file) if project.narration_file else "", project.keep_clip_audio))
            except Exception as exc:
                QMessageBox.warning(self, "Chưa xuất được phim", str(exc))

    def _folder(self):
        if self.store:
            open_in_explorer(str(self.store.root))

    def _open_clip(self):
        _, shot = self._selection()
        if shot and shot.clip:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.store.asset(shot.clip)))

    def _open_movie(self):
        if self.store and self.store.project.export_file:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.store.asset(self.store.project.export_file)))

    def _stop(self):
        if isinstance(self.script_worker, MuseStoryboardWorker) and self.script_worker.isRunning():
            self.script_worker.stop()
            self.status.setText("Đang dừng theo dõi kịch bản Muse; yêu cầu đã gửi được giữ để lấy lại.")
        if self.working:
            self.worker.stop()
            self.status.setText("Đang dừng và lưu tiến trình. Tác vụ đã gửi Muse không bị gửi lại tự động.")

    def closeEvent(self, event):
        if self.script_worker and self.script_worker.isRunning():
            self.status.setText("AI đang viết kịch bản. Chờ hoàn tất trước khi đóng cửa sổ.")
            event.ignore()
        elif self.working:
            self.closing = True
            self._stop()
            event.ignore()
        else:
            event.accept()
