from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from color_rush_desktop.theme import ACCENT
from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.views.dashboard import DashboardPage
from color_rush_desktop.views.health import HealthPage
from color_rush_desktop.views.leaderboards import LeaderboardsPage
from color_rush_desktop.views.moderation import ModerationPage
from color_rush_desktop.views.overlay_setup import OverlaySetupPage
from color_rush_desktop.views.players import PlayersPage
from color_rush_desktop.views.seasons import SeasonsPage
from color_rush_desktop.views.settings import SettingsPage
from color_rush_desktop.views.youtube import YouTubePage
from color_rush_desktop.widgets.status import StatusChip

PAGES = (
    "Dashboard",
    "YouTube",
    "Players",
    "Leaderboards",
    "Seasons",
    "Moderation",
    "Settings",
    "Health/Audit",
    "Overlay Setup",
)


class MainShell(QMainWindow):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vm = vm
        self.setWindowTitle("Color Rush Live")
        self.resize(1280, 800)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side_layout = QVBoxLayout(sidebar)
        brand = QLabel("Color Rush Live")
        brand.setStyleSheet(f"font-size:18px; font-weight:700; color:{ACCENT}; padding:12px;")
        self.nav = QListWidget()
        for name in PAGES:
            QListWidgetItem(name, self.nav)
        self.nav.setCurrentRow(0)
        logout = QPushButton("Sign out")
        side_layout.addWidget(brand)
        side_layout.addWidget(self.nav, 1)
        side_layout.addWidget(logout)
        self.stack = QStackedWidget()
        self.pages = [
            DashboardPage(vm),
            YouTubePage(vm),
            PlayersPage(vm),
            LeaderboardsPage(vm),
            SeasonsPage(vm),
            ModerationPage(vm),
            SettingsPage(vm),
            HealthPage(vm),
            OverlaySetupPage(vm),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        right = QVBoxLayout()
        self.banner = QLabel("SIMULATION")
        self.banner.setObjectName("banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.banner)
        right.addWidget(self.stack, 1)
        right_host = QWidget()
        right_host.setLayout(right)
        layout.addWidget(sidebar)
        layout.addWidget(right_host, 1)
        self.setCentralWidget(root)
        status = QStatusBar()
        self.conn = StatusChip()
        self.role = QLabel("")
        status.addPermanentWidget(self.role)
        status.addPermanentWidget(self.conn)
        self.setStatusBar(status)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        logout.clicked.connect(vm.logout)
        vm.env_changed.connect(self._env)
        vm.connected_changed.connect(self._connected)
        vm.stale_changed.connect(self._stale)
        vm.role_changed.connect(self._role)
        vm.error_occurred.connect(self._error)
        vm.compatibility_warning.connect(lambda text: status.showMessage(text, 8000))
        vm.busy_changed.connect(lambda busy: status.showMessage("Working…" if busy else "", 1000))
        self._role(vm.role)
        self._env(vm.env)
        self._connected(vm.connected)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.statusBar().showMessage("Console closed. Backend keeps running.")
        super().closeEvent(event)

    def _env(self, env: str) -> None:
        if env == "simulation":
            self.banner.setText("SIMULATION — scores are isolated from production")
            self.banner.show()
        else:
            self.banner.hide()

    def _connected(self, ok: bool) -> None:
        if ok:
            self.conn.set_state("ok", "Connected")
        else:
            self.conn.set_state("disconnected", "Disconnected")

    def _stale(self, stale: bool) -> None:
        if stale:
            self.conn.set_state("warn", "Stale / reconnecting")
            self.statusBar().showMessage("Showing last snapshot. Mutations disabled until refresh.")

    def _role(self, role: str) -> None:
        self.role.setText(f"Role: {role}")

    def _error(self, code: str, message: str) -> None:
        self.statusBar().showMessage(f"{code}: {message}", 10000)
        page = self.stack.currentWidget()
        if hasattr(page, "set_error"):
            page.set_error(f"{code}: {message}")
