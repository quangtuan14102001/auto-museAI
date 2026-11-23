import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["PYTHONIOENCODING"] = "utf-8"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from config.settings import SettingsManager
from core.models import AliasItem, TaskItem, ProfileItem, TaskStatus, JobMode
from core.prompt_parser import PromptParser
from core.selectors import MuseSelectors
from utils.file_utils import (
    ensure_dir, sanitize_filename, generate_output_filename, find_ffmpeg_binary
)
from workers.llm_rewriter import LLMRewriterWorker
from workers.video_merger import VideoMergerWorker

from ui.main_window import MainWindow
from ui.cursor_filter import GlobalCursorFilter
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.alias_dialog import AliasDialog
from ui.dialogs.llm_dialog import LLMDictationDialog
from ui.dialogs.tts_dialog import TTSDialog
from ui.dialogs.video_merge_dialog import VideoMergeDialog
from ui.styles.theme import get_theme_stylesheet


class TestFullAppAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.cursor_filter = GlobalCursorFilter()
        cls.app.installEventFilter(cls.cursor_filter)
        cls.settings = SettingsManager.get_instance()

    # -------------------------------------------------------------
    # 1. Config & Settings Manager
    # -------------------------------------------------------------
    def test_01_settings_manager_load_and_models(self):
        sm = self.settings
        self.assertIsNotNone(sm.app_config)
        self.assertIn("theme", sm.app_config)
        self.assertIn("default_timeout", sm.app_config)
        self.assertIn("max_concurrent_tabs", sm.app_config)
        self.assertIsInstance(sm.profiles, list)
        self.assertIsInstance(sm.aliases, list)
        self.assertIsInstance(sm.tasks, list)
        self.assertIsInstance(sm.muse_selectors, MuseSelectors)

    def test_02_file_utils(self):
        # Sanitize filename
        clean = sanitize_filename("test/\\file:?*name")
        self.assertNotIn("/", clean)
        self.assertNotIn("\\", clean)
        self.assertNotIn(":", clean)

        # Generate output filename
        out = generate_output_filename("output", "so1", 1, "mp4")
        self.assertTrue(out.endswith(".mp4"))
        self.assertIn("so1", out)
        self.assertIn("Prompt_001_", out)

        # FFmpeg presence
        ffmpeg_bin = find_ffmpeg_binary()
        self.assertIsNotNone(ffmpeg_bin, "FFmpeg binary must exist on system PATH")

    # -------------------------------------------------------------
    # 2. Prompt Parser & Multi-Reference Alias Engine
    # -------------------------------------------------------------
    def test_03_prompt_parser(self):
        prompt = "Tạo video người mẫu mặc @aothun và đeo @dongho đi dạo phố"
        tags = PromptParser.extract_tags(prompt)
        self.assertEqual(tags, ["@aothun", "@dongho"])

        alias_dict = {
            "@aothun": AliasItem(tag="@aothun", name="Áo thun", file_path="assets/sample_cloth1.jpg")
        }
        matched, missing = PromptParser.resolve_aliases(prompt, alias_dict)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].tag, "@aothun")
        self.assertEqual(missing, ["@dongho"])

        # Auto attach all if none
        prompt_no_tag = "Tạo video phong cảnh thiên nhiên"
        matched_auto, _ = PromptParser.resolve_aliases(prompt_no_tag, alias_dict, auto_attach_all_if_none=True)
        self.assertEqual(len(matched_auto), 1)

        # Clean prompt for composer (strip tags)
        cleaned = PromptParser.clean_prompt_for_composer(prompt, strip_tags=True)
        self.assertNotIn("@aothun", cleaned)
        self.assertNotIn("@dongho", cleaned)

        # Split raw prompt list
        multi_prompts = "Cảnh 1\n\nCảnh 2\n\nCảnh 3"
        split_res = PromptParser.split_raw_prompt_list(multi_prompts)
        self.assertEqual(len(split_res), 3)

    # -------------------------------------------------------------
    # 3. Workers (LLM Rewriter, Video Merger)
    # -------------------------------------------------------------
    def test_04_llm_rewriter_local_fallback(self):
        worker = LLMRewriterWorker(
            raw_script="Cảnh 1: Mặt trời mọc\nCảnh 2: Biển xanh sóng vỗ",
            num_scenes=2,
            alias_tags=["@nhanvat"]
        )
        scenes = worker._local_scene_generator()
        self.assertEqual(len(scenes), 2)
        self.assertIn("Phân cảnh #1", scenes[0])
        self.assertIn("Phân cảnh #2", scenes[1])

    def test_05_video_merger_worker_init(self):
        merger = VideoMergerWorker(["file1.mp4", "file2.mp4"], "output/merged.mp4")
        self.assertEqual(len(merger.video_files), 2)
        self.assertEqual(merger.output_path, "output/merged.mp4")

    # -------------------------------------------------------------
    # 4. Main Window & Sub-Panels
    # -------------------------------------------------------------
    def test_06_ui_main_window_components(self):
        win = MainWindow()
        self.assertIsNotNone(win.ribbon)
        self.assertIsNotNone(win.left_panel)
        self.assertIsNotNone(win.right_panel)

        # Left panel: Profiles table has rows
        table = win.left_panel.table_profiles
        self.assertGreaterEqual(table.rowCount(), 1)

        # Right panel: Parameters inputs exist
        self.assertIsNotNone(win.right_panel.combo_mode)
        self.assertIsNotNone(win.right_panel.combo_aspect)
        self.assertIsNotNone(win.right_panel.spin_video_duration)
        self.assertIsNotNone(win.right_panel.txt_raw_prompts)
        self.assertIsNotNone(win.right_panel.table_tasks)

    def test_07_prompt_queue_loading(self):
        win = MainWindow()
        rp = win.right_panel
        initial_count = rp.table_tasks.rowCount()

        # Set text and click parse
        rp.txt_raw_prompts.setPlainText("Cảnh quay 1 @aothun đẹp mắt\n\nCảnh quay 2 phong cảnh")
        rp._parse_and_feed_prompts()

        # Tasks should now be added to queue
        queue_count = rp.table_tasks.rowCount()
        self.assertGreaterEqual(queue_count, initial_count + 2)

    def test_08_alias_chips_interaction(self):
        win = MainWindow()
        rp = win.right_panel
        rp.txt_raw_prompts.setPlainText("Nhân vật đang mặc")
        cursor = rp.txt_raw_prompts.textCursor()
        cursor.setPosition(17)
        rp.txt_raw_prompts.setTextCursor(cursor)

        # Click alias chip
        rp._insert_tag_to_prompt("@aothun")
        self.assertIn("@aothun", rp.txt_raw_prompts.toPlainText())

    # -------------------------------------------------------------
    # 5. Dialogs Validation
    # -------------------------------------------------------------
    def test_09_all_dialogs_instantiation(self):
        d_settings = SettingsDialog()
        self.assertIsNotNone(d_settings)

        d_alias = AliasDialog()
        self.assertIsNotNone(d_alias)

        d_llm = LLMDictationDialog(["@anh1"])
        self.assertIsNotNone(d_llm)

        d_tts = TTSDialog()
        self.assertIsNotNone(d_tts)

        d_video = VideoMergeDialog()
        self.assertIsNotNone(d_video)

    # -------------------------------------------------------------
    # 6. Themes & Hand Cursors
    # -------------------------------------------------------------
    def test_10_theme_stylesheets(self):
        css_cyberpunk = get_theme_stylesheet("cyberpunk")
        self.assertIn("QPushButton", css_cyberpunk)
        self.assertIn("QSpinBox", css_cyberpunk)
        self.assertIn("btn-run", css_cyberpunk)

        css_obsidian = get_theme_stylesheet("obsidian")
        self.assertIn("QPushButton", css_obsidian)
        self.assertIn("btn-run", css_obsidian)

    def test_11_hand_cursor_filter(self):
        win = MainWindow()
        btn = win.left_panel.btn_run
        self.assertEqual(btn.cursor().shape(), Qt.CursorShape.PointingHandCursor)


if __name__ == "__main__":
    unittest.main()
