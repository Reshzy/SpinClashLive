from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from color_rush_desktop.theme import ACCENT, MUTED
from color_rush_desktop.viewmodels.session import SessionViewModel


class LoginView(QWidget):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = vm
        title = QLabel("Color Rush Live")
        title.setStyleSheet(f"font-size:28px; font-weight:700; color:{ACCENT};")
        subtitle = QLabel("Operator console — backend owns every round.")
        subtitle.setStyleSheet(f"color:{MUTED};")
        self.api = QLabel(vm.config.api_base)
        self.api.setObjectName("muted")
        self.user = QLineEdit()
        self.user.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.button = QPushButton("Sign in")
        self.button.setProperty("cssClass", "accent")
        self.button.setDefault(True)
        self.error = QLabel("")
        self.error.setObjectName("error")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box = QVBoxLayout()
        box.addWidget(title)
        box.addWidget(subtitle)
        box.addWidget(self.api)
        box.addSpacing(12)
        box.addWidget(self.user)
        box.addWidget(self.password)
        box.addWidget(self.button)
        box.addWidget(self.error)
        holder = QWidget()
        holder.setLayout(box)
        holder.setMaximumWidth(420)
        layout.addWidget(holder, alignment=Qt.AlignmentFlag.AlignCenter)
        self.button.clicked.connect(self._submit)
        self.password.returnPressed.connect(self._submit)
        vm.error_occurred.connect(self._on_error)
        vm.connected_changed.connect(self._on_connected)

    def _submit(self) -> None:
        self.error.clear()
        self.button.setEnabled(False)
        self._vm.login(self.user.text().strip(), self.password.text())

    def _on_error(self, code: str, message: str) -> None:
        self.button.setEnabled(True)
        self.error.setText(f"{code}: {message}")

    def _on_connected(self, ok: bool) -> None:
        if not ok:
            self.button.setEnabled(True)
