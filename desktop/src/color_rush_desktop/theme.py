from __future__ import annotations

ACCENT = "#ff8a3d"
RED = "#e5484d"
GOLD = "#f5c542"
GREEN = "#3dd68c"
BG = "#16181d"
PANEL = "#1f232b"
TEXT = "#f4f6fb"
MUTED = "#9aa3b2"


def apply_theme(app: object) -> None:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    if not isinstance(app, QApplication):
        return
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setStyleSheet(
        f"""
        QWidget {{ background: {BG}; color: {TEXT}; }}
        QMainWindow, QDialog {{ background: {BG}; }}
        QFrame#sidebar {{ background: #12141a; }}
        QLabel#banner {{ background: #3b2a16; color: {ACCENT}; padding: 8px 12px; font-weight: 600; }}
        QLabel#muted {{ color: {MUTED}; }}
        QLabel#error {{ color: {RED}; }}
        QLabel#stale {{ color: {GOLD}; }}
        QPushButton {{
            background: #2a303a; color: {TEXT}; border: 1px solid #3a4150;
            padding: 8px 14px; border-radius: 6px;
        }}
        QPushButton:hover {{ background: #343b47; }}
        QPushButton:disabled {{ color: #6b7380; background: #22262e; }}
        QPushButton[cssClass="accent"], QPushButton#accent {{ background: {ACCENT}; color: #1a120c; font-weight: 600; border: none; }}
        QPushButton[cssClass="danger"], QPushButton#danger {{ background: {RED}; color: white; border: none; }}
        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QDateTimeEdit {{
            background: {PANEL}; color: {TEXT}; border: 1px solid #3a4150;
            padding: 6px 8px; border-radius: 4px;
        }}
        QTableWidget, QListWidget, QTreeWidget {{
            background: {PANEL}; alternate-background-color: #252a33; gridline-color: #3a4150;
        }}
        QHeaderView::section {{ background: #252a33; color: {MUTED}; padding: 6px; border: none; }}
        QTabBar::tab {{ background: #1b1f26; padding: 8px 14px; }}
        QTabBar::tab:selected {{ background: {PANEL}; color: {ACCENT}; }}
        QStatusBar {{ background: #12141a; color: {MUTED}; }}
        QListWidget::item:selected {{ background: #2d241c; color: {ACCENT}; }}
        """
    )
