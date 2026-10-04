from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_action(parent: QWidget | None, title: str, text: str) -> bool:
    result = QMessageBox.question(parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    return result == QMessageBox.StandardButton.Yes
