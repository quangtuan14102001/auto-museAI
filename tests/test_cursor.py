import sys
from PyQt6.QtWidgets import QApplication, QPushButton, QSpinBox, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QEvent, QObject
from PyQt6.QtGui import QCursor

app = QApplication([])
w = QWidget()
layout = QVBoxLayout(w)

btn1 = QPushButton("Test Button")
sb = QSpinBox()
sb.setValue(209)
sb.setRange(1, 999)

layout.addWidget(btn1)
layout.addWidget(sb)

# Check default cursor
print("Default btn cursor shape:", btn1.cursor().shape())
btn1.setCursor(Qt.CursorShape.PointingHandCursor)
print("Updated btn cursor shape:", btn1.cursor().shape())

app.quit()
