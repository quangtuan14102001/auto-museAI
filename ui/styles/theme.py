"""
Modern Theme and Stylesheets for Auto Muse AI Studio.
Provides Obsidian Dark, Cyberpunk Dark, and Slate themes.
"""

def get_theme_stylesheet(theme_name: str = "obsidian_dark", font_size: int = 13) -> str:
    base_font = f"font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif; font-size: {font_size}px;"

    if theme_name == "cyberpunk":
        return f"""
        * {{
            {base_font}
            color: #e2e8f0;
        }}
        QMainWindow, QDialog, QWidget#centralWidget {{
            background-color: #0b0d17;
        }}
        QFrame.card {{
            background-color: #121526;
            border: 1px solid #1f243d;
            border-radius: 8px;
        }}
        QLabel.section-title {{
            font-size: {font_size + 2}px;
            font-weight: bold;
            color: #38bdf8;
            padding-bottom: 4px;
        }}
        QPushButton {{
            background-color: #1e2442;
            color: #f1f5f9;
            border: 1px solid #313a68;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: #2b335e;
            border-color: #38bdf8;
        }}
        QPushButton:pressed {{
            background-color: #181d36;
        }}
        QPushButton.btn-primary {{
            background-color: #0284c7;
            border: 1px solid #38bdf8;
            color: #ffffff;
        }}
        QPushButton.btn-primary:hover {{
            background-color: #0369a1;
        }}
        QPushButton.btn-run {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #10b981);
            color: #ffffff;
            font-size: {font_size + 3}px;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
        }}
        QPushButton.btn-run:hover {{
            background: #059669;
        }}
        QPushButton.btn-stop {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dc2626, stop:1 #ef4444);
            color: #ffffff;
            font-size: {font_size + 3}px;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
        }}
        QPushButton.btn-stop:hover {{
            background: #dc2626;
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
            background-color: #0c0f1c;
            border: 1px solid #242b47;
            border-radius: 6px;
            padding: 6px 10px;
            color: #f8fafc;
            selection-background-color: #0284c7;
        }}
        QSpinBox, QDoubleSpinBox {{
            background-color: #0c0f1c;
            border: 1px solid #242b47;
            border-radius: 6px;
            padding-top: 5px;
            padding-bottom: 5px;
            padding-left: 9px;
            padding-right: 52px;
            min-width: 95px;
            color: #f8fafc;
            selection-background-color: #0284c7;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 1px solid #38bdf8;
        }}
        QTableWidget, QTableView {{
            background-color: #0e1222;
            border: 1px solid #212845;
            border-radius: 6px;
            gridline-color: #1b213b;
            selection-background-color: #1e293b;
            color: #e2e8f0;
        }}
        QHeaderView::section {{
            background-color: #161b33;
            color: #94a3b8;
            font-weight: bold;
            padding: 6px;
            border: none;
            border-bottom: 1px solid #273154;
        }}
        QScrollBar:vertical {{
            background: #0b0d17;
            width: 10px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: #252e50;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #38bdf8;
        }}
        """

    # Default: Obsidian Dark (Sleek, Modern, High Contrast Studio Look)
    return f"""
    * {{
        {base_font}
        color: #e5e7eb;
    }}
    QMainWindow, QDialog, QWidget#centralWidget {{
        background-color: #0f1117;
    }}
    QFrame.card {{
        background-color: #161922;
        border: 1px solid #232735;
        border-radius: 10px;
    }}
    QFrame.ribbon {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #181b26, stop:1 #13151e);
        border-bottom: 1px solid #262a3a;
    }}
    QLabel.brand-title {{
        font-size: {font_size + 4}px;
        font-weight: 800;
        color: #818cf8;
        letter-spacing: 0.5px;
    }}
    QLabel.section-title {{
        font-size: {font_size + 2}px;
        font-weight: 700;
        color: #f3f4f6;
        padding-bottom: 4px;
    }}
    QLabel.badge-tag {{
        background-color: #312e81;
        color: #c7d2fe;
        border-radius: 4px;
        padding: 2px 6px;
        font-weight: bold;
    }}
    QPushButton {{
        background-color: #1f2433;
        color: #f3f4f6;
        border: 1px solid #2e354a;
        border-radius: 7px;
        padding: 7px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: #2a3147;
        border-color: #6366f1;
        color: #ffffff;
    }}
    QPushButton:pressed {{
        background-color: #181b26;
    }}
    QPushButton.btn-ribbon {{
        background-color: #1e2230;
        border: 1px solid #2b3145;
        border-radius: 8px;
        padding: 8px 16px;
        font-weight: 600;
        color: #e0e7ff;
    }}
    QPushButton.btn-ribbon:hover {{
        background-color: #312e81;
        border-color: #6366f1;
        color: #ffffff;
    }}
    QPushButton.btn-run {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #10b981);
        color: #ffffff;
        font-size: {font_size + 3}px;
        font-weight: 800;
        border: none;
        border-radius: 9px;
        padding: 12px 24px;
    }}
    QPushButton.btn-run:hover {{
        background: #059669;
    }}
    QPushButton.btn-stop {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dc2626, stop:1 #ef4444);
        color: #ffffff;
        font-size: {font_size + 3}px;
        font-weight: 800;
        border: none;
        border-radius: 9px;
        padding: 12px 24px;
    }}
    QPushButton.btn-stop:hover {{
        background: #b91c1c;
    }}
    QPushButton.btn-accent {{
        background-color: #4f46e5;
        border: 1px solid #6366f1;
        color: #ffffff;
        font-weight: 700;
    }}
    QPushButton.btn-accent:hover {{
        background-color: #4338ca;
    }}
    QPushButton.chip-btn {{
        background-color: #272c40;
        border: 1px solid #3e4663;
        color: #c7d2fe;
        border-radius: 12px;
        padding: 3px 10px;
        font-size: {font_size - 1}px;
        font-weight: 600;
    }}
    QPushButton.chip-btn:hover {{
        background-color: #4338ca;
        color: #ffffff;
        border-color: #6366f1;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
        background-color: #12141c;
        border: 1px solid #262c3e;
        border-radius: 7px;
        padding: 7px 11px;
        color: #f9fafb;
        selection-background-color: #4f46e5;
    }}
    QSpinBox, QDoubleSpinBox {{
        background-color: #12141c;
        border: 1px solid #262c3e;
        border-radius: 7px;
        padding-top: 6px;
        padding-bottom: 6px;
        padding-left: 10px;
        padding-right: 52px;
        min-width: 95px;
        color: #f9fafb;
        selection-background-color: #4f46e5;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid #6366f1;
        background-color: #151824;
    }}
    QTableWidget, QTableView {{
        background-color: #12151f;
        border: 1px solid #232839;
        border-radius: 8px;
        gridline-color: #1c2130;
        selection-background-color: #22283a;
        color: #f3f4f6;
    }}
    QHeaderView::section {{
        background-color: #171b28;
        color: #9ca3af;
        font-weight: 700;
        padding: 8px;
        border: none;
        border-bottom: 1px solid #272d40;
    }}
    QCheckBox {{
        spacing: 8px;
        color: #d1d5db;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid #374151;
        background-color: #181b26;
    }}
    QCheckBox::indicator:checked {{
        background-color: #4f46e5;
        border-color: #6366f1;
    }}
    QScrollBar:vertical {{
        background: #0f1117;
        width: 10px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background: #2b3145;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #4f46e5;
    }}
    QScrollBar:horizontal {{
        background: #0f1117;
        height: 10px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal {{
        background: #2b3145;
        border-radius: 5px;
    }}
    """
