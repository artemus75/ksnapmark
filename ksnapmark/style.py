"""Dunkles Stylesheet für alle KSnapMark-Fenster."""

STYLE = """
QWidget { background: #1f2024; color: #e8e8ec; font-size: 13px; }
QMainWindow, QDialog { background: #1f2024; }
QScrollArea { background: #16171a; border: none; }
QScrollArea > QWidget > QWidget { background: #16171a; }
QToolBar { background: #2a2b31; border: none; border-top: 1px solid #373942; padding: 4px 8px; spacing: 3px; }
QToolBar::separator { background: #44464f; width: 1px; margin: 4px 6px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px 7px; }
QToolButton:hover { background: #3a3c45; }
QToolButton:checked { background: #3b6fd6; border-color: #5c8cf0; }
QToolButton:disabled { color: #6b6d76; }
QToolButton::menu-indicator { image: none; width: 0; }
QToolButton::menu-button { border: none; width: 14px; }
QToolButton[swatch="true"] { border: 2px solid #1f2024; border-radius: 11px; padding: 0; min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }
QToolButton[swatch="true"]:checked { border: 2px solid #ffffff; }
QToolButton[swatch="true"]:hover { border: 2px solid #9aa0b5; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox { background: #2b2d34; border: 1px solid #40434d; border-radius: 6px; padding: 5px 7px; selection-background-color: #3b6fd6; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus { border-color: #5c8cf0; }
QPushButton { background: #33353d; border: 1px solid #464955; border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { background: #3f424c; }
QPushButton:default { background: #3b6fd6; border-color: #5c8cf0; color: #ffffff; }
QPushButton:disabled { color: #6b6d76; }
QMenu { background: #2a2b31; border: 1px solid #44464f; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #3b6fd6; }
QMenu::separator { height: 1px; background: #44464f; margin: 4px 6px; }
QStatusBar { background: #1a1b1e; color: #a9acb8; }
QSlider::groove:horizontal { height: 4px; background: #44464f; border-radius: 2px; }
QSlider::handle:horizontal { background: #e8e8ec; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::sub-page:horizontal { background: #5c8cf0; border-radius: 2px; }
QListWidget { background: #1a1b1e; border: 1px solid #33353d; border-radius: 8px; padding: 6px; }
QListWidget::item { border-radius: 8px; padding: 6px; color: #c9ccd8; }
QListWidget::item:selected { background: #2f4a85; color: #ffffff; }
QListWidget::item:hover:!selected { background: #2a2c33; }
QLabel[muted="true"] { color: #8d909d; }
QSplitter::handle { background: #2a2b31; width: 3px; }
QToolBar QLabel, QToolBar QCheckBox, QToolBar QSlider, QToolBar QWidget#spacer { background: transparent; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #6a6d7a; border-radius: 4px; background: #2b2d34; }
QCheckBox::indicator:checked { background: #3b6fd6; border-color: #5c8cf0; }
QToolTip { background: #101114; color: #e8e8ec; border: 1px solid #44464f; padding: 4px; }
"""
