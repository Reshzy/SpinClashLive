from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QStackedWidget

from color_rush_desktop.config import load_config
from color_rush_desktop.theme import apply_theme
from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.views.login import LoginView
from color_rush_desktop.views.shell import MainShell


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    app = QApplication(args)
    apply_theme(app)
    config = load_config()
    vm = SessionViewModel(config)
    stack = QStackedWidget()
    login = LoginView(vm)
    shell = MainShell(vm)
    stack.addWidget(login)
    stack.addWidget(shell)
    stack.resize(1280, 800)
    stack.setWindowTitle("Color Rush Live")
    stack.show()

    def on_connected(ok: bool) -> None:
        stack.setCurrentWidget(shell if ok else login)

    vm.connected_changed.connect(on_connected)
    app.aboutToQuit.connect(vm.shutdown)
    vm.restore_session()
    return app.exec()
