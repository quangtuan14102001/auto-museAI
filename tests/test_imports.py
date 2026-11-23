import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Testing core imports...")
import core.models
import core.prompt_parser
import core.selectors
import config.settings
import utils.file_utils
import utils.logger
import workers.automation_worker
import workers.login_worker
import workers.tts_engine
import workers.video_merger
import workers.llm_rewriter
import ui.styles.theme
import ui.ribbon
import ui.left_panel
import ui.right_panel
import ui.dialogs.settings_dialog
import ui.dialogs.alias_dialog
import ui.dialogs.llm_dialog
import ui.dialogs.tts_dialog
import ui.dialogs.video_merge_dialog
import ui.main_window

print("ALL MODULES IMPORTED SUCCESSFULLY WITHOUT ERRORS!")
