"""Regression tests using real media and Chromium, without external generation."""
import asyncio
import base64
import json
import os
import subprocess
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication
from playwright.async_api import async_playwright

from core.media_output import (build_generation_prompt, detect_media_format,
                               validate_output, validate_audio_output)
from core.models import JobMode, TaskItem, ProfileItem, TaskStatus
from core.selectors import MuseSelectors
from config.settings import SettingsManager
from utils.file_utils import find_chromium_executable, find_ffmpeg_binary
from workers.automation_worker import AutomationWorker


class MediaFixtures:
    @classmethod
    def make(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="automuse-media-tests-")
        cls.root = Path(cls.temp.name)
        image = QImage(256, 256, QImage.Format.Format_RGB32)
        image.fill(QColor("#3344aa"))
        cls.images = {}
        for fmt in ("png", "jpg", "webp"):
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            assert image.save(buffer, fmt.upper())
            cls.images[fmt] = bytes(buffer.data())
            (cls.root / f"image.{fmt}").write_bytes(cls.images[fmt])
        cls.video = cls.root / "clip.mp4"
        cls.audio = cls.root / "voice.mp3"
        for args in [
            ["-f", "lavfi", "-i", "color=c=blue:s=256x256:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(cls.video)],
            ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "libmp3lame", str(cls.audio)],
        ]:
            subprocess.run([find_ffmpeg_binary(), "-y", "-v", "error", *args], check=True,
                           capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0)
        cls.video_bytes = cls.video.read_bytes()


class OutputValidationTests(unittest.TestCase, MediaFixtures):
    @classmethod
    def setUpClass(cls):
        cls.make()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_decodes_real_formats_and_checks_extension(self):
        for fmt, data in self.images.items():
            self.assertEqual(detect_media_format(data).extension, fmt)
            validate_output(str(self.root / f"image.{fmt}"), JobMode.TEXT_TO_IMAGE.value)
        disguised = self.root / "wrong.webp"
        disguised.write_bytes(self.images["png"])
        with self.assertRaises(ValueError):
            validate_output(str(disguised), JobMode.TEXT_TO_IMAGE.value)

    def test_image_and_video_cannot_be_swapped(self):
        validate_output(str(self.video), JobMode.TEXT_TO_VIDEO.value)
        for mode, path in [(JobMode.TEXT_TO_IMAGE.value, self.video),
                           (JobMode.TEXT_TO_VIDEO.value, self.root / "image.png"),
                           (JobMode.REFERENCE_IMAGE_TO_VIDEO.value, self.root / "image.png"),
                           (JobMode.TEXT_TO_IMAGE_TO_VIDEO.value, self.root / "image.png")]:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_output(str(path), mode)

    def test_html_corruption_and_audio_are_not_video(self):
        self.assertIsNone(detect_media_format(b"<html>Error</html>" * 100000))
        self.assertIsNone(detect_media_format(b"\x89PNG\r\n\x1a\ncorrupt"))
        invalid = self.root / "invalid.mp4"
        invalid.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")
        with self.assertRaises(ValueError):
            validate_output(str(invalid), JobMode.TEXT_TO_VIDEO.value)
        validate_audio_output(str(self.audio))
        with self.assertRaises(ValueError):
            validate_audio_output(str(self.video))

    def test_mode_instruction_wins_over_camera_language(self):
        task = TaskItem(id="image", prompt="Camera tracking, tạo video cảnh đường phố", mode=JobMode.TEXT_TO_IMAGE.value)
        prompt = build_generation_prompt(task)
        self.assertTrue(prompt.startswith("Tạo một ảnh tĩnh"))
        self.assertIn("không tạo video", prompt)
        for mode in [JobMode.TEXT_TO_VIDEO.value, JobMode.REFERENCE_IMAGE_TO_VIDEO.value]:
            task.mode = mode
            self.assertTrue(build_generation_prompt(task).startswith("Tạo một video"))
        task.mode = "UNKNOWN"
        with self.assertRaises(ValueError):
            build_generation_prompt(task)

    def test_video_uses_native_generator_in_both_video_modes(self):
        for mode in [JobMode.TEXT_TO_VIDEO.value, JobMode.REFERENCE_IMAGE_TO_VIDEO.value]:
            task = TaskItem(id="native", prompt="Báo tuyết đi chậm", mode=mode,
                            video_duration=10, aspect_ratio="16:9")
            prompt = build_generation_prompt(task)
            self.assertIn("media.generate_video", prompt)
            self.assertIn("Không chuyển sang Runway", prompt)
            self.assertIn("10 giây", prompt)
            self.assertIn("16:9", prompt)
            self.assertTrue(prompt.endswith(task.prompt))
        task.mode = JobMode.TEXT_TO_IMAGE.value
        self.assertNotIn("media.generate_video", build_generation_prompt(task))


