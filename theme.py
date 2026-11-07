"""配色と Qt スタイルシート（ダーク基調）。"""

PALETTE = {
    "bg": "#101217",
    "panel": "#181B22",
    "panel2": "#1F232C",
    "border": "#2A2F3A",
    "text": "#E6E9F0",
    "muted": "#8B93A4",
    "accent": "#7A95FF",
    "accent_hi": "#95AAFF",
    "ok": "#4ADE80",
    "warn": "#FBBF24",
    "err": "#F87171",
}

_QSS = """
QWidget {
    background: @bg@;
    color: @text@;
    font-family: "Yu Gothic UI", "Segoe UI", "Meiryo", sans-serif;
    font-size: 10pt;
}
QMainWindow, QDialog { background: @bg@; }
QLabel#title { font-size: 15pt; font-weight: 600; }
QLabel#subtle { color: @muted@; }

QLineEdit, QPlainTextEdit, QComboBox {
    background: @panel@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: @accent@;
    selection-color: #0B0D12;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid @accent@; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: @panel2@;
    border: 1px solid @border@;
    selection-background-color: @accent@;
    selection-color: #0B0D12;
    outline: 0;
}

QPushButton {
    background: @panel2@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 6px 14px;
}
QPushButton:hover { border-color: @accent@; }
QPushButton:pressed { background: @panel@; }
QPushButton:disabled { color: @muted@; background: @panel@; }
QPushButton#primary {
    background: @accent@;
    border: none;
    color: #0B0D12;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#primary:hover { background: @accent_hi@; }
QPushButton#primary:disabled { background: @border@; color: @muted@; }
QPushButton#danger { color: @err@; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid @border@;
    border-radius: 4px;
    background: @panel2@;
}
QCheckBox::indicator:checked { background: @accent@; border-color: @accent@; }

QTableWidget {
    background: @panel@;
    alternate-background-color: @panel2@;
    border: 1px solid @border@;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: rgba(122, 149, 255, 40);
    selection-color: @text@;
    outline: 0;
}
QTableWidget::item { padding: 4px 6px; }
QHeaderView::section {
    background: @panel2@;
    color: @muted@;
    border: none;
    border-bottom: 1px solid @border@;
    padding: 8px;
    font-weight: 600;
}

QTabWidget::pane {
    border: 1px solid @border@;
    border-radius: 10px;
    background: @panel@;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: @muted@;
    padding: 8px 16px;
    border: none;
}
QTabBar::tab:selected { color: @text@; border-bottom: 2px solid @accent@; }
QTabBar::tab:hover { color: @text@; }

QProgressBar {
    background: @panel@;
    border: 1px solid @border@;
    border-radius: 8px;
    text-align: center;
    min-height: 18px;
    color: @text@;
}
QProgressBar::chunk { background: @accent@; border-radius: 7px; }

QSplitter::handle { background: transparent; }
QSplitter::handle:vertical { height: 10px; }

QStatusBar { background: @panel@; color: @muted@; border-top: 1px solid @border@; }
QMenuBar { background: @bg@; }
QMenuBar::item { padding: 6px 10px; background: transparent; }
QMenuBar::item:selected { background: @panel2@; border-radius: 6px; }
QMenu {
    background: @panel@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: @panel2@; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @border@; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @muted@; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border@; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

QMessageBox { background: @bg@; }
QToolTip {
    background: @panel2@;
    color: @text@;
    border: 1px solid @border@;
    padding: 4px;
}
"""


def qss() -> str:
    s = _QSS
    for key, value in PALETTE.items():
        s = s.replace(f"@{key}@", value)
    return s
