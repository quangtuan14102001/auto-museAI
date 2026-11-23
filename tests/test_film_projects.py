import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from core.film_project import FilmStore, plan_film, film_prompt
from core.models import ProfileItem, JobMode
from core.selectors import MuseSelectors
from core.media_output import validate_output
from utils.film_media import run_ffmpeg, normalize_clip, extract_frame, assemble_film, probe_video
from workers.film_worker import FilmWorker, FilmImportWorker
from config.settings import SettingsManager


class Fixture:
    @classmethod
    def make_media(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="automuse-film-tests-")
        cls.root = Path(cls.temp.name)
        cls.source = str(cls.root / "source.mp4")
        run_ffmpeg(["-y", "-f", "lavfi", "-i", "color=red:s=160x90:r=24:d=2.5",
                    "-f", "lavfi", "-i", "color=blue:s=160x90:r=24:d=2.5",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.source])

    def store(self, name, seconds=6, paragraphs=None, review=True):
        project = plan_film("Test film", paragraphs or ["A subject moves to the right"], seconds, 5,
                            continuity_notes="Same subject and blue jacket")
        project.width, project.height = 160, 90
        project.review_required = review
        store = FilmStore(self.root / name / "project.film.json", project)
        store.save()
        return store


class FilmPlanTests(unittest.TestCase):
    def test_ten_minute_plan_has_sixty_clips_and_explicit_scene_boundaries(self):
        project = plan_film("10 minute movie", ["Scene A", "Scene B"], 600, 10)
        self.assertEqual(len(project.shots), 60)
        self.assertEqual(sum(shot.timeline_seconds for shot in project.shots), 600)
        self.assertFalse(project.shots[0].continuation)
        self.assertFalse(project.shots[30].continuation)
        self.assertEqual(sum(shot.continuation for shot in project.shots), 58)
        self.assertTrue(project.review_required)

    def test_remainder_is_trimmed_on_timeline_not_looped_or_slowed(self):
        project = plan_film("Remainder", ["Scene"], 601, 10)
        self.assertEqual(len(project.shots), 61)
        self.assertEqual(project.shots[-1].timeline_seconds, 1)
        self.assertEqual(project.shots[-1].request_seconds, 10)

    def test_invalid_plans_are_rejected(self):
        for paragraphs, seconds, clip in [([], 600, 10), (["A"], 0, 10), (["A"], 600, 20), (["A", "B"], 5, 10)]:
            with self.subTest(seconds=seconds, paragraphs=paragraphs), self.assertRaises(ValueError):
                plan_film("Test", paragraphs, seconds, clip)


class FilmStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = plan_film("Movie", ["A", "B"], 20, 5)
        self.store = FilmStore(self.root / "project.film.json", self.project)
        self.store.save()

    def tearDown(self):
        self.temp.cleanup()

    def test_interrupted_submitted_scene_is_not_ready_for_duplicate_generation(self):
        self.project.shots[0].status = "GENERATING"
        self.project.shots[0].submission_url = "https://muse.ai/"
        self.store.save()
        restored = FilmStore.load(self.store.manifest)
        self.assertEqual(restored.project.shots[0].status, "WAITING")
        self.assertTrue(restored.project.shots[0].error)

    def test_invalidation_preserves_takes_and_stops_at_new_scene(self):
        for shot in self.project.shots:
            shot.status, shot.clip = "APPROVED", "shots/old.mp4"
        old = self.root / "shots/old.mp4"
        old.parent.mkdir()
        old.write_bytes(b"old artifact")
        changed = self.store.invalidate_from(0)
        self.assertEqual(changed, [0, 1])
        self.assertEqual(self.project.shots[1].status, "PENDING")
        self.assertEqual(self.project.shots[2].status, "APPROVED")
        self.assertEqual(self.project.shots[0].history[0]["clip"], "shots/old.mp4")
        self.assertTrue(old.exists())

    def test_project_paths_and_clip_ids_cannot_escape_project_folder(self):
        with self.assertRaises(ValueError):
            self.store.asset("../outside.mp4")
        self.project.shots[0].id = "../../outside"
        self.store.save()
        with self.assertRaises(ValueError):
            FilmStore.load(self.store.manifest)

    def test_continuation_prompt_preserves_rules_and_first_reference_role(self):
        project = plan_film("Movie", ["Walk right"], 10, 5, continuity_notes="Blue jacket")
        text = film_prompt(project, project.shots[1])
        self.assertIn("KHUNG HÌNH CUỐI", text)
        self.assertIn("Blue jacket", text)
        self.assertIn("Walk right", text)