class BrowserOutputTests(unittest.IsolatedAsyncioTestCase, MediaFixtures):
    @classmethod
    def setUpClass(cls):
        cls.make()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    async def asyncSetUp(self):
        self.engine = await async_playwright().start()
        self.browser = await self.engine.chromium.launch(headless=True, executable_path=find_chromium_executable())
        self.context = await self.browser.new_context()
        self.worker = AutomationWorker([], [], [], MuseSelectors(studio_url="http://fixture.test/"),
                                       output_dir=str(self.root / "results"), auto_new_chat=False, timeout_seconds=12)
        self.profile = ProfileItem(id="test", name="test", path=str(self.root / "profile"))
        self.sent = []
        self.return_kind = None
        test = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.endswith("result-image"):
                    body, mime = test.images["png"], "video/mp4"
                elif self.path.endswith("result-video"):
                    body, mime = test.video_bytes, "image/webp"
                else:
                    body, mime = b"<html>Error</html>" * 100000, "video/mp4"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        original_fetch = self.worker._fetch_result_bytes
        async def local_fetch(page, url):
            if url.startswith("http://fixture.test/"):
                url = url.replace("http://fixture.test", f"http://127.0.0.1:{self.server.server_port}", 1)
            return await original_fetch(page, url)
        self.worker._fetch_result_bytes = local_fetch

        async def route(request):
            url = request.request.url
            if url.endswith("/"):
                await request.fulfill(content_type="text/html", body="""
                    <main id="results"></main>
                    <form onsubmit="return false"><input type="file"><textarea placeholder="Message"></textarea>
                    <button type="submit" onclick="submitPrompt()">Send</button></form>
                    <script>async function submitPrompt() {
                        let text=document.querySelector('textarea').value;
                        let message=document.createElement('div'); message.textContent=text;
                        document.querySelector('main').appendChild(message);
                        let r=await fetch('/generate',{method:'POST',body:text});
                        let result=await r.json();
                        let link=document.createElement('a'); link.href=result.url;
                        link.download='result'; link.innerText='Download';
                        document.querySelector('main').appendChild(link);
                    }</script>
                """)
            elif url.endswith("/generate"):
                prompt = request.request.post_data
                self.sent.append(prompt)
                kind = self.return_kind or ("image" if prompt.startswith("Tạo một ảnh tĩnh") else "video")
                await request.fulfill(content_type="application/json", body=json.dumps({"url": f"/result-{kind}"}))
            elif url.endswith("result-image"):
                # Deliberately lie about MIME: bytes determine the output type.
                await request.fulfill(content_type="video/mp4", body=self.images["png"])
            elif url.endswith("result-video"):
                await request.fulfill(content_type="image/webp", body=self.video_bytes)
            elif url.endswith("invalid"):
                await request.fulfill(content_type="video/mp4", body=b"<html>error</html>" * 100000)
            else:
                await request.fulfill(status=404)
        await self.context.route("**/*", route)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.engine.stop()
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()

    async def test_mixed_dom_only_accepts_requested_type(self):
        page = await self.context.new_page()
        await page.goto("http://fixture.test/")
        await page.locator("main").evaluate("el => el.innerHTML='<a download href=\"/result-video\">Download video</a>'")
        self.assertIsNone(await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True))
        await page.locator("main").evaluate("el => el.innerHTML='<a download href=\"/result-image\">Download image</a>'")
        self.assertIsNone(await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=False))
        await page.locator("main").evaluate("el => el.innerHTML += '<a download href=\"/result-video\">Download video</a>'")
        image = await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True)
        video = await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=False)
        self.assertTrue(image.endswith(".png"))
        self.assertTrue(video.endswith(".mp4"))
        validate_output(image, JobMode.TEXT_TO_IMAGE.value)
        validate_output(video, JobMode.TEXT_TO_VIDEO.value)

    async def test_muse_image_card_outside_main_downloads_actual_blob(self):
        page = await self.context.new_page()
        await page.goto("http://fixture.test/")
        await page.set_content('<div id="conversation"></div>')
        url = await page.evaluate("""encoded => {
            const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
            const url = URL.createObjectURL(new Blob([bytes], {type:'image/png'}));
            document.querySelector('#conversation').innerHTML = '<button aria-label="Open generated image test" class="hatch-chat-groupable-bubble rounded-22" style="width:220px;height:124px;position:relative"><img style="width:220px;height:124px" src="'+url+'"></button>';
            return url;
        }""", base64.b64encode(self.images["png"]).decode())
        await page.locator('img').evaluate("el => el.decode()")
        self.assertEqual(await page.locator('main img, .chat img, [data-message] img, article img, div.space-y-4 img').count(), 0)
        result = await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True)
        self.assertIsNotNone(result)
        self.assertEqual(Path(result).read_bytes(), self.images["png"])

    async def test_late_old_card_is_ignored_but_new_same_title_is_accepted(self):
        page = await self.context.new_page()
        await page.goto("http://fixture.test/")
        await page.set_content('<div><button id="old" aria-label="Open generated image same title" aria-busy="true"></button></div>')
        await self.worker._mark_existing_result_cards(page)
        data_url = 'data:image/png;base64,' + base64.b64encode(self.images["png"]).decode()
        await page.locator('#old').evaluate("(el,url) => { el.removeAttribute('aria-busy'); el.innerHTML='<img src=\"'+url+'\">'; }", data_url)
        await page.locator('#old img').evaluate("el => el.decode()")
        self.assertIsNone(await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True))
        await page.evaluate("url => { const card=document.createElement('button'); card.setAttribute('aria-label','Open generated image same title'); card.id='new'; card.innerHTML='<img src=\"'+url+'\">'; document.body.appendChild(card); }", data_url)
        await page.locator('#new img').evaluate("el => el.decode()")
        self.assertIsNotNone(await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True))

    async def test_new_lazy_card_is_scrolled_into_view(self):
        page = await self.context.new_page()
        await page.goto("http://fixture.test/")
        await page.set_content('<div style="height:5000px"></div><button id="lazy" aria-label="Open generated image lazy" style="width:220px;height:124px"></button>')
        data_url = 'data:image/png;base64,' + base64.b64encode(self.images["png"]).decode()
        await page.evaluate("url => { new IntersectionObserver(entries => { for (const entry of entries) if (entry.isIntersecting) entry.target.innerHTML='<img src=\"'+url+'\">'; }).observe(document.querySelector('#lazy')); }", data_url)
        await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True)
        await page.locator('#lazy img').wait_for()
        await page.locator('#lazy img').evaluate("el => el.decode()")
        self.assertIsNotNone(await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True))

    async def test_old_media_reference_and_html_are_excluded(self):
        page = await self.context.new_page()
        await page.goto("http://fixture.test/")
        await page.locator("main").evaluate("el => el.innerHTML='<a download href=\"/result-image\">old</a><a download href=\"/invalid\">bad</a>'")
        self.assertIsNone(await self.worker._check_dom_real_media(page, "test", 1,
                          {"http://fixture.test/result-image"}, is_image_mode=True))
        import hashlib
        self.assertIsNone(await self.worker._check_dom_real_media(page, "test", 1, is_image_mode=True,
                          reference_hashes={hashlib.sha256(self.images["png"]).digest()}))

    async def test_results_must_follow_current_prompt_even_if_old_node_is_remounted(self):
        page = await self.context.new_page()
        await page.goto('http://fixture.test/')
        await page.set_content('<main><a download href="/result-image">old result</a><div>Current prompt</div></main>')
        self.assertIsNone(await self.worker._check_dom_real_media(page, 'test', 1, is_image_mode=True, prompt_text='Current prompt'))
        await page.locator('main').evaluate("el=>el.insertAdjacentHTML('beforeend','<a download href=\"/result-image\">new result</a>')")
        self.assertIsNotNone(await self.worker._check_dom_real_media(page, 'test', 1, is_image_mode=True, prompt_text='Current prompt'))

    async def test_all_four_modes_submit_and_return_correct_files(self):
        for mode in JobMode:
            with self.subTest(mode=mode.value):
                task = TaskItem(id=mode.name, prompt="Camera tracking qua đường phố", mode=mode.value)
                if mode == JobMode.REFERENCE_IMAGE_TO_VIDEO:
                    task.references = [str(self.root / "image.jpg")]
                before = len(self.sent)
                success, error, output = await self.worker._execute_task_on_profile(self.context, task, self.profile, 1)
                self.assertTrue(success, error)
                validate_output(output, mode.value)
                self.assertEqual(len(self.sent)-before, 2 if mode == JobMode.TEXT_TO_IMAGE_TO_VIDEO else 1)
                self.assertEqual(task.references, [str(self.root / "image.jpg")] if mode == JobMode.REFERENCE_IMAGE_TO_VIDEO else [])
                if mode == JobMode.TEXT_TO_IMAGE_TO_VIDEO:
                    validate_output(task.generated_image_file, JobMode.TEXT_TO_IMAGE.value)

    async def test_wrong_image_phase_stops_pipeline(self):
        task = TaskItem(id="pipeline", prompt="scene", mode=JobMode.TEXT_TO_IMAGE_TO_VIDEO.value)
        with patch.object(self.worker, "_execute_task_single_phase", new=AsyncMock(return_value=(True, "", str(self.video)))) as phase:
            success, error, output = await self.worker._execute_task_on_profile(self.context, task, self.profile, 1)
            self.assertFalse(success)
            self.assertEqual(output, "")
            self.assertEqual(phase.await_count, 1)

    async def test_wrong_product_from_site_is_not_success(self):
        self.worker.timeout_seconds = 0.2
        for mode, wrong in [(JobMode.TEXT_TO_IMAGE.value, "video"), (JobMode.TEXT_TO_VIDEO.value, "image")]:
            with self.subTest(mode=mode):
                self.return_kind = wrong
                self.worker._stop_requested = False
                task = TaskItem(id="wrong", prompt="scene", mode=mode)
                before = len(self.sent)
                job = asyncio.create_task(self.worker._execute_task_on_profile(self.context, task, self.profile, 1))
                for _ in range(100):
                    if len(self.sent) > before:
                        break
                    await asyncio.sleep(0.1)
                await asyncio.sleep(0.4)
                self.assertFalse(job.done(), "Wrong media must keep waiting instead of timing out or succeeding")
                self.worker.stop()
                success, error, output = await asyncio.wait_for(job, 5)
                self.assertFalse(success)
                self.assertEqual(output, "")
                self.assertNotIn("Timeout", error)

    async def test_waits_past_old_deadline_then_accepts_late_result(self):
        page = await self.context.new_page()
        task = TaskItem(id="late", prompt="scene", mode=JobMode.TEXT_TO_IMAGE.value)
        self.worker.timeout_seconds = 0.01
        with patch.object(self.worker, '_check_dom_real_media', new=AsyncMock(side_effect=[None, str(self.root / 'image.png')])), patch.object(self.worker, '_read_muse_feedback', new=AsyncMock(return_value=('waiting',''))):
            success, error, output = await self.worker._wait_for_result(page, task, self.profile, 1, set(), set(), 'scene')
        self.assertTrue(success, error)
        self.assertEqual(output, str(self.root / 'image.png'))
        self.assertEqual(self.sent, [])

    async def test_muse_complete_keeps_retrying_transient_download_error(self):
        page = await self.context.new_page()
        task = TaskItem(id="download", prompt="scene", mode=JobMode.TEXT_TO_IMAGE.value)
        self.worker.timeout_seconds = 0.01
        with patch.object(self.worker, '_check_dom_real_media', new=AsyncMock(side_effect=[OSError('temporary network failure'), None, str(self.root / 'image.png')])), patch.object(self.worker, '_read_muse_feedback', new=AsyncMock(return_value=('complete',''))):
            success, error, output = await self.worker._wait_for_result(page, task, self.profile, 1, set(), set(), 'scene')
        self.assertTrue(success, error)
        self.assertEqual(output, str(self.root / 'image.png'))

    async def test_only_current_muse_error_fails_generation(self):
        page = await self.context.new_page()
        await page.set_content('<div class="hatch-chat-groupable-bubble">Generation failed in old chat</div><div id="prompt">Current request</div><div class="hatch-chat-groupable-bubble" id="reply">Đang tạo video</div>')
        self.assertEqual((await self.worker._read_muse_feedback(page, 'Current request'))[0], 'waiting')
        await page.locator('#reply').evaluate("el=>el.innerText='Không thể tạo video: hết tín dụng'")
        task = TaskItem(id="error", prompt="Current request", mode=JobMode.TEXT_TO_VIDEO.value)
        with patch.object(self.worker, '_check_dom_real_media', new=AsyncMock(return_value=None)):
            success, error, output = await self.worker._wait_for_result(page, task, self.profile, 1, set(), set(), 'Current request')
        self.assertFalse(success)
        self.assertTrue(error.startswith('Muse báo lỗi:'))
        self.assertEqual(output, '')

    async def test_request_boundary_rejects_media_and_errors_after_next_user(self):
        page = await self.context.new_page()
        uri = 'data:image/png;base64,' + base64.b64encode(self.images['png']).decode()
        await page.set_content(f'<main><div data-message-author-role="user">Current prompt</div>'
            '<div data-message-author-role="assistant">Đang tạo ảnh</div>'
            '<div data-message-author-role="user">Unrelated next prompt</div>'
            f'<div data-message-author-role="assistant">Generation failed<img src="{uri}"></div></main>')
        await page.locator('img').evaluate('el=>el.decode()')
        self.assertIsNone(await self.worker._check_dom_real_media(page,'test',1,is_image_mode=True,prompt_text='Current prompt'))
        self.assertEqual((await self.worker._read_muse_feedback(page,'Current prompt'))[0],'waiting')

    async def test_request_uses_first_image_not_later_assistant_collage(self):
        page = await self.context.new_page()
        uri = 'data:image/png;base64,' + base64.b64encode(self.images['png']).decode()
        other = 'data:image/jpeg;base64,' + base64.b64encode(self.images['jpg']).decode()
        await page.set_content(f'<main><div data-message-author-role="user">Current prompt</div>'
            f'<button aria-label="Open generated image first"><img src="{uri}"></button>'
            f'<button aria-label="Open generated image later collage"><img src="{other}"></button></main>')
        await page.locator('img').evaluate_all('els=>Promise.all(els.map(el=>el.decode()))')
        output = await self.worker._check_dom_real_media(page,'test',1,is_image_mode=True,prompt_text='Current prompt')
        self.assertTrue(output.endswith('.png'), output)

    async def test_scrolling_current_request_mounts_virtual_reply(self):
        page = await self.context.new_page()
        uri = 'data:image/png;base64,' + base64.b64encode(self.images['png']).decode()
        await page.set_content('<div style="height:5000px"></div><main><div data-message-author-role="user">Current prompt</div>'
                               '<div id="reply" style="height:160px"></div></main>')
        await page.evaluate("""uri => new IntersectionObserver(entries => {
            if(entries.some(e=>e.isIntersecting)) document.querySelector('#reply').innerHTML =
                '<button aria-label="Open generated image"><img src="'+uri+'"></button>';
        }).observe(document.querySelector('#reply'))""",uri)
        output = await self.worker._check_dom_real_media(page,'test',1,is_image_mode=True,prompt_text='Current prompt')
        if not output:
            await page.locator('#reply img').wait_for()
            output = await self.worker._check_dom_real_media(page,'test',1,is_image_mode=True,prompt_text='Current prompt')
        self.assertIsNotNone(output)

    async def test_muse_alternative_stops_monitor_without_resubmitting(self):
        page = await self.context.new_page()
        await page.set_content('<div>Current request</div><div class="hatch-chat-groupable-bubble">Mình chưa tạo được video này theo đúng mô tả đó. Mình có thể làm một phương án khác. Bạn muốn mình làm theo hướng đó không?</div>')
        task = TaskItem(id="alternative", prompt="Current request", mode=JobMode.TEXT_TO_VIDEO.value)
        with patch.object(self.worker, '_check_dom_real_media', new=AsyncMock(return_value=None)):
            success, error, output = await asyncio.wait_for(self.worker._wait_for_result(page, task, self.profile, 1, set(), set(), 'Current request'), 5)
        self.assertFalse(success)
        self.assertTrue(error.startswith('WAITING: Cần sửa mô tả'))
        self.assertEqual(output, '')
        self.assertEqual(self.sent, [])

    async def test_old_alternative_does_not_stop_current_generation(self):
        page = await self.context.new_page()
        await page.set_content('<div class="hatch-chat-groupable-bubble">Chưa tạo được, có phương án khác</div><div>Current request</div><div class="hatch-chat-groupable-bubble">Đang tạo video theo phương án khác</div>')
        self.assertEqual((await self.worker._read_muse_feedback(page, 'Current request'))[0], 'waiting')

    async def test_direct_refusal_needs_input_but_unfinished_render_keeps_waiting(self):
        page = await self.context.new_page()
        await page.set_content('<div>Current request</div><div class="hatch-chat-groupable-bubble" id="reply">Mình chưa tạo xong video, đang xử lý.</div>')
        self.assertEqual((await self.worker._read_muse_feedback(page, 'Current request'))[0], 'waiting')
        for reply in ("Mình chưa tạo được video này theo đúng mô tả đó.", "I can't help create this content."):
            await page.locator('#reply').evaluate('(el, text) => el.innerText = text', reply)
            self.assertEqual((await self.worker._read_muse_feedback(page, 'Current request'))[0], 'needs_input')

    async def test_closed_monitor_page_is_waiting_not_generation_failure(self):
        page = await self.context.new_page()
        await page.close()
        task = TaskItem(id="closed", prompt="scene", mode=JobMode.TEXT_TO_IMAGE.value)
        success, message, output = await self.worker._wait_for_result(page, task, self.profile, 1, set(), set(), 'scene')
        self.assertFalse(success)
        self.assertTrue(message.startswith('WAITING:'))
        self.assertEqual(output, '')

    async def test_queue_does_not_mark_monitoring_interruption_as_failed(self):
        task = TaskItem(id='monitor', prompt='scene', mode=JobMode.TEXT_TO_IMAGE.value)
        self.worker.tasks = [task]
        self.worker.profiles = [self.profile]
        failed, completed, waiting = [], [], []
        self.worker.task_failed_signal.connect(lambda *args: failed.append(args))
        self.worker.task_completed_signal.connect(lambda *args: completed.append(args))
        self.worker.task_waiting_signal.connect(lambda *args: waiting.append(args))
        with patch.object(self.worker, '_execute_task_on_profile', new=AsyncMock(return_value=(False, 'WAITING: monitoring interrupted', ''))):
            await self.worker._main_loop()
        self.assertEqual(task.status, TaskStatus.WAITING.value)
        self.assertEqual(failed, [])
        self.assertEqual(completed, [])
        self.assertEqual(len(waiting), 1)

    async def test_pipeline_preserves_waiting_status_for_video_stage(self):
        task = TaskItem(id='pipeline-wait', prompt='scene', mode=JobMode.TEXT_TO_IMAGE_TO_VIDEO.value)
        with patch.object(self.worker, '_execute_task_single_phase', new=AsyncMock(side_effect=[
            (True, '', str(self.root / 'image.png')), (False, 'WAITING: monitoring interrupted', '')
        ])):
            success, message, output = await self.worker._execute_task_on_profile(self.context, task, self.profile, 1)
        self.assertFalse(success)
        self.assertTrue(message.startswith('WAITING:'))
        self.assertEqual(output, '')
        self.assertEqual(task.generated_image_file, str(self.root / 'image.png'))

    async def test_looping_result_video_is_accepted_but_avatar_is_not(self):
        page = await self.context.new_page()
        await page.goto('http://fixture.test/')
        await page.set_content('<div id="results"></div>')
        await page.evaluate("""encoded => {
            const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
            const url=URL.createObjectURL(new Blob([bytes],{type:'video/mp4'}));
            document.querySelector('#results').innerHTML='<video id="result" loop muted src="'+url+'" style="width:280px;height:280px"></video><video id="avatar" data-hatch-media-owner="avatar-layer" loop muted src="'+url+'" style="width:280px;height:280px"></video>';
        }""", base64.b64encode(self.video_bytes).decode())
        await page.wait_for_function("document.querySelector('#result').readyState >= 2 && document.querySelector('#avatar').readyState >= 2")
        result = await self.worker._check_dom_real_media(page, 'test', 1, is_image_mode=False)
        self.assertIsNotNone(result)
        validate_output(result, JobMode.TEXT_TO_VIDEO.value)
        await page.locator('#result').evaluate('el=>el.remove()')
        self.assertIsNone(await self.worker._check_dom_real_media(page, 'test', 1, is_image_mode=False))

    async def test_failed_video_does_not_report_intermediate_image_as_final(self):
        task = TaskItem(id="pipeline", prompt="scene", mode=JobMode.TEXT_TO_IMAGE_TO_VIDEO.value)
        with patch.object(self.worker, "_execute_task_single_phase", new=AsyncMock(side_effect=[
            (True, "", str(self.root / "image.png")), (True, "", str(self.root / "image.png"))
        ])):
            success, error, output = await self.worker._execute_task_on_profile(self.context, task, self.profile, 1)
            self.assertFalse(success)
            self.assertEqual(output, "")
            self.assertEqual(task.generated_image_file, str(self.root / "image.png"))

    async def test_missing_or_invalid_reference_never_submits(self):
        for refs in [[], [str(self.video)], [str(self.root / "missing.png")]]:
            task = TaskItem(id="reference", prompt="scene", mode=JobMode.REFERENCE_IMAGE_TO_VIDEO.value, references=refs)
            success, _, output = await self.worker._execute_task_on_profile(self.context, task, self.profile, 1)
            self.assertFalse(success)
            self.assertEqual(output, "")
        self.assertEqual(self.sent, [])

    async def test_signed_out_root_page_stops_before_upload_or_submission(self):
        await self.context.route("http://fixture.test/", lambda route: route.fulfill(
            content_type="text/html", body="<h1>Log in or create an account</h1>"))
        task = TaskItem(id="signed-out", prompt="scene", mode=JobMode.REFERENCE_IMAGE_TO_VIDEO.value,
                        references=[str(self.root / "image.png")])
        success, message, output = await self.worker._execute_task_on_profile(
            self.context, task, self.profile, 1)
        self.assertFalse(success)
        self.assertIn("trang chọn/đăng nhập", message)
        self.assertNotIn("Không tải được ảnh", message)
        self.assertEqual(output, "")
        self.assertEqual(self.sent, [])

    async def test_disconnected_muse_is_reported_before_editor_or_send(self):
        await self.context.route("http://fixture.test/", lambda route: route.fulfill(
            content_type="text/html", body="<h1>Muse is disconnected</h1><textarea></textarea>"))
        task = TaskItem(id="disconnected", prompt="scene", mode=JobMode.TEXT_TO_IMAGE.value)
        success, message, output = await self.worker._execute_task_on_profile(self.context, task, self.profile, 1)
        self.assertFalse(success)
        self.assertIn("Muse đã ngắt kết nối", message)
        self.assertEqual(output, "")
        self.assertEqual(self.sent, [])

    async def test_session_waits_for_landing_page_to_hydrate_into_chat(self):
        from core.muse_session import wait_for_session
        page = await self.context.new_page()
        await page.set_content('''<h1>Log in or create an account</h1>
            <script>setTimeout(()=>document.body.innerHTML='<textarea></textarea>', 700)</script>''')
        self.assertEqual(await wait_for_session(page, timeout=4), "authenticated")

    async def test_session_does_not_accept_hidden_editor_on_login_page(self):
        from core.muse_session import session_state
        page = await self.context.new_page()
        await page.set_content('<h1>Log in or create an account</h1><textarea hidden></textarea>')
        self.assertEqual(await session_state(page), "signed_out")

    async def test_session_rejects_cached_chat_before_signed_out_redirect(self):
        from core.muse_session import wait_for_session
        page = await self.context.new_page()
        await page.set_content('''<textarea></textarea>
            <script>setTimeout(()=>document.body.innerHTML='<h1>Log in or create an account</h1>', 500)</script>''')
        self.assertEqual(await wait_for_session(page, timeout=6), "signed_out")


