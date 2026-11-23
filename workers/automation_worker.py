import os
import re
import time
import asyncio
import copy
import base64
import subprocess
import hashlib
from pathlib import Path
from typing import List, Dict, Optional
from PyQt6.QtCore import QThread, pyqtSignal

from playwright.async_api import (
    async_playwright,
    BrowserContext,
    Page,
    Response,
    TimeoutError as PlaywrightTimeoutError
)

from core.models import TaskItem, ProfileItem, AliasItem, TaskStatus, JobMode
from core.prompt_parser import PromptParser
from core.selectors import MuseSelectors
from core.media_output import (build_generation_prompt, detect_media_format, expected_media_kind, validate_output)
from utils.file_utils import generate_output_filename, ensure_dir, find_chromium_executable
from utils.logger import log_event
from utils.proxy_utils import parse_proxy, format_proxy_display


class AutomationWorker(QThread):
    # Signals to update UI
    task_started_signal = pyqtSignal(str, str) # task_id, profile_name
    task_progress_signal = pyqtSignal(str, str) # task_id, message
    task_completed_signal = pyqtSignal(str, str, str) # task_id, profile_name, output_file
    task_failed_signal = pyqtSignal(str, str, str) # task_id, profile_name, error_msg
    task_waiting_signal = pyqtSignal(str, str, str)
    profile_updated_signal = pyqtSignal(str, str, int, int) # profile_id, status, done, total
    all_finished_signal = pyqtSignal()

    def __init__(
        self,
        tasks: List[TaskItem],
        profiles: List[ProfileItem],
        aliases: List[AliasItem],
        selectors: MuseSelectors,
        output_dir: str = "output",
        timeout_seconds: int = 210,
        max_concurrent_tabs: int = 2,
        auto_attach_if_none: bool = False,
        headless: bool = True,
        auto_new_chat: bool = True,
        global_proxy: str = ""
    ):
        super().__init__()
        self.tasks = tasks
        self.profiles = [p for p in profiles if p.enabled]
        self.alias_dict = {a.tag.lower(): a for a in aliases}
        self.selectors = selectors
        self.output_dir = ensure_dir(output_dir)
        self.timeout_seconds = timeout_seconds
        self.max_concurrent_tabs = max(1, max_concurrent_tabs)
        self.auto_attach_if_none = auto_attach_if_none
        self.headless = headless
        self.auto_new_chat = auto_new_chat
        self.global_proxy = global_proxy.strip()

        self._stop_requested = False
        self._playwright = None
        self._current_context: Optional[BrowserContext] = None
        self._active_contexts: List[BrowserContext] = []

    def stop(self):
        """Emergency stop"""
        self._stop_requested = True
        log_event("Đang kích hoạt DỪNG KHẨN CẤP. Đang dọn dẹp tiến trình...", "WARNING")

    def run(self):
        if not self.profiles:
            log_event("Không có profile nào được chọn (tick) để chạy!", "ERROR")
            self.all_finished_signal.emit()
            return

        if not self.tasks:
            log_event("Danh sách hàng đợi task rỗng!", "WARNING")
            self.all_finished_signal.emit()
            return

        asyncio.run(self._main_loop())

    async def _main_loop(self):
        self._active_contexts = []
        log_event("Đang khởi động Match VM...")
        try:
            self._playwright = await async_playwright().start()
        except Exception as e:
            log_event(f"Không thể khởi tạo Playwright Engine: {e}", "ERROR")
            self.all_finished_signal.emit()
            return

        # Chuẩn bị hàng đợi task
        task_queue = asyncio.Queue()
        task_number_map = {}
        for idx, t in enumerate(self.tasks, 1):
            task_number_map[t.id] = idx
            if t.status in [TaskStatus.READY.value, TaskStatus.QUEUED.value]:
                await task_queue.put(t)

        if task_queue.empty():
            log_event("Không có task nào ở trạng thái READY/QUEUED để chạy!", "WARNING")
            self.all_finished_signal.emit()
            return

        active_profiles = [p for p in self.profiles if "hết quota" not in p.status.lower()]
        if not active_profiles:
            log_event("Tất cả profile đều đã hết quota. Dừng hàng đợi.", "ERROR")
            self.all_finished_signal.emit()
            return

        # Tính toán số luồng song song thực tế
        concurrency = min(len(active_profiles), max(1, self.max_concurrent_tabs))
        selected_profiles = active_profiles[:concurrency]
        log_event(
            f"🚀 KÍCH HOẠT CHẠY ĐA LUỒNG SONG SONG: {len(selected_profiles)} tài khoản "
            f"({', '.join(p.name for p in selected_profiles)})", "SUCCESS"
        )

        async def profile_worker(profile: ProfileItem):
            context = None
            task = None
            try:
                ensure_dir(profile.path)
                launch_kwargs = {
                    "user_data_dir": os.path.abspath(profile.path),
                    "headless": self.headless,
                    "viewport": {"width": 1366, "height": 768},
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu"
                    ]
                }
                exec_path = find_chromium_executable(headless=self.headless)
                if exec_path:
                    launch_kwargs["executable_path"] = exec_path

                prof_proxy = (getattr(profile, "proxy", "") or "").strip() or self.global_proxy
                proxy_log = ""
                if prof_proxy:
                    parsed_p = parse_proxy(prof_proxy)
                    if parsed_p:
                        launch_kwargs["proxy"] = parsed_p
                        proxy_log = f" [Proxy: {format_proxy_display(prof_proxy)}]"

                log_event(f"[{profile.name}] Khởi chạy trình duyệt song song{proxy_log}...")
                context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
                self._active_contexts.append(context)

                self.profile_updated_signal.emit(
                    profile.id, "Đang chạy", profile.tasks_done, profile.tasks_total
                )
                log_event(f"[{profile.name}] VM sẵn sàng. Bắt đầu nhận task song song...", "SUCCESS")

                while not self._stop_requested:
                    try:
                        task = task_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    task_idx = task_number_map.get(task.id, 1)
                    remaining = task_queue.qsize()
                    task.status = TaskStatus.PROCESSING.value
                    task.error_message = ""
                    task.output_file = ""
                    self.task_started_signal.emit(task.id, profile.name)
                    log_event(f"[{profile.name}] Nhận Task #{task_idx} (Còn {remaining} task trong hàng đợi)...")

                    success, error_or_quota, output_file = await self._execute_task_on_profile(
                        context, task, profile, task_idx
                    )
                    if success:
                        try:
                            validate_output(output_file, task.mode, probe_video=False)
                        except (ValueError, OSError) as exc:
                            success, error_or_quota, output_file = False, str(exc), ""

                    if self._stop_requested:
                        task.status = TaskStatus.READY.value
                        task_queue.task_done()
                        break

                    if success:
                        task.status = f"OK - [{profile.name}]"
                        task.output_file = output_file
                        task.error_message = ""
                        profile.tasks_done += 1
                        self.task_completed_signal.emit(task.id, profile.name, output_file)
                        log_event(f"[{profile.name}] Hoàn tất Task #{task_idx}: {output_file}", "SUCCESS")
                        self.profile_updated_signal.emit(
                            profile.id, "Sẵn sàng", profile.tasks_done, profile.tasks_total
                        )
                    else:
                        if str(error_or_quota).startswith("WAITING:"):
                            task.status = TaskStatus.WAITING.value
                            task.error_message = str(error_or_quota).removeprefix("WAITING:").strip()
                            task.output_file = ""
                            self.task_waiting_signal.emit(task.id, profile.name, task.error_message)
                            log_event(f"[{profile.name}] {task.error_message}", "WARNING")
                        elif "quota" in str(error_or_quota).lower():
                            task.status = TaskStatus.QUEUED.value
                            profile.status = "Hết quota"
                            self.profile_updated_signal.emit(
                                profile.id, "Hết quota", profile.tasks_done, profile.tasks_total
                            )
                            log_event(f"[{profile.name}] Đã hết quota! Trả lại Task #{task_idx} về hàng đợi...", "WARNING")
                            await task_queue.put(task)
                            task_queue.task_done()
                            break
                        else:
                            task.status = TaskStatus.FAIL.value
                            task.error_message = str(error_or_quota)
                            task.output_file = ""
                            self.task_failed_signal.emit(task.id, profile.name, str(error_or_quota))
                            log_event(f"[{profile.name}] Task #{task_idx} thất bại: {error_or_quota}", "ERROR")

                    task_queue.task_done()

            except Exception as e:
                log_event(f"Lỗi luồng profile '{profile.name}': {e}", "ERROR")
                if task is not None and task.status == TaskStatus.PROCESSING.value:
                    task.status = TaskStatus.FAIL.value
                    task.output_file = ""
                    task.error_message = str(e)
                    self.task_failed_signal.emit(task.id, profile.name, str(e))
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    if context in self._active_contexts:
                        self._active_contexts.remove(context)
                status_final = "Hết quota" if "hết quota" in profile.status.lower() else "Sẵn sàng"
                self.profile_updated_signal.emit(
                    profile.id, status_final, profile.tasks_done, profile.tasks_total
                )
                log_event(f"[{profile.name}] Đã đóng luồng trình duyệt.")

        # Khởi chạy song song tất cả các profile worker bằng asyncio.gather!
        worker_coroutines = [profile_worker(p) for p in selected_profiles]
        await asyncio.gather(*worker_coroutines, return_exceptions=True)

        # Cleanup
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        log_event("Hoàn tất toàn bộ chu trình xử lý hàng đợi.", "SUCCESS")
        self.all_finished_signal.emit()

    async def _execute_task_on_profile(
        self,
        context: BrowserContext,
        task: TaskItem,
        profile: ProfileItem,
        task_idx: int
    ) -> tuple[bool, str, str]:
        """
        Executes a task on profile. Supports 2-phase TEXT -> IMAGE -> VIDEO pipeline.
        """
        original_task = task
        task = copy.deepcopy(task)
        original_task.generated_image_file = ""
        if not task.prompt.strip():
            return False, "Prompt không được để trống.", ""
        try:
            expected_media_kind(task.mode)
        except ValueError:
            return False, f"Chế độ không hợp lệ: {task.mode}", ""
        if task.mode == JobMode.TEXT_TO_IMAGE_TO_VIDEO.value:
            # GIAI ĐOẠN 1: Tạo Ảnh từ Text
            self.task_progress_signal.emit(task.id, "[1/2] Đang tạo hình ảnh từ Prompt...")
            log_event(f"[{profile.name}] Task #{task_idx}: Bắt đầu Bước 1/2: Tạo hình ảnh (TEXT -> IMAGE)...")
            img_task = copy.deepcopy(task)
            img_task.mode = JobMode.TEXT_TO_IMAGE.value
            
            ok_img, err_img, img_path = await self._execute_validated_phase(context, img_task, profile, task_idx)
            if not ok_img or not img_path:
                if err_img.startswith("WAITING:"):
                    return False, err_img, ""
                return False, f"Lỗi tạo ảnh (Bước 1): {err_img}", ""
            original_task.generated_image_file = img_path
            if self._stop_requested:
                return False, "Người dùng đã dừng tác vụ", ""

            self.task_progress_signal.emit(task.id, "[2/2] Tạo ảnh thành công! Đang dùng ảnh này tạo tiếp Video...")
            log_event(f"[{profile.name}] Task #{task_idx}: Đã có ảnh ({os.path.basename(img_path)}). Bắt đầu Bước 2/2: Tạo Video từ ảnh này...")
            
            # GIAI ĐOẠN 2: Dùng ảnh vừa tạo làm tham chiếu để tạo Video
            vid_task = copy.deepcopy(task)
            vid_task.mode = JobMode.REFERENCE_IMAGE_TO_VIDEO.value
            vid_task.references = list(dict.fromkeys([img_path, *task.references]))
            
            ok_vid, err_vid, vid_path = await self._execute_validated_phase(context, vid_task, profile, task_idx)
            if not ok_vid or not vid_path:
                if err_vid.startswith("WAITING:"):
                    return False, err_vid, ""
                return False, f"Đã tạo ảnh nhưng lỗi tạo video (Bước 2): {err_vid}", ""

            return True, "", vid_path
        else:
            return await self._execute_validated_phase(context, task, profile, task_idx)

    async def _execute_validated_phase(self, context, task, profile, task_idx):
        success, error, output = await self._execute_task_single_phase(context, task, profile, task_idx)
        if not success:
            return False, error, ""
        try:
            await asyncio.to_thread(validate_output, output, task.mode)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return False, str(exc), ""
        return True, "", output

    async def _execute_task_single_phase(
        self,
        context: BrowserContext,
        task: TaskItem,
        profile: ProfileItem,
        task_idx: int
    ) -> tuple[bool, str, str]:
        page: Optional[Page] = None

        has_submitted_prompt = False

        is_image_mode = expected_media_kind(task.mode) == "image"

        existing_media_srcs = set()

        try:
            page = await context.new_page()

            # Navigate to Muse AI
            target_url = self.selectors.studio_url or "https://muse.ai"
            self.task_progress_signal.emit(task.id, "Đang tải trang Muse AI...")
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                log_event(f"Không thể kết nối đến {target_url}: {e}", "WARNING")

            await asyncio.sleep(2)

            # Muse can show its signed-out landing page at / without redirecting
            # to /login. Check before attempting reference uploads or Send.
            from core.muse_session import wait_for_session
            session = await wait_for_session(page)
            if session == "unknown":
                await self._capture_composer_diagnostics(page, profile, task_idx)
            if session == "signed_out" and getattr(self, "wait_for_login", False):
                self.task_progress_signal.emit(task.id,
                    f"Đang chờ tài khoản {profile.name}: chọn tài khoản/đăng nhập trong cửa sổ Muse đang mở. App sẽ tự tiếp tục.")
                while session != "authenticated":
                    if self._stop_requested:
                        return False, "WAITING: Đã dừng khi chờ đăng nhập; chưa gửi yêu cầu tạo clip.", ""
                    if page.is_closed():
                        return False, "WAITING: Cửa sổ Muse đã đóng; chưa gửi yêu cầu tạo clip.", ""
                    session = await wait_for_session(page, timeout=4)
                    if session == "disconnected":
                        break
            if session == "disconnected":
                await self._capture_composer_diagnostics(page, profile, task_idx)
                return False, (
                    f"Muse đã ngắt kết nối tài khoản '{profile.name}' để bảo vệ thông tin. "
                    "Trang Muse yêu cầu Submit a ticket để được kết nối lại. "
                    "Chưa gửi yêu cầu tạo ảnh/video. Không cần đăng nhập lại hoặc xóa cookie."
                ), ""
            if session == "signed_out":
                return False, (
                    f"Muse đang hiển thị trang chọn/đăng nhập tài khoản trong profile '{profile.name}'. "
                    "Bấm Mở/Đăng nhập để đăng nhập lại, sau đó chọn Tạo lại clip. "
                    "App chưa gửi yêu cầu tạo video/ảnh."
                ), ""

            # Tạo đoạn chat mới (Fresh Thread) cho từng task nếu được bật
            if self.auto_new_chat:
                self.task_progress_signal.emit(task.id, "Đang mở đoạn chat mới...")
                await self._ensure_fresh_chat(page)

            # Explicit references from a pipeline take precedence over aliases.
            file_paths_to_upload = []
            if task.references:
                file_paths_to_upload = [os.path.abspath(path) for path in task.references]
            else:
                resolved_aliases, missing = PromptParser.resolve_aliases(
                    task.prompt, self.alias_dict, auto_attach_all_if_none=self.auto_attach_if_none
                )
                if missing:
                    return False, "Chưa gán ảnh cho: " + ", ".join(missing), ""
                file_paths_to_upload = [os.path.abspath(a.file_path) for a in resolved_aliases]
                file_paths_to_upload.extend(os.path.abspath(path) for path in task.references)
            file_paths_to_upload = list(dict.fromkeys(file_paths_to_upload))
            if task.mode == JobMode.REFERENCE_IMAGE_TO_VIDEO.value and not file_paths_to_upload:
                return False, "Chế độ ảnh tham chiếu sang video cần ít nhất một ảnh đầu vào.", ""
            for reference in file_paths_to_upload:
                try:
                    validate_output(reference, JobMode.TEXT_TO_IMAGE.value)
                except (ValueError, OSError) as exc:
                    return False, f"Ảnh tham chiếu không hợp lệ: {os.path.basename(reference)} ({exc})", ""
            reference_hashes = set()
            for reference in file_paths_to_upload:
                with open(reference, "rb") as stream:
                    reference_hashes.add(hashlib.sha256(stream.read()).digest())

            if file_paths_to_upload:
                self.task_progress_signal.emit(task.id, f"Đang upload {len(file_paths_to_upload)} ảnh tham chiếu...")
                uploaded = False
                for sel in self.selectors.file_input:
                    try:
                        loc = page.locator(sel)
                        if await loc.count() > 0:
                            await loc.first.set_input_files(file_paths_to_upload)
                            uploaded = True
                            break
                    except Exception:
                        continue
                if not uploaded:
                    for sel in self.selectors.upload_button:
                        try:
                            button = page.locator(sel).first
                            if await button.is_visible():
                                async with page.expect_file_chooser(timeout=5000) as chooser:
                                    await button.click()
                                await (await chooser.value).set_files(file_paths_to_upload)
                                uploaded = True
                                break
                        except Exception:
                            continue
                if not uploaded:
                    return False, "Không tải được ảnh tham chiếu lên trang; chưa gửi yêu cầu tạo sản phẩm.", ""
                await asyncio.sleep(1.5)

            # 2. Wait up to 25s for Composer to mount/appear (essential when multi-threading or dynamic React load)
            composer_element = None
            composer_selectors = list(self.selectors.composer_textarea)
            for extra in [
                "div[contenteditable='true']",
                "div[role='textbox']",
                "textarea[placeholder*='Message' i]",
                "input[placeholder*='Message' i]",
                "textarea",
                "[data-testid*='composer']",
                "[data-testid*='prompt']"
            ]:
                if extra not in composer_selectors:
                    composer_selectors.append(extra)

            wait_start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - wait_start) < 25:
                if self._stop_requested:
                    return False, "Người dùng đã dừng tác vụ", ""

                # Check if redirected to login/join
                curr_url = page.url.lower()
                if "/login" in curr_url or "/join" in curr_url:
                    return False, f"Profile '{profile.name}' chưa đăng nhập Muse AI. Vui lòng bấm 'Đăng nhập' ở Profile để đăng nhập!", ""

                # Check if landed on 404 Page Not Found
                try:
                    title_text = (await page.title()).lower()
                    if "not found" in title_text or await page.locator("text='Page not found'").count() > 0:
                        back_btn = page.locator("a:has-text('Back to chat'), button:has-text('Back to chat')")
                        if await back_btn.count() > 0 and await back_btn.first.is_visible():
                            await back_btn.first.click()
                            await asyncio.sleep(2)
                        else:
                            await page.goto(self.selectors.studio_url or "https://muse.ai", wait_until="domcontentloaded")
                            await asyncio.sleep(2)
                except Exception:
                    pass

                for sel in composer_selectors:
                    try:
                        loc = page.locator(sel)
                        if await loc.count() > 0 and await loc.first.is_visible():
                            composer_element = loc.first
                            break
                    except Exception:
                        continue

                if composer_element:
                    break
                await asyncio.sleep(1)

            final_prompt = self._build_generation_prompt(task)

            if not composer_element:
                await self._capture_composer_diagnostics(page, profile, task_idx)
                message = (f"[{profile.name}] Chưa vào được màn hình nhập prompt. "
                           "Bấm Mở/Đăng nhập cho tài khoản này và kiểm tra trang đã đăng nhập. "
                           "Nếu đã đăng nhập, kiểm tra URL hoặc giao diện trang. "
                           f"Trang hiện tại: {page.url.split('?')[0].split('#')[0]}")
                log_event(message, "ERROR")
                return False, message, ""

            self.task_progress_signal.emit(task.id, f"Đang điền prompt ({task.mode}) vào Composer...")
            log_event(f"Nạp prompt ({task.mode}): {final_prompt[:90]}...")
            await composer_element.click()
            await composer_element.fill(final_prompt)
            await asyncio.sleep(1)

            # 3. Submit
            submit_btn = None
            for sel in self.selectors.submit_button:
                try:
                    loc = page.locator(sel)
                    if await loc.count() > 0 and await loc.first.is_visible():
                        submit_btn = loc.first
                        break
                except Exception:
                    continue

            # Mark existing result cards even when their blob/image has not loaded
            # yet. A late-loading old card must not become this task's output.
            await self._mark_existing_result_cards(page)
            # Ghi nhận TOÀN BỘ các video, nút tải và ảnh đã có sẵn từ trước trong chat để tuyệt đối không bắt nhầm video cũ
            try:
                # 1. Quét tất cả thẻ <video> hiện có
                for v in await page.locator("video").all():
                    s = await v.get_attribute("src") or await v.evaluate("el => el.currentSrc")
                    if s:
                        existing_media_srcs.add(s)
                # 2. Quét tất cả link/nút download của các tin nhắn cũ
                for dl_sel in self.selectors.download_button:
                    loc = page.locator(dl_sel)
                    cnt = await loc.count()
                    for i in range(cnt):
                        h = await loc.nth(i).evaluate("el => el.href || ''")
                        if h:
                            existing_media_srcs.add(h)
                # 3. Quét tất cả ảnh đã có
                for img in await page.locator("img").all():
                    src = await img.evaluate("el => el.currentSrc || el.src")
                    if src:
                        existing_media_srcs.add(src)
            except Exception:
                pass

            has_submitted_prompt = True # Bắt đầu kích hoạt lắng nghe media sau khi gửi
            await self._before_submit(page, task, final_prompt)
            if submit_btn:
                await submit_btn.click()
                log_event("Đã nhấn nút Gửi (Send) trên Muse AI.")
            else:
                await composer_element.press("Enter")
                log_event("Đã nhấn Enter để gửi prompt trên Muse AI.")
            await self._after_submit(page, task, final_prompt)

            return await self._wait_for_result(
                page, task, profile, task_idx, existing_media_srcs, reference_hashes, final_prompt
            )

        except Exception as e:
            if has_submitted_prompt:
                return False, "WAITING: Chưa theo dõi được kết quả sau khi gửi; chưa xác nhận Muse thất bại. Kiểm tra cuộc chat.", ""
            return False, str(e), ""
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass

    def _build_generation_prompt(self, task):
        return build_generation_prompt(task)

    async def _capture_composer_diagnostics(self, page, profile, task_idx):
        """Local failure evidence; never send page contents to an external API."""
        import json
        try:
            root = Path(self.output_dir) / "debug"
            root.mkdir(parents=True, exist_ok=True)
            name = "composer_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(profile.id)) + f"_{task_idx}"
            evidence = await page.evaluate("""() => ({
                title: document.title, ready: document.readyState,
                text: (document.body?.innerText || '').slice(0,2500),
                editors: [...document.querySelectorAll('textarea,input,[contenteditable]')].map(e=>({
                    tag:e.tagName, type:e.getAttribute('type'), placeholder:e.getAttribute('placeholder'),
                    role:e.getAttribute('role'), editable:e.getAttribute('contenteditable'),
                    visible:!!e.getBoundingClientRect().width})),
                frameCount: document.querySelectorAll('iframe').length
            })""")
            evidence["url"] = page.url.split("?")[0].split("#")[0]
            (root / f"{name}.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            await page.screenshot(path=str(root / f"{name}.png"), full_page=False)
        except Exception:
            pass

    async def _before_submit(self, page, task, prompt):
        """Optional durable submission checkpoint used by film projects."""

    async def _after_submit(self, page, task, prompt):
        """Optional checkpoint after the site has accepted the request."""

    async def _ensure_fresh_chat(self, page: Page) -> bool:
        """
        Creates a new chat session on Muse AI so each task runs in an isolated, fresh thread.
        Clicks 'New Chat' / '+' button or navigates to fresh chat endpoint.
        """
        try:
            # 1. First, check if there is a 'New Chat' button visible
            for sel in self.selectors.new_chat_button:
                try:
                    loc = page.locator(sel)
                    cnt = await loc.count()
                    for i in range(cnt):
                        btn = loc.nth(i)
                        if await btn.is_visible():
                            await btn.click()
                            log_event("Đã nhấn nút 'New Chat' (+) để mở phiên chat mới trên Muse AI.")
                            await asyncio.sleep(2)
                            return True
                except Exception:
                    continue

            # 2. Fallback: If URL has a specific chat/thread ID, navigate back to base URL
            curr_url = page.url.lower()
            if any(k in curr_url for k in ["/chat/", "thread=", "conversation="]):
                base = self.selectors.studio_url or "https://muse.ai"
                await page.goto(base, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(2)
                return True

        except Exception as e:
            log_event(f"Lỗi khi mở phiên chat mới: {e}", "WARNING")

        return False

    async def _muse_request_boundary(self, page, prompt_text):
        prompt = page.get_by_text(prompt_text, exact=True).last
        if not await prompt.count():
            return None
        return await prompt.evaluate_handle("""el => {
            const selector = '[data-pel-impression="chat_message_impression"], [data-message-author-role="user"], [data-role="user"], .hatch-chat-groupable-bubble.bg-chat-user-bubble';
            const start = el.closest(selector) || el;
            const users = [...document.querySelectorAll(selector)].filter(row => {
                const surrogate = row.querySelector('[data-message-accessibility-surrogate]');
                return row !== start && !row.contains(start) && !start.contains(row)
                    && !!(start.compareDocumentPosition(row) & Node.DOCUMENT_POSITION_FOLLOWING)
                    && (row.matches('[data-message-author-role="user"], [data-role="user"], .bg-chat-user-bubble')
                        || surrogate?.textContent.trim().startsWith('User message:'));
            });
            return {start, end:users[0] || null};
        }""")

    async def _read_muse_feedback(self, page: Page, prompt_text: str) -> tuple[str, str]:
        """Read only replies after this task's submitted prompt, never old errors."""
        handle = await self._muse_request_boundary(page, prompt_text)
        if handle is None:
            return "waiting", ""
        messages = await page.locator(
            '.hatch-chat-groupable-bubble, [data-message-author-role="assistant"], '
            '[data-role="assistant"], [role="alert"]'
        ).evaluate_all("""(elements, boundary) => elements.filter(el =>
            !boundary.start.contains(el)
            && !!(boundary.start.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)
            && (!boundary.end || !!(el.compareDocumentPosition(boundary.end) & Node.DOCUMENT_POSITION_FOLLOWING))
            && el.getBoundingClientRect().width > 0
            && !el.closest('[data-message-author-role="user"], [data-role="user"]')
        ).map(el => el.innerText || '')""", handle)
        text = "\n".join(messages).lower()
        # A proposed replacement needs a decision, not an endless render wait.
        # Require both an unfulfilled request and an explicit alternative in the
        # same current reply; ordinary generation progress must keep waiting.
        for message in reversed(messages):
            reply = message.lower()
            if any(phrase in reply for phrase in (
                "chưa tạo được video này theo đúng mô tả", "không thể hỗ trợ tạo nội dung này",
                "i can't help create", "i cannot help create", "i can't generate that",
                "i cannot generate that", "this request violates our",
            )):
                return "needs_input", message.strip()[:800]
            if (any(phrase in reply for phrase in (
                "chưa tạo được", "không thể tạo", "không tạo được",
                "unable to generate", "could not generate", "can't create",
            )) and any(phrase in reply for phrase in (
                "phương án khác", "theo hướng đó", "would you like", "alternative",
            ))):
                return "needs_input", message.strip()[:800]
        failures = [
            "generation failed", "failed to generate", "unable to generate", "could not generate",
            "error generating", "tạo video thất bại", "tạo ảnh thất bại", "không thể tạo",
            "không tạo được", "chưa tạo được vì runway", "runway chưa được kết nối",
            "out of credits", "quota exceeded", "insufficient credits", "không đủ tín dụng",
            "blocked by policy", "vi phạm chính sách",
            "something went wrong", "an error occurred", "đã xảy ra lỗi",
            "failed to create", "unable to create", "không đủ credit", "tạo không thành công",
        ]
        if any(phrase in text for phrase in failures):
            return "error", next((message.strip() for message in reversed(messages)
                                   if any(phrase in message.lower() for phrase in failures)), text)[:800]
        if any(phrase in text for phrase in ["đã xong", "đã tạo xong", "đã hoàn tất", "video is ready", "image is ready"]):
            return "complete", ""
        return "waiting", ""

    async def _wait_for_result(self, page, task, profile, task_idx, existing_srcs, reference_hashes, prompt_text):
        """The reminder interval is not a render deadline. Only Muse errors fail generation."""
        start = asyncio.get_running_loop().time()
        last_notice = -10.0
        reminder_sent = False
        observed_types = set()
        pending_reason = ""
        while not self._stop_requested:
            if page.is_closed():
                return False, "WAITING: Trang theo dõi đã đóng; chưa xác nhận Muse thất bại. Kiểm tra kết quả trong cuộc chat.", ""
            elapsed = asyncio.get_running_loop().time() - start
            try:
                # Check files first: a valid result is stronger evidence than a
                # delayed status message. Never submit the prompt a second time.
                output = await self._check_dom_real_media(
                    page, profile.name, task_idx, existing_srcs, int(elapsed),
                    task.mode == JobMode.TEXT_TO_IMAGE.value, reference_hashes, observed_types, prompt_text
                )
                if output:
                    try:
                        await asyncio.to_thread(validate_output, output, task.mode)
                    except (ValueError, OSError, subprocess.SubprocessError):
                        if os.path.isfile(output):
                            os.remove(output)
                        pending_reason = "Đã thấy kết quả; đang thử tải lại file hoàn chỉnh"
                    else:
                        log_event(f"Đã tải và kiểm tra thành công {task.mode} ({int(elapsed)}s).", "SUCCESS")
                        return True, "", output
                state, message = await self._read_muse_feedback(page, prompt_text)
                if state == "needs_input":
                    return False, f"WAITING: Cần sửa mô tả hoặc trả lời Muse trước khi tiếp tục. {message}", ""
                if state == "error":
                    return False, f"Muse báo lỗi: {message}", ""
                if state == "complete":
                    pending_reason = "Muse đã báo xong; đang lấy file kết quả"
            except Exception:
                if page.is_closed():
                    return False, "WAITING: Mất kết nối trang theo dõi; chưa xác nhận Muse thất bại.", ""
                pending_reason = "Đang chờ kết nối hoặc thử tải lại kết quả"
            if elapsed - last_notice >= 10:
                status = pending_reason or "Đang chờ Muse xử lý và trả kết quả"
                self.task_progress_signal.emit(task.id, f"{status} ({int(elapsed)} giây). Có thể bấm Dừng.")
                last_notice = elapsed
            if not reminder_sent and elapsed >= self.timeout_seconds:
                log_event(f"[{profile.name}] Đã chờ {int(elapsed)}s; tiếp tục đợi kết quả, không đánh dấu lỗi do thời gian chờ.")
                reminder_sent = True
            await asyncio.sleep(2)
        return False, "Người dùng đã dừng theo dõi kết quả", ""

    def _save_result_bytes(self, data: bytes, profile_name: str, task_idx: int, kind: str) -> Optional[str]:
        media = detect_media_format(data)
        if media is None or media.kind != kind:
            return None
        path = generate_output_filename(self.output_dir, profile_name, task_idx, media.extension)
        with open(path, "wb") as stream:
            stream.write(data)
        return path

    async def _mark_existing_result_cards(self, page: Page):
        await page.evaluate("""() => {
            window.__automuseExistingResults = new WeakSet(document.querySelectorAll(
                'video, button[aria-label^="Open generated image" i], button[aria-label^="Open generated video" i], [data-pel-click="chat_media_click"]'
            ));
        }""")

    async def _fetch_result_bytes(self, page: Page, url: str) -> bytes:
        if url.startswith(("blob:", "data:")):
            encoded = await page.evaluate("""async url => {
                const response = await fetch(url);
                if (!response.ok) return null;
                const blob = await response.blob();
                return await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result.split(',')[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(blob);
                });
            }""", url)
            return base64.b64decode(encoded) if encoded else b""
        if url.startswith(("https://", "http://")):
            response = await page.request.get(url)
            return await response.body() if response.ok else b""
        return b""

    async def _check_dom_real_media(
        self, page: Page, profile_name: str, task_idx: int, existing_srcs: set = None,
        elapsed: int = 0, is_image_mode: bool = False, reference_hashes: set = None,
        observed_output_types: set = None, prompt_text: str = None
    ) -> Optional[str]:
        """Accept only new, visible media of the requested type in the result DOM."""
        existing_srcs = existing_srcs or set()
        kind = "image" if is_image_mode else "video"
        candidates = []
        prompt_handle = None
        if prompt_text:
            prompt_handle = await self._muse_request_boundary(page, prompt_text)
            if prompt_handle is None:
                return None
            # Muse virtualizes old messages. Bring this request into view so its
            # adjacent reply/media can mount, without scrolling unrelated cards.
            await page.evaluate("b => b.start.scrollIntoView({block:'center'})", prompt_handle)
            await page.wait_for_timeout(150)
            prompt_handle = await self._muse_request_boundary(page, prompt_text)
            if prompt_handle is None:
                return None
        if is_image_mode:
            # Muse uses custom result buttons outside main/article/.chat. Scroll
            # only new result cards so lazy-loaded images can acquire a blob URL.
            cards = page.locator('button[aria-label^="Open generated image" i]')
            eligible_cards = await cards.all()
            if not prompt_text:
                eligible_cards.reverse()
            for card in eligible_cards:
                try:
                    if prompt_handle and not await card.evaluate("""(el,b) =>
                        !b.start.contains(el) && !!(b.start.compareDocumentPosition(el)&Node.DOCUMENT_POSITION_FOLLOWING)
                        && (!b.end || !!(el.compareDocumentPosition(b.end)&Node.DOCUMENT_POSITION_FOLLOWING))""",prompt_handle):
                        continue
                    if await card.evaluate("el => !!window.__automuseExistingResults?.has(el)"):
                        continue
                    await card.scroll_into_view_if_needed(timeout=1000)
                    if prompt_text:
                        # Stay on the first result of this request. Scrolling
                        # every later card can unmount this image again.
                        break
                except Exception:
                    continue
        # Each mode has its own DOM branch. Images never fall through to video,
        # and videos never fall back to a reference image or a video poster.
        selector = ('button[aria-label^="Open generated image" i] img, main img, .chat img, [data-message] img, article img, div.space-y-4 img'
                    if is_image_mode else "video")
        elements = await page.locator(selector).all()
        if not prompt_text:
            elements.reverse()
        for element in elements:
            try:
                metadata = await element.evaluate("""(el, prompt) => {
                    const rect = el.getBoundingClientRect();
                    const src = el.currentSrc || el.src || '';
                    const resultCard = el.closest('button[aria-label^="Open generated image" i], button[aria-label^="Open generated video" i]');
                    const oldResult = window.__automuseExistingResults?.has(el) || (resultCard && window.__automuseExistingResults?.has(resultCard));
                    const excluded = el.closest('.rounded-full, [aria-label*="avatar" i], [data-hatch-media-owner="avatar-layer"], [data-hatch-avatar-layer], [aria-hidden="true"], [data-message-author-role="user"], [data-role="user"], form, [data-testid*="composer"], .loading, .generating, [data-state="loading"], [aria-busy="true"], [class*="mascot" i]');
                    const isVideo = el.tagName === 'VIDEO';
                    const isPoster = !isVideo && (el.closest('a[href*=".mp4"], a[href*=".webm"]') || el.parentElement?.querySelector('video'));
                    const width = isVideo ? el.videoWidth : el.naturalWidth;
                    const height = isVideo ? el.videoHeight : el.naturalHeight;
                    const loader = /avatar|favicon|mascot|loader|loading|placeholder|spinner|poster|thumbnail/i.test(src);
                    const beforePrompt = prompt && (prompt.start.contains(el)
                        || !(prompt.start.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)
                        || (prompt.end && !(el.compareDocumentPosition(prompt.end) & Node.DOCUMENT_POSITION_FOLLOWING)));
                    return {src, excluded: !!excluded || !!isPoster || loader || !!oldResult || !!beforePrompt,
                        visible: rect.width > 0 && rect.height > 0,
                        large: width >= 128 && height >= 128,
                        ready: !isVideo || (el.readyState >= 2 && el.duration > 0)};
                }""", prompt_handle)
                if (metadata["src"] and not metadata["excluded"] and metadata["visible"]
                        and metadata["large"] and metadata["ready"]):
                    candidates.append(metadata["src"])
            except Exception:
                continue
        # Explicit downloads may have no img/video tag. Their body still must
        # decode as the requested type; filenames and content-type are not trusted.
        for selector in self.selectors.download_button:
            for element in reversed(await page.locator(selector).all()):
                try:
                    if await element.is_visible():
                        excluded = await element.evaluate("""(el, prompt) => {
                            const card = el.closest('button[aria-label^="Open generated image" i], button[aria-label^="Open generated video" i]');
                            const beforePrompt = prompt && (prompt.start.contains(el)
                                || !(prompt.start.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)
                                || (prompt.end && !(el.compareDocumentPosition(prompt.end) & Node.DOCUMENT_POSITION_FOLLOWING)));
                            return !!beforePrompt || !!window.__automuseExistingResults?.has(card) || !!el.closest('[data-message-author-role="user"], [data-role="user"], form, [data-testid*="composer"], .loading, .generating, [data-state="loading"]');
                        }""", prompt_handle)
                        if excluded:
                            continue
                        href = await element.evaluate("el => el.href || ''")
                        if href:
                            candidates.append(href)
                except Exception:
                    continue
        for url in dict.fromkeys(candidates):
            if url in existing_srcs:
                continue
            try:
                body = await self._fetch_result_bytes(page, url)
                if reference_hashes and hashlib.sha256(body).digest() in reference_hashes:
                    continue
                media = detect_media_format(body)
                if observed_output_types is not None and media is not None:
                    observed_output_types.add(media.kind)
                result = self._save_result_bytes(body, profile_name, task_idx, kind)
                if result:
                    if kind == "video":
                        try:
                            await asyncio.to_thread(validate_output, result, JobMode.TEXT_TO_VIDEO.value)
                        except (ValueError, OSError, subprocess.SubprocessError):
                            os.remove(result)
                            continue
                    return result
            except Exception:
                continue
        return None
