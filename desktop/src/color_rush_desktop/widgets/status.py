from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from color_rush_desktop.theme import GOLD, MUTED, RED


class StatusChip(QLabel):
    def __init__(self, text: str = "Disconnected", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_state("disconnected")

    def set_state(self, kind: str, text: str | None = None) -> None:
        colors = {
            "ok": "#1f3d2d",
            "warn": "#3d3218",
            "error": "#3d1d22",
            "disconnected": "#2a2e36",
        }
        fg = {"ok": "#3dd68c", "warn": GOLD, "error": RED, "disconnected": MUTED}
        key = kind if kind in colors else "disconnected"
        self.setText(text or kind)
        self.setStyleSheet(
            f"background:{colors[key]}; color:{fg[key]}; padding:4px 10px; border-radius:10px; font-weight:600;"
        )


class PageFrame(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.hide()
        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.hide()
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.error)
        layout.addWidget(self.empty)
        self.body = QVBoxLayout()
        frame = QFrame()
        frame.setLayout(self.body)
        layout.addWidget(frame, 1)

    def set_loading(self, loading: bool) -> None:
        self.status.setText("Loading…" if loading else "Ready")

    def set_error(self, message: str | None) -> None:
        if message:
            self.error.setText(message)
            self.error.show()
        else:
            self.error.hide()

    def set_empty(self, message: str | None) -> None:
        if message:
            self.empty.setText(message)
            self.empty.show()
        else:
            self.empty.hide()