class QueueOutputTests(unittest.TestCase, MediaFixtures):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.make()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.old_settings = SettingsManager._instance
        cfg = self.root / "settings.json"
        cfg.write_text('{}', encoding="utf-8")
        SettingsManager._instance = SettingsManager(str(cfg))
        from ui.right_panel import RightPanel
        self.panel = RightPanel()

    def tearDown(self):
        self.panel.close()
        SettingsManager._instance = self.old_settings

    def test_running_task_cannot_be_relabeled_or_retried(self):
        task = TaskItem(id="running", prompt="scene", mode=JobMode.TEXT_TO_VIDEO.value,
                        status=TaskStatus.PROCESSING.value)
        self.panel.settings.tasks = [task]
        self.panel.combo_mode.setCurrentText(JobMode.TEXT_TO_IMAGE.value)
        self.assertEqual(task.mode, JobMode.TEXT_TO_VIDEO.value)
        self.panel.set_running(True)
        self.panel._retry_single_task(task.id)
        self.assertEqual(task.status, TaskStatus.PROCESSING.value)
        self.assertFalse(self.panel.combo_mode.isEnabled())

    def test_retry_clears_stale_output(self):
        task = TaskItem(id="retry", prompt="scene", status="FAIL", output_file=str(self.video), error_message="old")
        self.panel.settings.tasks = [task]
        self.panel._retry_single_task(task.id)
        self.assertEqual(task.output_file, "")
        self.assertEqual(task.error_message, "")

    def test_waiting_message_is_shown_and_persisted_without_failure(self):
        task = TaskItem(id='waiting', prompt='scene', status=TaskStatus.PROCESSING.value)
        self.panel.settings.tasks = [task]
        self.panel.on_task_waiting(task.id, 'test', 'Chưa xác nhận Muse thất bại')
        self.assertEqual(task.status, TaskStatus.WAITING.value)
        self.assertEqual(task.error_message, '')
        restored = TaskItem.from_dict(task.to_dict())
        self.assertEqual(restored.progress_message, 'Chưa xác nhận Muse thất bại')

    def test_completion_and_saved_history_reject_mismatch(self):
        task = TaskItem(id="image", prompt="scene", mode=JobMode.TEXT_TO_IMAGE.value)
        self.panel.settings.tasks = [task]
        self.panel.on_task_completed(task.id, "test", str(self.video))
        self.assertEqual(task.status, "FAIL")
        self.assertEqual(task.output_file, "")
        task.status = "OK - [test]"
        task.output_file = str(self.video)
        self.panel._audit_saved_outputs()
        self.assertEqual(task.status, "FAIL")
        self.assertTrue(self.video.exists())

    def test_fpt_uses_fpt_key_and_voice(self):
        from ui.dialogs.tts_dialog import TTSDialog
        self.panel.settings.tts_config.update(provider="fpt", fpt_api_key="fpt-test", elevenlabs_api_key="eleven-test", fpt_voice="banmai")
        dialog = TTSDialog()
        dialog.txt_content.setPlainText("Xin chao")
        with patch("ui.dialogs.tts_dialog.TTSEngineWorker", return_value=MagicMock()) as factory:
            dialog._start_tts()
            self.assertEqual(factory.call_args.kwargs["api_key"], "fpt-test")
            self.assertEqual(factory.call_args.kwargs["voice"], "banmai")
        dialog.close()


