import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.alias_dialog import AliasDialog
from ui.dialogs.llm_dialog import LLMDictationDialog
from ui.dialogs.tts_dialog import TTSDialog
from ui.dialogs.video_merge_dialog import VideoMergeDialog

def test_dialogs():
    app = QApplication(sys.argv)

    d_set = SettingsDialog()
    assert d_set is not None

    d_alias = AliasDialog()
    assert d_alias is not None

    d_llm = LLMDictationDialog(available_tags=["@anh1", "@anh3"])
    assert d_llm is not None

    d_tts = TTSDialog()
    assert d_tts is not None

    d_video = VideoMergeDialog()
    assert d_video is not None

    print("ALL DIALOGS INSTANTIATED AND VALIDATED WITHOUT ERRORS!")
    app.quit()

if __name__ == "__main__":
    test_dialogs()
