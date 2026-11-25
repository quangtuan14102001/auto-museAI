import os
import sys

# Ensure project root is in python path (support PyInstaller frozen binary)
if getattr(sys, "frozen", False):
    basedir = os.path.dirname(sys.executable)
    os.chdir(basedir)
    sys.path.insert(0, basedir)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure Playwright browser path
local_app_data = os.environ.get("LOCALAPPDATA", "")
ms_playwright_dir = os.path.join(local_app_data, "ms-playwright") if local_app_data else ""

if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    meipass = getattr(sys, "_MEIPASS", "")
    meipass_browsers = os.path.join(meipass, "playwright", "driver", "package", ".local-browsers")
    bundled_browsers = os.path.join(exe_dir, "_internal", "playwright", "driver", "package", ".local-browsers")
    if meipass and os.path.exists(meipass_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = meipass_browsers
    elif os.path.exists(bundled_browsers) and any(os.listdir(bundled_browsers)):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    elif ms_playwright_dir and os.path.exists(ms_playwright_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = ms_playwright_dir
else:
    if ms_playwright_dir and os.path.exists(ms_playwright_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = ms_playwright_dir

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from ui.main_window import MainWindow
from utils.logger import log_event


def ensure_desktop_shortcut():
    """Tự động tạo biểu tượng Shortcut ngoài màn hình Desktop kèm logo như các app cài đặt chuyên nghiệp."""
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        try:
            desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
            shortcut_path = os.path.join(desktop, "AutoMuseAI Studio.lnk")
            exe_path = os.path.abspath(sys.executable)
            if not os.path.exists(shortcut_path):
                import subprocess
                ps_cmd = (
                    f'$ws = New-Object -ComObject WScript.Shell; '
                    f'$s = $ws.CreateShortcut("{shortcut_path}"); '
                    f'$s.TargetPath = "{exe_path}"; '
                    f'$s.WorkingDirectory = "{os.path.dirname(exe_path)}"; '
                    f'$s.IconLocation = "{exe_path},0"; '
                    f'$s.Save()'
                )
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    creationflags=0x08000000
                )
        except Exception:
            pass


def main():
    film_project_path = None
    if "--film-project" in sys.argv:
        index = sys.argv.index("--film-project")
        if index + 1 < len(sys.argv):
            film_project_path = os.path.abspath(sys.argv[index + 1])
            del sys.argv[index:index + 2]
    # Set Windows AppUserModelID for taskbar branding
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("automuseai.studio.runner.v1")
        except Exception:
            pass

    # Enable High DPI scaling
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("AutoMuseAI Studio")
    app.setOrganizationName("AutoMuseAI")

    # Set Application Window & Taskbar Icon
    from PyQt6.QtGui import QIcon
    icon_candidates = [
        os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "logo.ico"),
        os.path.join(getattr(sys, "_MEIPASS", ""), "assets", "logo.png"),
        os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)), "assets", "logo.ico"),
        os.path.join(os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png"),
    ]
    for ic in icon_candidates:
        if ic and os.path.exists(ic):
            app.setWindowIcon(QIcon(ic))
            break

    from ui.cursor_filter import GlobalCursorFilter
    cursor_filter = GlobalCursorFilter()
    app.installEventFilter(cursor_filter)

    # Tự động tạo biểu tượng ngoài màn hình Desktop cho người dùng
    ensure_desktop_shortcut()

    try:
        log_event("Khởi động ứng dụng Auto Muse AI Studio Batch Runner...")
        
        from core.license_source import LICENSE_REQUIRED
        license_session = None
        if LICENSE_REQUIRED:
            from core.licensing import LicenseSession
            from ui.dialogs.license_dialog import LicenseDialog
            from PyQt6.QtWidgets import QDialog
            license_session = LicenseSession()
            activation = LicenseDialog(license_session)
            if license_session.key:
                QTimer.singleShot(0, activation.check)
            if activation.exec() != QDialog.DialogCode.Accepted or not license_session.valid:
                sys.exit(0)
        window = MainWindow()
        if license_session is not None:
            from ui.license_guard import LicenseGuard
            window.license_guard = LicenseGuard(license_session, window)
        # Set window icon explicitly
        for ic in icon_candidates:
            if ic and os.path.exists(ic):
                window.setWindowIcon(QIcon(ic))
                break
        window.show()
        if film_project_path:
            QTimer.singleShot(0, lambda: window._open_film_dialog(film_project_path))

        sys.exit(app.exec())
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            with open("crash.log", "w", encoding="utf-8") as f:
                f.write(err_msg)
        except Exception:
            pass
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Lỗi Khởi Động", f"Đã xảy ra sự cố khi khởi động:\n\n{err_msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
