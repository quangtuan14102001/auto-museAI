from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtWidgets import (
    QAbstractButton, QComboBox, QTabBar, QSlider,
    QSpinBox, QDoubleSpinBox, QStyle, QStyleOptionSpinBox
)


class GlobalCursorFilter(QObject):
    """
    Bộ lọc sự kiện toàn ứng dụng để đảm bảo tất cả các nút bấm,
    hộp chọn, checkbox và thành phần tương tác hiển thị con trỏ chuột
    hình bàn tay (PointingHandCursor) thay vì con trỏ mũi tên mặc định.
    """
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        etype = event.type()

        # Áp dụng PointingHandCursor cho các nút bấm, checkbox, combobox, tab bar, slider
        if etype in (QEvent.Type.Enter, QEvent.Type.Polish, QEvent.Type.Show):
            if isinstance(watched, (QAbstractButton, QComboBox, QTabBar, QSlider)):
                if watched.cursor().shape() != Qt.CursorShape.PointingHandCursor:
                    watched.setCursor(Qt.CursorShape.PointingHandCursor)
            elif isinstance(watched, (QSpinBox, QDoubleSpinBox)):
                if not watched.hasMouseTracking():
                    watched.setMouseTracking(True)

        # Xử lý con trỏ chuột thông minh cho QSpinBox (bàn tay khi rê lên nút mũi tên tăng/giảm)
        elif isinstance(watched, (QSpinBox, QDoubleSpinBox)):
            if etype == QEvent.Type.MouseMove:
                opt = QStyleOptionSpinBox()
                watched.initStyleOption(opt)
                pos = event.position().toPoint()
                sub = watched.style().hitTestComplexControl(
                    QStyle.ComplexControl.CC_SpinBox, opt, pos, watched
                )
                if sub in (QStyle.SubControl.SC_SpinBoxUp, QStyle.SubControl.SC_SpinBoxDown):
                    watched.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    watched.setCursor(Qt.CursorShape.IBeamCursor)
            elif etype == QEvent.Type.Leave:
                watched.unsetCursor()

        return super().eventFilter(watched, event)
