import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication, QSpinBox, QWidget, QVBoxLayout
from ui.styles.theme import get_theme_stylesheet

app = QApplication([])
w = QWidget()
w.setStyleSheet(get_theme_stylesheet("cyberpunk"))

sb = QSpinBox(w)
sb.setRange(1, 999)
sb.setValue(209)

# Show and measure subcontrols
w.show()
app.processEvents()

# Find up-button and down-button rects
from PyQt6.QtWidgets import QStyle, QStyleOptionSpinBox
opt = QStyleOptionSpinBox()
sb.initStyleOption(opt)
up_rect = sb.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, sb)
down_rect = sb.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxDown, sb)

print(f"Spinbox size: {sb.size()}")
print(f"Up button rect: {up_rect.x()}, {up_rect.y()}, {up_rect.width()}x{up_rect.height()}")
print(f"Down button rect: {down_rect.x()}, {down_rect.y()}, {down_rect.width()}x{down_rect.height()}")

app.quit()
