import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from PyQt6.QtGui import QImage, QColor
from core.film_project import (FilmReference, FilmStore, plan_film, film_prompt,
                               shot_reference_assets, validate_continuity)
from core.models import JobMode, ProfileItem, TaskItem
from core.selectors import MuseSelectors
from workers.film_worker import FilmWorker
from workers.automation_worker import AutomationWorker
from workers.film_storyboard_worker import apply_storyboard


def outline():
    return {"characters": [{"id": "robot", "name": "Rô", "description": "Robot trắng, ba lô đỏ"}],
            "locations": [{"id": "forest", "name": "Rừng", "description": "Cầu đá phía trái, bình minh"}],
            "shots": [{"action": "Robot nhặt bản đồ.", "sequence": 1, "continuation": False,
                       "character_ids": ["robot"], "location_id": "forest", "start_state": "Tay trống", "end_state": "Cầm bản đồ"},
                      {"action": "Robot bước lên cầu đá.", "sequence": 1, "continuation": True,
                       "character_ids": ["robot"], "location_id": "forest", "start_state": "Cầm bản đồ", "end_state": "Trên cầu, cầm bản đồ"}]}


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = apply_storyboard(outline(), "Robot", 20, 10, "16:9", "so1", "Hoạt hình 3D")
        self.store = FilmStore(self.root / "project.film.json", self.project)
        for index, ref in enumerate(self.project.references):
            image = QImage(32, 32, QImage.Format.Format_RGB32)
            image.fill(QColor("red" if index == 0 else "blue"))
            source = self.root / f"{ref.id}.png"
            image.save(str(source))
            relative = self.store.snapshot(source, "canonical")
            ref.images, ref.image_hashes = [relative], {relative: self.store.digest(self.store.asset(relative))}
        self.store.save()

    def tearDown(self):
        self.temp.cleanup()

    def test_storyboard_contains_individual_actions_and_state(self):
        self.assertNotEqual(self.project.shots[0].prompt, self.project.shots[1].prompt)
        self.assertEqual(self.project.shots[1].start_state, self.project.shots[0].end_state)
        text = film_prompt(self.project, self.project.shots[1])
        for word in ("Rô", "ba lô đỏ", "Cầu đá", "Cầm bản đồ", "KHUNG HÌNH CUỐI"):
            self.assertIn(word, text)

    def test_only_shot_characters_and_location_are_attached(self):
        unused = copy.deepcopy(self.project.references[0])
        unused.id, unused.name = "stranger", "Người lạ"
        self.project.references.append(unused)
        files, audit = shot_reference_assets(self.store, self.project.shots[0])
        self.assertEqual(len(files), 2)
        self.assertEqual({item["id"] for item in audit}, {"robot", "forest"})

    def test_changed_canonical_file_is_rejected(self):
        Path(self.store.asset(self.project.references[0].images[0])).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "thay đổi"):
            shot_reference_assets(self.store, self.project.shots[0])

    def test_state_and_location_discontinuity_are_rejected(self):
        self.project.shots[1].start_state = "Tay trống"
        with self.assertRaisesRegex(ValueError, "trạng thái"):
            validate_continuity(self.project)
        self.project.shots[1].start_state = "Cầm bản đồ"
        self.project.shots[1].location_id = ""
        with self.assertRaisesRegex(ValueError, "bối cảnh"):
            validate_continuity(self.project)

    def test_missing_ids_and_duplicate_actions_are_rejected(self):
        for mutate in [lambda d: d["shots"][0].update(character_ids=["ghost"]),
                       lambda d: d["shots"][1].update(action=d["shots"][0]["action"])]:
            data = outline()
            mutate(data)
            with self.assertRaises(ValueError):
                apply_storyboard(data, "Robot", 20, 10, "16:9", "so1", "")

    def test_references_round_trip_and_v1_backup(self):
        loaded = FilmStore.load(self.store.manifest)
        self.assertEqual(loaded.project.references[0].image_hashes, self.project.references[0].image_hashes)
        legacy = plan_film("Legacy", ["Walk"], 10, 10)
        legacy.format_version = 1
        from dataclasses import asdict
        data = asdict(legacy)
        data.pop("references")
        self.store.manifest.write_text(json.dumps(data))
        migrated = FilmStore.load(self.store.manifest)
        migrated.save()
        self.assertEqual(migrated.project.format_version, 2)
        self.assertTrue(self.store.manifest.with_name("project.film.v1.backup.json").exists())

    def worker(self):
        return FilmWorker(self.store, ProfileItem("so1", "so1", str(self.root / "profile")), MuseSelectors())

    def test_reference_roles_differ_between_image_and_video_phases(self):
        worker = self.worker()
        files, _ = shot_reference_assets(self.store, self.project.shots[0])
        task = TaskItem("shot", "Move", mode=JobMode.TEXT_TO_IMAGE.value, references=files)
        image_text = worker._build_generation_prompt(task)
        self.assertIn("Ảnh 1: Rô", image_text)
        self.assertIn("Ảnh 2: Rừng", image_text)
        frame = self.root / "frame.png"
        QImage(self.store.asset(self.project.references[0].images[0])).save(str(frame))
        task.mode, task.references = JobMode.REFERENCE_IMAGE_TO_VIDEO.value, [str(frame), *files]
        video_text = worker._build_generation_prompt(task)
        self.assertIn("Ảnh 1: Khung bắt đầu video", video_text)
        self.assertIn("Ảnh 2: Rô", video_text)
        self.assertIn("Ảnh 3: Rừng", video_text)

    def test_pipeline_keeps_original_references_in_video_phase(self):
        worker = AutomationWorker([], [], [], MuseSelectors(), output_dir=str(self.root))
        files, _ = shot_reference_assets(self.store, self.project.shots[0])
        task = TaskItem("pipeline", "Move", mode=JobMode.TEXT_TO_IMAGE_TO_VIDEO.value, references=files)
        image, video = str(self.root / "frame.png"), str(self.root / "video.mp4")
        with patch.object(worker, "_execute_validated_phase", new=AsyncMock(side_effect=[(True, "", image), (True, "", video)])) as phase:
            result = asyncio.run(worker._execute_task_on_profile(None, task, ProfileItem("so1", "so1", "unused"), 1))
        self.assertTrue(result[0])
        self.assertEqual(phase.call_args_list[1].args[1].references, [image, *files])
        self.assertEqual(task.references, files)

    def test_pending_reference_is_generated_once_then_reused(self):
        worker = self.worker()
        ref = self.project.references[0]
        source = self.store.asset(ref.images[0])
        ref.images, ref.image_hashes = [], {}
        with patch.object(worker, "_execute_validated_phase", new=AsyncMock(return_value=(True, "", source))) as generate:
            asyncio.run(worker._ensure_canonical_references(None, worker.profiles[0]))
            asyncio.run(worker._ensure_canonical_references(None, worker.profiles[0]))
        self.assertEqual(generate.await_count, 1)
        self.assertTrue(ref.images)

    def test_interrupted_reference_is_not_submitted_again(self):
        worker = self.worker()
        ref = self.project.references[0]
        ref.images, ref.generation_status, ref.submitted_prompt = [], "WAITING", "already sent"
        with patch.object(worker, "_execute_validated_phase", new=AsyncMock()) as generate:
            with self.assertRaises(ValueError):
                asyncio.run(worker._ensure_canonical_references(None, worker.profiles[0]))
            generate.assert_not_awaited()

    def test_unsent_reference_failure_is_rechecked_after_login(self):
        worker = self.worker()
        ref = self.project.references[0]
        source = self.store.asset(ref.images[0])
        ref.images, ref.image_hashes = [], {}
        ref.generation_status, ref.error = "FAILED", "Old disconnected page"
        ref.submitted_prompt = ""
        with patch.object(worker, "_execute_validated_phase", new=AsyncMock(return_value=(True, "", source))) as generate:
            asyncio.run(worker._ensure_canonical_references(None, worker.profiles[0]))
        self.assertEqual(generate.await_count, 1)
        self.assertEqual(ref.generation_status, "READY")
        self.assertEqual(ref.error, "")
