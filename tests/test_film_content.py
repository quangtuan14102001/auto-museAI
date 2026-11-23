import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.film_content import inspect_text, inspect_project
from core.film_project import FilmStore
from core.models import ProfileItem
from core.selectors import MuseSelectors
from workers.film_worker import FilmWorker
from workers.film_storyboard_worker import FilmStoryboardWorker, apply_storyboard
from test_storyboard_completion import data


class FilmContentTests(unittest.TestCase):
    def test_original_vietnamese_refused_actions_and_states_are_found(self):
        for text in ("Chuột Xám cắn mạnh vào chân Mèo Đen", "Cào một đường rách sâu trên mặt",
                     "Mèo Đen bị cào trúng mặt, gầm thét đau đớn", "Deep wound with exposed organs",
                     "Chuột có bộ lông bết máu khô", "Vết cào sâu trên mặt mèo"):
            with self.subTest(text=text):
                self.assertTrue(inspect_text(text, "action"))

    def test_negation_and_benign_horror_do_not_get_flagged(self):
        for text in ("Không máu me, không có khỏa thân, không thương tích.",
                     "Không mô tả vết thương hở. Without nudity.",
                     "Mèo Đen rình rập; Chuột Xám lăn né rồi chạy sau thùng gỗ.",
                     "Bóng ma vụt qua ánh đèn đỏ, nhịp tim dồn dập.", "Mèo ăn cơm, chuột cắn miếng bánh.",
                     "Cô gái đau đớn vì chia tay, ngồi khóc bên cửa sổ."):
            with self.subTest(text=text):
                self.assertFalse(inspect_text(text, "action"))
        self.assertTrue(inspect_text("Không máu me, nhưng cào rách sâu trên mặt", "action"))

    def test_checks_notes_references_and_states_not_just_action(self):
        project = apply_storyboard(data(2), "Film", 20, 10, "16:9", "", "Cảnh tra tấn")
        project.references[0].description = "Robot với vết thương hở"
        project.shots[1].end_state = "Mèo bị cào trúng mặt"
        issues = inspect_project(project)
        self.assertTrue(any(x.field == "Quy tắc xuyên suốt" for x in issues))
        self.assertTrue(any(x.field.startswith("Tham chiếu") for x in issues))
        self.assertTrue(any(x.shot_index == 1 for x in issues))

    def test_approved_shots_are_preserved_and_not_blocked_again(self):
        project = apply_storyboard(data(2), "Film", 20, 10, "16:9", "", "")
        project.shots[0].prompt = "Cắn mạnh vào chân"
        project.shots[0].status = "APPROVED"
        self.assertFalse(inspect_project(project))

    def test_generated_storyboard_is_revised_once_before_ready(self):
        risky, repaired = data(2), data(2)
        risky["shots"][1]["action"] = "Cắn mạnh vào chân"
        worker = FilmStoryboardWorker("Mèo và chuột", 20, 10, "", "gemini", "test", "model")
        ready, errors = [], []
        worker.storyboard_ready.connect(ready.append)
        worker.error_signal.connect(errors.append)
        original = copy.deepcopy(risky)
        with patch.object(worker, "_call_gemini", side_effect=[risky, repaired]) as call:
            worker.run()
        self.assertEqual(call.call_count, 2)
        self.assertEqual(ready, [repaired])
        self.assertFalse(errors)
        self.assertEqual(risky, original)

    def test_failed_content_revision_stops_without_endless_requests(self):
        risky = data(2)
        risky["shots"][1]["action"] = "Cắn mạnh vào chân"
        worker = FilmStoryboardWorker("Mèo và chuột", 20, 10, "", "gemini", "test", "model")
        errors, ready = [], []
        worker.error_signal.connect(errors.append)
        worker.storyboard_ready.connect(ready.append)
        with patch.object(worker, "_call_gemini", return_value=risky) as call:
            worker.run()
        self.assertEqual(call.call_count, 2)
        self.assertTrue(errors)
        self.assertFalse(ready)

    def test_worker_preflight_does_not_open_browser_or_send_references(self):
        with tempfile.TemporaryDirectory() as folder:
            project = apply_storyboard(data(2), "Film", 20, 10, "16:9", "", "")
            project.shots[1].prompt = "Cào rách sâu trên mặt"
            store = FilmStore(Path(folder) / "project.film.json", project)
            worker = FilmWorker(store, ProfileItem(id="test", name="test", path=folder), MuseSelectors())
            with patch("workers.film_worker.async_playwright") as browser:
                worker.run()
            browser.assert_not_called()
            self.assertEqual(project.shots[1].take, 0)
            self.assertEqual(project.shots[1].submitted_prompt, "")

