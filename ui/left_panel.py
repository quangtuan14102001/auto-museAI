import os
import shutil
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QPlainTextEdit,
    QInputDialog, QMessageBox, QAbstractItemView, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QTextCursor, QAction

from config.settings import SettingsManager
from core.models import ProfileItem
from utils.file_utils import open_in_explorer, ensure_dir
from utils.logger import get_log_emitter, log_event
from utils.proxy_utils import format_proxy_display
from workers.login_worker import LoginWorker


class LeftPanel(QFrame):
    start_batch_signal = pyqtSignal()
    stop_batch_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "card")
        self.settings = SettingsManager.get_instance()
        self.active_login_worker: LoginWorker = None
        self._init_ui()
        self._load_profiles()
        self._connect_logger()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. Title
        lbl_acc_title = QLabel("👥 QUẢN LÝ TÀI KHOẢN & PROFILES")
        lbl_acc_title.setProperty("class", "section-title")
        layout.addWidget(lbl_acc_title)

        # 2. Profile Table (5 columns: CHẠY, TÀI KHOẢN, PROXY, TRẠNG THÁI, TASKS)
        self.table_profiles = QTableWidget()
        self.table_profiles.setColumnCount(5)
        self.table_profiles.setHorizontalHeaderLabels(["CHẠY", "TÀI KHOẢN", "PROXY", "TRẠNG THÁI", "TASKS"])
        self.table_profiles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_profiles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table_profiles.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_profiles.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_profiles.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_profiles.setColumnWidth(1, 85)
        self.table_profiles.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_profiles.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_profiles.verticalHeader().setVisible(False)
        self.table_profiles.setFixedHeight(180)
        self.table_profiles.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        self.table_profiles.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_profiles.customContextMenuRequested.connect(self._show_profile_context_menu)
        layout.addWidget(self.table_profiles)

        # 3. Action buttons for profiles
        h_prof_btns_1 = QHBoxLayout()
        btn_add = QPushButton("+ Thêm")
        btn_add.clicked.connect(self._add_profile)
        btn_del = QPushButton("Xóa")
        btn_del.clicked.connect(self._delete_profile)
        btn_login = QPushButton("Mở/Đăng nhập")
        btn_login.setProperty("class", "btn-accent")
        btn_login.setToolTip("Mở Chromium để đăng nhập — giữ nguyên session cũ nếu có")
        btn_login.clicked.connect(self._open_login)
        btn_login_fresh = QPushButton("🔑 Đăng nhập mới")
        btn_login_fresh.setToolTip("Xóa cookies/session cũ và mở trang Muse AI để đăng nhập bằng email")
        btn_login_fresh.clicked.connect(self._open_login_fresh)
        btn_close_browser = QPushButton("Đóng")
        btn_close_browser.clicked.connect(self._close_login)

        h_prof_btns_1.addWidget(btn_add)
        h_prof_btns_1.addWidget(btn_del)
        h_prof_btns_1.addWidget(btn_login)
        h_prof_btns_1.addWidget(btn_login_fresh)
        h_prof_btns_1.addWidget(btn_close_browser)
        layout.addLayout(h_prof_btns_1)

        h_prof_btns_2 = QHBoxLayout()
        btn_proxy = QPushButton("🌐 Gán Proxy")
        btn_proxy.setToolTip("Gán Proxy riêng cho tài khoản đã chọn (ip:port:user:pass hoặc http://...)")
        btn_proxy.clicked.connect(self._set_profile_proxy)
        btn_prof_dir = QPushButton("📁 Profile dir")
        btn_prof_dir.clicked.connect(self._open_profile_dir)
        btn_reset_vm = QPushButton("⚡ Reset VM")
        btn_reset_vm.clicked.connect(self._reset_vm)
        btn_test = QPushButton("Test")
        btn_test.clicked.connect(self._test_profile)
        btn_new_thread = QPushButton("Thread mới")
        btn_new_thread.clicked.connect(self._new_thread)

        h_prof_btns_2.addWidget(btn_proxy)
        h_prof_btns_2.addWidget(btn_prof_dir)
        h_prof_btns_2.addWidget(btn_reset_vm)
        h_prof_btns_2.addWidget(btn_test)
        h_prof_btns_2.addWidget(btn_new_thread)
        layout.addLayout(h_prof_btns_2)

        # 4. Big Run / Stop Control Buttons
        h_ctrl = QHBoxLayout()
        self.btn_run = QPushButton("▶ CHẠY / LUÂN CHUYỂN")
        self.btn_run.setProperty("class", "btn-run")
        self.btn_run.setToolTip("Kích hoạt chế độ chạy hàng loạt tự động luân phiên giữa các tài khoản được tick chọn")
        self.btn_run.clicked.connect(self.start_batch_signal.emit)

        self.btn_stop = QPushButton("⏹ DỪNG")
        self.btn_stop.setProperty("class", "btn-stop")
        self.btn_stop.setToolTip("Dừng khẩn cấp toàn bộ luồng tác vụ đang chạy")
        self.btn_stop.clicked.connect(self.stop_batch_signal.emit)

        h_ctrl.addWidget(self.btn_run, stretch=3)
        h_ctrl.addWidget(self.btn_stop, stretch=1)
        layout.addLayout(h_ctrl)

        # 5. Live Console
        h_log_header = QHBoxLayout()
        lbl_log_title = QLabel("📟 LOG TIẾN TRÌNH (LIVE CONSOLE)")
        lbl_log_title.setProperty("class", "section-title")
        btn_clear_log = QPushButton("Xóa log")
        btn_clear_log.setFixedHeight(24)
        btn_clear_log.clicked.connect(self._clear_log)
        h_log_header.addWidget(lbl_log_title)
        h_log_header.addStretch()
        h_log_header.addWidget(btn_clear_log)
        layout.addLayout(h_log_header)

        self.txt_console = QPlainTextEdit()
        self.txt_console.setReadOnly(True)
        self.txt_console.setStyleSheet(
            "background-color: #0b0d13; color: #cbd5e1; font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 11px; border: 1px solid #1e2436; border-radius: 6px; padding: 8px;"
        )
        layout.addWidget(self.txt_console, stretch=1)

    def _load_profiles(self):
        self.table_profiles.setRowCount(0)
        for p in self.settings.profiles:
            row = self.table_profiles.rowCount()
            self.table_profiles.insertRow(row)

            # Col 0: Checkbox CHẠY
            item_check = QTableWidgetItem()
            item_check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item_check.setCheckState(Qt.CheckState.Checked if p.enabled else Qt.CheckState.Unchecked)
            self.table_profiles.setItem(row, 0, item_check)

            # Col 1: Name
            item_name = QTableWidgetItem(p.name)
            item_name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table_profiles.setItem(row, 1, item_name)

            # Col 2: Proxy
            raw_proxy = getattr(p, "proxy", "") or ""
            disp_proxy = format_proxy_display(raw_proxy)
            item_proxy = QTableWidgetItem(disp_proxy)
            item_proxy.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if raw_proxy:
                item_proxy.setForeground(QColor("#38bdf8")) # Blue/Cyan for custom proxy
                item_proxy.setToolTip(f"Proxy riêng: {raw_proxy}\n(Click đúp để chỉnh sửa)")
            else:
                item_proxy.setForeground(QColor("#64748b")) # Gray for direct/default
                item_proxy.setToolTip("Chưa gán proxy riêng (Click đúp để gán proxy)")
            self.table_profiles.setItem(row, 2, item_proxy)

            # Col 3: Status
            status_text = p.status or "Sẵn sàng"
            cookie_file = os.path.join(p.path, "Default", "Network", "Cookies")
            alt_cookie = os.path.join(p.path, "Default", "Cookies")
            has_cookies = (os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 1024) or \
                          (os.path.exists(alt_cookie) and os.path.getsize(alt_cookie) > 1024)
            if has_cookies:
                if status_text in ["Sẵn sàng", "", "Chưa đăng nhập", "Đã đăng nhập ✓"]:
                    status_text = "Có cookie · cần kiểm tra phiên"
                    p.status = status_text
            else:
                if status_text in ["Đã đăng nhập ✓", "Sẵn sàng", "", "Có cookie · cần kiểm tra phiên", "Có dữ liệu · chưa xác minh phiên"]:
                    status_text = "Chưa đăng nhập"
                    p.status = status_text

            item_status = QTableWidgetItem(status_text)
            item_status.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if "hết quota" in status_text.lower():
                item_status.setForeground(QColor("#f87171"))
            elif "đang chạy" in status_text.lower():
                item_status.setForeground(QColor("#38bdf8"))
            elif "chưa đăng nhập" in status_text.lower():
                item_status.setForeground(QColor("#fbbf24"))
            elif "đã đăng nhập" in status_text.lower():
                item_status.setForeground(QColor("#4ade80"))
            else:
                item_status.setForeground(QColor("#cbd5e1"))
            self.table_profiles.setItem(row, 3, item_status)

            # Col 4: Tasks done/total
            item_tasks = QTableWidgetItem(f"{p.tasks_done}/{p.tasks_total}")
            item_tasks.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_tasks.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_profiles.setItem(row, 4, item_tasks)

        self.table_profiles.itemChanged.connect(self._on_table_item_changed)
        if self.settings.profiles:
            self.table_profiles.selectRow(0)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            row = item.row()
            if 0 <= row < len(self.settings.profiles):
                self.settings.profiles[row].enabled = (item.checkState() == Qt.CheckState.Checked)
                self.settings.save()

    def _get_selected_profile(self) -> ProfileItem:
        row = self.table_profiles.currentRow()
        if 0 <= row < len(self.settings.profiles):
            return self.settings.profiles[row]
        # Fallback thông minh: nếu chưa click chọn dòng, tự động lấy profile đầu tiên đang được tick CHẠY
        for idx, p in enumerate(self.settings.profiles):
            if p.enabled:
                self.table_profiles.selectRow(idx)
                return p
        if self.settings.profiles:
            self.table_profiles.selectRow(0)
            return self.settings.profiles[0]
        return None

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, "Thêm Profile", "Nhập tên định danh tài khoản (ví dụ: so3):")
        if ok and name.strip():
            clean_name = name.strip()
            path = self.settings.profile_directory(clean_name)
            ensure_dir(path)
            new_p = ProfileItem(id=clean_name, name=clean_name, path=path, enabled=True)
            self.settings.profiles.append(new_p)
            self.settings.save()
            self._load_profiles()
            log_event(f"Đã thêm profile mới '{clean_name}'. Thư mục: {path}")

    def _delete_profile(self):
        p = self._get_selected_profile()
        if not p:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một profile để xóa!")
            return
        reply = QMessageBox.question(
            self, "Xác nhận", f"Bạn có chắc muốn xóa profile '{p.name}' không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings.profiles.remove(p)
            self.settings.save()
            self._load_profiles()
            log_event(f"Đã xóa profile '{p.name}'.")

    def _open_login(self):
        if not self.settings.profiles:
            reply = QMessageBox.question(
                self, "Chưa có tài khoản",
                "Danh sách tài khoản đang trống!\nBạn có muốn tự động tạo tài khoản 'so1' và mở trình duyệt đăng nhập ngay không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                clean_name = "so1"
                path = self.settings.profile_directory(clean_name)
                ensure_dir(path)
                new_p = ProfileItem(id=clean_name, name=clean_name, path=path, enabled=True)
                self.settings.profiles.append(new_p)
                self.settings.save()
                self._load_profiles()
                log_event(f"Đã tạo profile mặc định '{clean_name}'.")
            else:
                return

        p = self._get_selected_profile()
        if not p:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một profile để đăng nhập!")
            return

        if self.active_login_worker and self.active_login_worker.isRunning():
            QMessageBox.warning(self, "Thông báo", "Đang có một trình duyệt đăng nhập mở sẵn. Vui lòng đóng trước!")
            return

        prof_proxy = (getattr(p, "proxy", "") or "").strip() or self.settings.app_config.get("proxy", "").strip()
        proxy_info = f" [Proxy: {format_proxy_display(prof_proxy)}]" if prof_proxy else ""
        log_event(f"Mở Chromium đăng nhập cho profile: {p.name}{proxy_info}")
        self.active_login_worker = LoginWorker(
            profile_name=p.name,
            profile_path=p.path,
            start_url="https://muse.ai/join",
            proxy=prof_proxy
        )
        self.active_login_worker.finished_signal.connect(self._on_login_finished)
        self.active_login_worker.error_signal.connect(self._on_login_error)
        self.active_login_worker.start()

    def _open_login_fresh(self):
        """Xóa toàn bộ cookies/session cũ, mở Chromium sạch → trang muse.ai/join để đăng nhập bằng email OTP."""
        p = self._get_selected_profile()
        if not p:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một profile để đăng nhập!")
            return

        if self.active_login_worker and self.active_login_worker.isRunning():
            QMessageBox.warning(self, "Thông báo", "Đang có một trình duyệt đăng nhập mở sẵn. Vui lòng đóng trước!")
            return

        reply = QMessageBox.question(
            self, "Xóa Session Cũ?",
            f"Sẽ XÓA TOÀN BỘ cookies & session cũ của profile '{p.name}'\nvà mở Chromium sạch để đăng nhập Muse AI bằng email OTP.\n\nBạn có chắc không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Xóa thư mục profile để bắt đầu sạch
        profile_abs = os.path.abspath(p.path)
        if os.path.exists(profile_abs):
            try:
                shutil.rmtree(profile_abs)
                log_event(f"Đã xóa session cũ của profile '{p.name}'.")
            except Exception as e:
                log_event(f"Không thể xóa session cũ: {e}", "WARNING")
        os.makedirs(profile_abs, exist_ok=True)

        p.status = "Sẵn sàng"
        self.settings.save()

        prof_proxy = (getattr(p, "proxy", "") or "").strip() or self.settings.app_config.get("proxy", "").strip()
        proxy_info = f" [Proxy: {format_proxy_display(prof_proxy)}]" if prof_proxy else ""
        log_event(f"Mở Chromium SẠCH (Fresh) để đăng nhập Muse AI cho profile: {p.name}{proxy_info}")
        self.active_login_worker = LoginWorker(
            profile_name=p.name,
            profile_path=p.path,
            start_url="https://muse.ai/join",
            proxy=prof_proxy
        )
        self.active_login_worker.finished_signal.connect(self._on_login_finished)
        self.active_login_worker.error_signal.connect(self._on_login_error)
        self.active_login_worker.start()

    def _close_login(self):
        if self.active_login_worker:
            self.active_login_worker.stop()
            log_event("Đã yêu cầu đóng trình duyệt đăng nhập thủ công.")

    def _on_login_error(self, prof_name: str, err_msg: str):
        self.active_login_worker = None
        QMessageBox.critical(
            self, "Lỗi Khởi Chạy Trình Duyệt",
            f"Không thể mở Chromium cho profile '{prof_name}'!\n\n"
            f"Chi tiết lỗi:\n{err_msg}"
        )

    def _on_login_finished(self, prof_name: str):
        authenticated = bool(self.active_login_worker and self.active_login_worker.authenticated)
        issue = getattr(self.active_login_worker, "session_issue", "")
        status = "Đã đăng nhập ✓" if authenticated else (issue or "Chưa xác nhận đăng nhập")
        log_event(f"{prof_name}: {status}", "SUCCESS" if authenticated else "WARNING")
        self.active_login_worker = None

        # Cập nhật trạng thái thành 'Đã đăng nhập ✓'
        for idx, p in enumerate(self.settings.profiles):
            if p.name == prof_name or p.id == prof_name:
                p.status = status
                self.settings.save()
                if idx < self.table_profiles.rowCount():
                    item_s = self.table_profiles.item(idx, 3)
                    if item_s:
                        item_s.setText(status)
                        item_s.setForeground(QColor("#4ade80" if authenticated else "#fbbf24"))
                break

        if authenticated:
            QMessageBox.information(self, "Đã xác nhận phiên Muse",
                                    f"Đã vào khung chat Muse của '{prof_name}'. Phiên trình duyệt đã được lưu.")
        else:
            QMessageBox.warning(self, "Chưa xác nhận được phiên Muse", f"{prof_name}: {status}. Chưa xác nhận tài khoản sẵn sàng tạo ảnh/video.")

    def _set_profile_proxy(self):
        """Mở hộp thoại gán proxy cho profile được chọn."""
        p = self._get_selected_profile()
        if not p:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn một profile trong bảng để gán proxy!")
            return

        curr_proxy = getattr(p, "proxy", "") or ""
        proxy_val, ok = QInputDialog.getText(
            self,
            f"Gán Proxy — {p.name}",
            f"Nhập proxy riêng cho tài khoản '{p.name}':\n\n"
            "Các định dạng được hỗ trợ:\n"
            " • ip:port:username:password  (ví dụ: 103.142.12.3:8080:user:pass)\n"
            " • ip:port                    (ví dụ: 103.142.12.3:8080)\n"
            " • http://user:pass@ip:port\n"
            " • socks5://user:pass@ip:port\n\n"
            "(Để trống nếu muốn chạy trực tiếp qua mạng nhà / proxy chung)",
            text=curr_proxy
        )
        if ok:
            p.proxy = proxy_val.strip()
            self.settings.save()
            self._load_profiles()
            disp = format_proxy_display(p.proxy)
            log_event(f"Đã cập nhật proxy cho profile '{p.name}': {disp}", "SUCCESS")

    def _on_table_cell_double_clicked(self, row: int, col: int):
        if 0 <= row < len(self.settings.profiles):
            self.table_profiles.selectRow(row)
            self._set_profile_proxy()

    def _show_profile_context_menu(self, pos: QPoint):
        item = self.table_profiles.itemAt(pos)
        if not item:
            return
        row = item.row()
        if not (0 <= row < len(self.settings.profiles)):
            return
        self.table_profiles.selectRow(row)
        prof = self.settings.profiles[row]

        menu = QMenu(self)
        act_proxy = menu.addAction(f"🌐 Gán / Đổi Proxy ({prof.name})...")
        act_login = menu.addAction(f"🔑 Mở Chromium Đăng nhập...")
        act_open_dir = menu.addAction(f"📁 Mở thư mục dữ liệu...")
        menu.addSeparator()
        act_del = menu.addAction(f"🗑️ Xóa profile '{prof.name}'")

        action = menu.exec(self.table_profiles.viewport().mapToGlobal(pos))
        if action == act_proxy:
            self._set_profile_proxy()
        elif action == act_login:
            self._open_login()
        elif action == act_open_dir:
            self._open_profile_dir()
        elif action == act_del:
            self._delete_profile()

    def _open_profile_dir(self):
        p = self._get_selected_profile()
        if p:
            ensure_dir(p.path)
            open_in_explorer(p.path)
        else:
            open_in_explorer("profiles")

    def _reset_vm(self):
        p = self._get_selected_profile()
        name = p.name if p else "Tất cả VM"
        log_event(f"Reset VM cho profile '{name}'. Sẵn sàng cho thread mới.")
        if p:
            p.status = "Sẵn sàng"
            self.settings.save()
            self._load_profiles()

    def _test_profile(self):
        p = self._get_selected_profile()
        if not p:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn profile để Test!")
            return

        # Kiểm tra xem thư mục profile đã có dữ liệu session Chrome chưa
        default_dir = os.path.join(p.path, "Default")
        has_session = os.path.exists(default_dir) and len(os.listdir(default_dir)) > 0
        proxy_info = f"\nProxy riêng: {p.proxy}" if getattr(p, "proxy", "") else "\nProxy: Dùng mạng nhà / mặc định"

        if has_session:
            p.status = "Có dữ liệu · chưa xác minh phiên"
            self.settings.save()
            self._load_profiles()
            log_event(f"Profile '{p.name}' có dữ liệu trình duyệt; cần mở trang để xác minh đăng nhập.", "INFO")
            QMessageBox.information(
                self, "Kiểm Tra Tài Khoản",
                f"Tài khoản '{p.name}' có dữ liệu trình duyệt, chưa xác minh đăng nhập.{proxy_info}\n"
                "Bấm Mở/Đăng nhập để kiểm tra phiên trên trang web.\n"
                f"Thư mục lưu trữ: {os.path.abspath(p.path)}"
            )
        else:
            log_event(f"Profile '{p.name}' chưa có phiên đăng nhập nào.", "WARNING")
            QMessageBox.warning(
                self, "Chưa Có Dữ Liệu",
                f"Tài khoản '{p.name}' chưa có dữ liệu đăng nhập.{proxy_info}\n"
                f"Vui lòng bấm nút 'Mở/Đăng nhập' để đăng nhập tài khoản lần đầu."
            )

    def _new_thread(self):
        log_event("Đã khởi tạo Thread worker mới trong bộ nhớ đệm.")

    def update_profile_status(self, prof_id: str, status: str, done: int, total: int):
        for idx, p in enumerate(self.settings.profiles):
            if p.id == prof_id or p.name == prof_id:
                p.status = status
                p.tasks_done = done
                p.tasks_total = total
                # Update table row (Col 3: Status, Col 4: Tasks)
                if idx < self.table_profiles.rowCount():
                    item_s = self.table_profiles.item(idx, 3)
                    if item_s:
                        item_s.setText(status)
                        if "hết quota" in status.lower():
                            item_s.setForeground(QColor("#f87171"))
                        elif "đang chạy" in status.lower():
                            item_s.setForeground(QColor("#38bdf8"))
                        else:
                            item_s.setForeground(QColor("#4ade80"))
                    item_t = self.table_profiles.item(idx, 4)
                    if item_t:
                        item_t.setText(f"{done}/{total}")
                break

    def _connect_logger(self):
        get_log_emitter().log_received.connect(self._append_log)

    def _append_log(self, time_str: str, level: str, msg: str):
        color = "#cbd5e1"
        if level == "SUCCESS":
            color = "#4ade80"
        elif level == "WARNING":
            color = "#fbbf24"
        elif level == "ERROR":
            color = "#f87171"
        elif level == "DEBUG":
            color = "#94a3b8"

        html_line = f"<span style='color: #64748b;'>[{time_str}]</span> <span style='color: {color};'>{msg}</span>"
        self.txt_console.appendHtml(html_line)
        self.txt_console.moveCursor(QTextCursor.MoveOperation.End)

    def _clear_log(self):
        self.txt_console.clear()
        log_event("Log đã được làm mới.")