class FilmMediaTests(unittest.TestCase, Fixture):
    @classmethod
    def setUpClass(cls):
        cls.make_media()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_last_frame_is_from_trimmed_clip_not_end_of_original(self):
        clip = normalize_clip(self.source, str(self.root / "trimmed.mp4"), 2, (160, 90))
        frame = extract_frame(clip, str(self.root / "last.png"), last=True)
        color = QImage(frame).pixelColor(50, 40)
        self.assertGreater(color.red(), 200)
        self.assertLess(color.blue(), 30)
        self.assertTrue(probe_video(clip)["audio"], "Silent inputs need a compatible audio stream")

    def test_short_clip_is_rejected_without_replacing_previous_good_file(self):
        target = self.root / "keep.mp4"
        target.write_bytes(b"previous export")
        with self.assertRaises(ValueError):
            normalize_clip(self.source, target, 6, (160, 90))
        self.assertEqual(target.read_bytes(), b"previous export")
        with self.assertRaises(RuntimeError):
            normalize_clip(self.source, target, 2, (160, 90), stop=lambda: True)
        self.assertEqual(target.read_bytes(), b"previous export")

    def test_modified_clip_is_not_silently_used_for_continuation_or_export(self):
        store = self.store("tampered", 5, review=False)
        worker = FilmImportWorker(store, 0, self.source)
        worker.run()
        shot = store.project.shots[0]
        self.assertTrue(shot.clip_sha256)
        Path(store.asset(shot.last_frame)).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            store.check_integrity(shot)

    def test_import_normalizes_clip_and_requires_review(self):
        store = self.store("import", 5)
        worker = FilmImportWorker(store, 0, self.source)
        worker.run()
        shot = store.project.shots[0]
        self.assertEqual(shot.status, "REVIEW", shot.error)
        validate_output(store.asset(shot.clip), JobMode.TEXT_TO_VIDEO.value)
        self.assertTrue(Path(store.asset(shot.first_frame)).is_file())
        self.assertTrue(Path(store.asset(shot.last_frame)).is_file())
        with self.assertRaises(ValueError):
            assemble_film(store, self.root / "unreviewed.mp4")

    def test_export_mixes_music_and_narration_without_looping_narration(self):
        store = self.store("audio-export", 2, review=False)
        importer = FilmImportWorker(store, 0, self.source)
        importer.run()
        music, voice = str(self.root / "music.wav"), str(self.root / "voice.wav")
        for path, duration, frequency in [(music, 0.5, 220), (voice, 1, 440)]:
            run_ffmpeg(["-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}", path])
        output = assemble_film(store, store.root / "movie.mp4", music, voice, keep_clip_audio=False)
        metadata = probe_video(output)
        self.assertTrue(metadata["audio"])
        self.assertAlmostEqual(metadata["duration"], 2, delta=0.1)

    def test_real_sixty_clip_export_lasts_ten_minutes(self):
        project = plan_film("600 seconds", ["Sequence"], 600, 10)
        project.width, project.height = 160, 90
        store = FilmStore(self.root / "ten-minute" / "project.film.json", project)
        store.save()
        source = str(self.root / "ten-second.mp4")
        run_ffmpeg(["-y", "-f", "lavfi", "-i", "color=green:s=160x90:r=24:d=10", "-c:v", "libx264", source])
        clip = normalize_clip(source, store.root / "normalized.mp4", 10, (160, 90))
        for shot in project.shots:
            shot.clip, shot.status = store.relative(clip), "APPROVED"
        output = assemble_film(store, store.root / "film-600s.mp4")
        self.assertAlmostEqual(probe_video(output)["duration"], 600, delta=0.1)
        self.assertTrue(Path(output).stat().st_size > 0)


