"""AIMatting 现代暗色主题样式。"""

ACCENT = "#4C8DFF"
ACCENT_DARK = "#3B78E7"
GREEN = "#22C07A"
GREEN_DARK = "#1CA96A"
BG = "#17181C"
CARD = "#23252B"
BORDER = "#343741"
TEXT = "#E6E8EE"
TEXT_MUTED = "#9AA0AC"
DANGER = "#F04A50"
INPUT_BG = "#1C1E23"
SELECT_BG = "#2A3A55"
HOVER_BG = "#2C2F37"


MODERN_QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}
QMainWindow, QWidget#RootWidget {{
    background: {BG};
}}
QLabel {{
    background: transparent;
}}
QLabel#DropZone {{
    border: 2px dashed #4A4E59;
    border-radius: 12px;
    background: #1E2126;
    color: {TEXT_MUTED};
    font-size: 14px;
}}
QLabel#DropZone:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
    background: #232A36;
}}
QLabel#TitleLogo {{
    color: {ACCENT};
    font-size: 16px;
    font-weight: bold;
}}
QLabel#TitleText {{
    font-size: 14px;
    font-weight: 600;
}}
QWidget#TopBar {{
    background: {CARD};
    border-bottom: 1px solid {BORDER};
}}
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    color: {TEXT};
}}
QPushButton:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
    background: {HOVER_BG};
}}
QPushButton:pressed {{
    background: #33363E;
}}
QPushButton:disabled {{
    color: #5C616C;
    background: #202227;
    border-color: {BORDER};
}}
QPushButton:checked {{
    background: {ACCENT};
    color: white;
    border-color: {ACCENT};
}}
QPushButton:checked:hover {{
    background: {ACCENT_DARK};
}}
QPushButton#TopBarButton {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px 10px;
    color: {TEXT};
}}
QPushButton#TopBarButton:hover {{
    background: {HOVER_BG};
    color: {ACCENT};
}}
QPushButton#TopBarButton:disabled {{
    color: #5C616C;
}}
QPushButton#WindowButton {{
    border: none;
    border-radius: 6px;
    background: transparent;
    font-size: 14px;
    color: {TEXT_MUTED};
    padding: 0;
}}
QPushButton#WindowButton:hover {{
    background: {HOVER_BG};
    color: {TEXT};
}}
QPushButton#WindowButtonClose:hover {{
    background: {DANGER};
    color: white;
}}
QPushButton#WindowButton[gw_hover="true"] {{
    background: {HOVER_BG};
    color: {TEXT};
}}
QPushButton#WindowButton[gw_pressed="true"] {{
    background: #3A3E48;
    color: {TEXT};
}}
QPushButton#WindowButtonClose[gw_hover="true"] {{
    background: {DANGER};
    color: white;
}}
QPushButton#WindowButtonClose[gw_pressed="true"] {{
    background: #C33C42;
    color: white;
}}
QPushButton#CancelButton {{
    background: #3A2023;
    color: #FF8A8E;
    border: 1px solid #6E3338;
    font-weight: 600;
}}
QPushButton#CancelButton:hover {{
    background: {DANGER};
    color: white;
}}
QPushButton#SaveButton {{
    background: {ACCENT};
    color: white;
    font-weight: 600;
    border: none;
}}
QPushButton#SaveButton:hover {{
    background: {ACCENT_DARK};
}}
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {CARD};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    padding: 8px 14px;
    margin-right: 4px;
    border: none;
    border-bottom: 2px solid transparent;
    color: {TEXT_MUTED};
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {ACCENT};
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QListWidget, QTextEdit, QPlainTextEdit {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background: {SELECT_BG};
    color: {ACCENT};
}}
QListWidget::item:hover {{
    background: {HOVER_BG};
}}
QLineEdit, QSpinBox, QComboBox, QDoubleSpinBox {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 22px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {SELECT_BG};
    selection-color: {ACCENT};
}}
QComboBox QAbstractItemView::item {{
    padding: 5px 8px;
}}
QSlider::groove:horizontal {{
    height: 6px;
    border-radius: 3px;
    background: #3A3E48;
}}
QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
    background: {ACCENT};
}}
QSlider::sub-page:horizontal {{
    border-radius: 3px;
    background: {ACCENT};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid #4A4E59;
    border-radius: 5px;
    background: {INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #4A4E59;
    border-radius: 8px;
    background: {INPUT_BG};
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border: 4px solid {CARD};
    outline: 1px solid {ACCENT};
}}
QProgressBar {{
    border: none;
    border-radius: 5px;
    background: #3A3E48;
    text-align: center;
    color: {TEXT_MUTED};
    min-height: 10px;
}}
QProgressBar::chunk {{
    border-radius: 5px;
    background: {ACCENT};
}}
QStatusBar {{
    background: {CARD};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
}}
QToolTip {{
    background: #2E3138;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #454A56;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #5A6170;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QMessageBox, QDialog {{
    background: {BG};
}}
QMessageBox QPushButton {{
    min-width: 72px;
}}
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}
"""
