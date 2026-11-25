import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter,
    QStatusBar, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt

from config.settings import SettingsManager
from core.version import APP_VERSION
from ui.ribbon import HeaderRibbon
from ui.left_panel import LeftPanel
from ui.right_panel import RightPanel
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.llm_dialog import LLMDictationDialog
from ui.dialogs.tts_dialog import TTSDialog
from ui.dialogs.video_merge_dialog import VideoMergeDialog
from ui.styles.theme import get_theme_stylesheet
from workers.automation_worker import AutomationWorker
from utils.logger import log_event


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"AUTO MUSE AI STUDIO - Multi-Account Automation Engine v{APP_VERSION}")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        self.settings = SettingsManager.get_instance()
        self.automation_worker: AutomationWorker = None
        self.film_dialog = None
        self._closing_for_film = False

        self._init_ui()
        self._apply_theme(self.settings.app_config.get("theme", "obsidian_dark"))

    def _init_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Ribbon
        self.ribbon = HeaderRibbon()
        self.ribbon.script_rewriter_requested.connect(self._open_llm_dialog)
        self.ribbon.video_merge_requested.connect(self._open_video_merge_dialog)
        self.ribbon.tts_requested.connect(self._open_tts_dialog)
        self.ribbon.settings_requested.connect(self._open_settings_dialog)
        self.ribbon.film_requested.connect(self._open_film_dialog)
        self.ribbon.update_requested.connect(self._open_app_update)
        self.ribbon.theme_changed_signal.connect(self._apply_theme)
        main_layout.addWidget(self.ribbon)

        # 2. Main Content Splitter (Left & Right Panels)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setContentsMargins(10, 10, 10, 10)
        self.splitter.setHandleWidth(8)

        self.left_panel = LeftPanel()
        self.right_panel = RightPanel()

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)

        # Splitter sizing: 35% left, 65% right
        self.splitter.setStretchFactor(0, 35)
        self.splitter.setStretchFactor(1, 65)
        main_layout.addWidget(self.splitter, stretch=1)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Hệ thống Auto Muse AI sẵn sàng. Vui lòng tick chọn tài khoản và bấm CHẠY.")

        # Connect Left panel batch actions
        self.left_panel.start_batch_signal.connect(self._start_batch_automation)
        self.left_panel.stop_batch_signal.connect(self._stop_batch_automation)

    def _apply_theme(self, theme_name: str):
        font_size = self.settings.app_config.get("font_size", 13)
        self.settings.app_config["theme"] = theme_name
        self.settings.save()
        stylesheet = get_theme_stylesheet(theme_name, font_size)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        log_event(f"Đã chuyển giao diện sang theme: {theme_name}")

    def _open_llm_dialog(self):
        tags = [a.tag for a in self.settings.aliases]
        dlg = LLMDictationDialog(available_tags=tags, parent=self)
        dlg.prompts_generated_signal.connect(self.right_panel.feed_external_prompts)
        dlg.exec()

    def _update_busy(self):
        film = self.film_dialog
        return bool((self.automation_worker and self.automation_worker.isRunning())
                    or (self.left_panel.active_login_worker and self.left_panel.active_login_worker.isRunning())
                    or (film and (film.working or film.gemini_panel.checking
                                  or (film.script_worker and film.script_worker.isRunning()))))

    def _open_app_update(self):
        if self._update_busy():
            QMessageBox.information(self, "Đang có tác vụ", "Dừng tác vụ hoặc đóng trình duyệt đăng nhập trước khi cập nhật.")
            return
        from ui.dialogs.app_update_dialog import AppUpdateDialog
        from core.update_source import UPDATE_MANIFEST_URL
        source = self.settings.app_config.get("update_manifest_url") or UPDATE_MANIFEST_URL
        dialog = AppUpdateDialog(source, self, self._update_busy)
        dialog.exec()

    def _open_video_merge_dialog(self):
        # Collect generated video outputs from tasks if any
        videos = [
            t.output_file for t in self.settings.tasks
            if t.output_file and t.output_file.lower().endswith(".mp4") and os.path.exists(t.output_file)
        ]
        dlg = VideoMergeDialog(initial_videos=videos, parent=self)
        dlg.exec()

    def _open_tts_dialog(self):
        dlg = TTSDialog(parent=self)
        dlg.exec()

    def _open_settings_dialog(self):
        dlg = SettingsDialog(parent=self)
        if dlg.exec():
            # Refresh params if changed
            self.right_panel.spin_timeout.setValue(self.settings.app_config.get("default_timeout", 210))

    def _open_film_dialog(self, project_path=None):
        from ui.dialogs.film_dialog import FilmDialog
        if self.film_dialog is None:
            self.film_dialog = FilmDialog(self, busy_check=lambda: bool(
                (self.automation_worker and self.automation_worker.isRunning())
                or (self.left_panel.active_login_worker and self.left_panel.active_login_worker.isRunning())))
            self.film_dialog.busy_changed.connect(self._film_busy_changed)
        self.film_dialog.show()
        self.film_dialog.raise_()
        self.film_dialog.activateWindow()
        if project_path:
            try:
                self.film_dialog.load_project(project_path)
            except Exception as exc:
                QMessageBox.warning(self, "Không mở được dự án phim", str(exc))

    def _film_busy_changed(self, busy):
        self.left_panel.setEnabled(not busy)
        self.right_panel.setEnabled(not busy)

    def _start_batch_automation(self):
        if self.film_dialog is not None and self.film_dialog.working:
            QMessageBox.information(self, "Đang xử lý phim", "Dừng tác vụ trong cửa sổ Phim dài trước khi chạy hàng đợi khác.")
            return
        if self.automation_worker and self.automation_worker.isRunning():
            QMessageBox.warning(self, "Thông báo", "Hệ thống đang trong quá trình thực thi!")
            return

        enabled_profiles = self.settings.get_enabled_profiles()
        if not enabled_profiles:
            QMessageBox.warning(self, "Lỗi", "Chưa có tài khoản nào được tick chọn (CHẠY) ở cột trái!")
            return

        if not self.settings.tasks:
            # 1. Nếu người dùng đã gõ prompt trong Khung 1: Tự động nạp luôn và chạy, không cần bấm thêm nút
            raw_text = self.right_panel.txt_raw_prompts.toPlainText().strip()
            if raw_text:
                self.right_panel._parse_and_feed_prompts()
                log_event("Đã tự động nạp prompt từ Khung 1 vào Hàng Đợi và kích hoạt chạy.", "SUCCESS")
            else:
                # 2. Nếu cả Khung 1 và Hàng đợi đều trống: Gợi ý tạo nhanh prompt với thẻ alias có sẵn (ví dụ @aothun)
                first_tag = self.settings.aliases[0].tag if self.settings.aliases else "@anh1"
                sample_p = f"Người mẫu nam mặc áo {first_tag} dạo bước phong cách điện ảnh 4K sắc nét"
                reply = QMessageBox.question(
                    self, "Hàng đợi đang trống",
                    f"Ô 'KHUNG 1' và Hàng Đợi hiện chưa có câu prompt nào.\n\n"
                    f"Bạn có muốn hệ thống tự động tạo prompt mẫu với thẻ '{first_tag}' và bắt đầu chạy ngay không?\n\n"
                    f"Prompt: \"{sample_p}\"",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.right_panel.txt_raw_prompts.setPlainText(sample_p)
                    self.right_panel._parse_and_feed_prompts()
                else:
                    return

        ready_tasks = [t for t in self.settings.tasks if t.status in ["READY", "QUEUED"]]
        if not ready_tasks:
            QMessageBox.information(
                self, "Không có task chờ chạy",
                "Tất cả các task trong hàng đợi đều đã chạy xong (OK) hoặc bị lỗi (FAIL)!\n\n"
                "👉 Bạn có thể bấm nút '🔄 Retry all FAIL' để chạy lại các task lỗi, hoặc nhập thêm prompt mới để tiếp tục."
            )
            return

        log_event(f"Kích hoạt chạy tự động {len(ready_tasks)} tasks trên {len(enabled_profiles)} profile luân chuyển...", "SUCCESS")
        self.status_bar.showMessage("Đang chạy hàng đợi tự động luân phiên tài khoản...")
        self.left_panel.btn_run.setEnabled(False)
        self.left_panel.btn_stop.setEnabled(True)
        self.right_panel.set_running(True)

        self.automation_worker = AutomationWorker(
            tasks=self.settings.tasks,
            profiles=self.settings.profiles,
            aliases=self.settings.aliases,
            selectors=self.settings.muse_selectors,
            output_dir=self.settings.app_config.get("output_dir", "output"),
            timeout_seconds=self.settings.app_config.get("default_timeout", 210),
            max_concurrent_tabs=self.right_panel.spin_concurrency.value(),
            auto_attach_if_none=self.right_panel.chk_auto_attach.isChecked(),
            headless=True,
            auto_new_chat=self.settings.app_config.get("auto_new_chat", True),
            global_proxy=self.settings.app_config.get("proxy", "")
        )

        self.automation_worker.task_started_signal.connect(self.right_panel.on_task_started)
        self.automation_worker.task_progress_signal.connect(self.right_panel.on_task_progress)
        self.automation_worker.task_waiting_signal.connect(self.right_panel.on_task_waiting)
        self.automation_worker.task_completed_signal.connect(self.right_panel.on_task_completed)
        self.automation_worker.task_failed_signal.connect(self.right_panel.on_task_failed)
        self.automation_worker.profile_updated_signal.connect(self.left_panel.update_profile_status)
        self.automation_worker.all_finished_signal.connect(self._on_batch_finished)

        self.automation_worker.start()

    def _stop_batch_automation(self):
        if self.automation_worker and self.automation_worker.isRunning():
            self.status_bar.showMessage("Đang dừng khẩn cấp luồng tác vụ...")
            self.automation_worker.stop()
        else:
            log_event("Không có tiến trình nào đang chạy để dừng.")

    def _on_batch_finished(self):
        self.right_panel.set_running(False)
        self.right_panel._load_tasks()
        self.settings.save()
        self.left_panel.btn_run.setEnabled(True)
        self.left_panel.btn_stop.setEnabled(False)
        self.status_bar.showMessage("Chu trình hoàn tất hoặc đã dừng.")
        log_event("Hệ thống đã nghỉ. Sẵn sàng cho chu trình tiếp theo.")

    def closeEvent(self, event):
        if self.film_dialog and self.film_dialog.gemini_panel.checking:
            self.status_bar.showMessage('Đang kiểm tra key Gemini. Chờ hoàn tất trước khi đóng ứng dụng.')
            event.ignore()
            return
        guard = getattr(self, 'license_guard', None)
        if guard and guard.closing_is_pending():
            self.status_bar.showMessage('Đang hoàn tất kiểm tra bản quyền trước khi đóng…')
            event.ignore()
            return
        if self.film_dialog and self.film_dialog.script_worker and self.film_dialog.script_worker.isRunning():
            self.status_bar.showMessage("AI đang lập storyboard. Chờ hoàn tất trước khi đóng ứng dụng.")
            event.ignore()
            return
        if self.film_dialog is not None and self.film_dialog.working:
            if not self._closing_for_film:
                self._closing_for_film = True
                self.film_dialog.worker.finished.connect(self.close)
            self.film_dialog._stop()
            self.status_bar.showMessage("Đang lưu và dừng phim trước khi đóng ứng dụng...")
            event.ignore()
            return
        if self.film_dialog is not None:
            self.film_dialog.close()
        if self.automation_worker and self.automation_worker.isRunning():
            self.automation_worker.stop()
            self.automation_worker.wait(3000)
        if self.left_panel.active_login_worker and self.left_panel.active_login_worker.isRunning():
            self.left_panel.active_login_worker.stop()
            self.left_panel.active_login_worker.wait(2000)
        self.settings.save()
        event.accept()
