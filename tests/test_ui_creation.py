import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set offscreen platform plugin for automated testing without displaying a window
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow

def test_ui():
    app = QApplication(sys.argv)
    window = MainWindow()
    assert window is not None
    assert window.left_panel is not None
    assert window.right_panel is not None
    assert window.ribbon is not None
    print("MainWindow instantiated and initialized with all sub-panels successfully!")
    app.quit()

if __name__ == "__main__":
    test_ui()
