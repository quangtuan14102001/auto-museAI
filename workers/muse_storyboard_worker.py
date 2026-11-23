"""Muse chat transport for the shared, validated storyboard planner."""
import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from playwright.async_api import async_playwright
from core.muse_session import wait_for_session
from utils.file_utils import find_chromium_executable
from utils.proxy_utils import parse_proxy
from workers.automation_worker import AutomationWorker
from workers.film_storyboard_worker import FilmStoryboardWorker


async def current_reply(page, prompt):
    marker = re.search(r'Mã yêu cầu văn bản: ([a-f0-9]{32})', prompt)
    if marker:
        users = page.locator('[data-message-author-role="user"], [data-role="user"]').filter(has_text=marker[1])
        anchor = users.last if await users.count() else page.get_by_text(marker[1], exact=False).last
    else:
        anchor = page.get_by_text(prompt, exact=True).last
    if not await anchor.count():
        return ""
    handle = await anchor.element_handle()
    messages = await page.locator(
        '.hatch-chat-groupable-bubble, [data-message-author-role="assistant"], [data-role="assistant"]'
    ).evaluate_all("""(els, prompt) => els.filter(el =>
        !!(prompt.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING)
        && el.getBoundingClientRect().width > 0
        && !el.closest('[data-message-author-role="user"], [data-role="user"]')
    ).map(el => el.innerText || '')""", handle)
    return "\n".join(dict.fromkeys(m.strip() for m in messages if m.strip()))


