import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import unittest
from PyQt6.QtWidgets import QApplication

from config.settings import SettingsManager
from core.models import AliasItem, TaskItem, ProfileItem
from core.prompt_parser import PromptParser
from utils.file_utils import find_ffmpeg_binary
from workers.video_merger import VideoMergerWorker
from workers.llm_rewriter import LLMRewriterWorker
from ui.main_window import MainWindow

class TestAutoMuseQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication(sys.argv)

    def test_01_prompt_parser_multi_tags(self):
        prompt = "Review sản phẩm @aothun và phụ kiện @dongho"
        tags = PromptParser.extract_tags(prompt)
        self.assertEqual(tags, ["@aothun", "@dongho"])

        alias_dict = {
            "@aothun": AliasItem(tag="@aothun", name="Áo thun trắng", file_path="assets/sample_cloth1.jpg")
        }
        matched, missing = PromptParser.resolve_aliases(prompt, alias_dict)
        self.assertEqual(len(matched), 1)
        self.assertEqual(missing, ["@dongho"])

    def test_02_ffmpeg_ready(self):
        bin_path = find_ffmpeg_binary()
        self.assertIsNotNone(bin_path, "FFmpeg must be installed and detected on PATH")

    def test_03_settings_manager_state(self):
        sm = SettingsManager.get_instance()
        self.assertGreater(len(sm.profiles), 0)
        self.assertIsNotNone(sm.muse_selectors)

    def test_04_ui_creation(self):
        window = MainWindow()
        self.assertIsNotNone(window.left_panel)
        self.assertIsNotNone(window.right_panel)
        self.assertIsNotNone(window.ribbon)

if __name__ == "__main__":
    unittest.main()
