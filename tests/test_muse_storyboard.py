import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from playwright.async_api import async_playwright
from core.models import ProfileItem
from core.selectors import MuseSelectors
from utils.file_utils import find_chromium_executable
from workers.muse_storyboard_worker import MuseStoryboardWorker
from workers.film_storyboard_worker import FilmStoryboardWorker
from test_storyboard_completion import data


class MuseStoryboardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.engine = await async_playwright().start()
        self.browser = await self.engine.chromium.launch(headless=True, executable_path=find_chromium_executable())
        self.page = await self.browser.new_page()
        await self.page.set_content('<div data-message-author-role="assistant">Old unrelated answer</div><textarea></textarea><button aria-label="Send">Send</button>')
        await self.page.evaluate("""payload => {
          window.sent = 0;
          document.querySelector('button').onclick = () => {
            window.sent++;
            let user = document.createElement('div');
            user.dataset.messageAuthorRole = 'user';
            user.innerText = document.querySelector('textarea').value;
            document.body.append(user);
            let answer = document.createElement('div');
            answer.dataset.messageAuthorRole = 'assistant';
            answer.innerText = JSON.stringify(payload);
            document.body.append(answer);
          };
        }""", data(2))
        self.worker = MuseStoryboardWorker('Robot', 20, 10, '', ProfileItem(id='test',name='test',path=str(self.root)),
                                           MuseSelectors(), checkpoint_path=self.root/'draft.json')
        self.worker.page = self.page
        self.worker.stable_seconds = 0
        self.worker.poll_seconds = .01
        self.worker.response_timeout = 2
        self.worker._open = AsyncMock()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.engine.stop()
        self.temp.cleanup()

    async def test_text_only_request_reads_current_reply_not_old_chat(self):
        result = await self.worker._request('Write JSON')
        self.assertEqual(json.loads(result), data(2))
        self.assertEqual(await self.page.evaluate('window.sent'), 1)
        journal = json.loads(self.worker.journal.read_text(encoding='utf-8'))
        self.assertEqual(journal['status'], 'complete')
        self.assertIn('Không tạo ảnh/video', journal['prompt'])

    async def test_submitted_journal_resumes_without_another_send(self):
        self.worker._write_journal({'status':'submitted','url':'https://muse.ai/chat/test','prompt':'Existing request'})
        await self.page.evaluate("""payload => {
            let user=document.createElement('div'); user.innerText='Existing request'; document.body.append(user);
            let reply=document.createElement('div'); reply.dataset.messageAuthorRole='assistant';
            reply.innerText=JSON.stringify(payload); document.body.append(reply);
        }""", data(2))
        result = await self.worker._request('Do not send this again')
        self.assertEqual(json.loads(result), data(2))
        self.assertEqual(await self.page.evaluate('window.sent'), 0)

    async def test_timeout_preserves_submitted_request_for_resume(self):
        await self.page.evaluate("() => { document.querySelector('button').onclick = () => window.sent++; }")
        self.worker.response_timeout = .03
        with self.assertRaisesRegex(ValueError, 'không gửi trùng'):
            await self.worker._request('Write JSON')
        self.assertEqual(json.loads(self.worker.journal.read_text(encoding='utf-8'))['status'], 'submitted')
        self.assertEqual(await self.page.evaluate('window.sent'), 1)

    async def test_refusal_is_reported_instead_of_being_treated_as_json_to_repair(self):
        self.worker._write_journal({'status':'submitted','url':'https://muse.ai/chat/test','prompt':'Existing request'})
        await self.page.set_content('<div>Existing request</div><div data-message-author-role="assistant">Mình không thể hỗ trợ yêu cầu này.</div>')
        with self.assertRaisesRegex(ValueError, 'chưa chấp nhận'):
            await self.worker._request('Unused')
        self.assertEqual(json.loads(self.worker.journal.read_text(encoding='utf-8'))['status'], 'complete')

    async def test_shared_planner_accepts_muse_without_gemini_api_key(self):
        ready, errors = [], []
        self.worker.storyboard_ready.connect(ready.append)
        self.worker.error_signal.connect(errors.append)
        with patch.object(self.worker, '_call_muse', return_value=data(2)) as call:
            FilmStoryboardWorker.run(self.worker)
        self.assertEqual(call.call_count, 1)
        self.assertFalse(errors)
        self.assertEqual(len(ready[0]['shots']), 2)

    async def test_hidden_browser_reports_expired_login_without_waiting_or_sending(self):
        self.worker.page = None
        try:
            with patch('workers.muse_storyboard_worker.wait_for_session', new=AsyncMock(return_value='signed_out')):
                with self.assertRaisesRegex(ValueError, 'Mở/Đăng nhập'):
                    await MuseStoryboardWorker._open(self.worker, 'about:blank')
            session = await self.worker.context.browser.new_browser_cdp_session()
            browser_version = await session.send('Browser.getVersion')
            self.assertIn('HeadlessChrome', browser_version['userAgent'])
            self.assertFalse(self.worker.journal.exists())
            await session.detach()
        finally:
            await self.worker._close()