class FilmGenerationTests(unittest.IsolatedAsyncioTestCase, Fixture):
    @classmethod
    def setUpClass(cls):
        cls.make_media()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def worker(self, store):
        profile = ProfileItem("test", "test", str(store.root / "test-profile"))
        return FilmWorker(store, profile, MuseSelectors())

    async def test_visual_review_findings_or_api_failure_require_manual_review(self):
        for error in (False, True):
            store = self.store(f"visual-{error}", 5, review=False)
            store.project.visual_review_enabled = True
            worker = self.worker(store)
            with patch("core.film_visual_review.review_shot", side_effect=ValueError("offline") if error else None,
                       return_value={"verdict": "review", "summary": "Trang phục bị đổi", "issues": ["Trang phục"]}):
                await worker._prepare_and_review(0, self.source)
            self.assertEqual(store.project.shots[0].status, "REVIEW")
            self.assertEqual(store.project.shots[0].approved_by, "")
            self.assertTrue(store.project.shots[0].error)
            self.assertFalse(store.project.ready_to_export)

    async def test_sequential_generation_passes_actual_last_frame_to_next_clip(self):
        store = self.store("sequential", 6, review=False)
        worker = self.worker(store)
        calls = []
        async def generate(context, task, profile, index):
            browser_session = await context.browser.new_browser_cdp_session()
            browser_version = await browser_session.send("Browser.getVersion")
            self.assertIn("HeadlessChrome", browser_version["userAgent"])
            await browser_session.detach()
            self.assertFalse(worker.wait_for_login)
            calls.append((task.mode, list(task.references)))
            return True, "", self.source
        with patch.object(worker, "_execute_task_on_profile", new=generate):
            await worker._render_film()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], JobMode.TEXT_TO_IMAGE_TO_VIDEO.value)
        self.assertEqual(calls[1][0], JobMode.REFERENCE_IMAGE_TO_VIDEO.value)
        self.assertEqual(calls[1][1][0], store.asset(store.project.shots[0].last_frame))
        self.assertTrue(store.project.ready_to_export)

    async def test_review_gate_and_resume_reuse_approved_clip(self):
        store = self.store("review-resume", 6)
        worker = self.worker(store)
        with patch.object(worker, "_execute_task_on_profile", new=AsyncMock(return_value=(True, "", self.source))) as generate:
            await worker._render_film()
            self.assertEqual(generate.await_count, 1)
        self.assertEqual(store.project.shots[0].status, "REVIEW")
        self.assertEqual(store.project.shots[1].status, "PENDING")
        first = store.project.shots[0]
        original_clip = first.clip
        first.status, first.approved_by = "APPROVED", "manual"
        store.save()
        restored = FilmStore.load(store.manifest)
        worker = self.worker(restored)
        with patch.object(worker, "_execute_task_on_profile", new=AsyncMock(return_value=(True, "", self.source))) as generate:
            await worker._render_film()
            self.assertEqual(generate.await_count, 1)
        self.assertEqual(restored.project.shots[0].clip, original_clip)
        self.assertEqual(restored.project.shots[1].status, "REVIEW")

    async def test_waiting_scene_never_automatically_submits_again(self):
        store = self.store("waiting", 5)
        store.project.shots[0].status = "WAITING"
        worker = self.worker(store)
        with patch.object(worker, "_execute_task_on_profile", new=AsyncMock()) as generate:
            await worker._render_film()
            generate.assert_not_awaited()

    async def test_submission_checkpoint_is_saved_before_send(self):
        store = self.store("checkpoint", 5)
        worker = self.worker(store)
        shot = store.project.shots[0]
        worker.current_shot = shot
        shot.status = "GENERATING"
        from core.models import TaskItem
        class Page:
            url = "https://muse.ai/"
        await worker._before_submit(Page(), TaskItem("id", "scene"), "Actual submitted prompt")
        saved = json.loads(store.manifest.read_text(encoding="utf-8"))
        self.assertEqual(saved["shots"][0]["submitted_prompt"], "Actual submitted prompt")
        self.assertTrue(worker.submitted)


class FilmDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_can_load_plan_show_review_and_export_gate(self):
        from ui.dialogs.film_dialog import FilmDialog
        original = SettingsManager._instance
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            cfg.write_text('{}')
            SettingsManager._instance = SettingsManager(str(cfg))
            try:
                dialog = FilmDialog()
                project = plan_film("UI", ["Scene"], 600, 10)
                dialog.store = FilmStore(Path(tmp) / "project.film.json", project)
                dialog.store.save()
                dialog._refresh()
                self.assertEqual(dialog.table.rowCount(), 60)
                self.assertTrue(dialog.review_required.isChecked())
                self.assertFalse(dialog.export_button.isEnabled())
                dialog._set_busy(True)
                self.assertFalse(dialog.start_button.isEnabled())
                self.assertTrue(dialog.stop_button.isEnabled())
                dialog._set_busy(False)
                dialog.close()
            finally:
                SettingsManager._instance = original


if __name__ == "__main__":
    unittest.main()