class MuseStoryboardWorker(FilmStoryboardWorker):
    def __init__(self, idea, seconds, clip_seconds, notes, profile, selectors, global_proxy="", **kwargs):
        super().__init__(idea, seconds, clip_seconds, notes, "muse", "muse-session", "", **kwargs)
        self.profile, self.selectors, self.global_proxy = profile, selectors, global_proxy
        self._stopped = False
        self.context = self.engine = self.page = None
        self.response_timeout = 600
        self.poll_seconds = 1
        self.stable_seconds = 3
        self.journal = self.checkpoint_path.with_suffix(".muse-request.json") if self.checkpoint_path else None

    def stop(self):
        self._stopped = True

    def run(self):
        with asyncio.Runner() as runner:
            self.runner = runner
            try:
                super().run()
            finally:
                try:
                    runner.run(self._close())
                except Exception:
                    pass  # Preserve the planning outcome if Chrome already exited.

    async def _close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            if self.engine:
                await self.engine.stop()

    def _write_journal(self, record):
        if self.journal:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.journal.with_suffix('.tmp')
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.journal)

    def _call_muse(self, instruction):
        if self._stopped:
            raise ValueError("Đã dừng viết kịch bản Muse. Bản nháp đã lưu được giữ lại.")
        return self._extract_json_array(self.runner.run(self._request(instruction)))

    async def _open(self, url):
        if self.page and not self.page.is_closed():
            return
        self.engine = await async_playwright().start()
        options = dict(user_data_dir=os.path.abspath(self.profile.path), headless=True,
                       executable_path=find_chromium_executable(headless=True), viewport={"width": 1280, "height": 800},
                       args=["--no-first-run"])
        proxy = (self.profile.proxy or self.global_proxy).strip()
        if proxy:
            parsed = parse_proxy(proxy)
            if not parsed:
                raise ValueError("Proxy của tài khoản Muse không hợp lệ.")
            options['proxy'] = parsed
        self.context = await self.engine.chromium.launch_persistent_context(**options)
        self.page = await self.context.new_page()
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        session = await wait_for_session(self.page)
        if session != 'authenticated':
            if self._stopped or self.page.is_closed():
                raise ValueError("Đã dừng chờ đăng nhập Muse; chưa gửi kịch bản.")
            if session == 'disconnected':
                if self.journal:
                    await self.page.screenshot(path=str(self.journal.with_suffix('.session.png')))
                raise ValueError(f"Muse báo ngắt kết nối tài khoản '{self.profile.name}' để bảo vệ thông tin. "
                                 "Trang yêu cầu Submit a ticket để được kết nối lại. Chưa gửi kịch bản; "
                                 "không cần xóa cookie hoặc nhập Gemini API key.")
            raise ValueError(f"Chưa xác nhận được phiên Muse của '{self.profile.name}'. "
                             "Bấm Mở/Đăng nhập trong app để kiểm tra tài khoản, đóng cửa sổ đăng nhập "
                             "rồi bấm tạo kịch bản lại. Chưa gửi yêu cầu kịch bản.")

    async def _request(self, instruction):
        record = {}
        if self.journal and self.journal.exists():
            record = json.loads(self.journal.read_text(encoding="utf-8"))
        resuming = record.get('status') == 'submitted'
        await self._open(record.get('url') if resuming else self.selectors.studio_url)
        if resuming:
            prompt = record['prompt']
            self.progress.emit("Đang lấy lại câu trả lời Muse đã gửi; không gửi trùng.")
        else:
            helper = AutomationWorker([], [], [], self.selectors)
            if not record:
                await helper._ensure_fresh_chat(self.page)
            prompt = ("CHỈ VIẾT KỊCH BẢN DƯỚI DẠNG JSON BẰNG VĂN BẢN. Không tạo ảnh/video, "
                      "không dùng công cụ tạo media, không hỏi xác nhận.\n"
                      + instruction + "\nÝ TƯỞNG PHIM:\n" + self.raw_script
                      + "\nMã yêu cầu văn bản: " + uuid.uuid4().hex)
            editor = self.page.locator('textarea, [contenteditable="true"]').filter(visible=True).first
            await editor.wait_for(state='visible', timeout=25000)
            await editor.fill(prompt)
            record = {'status': 'submitted', 'url': self.page.url, 'prompt': prompt}
            # Persist before Send. An interrupted run resumes this exact chat.
            self._write_journal(record)
            button = None
            for selector in self.selectors.submit_button:
                candidate = self.page.locator(selector).first
                if await candidate.count() and await candidate.is_visible() and await candidate.is_enabled():
                    button = candidate
                    break
            if button:
                await button.click()
            else:
                await editor.press('Enter')
        started, last, changed = time.monotonic(), '', time.monotonic()
        while not self._stopped:
            if self.page.is_closed():
                raise ValueError("Cửa sổ Muse đã đóng. Bấm tạo kịch bản để lấy lại tác vụ đã gửi.")
            disconnected = self.page.get_by_text('Muse is disconnected', exact=True)
            if await disconnected.count() and await disconnected.first.is_visible():
                raise ValueError("Muse đã ngắt kết nối khi đang viết. Yêu cầu được lưu để kiểm tra, không tự gửi lại.")
            if record.get('url') != self.page.url:
                record['url'] = self.page.url
                self._write_journal(record)
            text = await current_reply(self.page, prompt)
            if text != last:
                last, changed = text, time.monotonic()
            busy = await self.page.locator('button[aria-label*="stop" i]').filter(visible=True).count()
            if text and not busy and time.monotonic() - changed >= self.stable_seconds:
                # Parse only settled replies; the shared parser may preserve a
                # complete partial storyboard for the existing append workflow.
                record.update(status='complete', url=self.page.url, reply=text)
                self._write_journal(record)
                if not text.lstrip().startswith(('{', '```')) and any(phrase in text.lower() for phrase in (
                    'không thể hỗ trợ', 'không thể viết', "can't help", 'cannot help', 'vi phạm chính sách',
                )):
                    raise ValueError('Muse chưa chấp nhận yêu cầu viết kịch bản: ' + text[:600])
                return text
            if time.monotonic() - started >= self.response_timeout:
                raise ValueError("Chưa lấy được kịch bản Muse. Tác vụ đã lưu; bấm tạo lại để theo dõi tiếp, không gửi trùng.")
            self.progress.emit(f"Muse đang viết kịch bản ({int(time.monotonic()-started)} giây). Có thể bấm Dừng.")
            await asyncio.sleep(self.poll_seconds)
        raise ValueError("Đã dừng theo dõi Muse. Bấm tạo kịch bản để lấy lại tác vụ đã gửi, không gửi trùng.")
