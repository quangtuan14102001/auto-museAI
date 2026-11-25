import os
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage
from config.settings import SettingsManager
from core.film_genres import DEFAULT_GENRE, FILM_GENRES, GENRE_PROFILES, genre_instruction, genre_profiles
from core.film_project import FilmStore, FilmReference, plan_film, film_prompt
from core.models import ProfileItem
from core.selectors import MuseSelectors
from workers.film_worker import FilmWorker
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
        self.assertIn("mục tiêu hành trình", api.call_args.args[0].lower())
        self.assertIn("Tự rà soát trước khi trả JSON", api.call_args.args[0])

    def test_all_selectable_genres_have_distinct_authoring_guides(self):
        self.assertEqual(set(FILM_GENRES[1:]), set(GENRE_PROFILES))
        self.assertEqual(len({p.story for p in GENRE_PROFILES.values()}), len(GENRE_PROFILES))
        for name in FILM_GENRES[1:]:
            with self.subTest(genre=name):
                story = genre_instruction(name)
                self.assertIn(GENRE_PROFILES[name].review, story)
                self.assertIn(GENRE_PROFILES[name].story, story)

    def test_combined_and_custom_genres_preserve_user_choice(self):
        self.assertEqual({n for n,p in genre_profiles('Phiêu lưu kết hợp hài')}, {'Phiêu lưu','Hài'})
        self.assertFalse(genre_profiles('Hải trình'))
        combined = genre_instruction('Phiêu lưu kết hợp hài')
        self.assertIn(GENRE_PROFILES['Hài'].story, combined)
        self.assertIn(GENRE_PROFILES['Phiêu lưu'].story, combined)
        self.assertIn('Thể loại phim: Thơ thị giác', genre_instruction('Thơ thị giác'))
        self.assertNotIn('Thể loại phim: Hành động', genre_instruction(DEFAULT_GENRE))

    def test_generation_guides_do_not_repeat_story_arc_or_obscure_canonicals(self):
        video = genre_instruction('Kinh dị', stage='video')
        self.assertNotIn(GENRE_PROFILES['Kinh dị'].story, video)
        self.assertIn('quy tắc liên tục và ảnh tham chiếu ưu tiên', video)
        reference = genre_instruction('Kinh dị', stage='reference')
        self.assertIn('không áp bóng tối', reference)
        self.assertNotIn('Âm thanh', reference)

    def test_reference_generation_receives_genre_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = QImage(32, 32, QImage.Format.Format_RGB32)
            image.fill(0xff557799)
            image.save(str(root/'source.png'))
            project = plan_film('Test', ['Quan sát căn phòng'], 10, 10)
            project.genre = 'Trinh thám'
            project.references = [FilmReference('robot', 'character', 'Rô', 'Robot xanh, mắt tròn')]
            project.shots[0].character_ids = ['robot']
            store = FilmStore(root/'film/project.film.json', project)
            store.save()
            profile = ProfileItem('test', 'test', str(root/'profile'))
            worker = FilmWorker(store, profile, MuseSelectors())
            with patch.object(worker, '_execute_validated_phase', new=AsyncMock(return_value=(True, '', str(root/'source.png')))) as generate:
                asyncio.run(worker._ensure_canonical_references(None, profile))
            prompt = generate.call_args.args[1].prompt
            self.assertIn('Thể loại phim: Trinh thám', prompt)
            self.assertIn('Robot xanh, mắt tròn', prompt)
            self.assertIn('Đây là ảnh chuẩn', prompt)
            self.assertEqual(project.references[0].generation_status, 'READY')

    def test_genre_round_trip_and_video_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = plan_film("Phim", ["Đi qua rừng"], 10, 10)
            project.genre = "Trinh thám"
            store = FilmStore(Path(tmp) / "project.film.json", project)
            store.save()
            loaded = FilmStore.load(store.manifest)
            self.assertEqual(loaded.project.genre, "Trinh thám")
            self.assertIn("Thể loại phim: Trinh thám", film_prompt(loaded.project, loaded.project.shots[0]))
            self.assertIn(GENRE_PROFILES['Trinh thám'].shot, film_prompt(loaded.project, loaded.project.shots[0]))
            self.assertNotIn('Tự rà soát trước khi trả JSON', film_prompt(loaded.project, loaded.project.shots[0]))

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
