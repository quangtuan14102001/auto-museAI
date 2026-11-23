import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QApplication, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QWidget, QVBoxLayout, QStyle, QStyleOptionSpinBox
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QMouseEvent

from ui.cursor_filter import GlobalCursorFilter
from ui.styles.theme import get_theme_stylesheet


def test_cursor_and_spinbox():
    app = QApplication.instance() or QApplication(sys.argv)
    filt = GlobalCursorFilter()
    app.installEventFilter(filt)

    w = QWidget()
    w.setStyleSheet(get_theme_stylesheet("cyberpunk"))
    layout = QVBoxLayout(w)

    btn = QPushButton("Test Button")
    combo = QComboBox()
    combo.addItems(["A", "B"])
    chk = QCheckBox("Test Checkbox")
    sb = QSpinBox()
    sb.setRange(30, 999)
    sb.setValue(209)
    sb.setMinimumWidth(110)

    layout.addWidget(btn)
    layout.addWidget(combo)
    layout.addWidget(chk)
    layout.addWidget(sb)

    w.show()
    app.processEvents()

    # 1. Check cursor shapes on widgets
    print(f"Button cursor: {btn.cursor().shape()} (Expected PointingHandCursor: {Qt.CursorShape.PointingHandCursor})")
    assert btn.cursor().shape() == Qt.CursorShape.PointingHandCursor, "Button must have PointingHandCursor"

    print(f"ComboBox cursor: {combo.cursor().shape()} (Expected PointingHandCursor)")
    assert combo.cursor().shape() == Qt.CursorShape.PointingHandCursor, "ComboBox must have PointingHandCursor"

    print(f"CheckBox cursor: {chk.cursor().shape()} (Expected PointingHandCursor)")
    assert chk.cursor().shape() == Qt.CursorShape.PointingHandCursor, "CheckBox must have PointingHandCursor"

    # 2. Check SpinBox subcontrol rects and ensure QLineEdit does NOT overlap up-button
    opt = QStyleOptionSpinBox()
    sb.initStyleOption(opt)
    up_rect = sb.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, sb)
    down_rect = sb.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxDown, sb)

    print(f"Spinbox size: {sb.size()}")
    print(f"Up button rect: {up_rect}")
    print(f"Down button rect: {down_rect}")

    # Inspect child QLineEdit geometry
    line_edit = None
    for c in sb.children():
        if hasattr(c, "geometry") and c.metaObject().className() == "QLineEdit":
            line_edit = c
            break

    assert line_edit is not None, "QLineEdit child must exist in QSpinBox"
    print(f"Child QLineEdit rect: {line_edit.geometry()}")

    # Ensure right edge of QLineEdit is strictly less than up_rect.left()
    assert line_edit.geometry().right() < up_rect.left(), (
        f"QLineEdit right edge ({line_edit.geometry().right()}) must be < up_rect.left ({up_rect.left()})"
    )

    # 3. Simulate click on Up button
    p_up = up_rect.center()
    app.sendEvent(sb, QMouseEvent(QMouseEvent.Type.MouseButtonPress, p_up.toPointF(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    app.sendEvent(sb, QMouseEvent(QMouseEvent.Type.MouseButtonRelease, p_up.toPointF(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    print(f"Value after UP click: {sb.value()} (Expected: 210)")
    assert sb.value() == 210, f"Expected 210, got {sb.value()}"

    # 4. Simulate click on Down button
    p_down = down_rect.center()
    app.sendEvent(sb, QMouseEvent(QMouseEvent.Type.MouseButtonPress, p_down.toPointF(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    app.sendEvent(sb, QMouseEvent(QMouseEvent.Type.MouseButtonRelease, p_down.toPointF(), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    print(f"Value after DOWN click: {sb.value()} (Expected: 209)")
    assert sb.value() == 209, f"Expected 209, got {sb.value()}"

    # 5. Check cursor over up button
    ev_move_up = QMouseEvent(QMouseEvent.Type.MouseMove, p_up.toPointF(), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    app.sendEvent(sb, ev_move_up)
    print(f"Spinbox cursor over UP arrow: {sb.cursor().shape()}")
    assert sb.cursor().shape() == Qt.CursorShape.PointingHandCursor, "Spinbox over up arrow must be PointingHandCursor"

    print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_cursor_and_spinbox()
