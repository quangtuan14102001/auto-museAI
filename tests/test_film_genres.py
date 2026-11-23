import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from config.settings import SettingsManager
from core.film_genres import DEFAULT_GENRE, FILM_GENRES
from core.film_project import FilmStore, plan_film, film_prompt
from workers.film_storyboard_worker import FilmStoryboardWorker
from ui.dialogs.film_dialog import FilmDialog
from test_storyboard_completion import data


class FilmGenreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selected_genre_is_sent_to_storyboard_ai(self):
        worker = FilmStoryboardWorker("Robot", 20, 10, "Ba lô đỏ", "gemini", "test", "model", genre="Phiêu lưu")
        errors = []
        worker.error_signal.connect(errors.append)
        with patch.object(worker, "_call_gemini", return_value=data(2)) as api:
            worker.run()
        self.assertFalse(errors)
        self.assertIn("Thể loại phim: Phiêu lưu", api.call_args.args[0])
        self.assertIn("Ba lô đỏ", api.call_args.args[0])
        self.assertIn("không chỉ đổi từ ngữ", api.call_args.args[0])
        self.assertIn("end_state", api.call_args.args[0])

    def test_genre_round_trip_and_video_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = plan_film("Phim", ["Đi qua rừng"], 10, 10)
            project.genre = "Trinh thám"
            store = FilmStore(Path(tmp) / "project.film.json", project)
            store.save()
            loaded = FilmStore.load(store.manifest)
            self.assertEqual(loaded.project.genre, "Trinh thám")
            self.assertIn("Thể loại phim: Trinh thám", film_prompt(loaded.project, loaded.project.shots[0]))

    def test_ui_exposes_genres_and_preserves_custom_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = SettingsManager._instance
            config = Path(tmp) / "config.json"
            config.write_text("{}")
            SettingsManager._instance = SettingsManager(str(config))
            dialog = FilmDialog()
            try:
                self.assertEqual(dialog.genre.currentText(), DEFAULT_GENRE)
                self.assertIn("Kinh dị", FILM_GENRES)
                project = plan_film("Phim", ["Đi qua rừng"], 10, 10)
                project.genre = "Phiêu lưu kết hợp hài"
                store = FilmStore(Path(tmp) / "film/project.film.json", project)
                store.save()
                dialog.load_project(str(store.manifest))
                self.assertEqual(dialog.genre.currentText(), project.genre)
                dialog._new()
                self.assertEqual(dialog.genre.currentText(), DEFAULT_GENRE)
            finally:
                dialog.close()
                SettingsManager._instance = previous
