import os
import asyncio
from PyQt6.QtCore import QThread, pyqtSignal
from playwright.async_api import async_playwright, BrowserContext
from utils.logger import log_event
from utils.file_utils import find_chromium_executable
from core.muse_session import session_state


from utils.proxy_utils import parse_proxy, format_proxy_display

class LoginWorker(QThread):
    finished_signal = pyqtSignal(str) # profile_name
    error_signal = pyqtSignal(str, str) # profile_name, error_msg

    def __init__(self, profile_name: str, profile_path: str, start_url: str = "https://muse.ai/join", proxy: str = ""):
        super().__init__()
        self.profile_name = profile_name
        self.profile_path = os.path.abspath(profile_path)
        self.start_url = start_url
        self.proxy = proxy
        self._is_running = True
        self.context: BrowserContext = None
        self._playwright = None
        self.authenticated = False
        self.session_issue = ""

    def run(self):
        proxy_info = f" (Proxy: {format_proxy_display(self.proxy)})" if self.proxy else ""
        log_event(f"Đang khởi chạy Chromium Headed cho profile '{self.profile_name}'{proxy_info} để đăng nhập...")
        os.makedirs(self.profile_path, exist_ok=True)

        has_error = False

        async def _run():
            nonlocal has_error
            try:
                self._playwright = await async_playwright().start()
                # Launch persistent context with GUI visible (KHÔNG dùng --new-window hay --no-session-restore
                # vì sẽ gây ra chế độ ẩn danh / guest mode không lưu cookies)
                launch_kwargs = {
                    "user_data_dir": self.profile_path,
                    "headless": False,
                    "viewport": {"width": 1280, "height": 800},
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-session-crashed-bubble",
                    ]
                }
                if self.proxy:
                    parsed_p = parse_proxy(self.proxy)
                    if parsed_p:
                        launch_kwargs["proxy"] = parsed_p

                exec_path = find_chromium_executable(headless=False)
                if exec_path:
                    launch_kwargs["executable_path"] = exec_path

                self.context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)

                # Mở tab mới sạch trỏ đến Muse AI
                page = await self.context.new_page()

                # Đóng tất cả các tab session cũ (Instagram/FB/v.v.) nếu có
                for old_page in list(self.context.pages):
                    if old_page != page:
                        try:
                            await old_page.close()
                        except Exception:
                            pass

                log_event(f"Mở trang Muse AI: {self.start_url}")
                try:
                    await page.goto(self.start_url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    log_event(f"Cảnh báo khi tải trang: {e}", "WARNING")

                log_event(f"Profile '{self.profile_name}' đã sẵn sàng. Người dùng hãy đăng nhập trên trình duyệt.", "SUCCESS")

                # Keep alive until user closes the window or stop requested
                while self._is_running and len(self.context.pages) > 0:
                    states = []
                    for current_page in list(self.context.pages):
                        try:
                            if not current_page.is_closed():
                                states.append(await session_state(current_page))
                        except Exception:
                            pass  # A user may close a tab while it is inspected.
                    if "authenticated" in states:
                        self.authenticated = True
                        self.session_issue = ""
                    elif "disconnected" in states:
                        self.authenticated = False
                        if self.session_issue != "Muse đã ngắt kết nối":
                            log_event(f"Muse đã ngắt kết nối '{self.profile_name}'. Trang Muse yêu cầu Submit a ticket để được kết nối lại.", "WARNING")
                        self.session_issue = "Muse đã ngắt kết nối"
                    elif "signed_out" in states:
                        self.authenticated = False
                    await asyncio.sleep(1)

            except Exception as e:
                has_error = True
                err_msg = str(e)
                if self._is_running:
                    log_event(f"Lỗi khi mở profile '{self.profile_name}': {err_msg}", "ERROR")
                    self.error_signal.emit(self.profile_name, err_msg)
            finally:
                if self.context:
                    try:
                        await self.context.close()
                    except Exception:
                        pass
                if self._playwright:
                    try:
                        await self._playwright.stop()
                    except Exception:
                        pass
                if not has_error:
                    log_event(f"Đã đóng trình duyệt '{self.profile_name}'. " +
                              ("Đã xác nhận khung chat Muse." if self.authenticated else "Chưa xác nhận đăng nhập Muse."))
                    self.finished_signal.emit(self.profile_name)

        asyncio.run(_run())

    def stop(self):
        self._is_running = False