class OtherOutputTests(unittest.TestCase, MediaFixtures):
    @classmethod
    def setUpClass(cls):
        cls.make()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_tts_never_reports_html_as_audio(self):
        from workers.tts_engine import TTSEngineWorker
        for valid in [False, True]:
            worker = TTSEngineWorker(text="test", output_dir=str(self.root / "tts"))
            outputs, errors = [], []
            worker.finished_signal.connect(outputs.append)
            worker.error_signal.connect(errors.append)
            async def generate(path):
                Path(path).write_bytes(self.audio.read_bytes() if valid else b"<html>Error</html>" * 1000)
            with patch.object(worker, "_run_edge_tts", new=generate):
                worker.run()
            self.assertEqual(bool(outputs), valid)
            self.assertEqual(bool(errors), not valid)

    def test_video_merge_checks_inputs_and_actual_output(self):
        from workers.video_merger import VideoMergerWorker
        quoted = self.root / "clip's.mp4"
        quoted.write_bytes(self.video_bytes)
        for files, valid in [([str(self.video), str(quoted)], True), ([str(self.root / "image.png")], False)]:
            worker = VideoMergerWorker(files, str(self.root / "joined.mp4"))
            outputs, errors = [], []
            worker.finished_signal.connect(outputs.append)
            worker.error_signal.connect(errors.append)
            worker.run()
            self.assertEqual(bool(outputs), valid, errors)
            self.assertEqual(bool(errors), not valid)
            if valid:
                validate_output(outputs[0], JobMode.TEXT_TO_VIDEO.value)

    def test_llm_result_is_a_list_of_nonempty_prompts(self):
        from workers.llm_rewriter import LLMRewriterWorker
        worker = LLMRewriterWorker("scene", 1, [])
        self.assertEqual(worker._extract_json_array('["scene"]'), ["scene"])
        for raw in ['{}', '[null]', '[42]', '[" "]', '[]']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                worker._extract_json_array(raw)


if __name__ == "__main__":
    unittest.main()
