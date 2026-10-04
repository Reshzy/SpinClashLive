from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from color_rush_desktop.theme import GOLD, GREEN, RED
from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.confirm import confirm_action
from color_rush_desktop.widgets.status import PageFrame


class DashboardPage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("Dashboard", parent)
        self._vm = vm
        self.state = QLabel("WAITING")
        self.state.setStyleSheet("font-size:28px; font-weight:700;")
        self.countdown = QLabel("--")
        self.countdown.setStyleSheet("font-size:42px; font-weight:700;")
        self.counts = QLabel("Red 0   Gold 0   Green 0")
        self.lag = QLabel("Source lag: —")
        self.jobs = QLabel("Queue: —")
        self.bonus = QLabel("Next bonus: none")
        self.players = QLabel("Active participants: 0")
        row = QHBoxLayout()
        self.btn_game = QPushButton("Create game")
        self.btn_session = QPushButton("Create session")
        self.btn_start = QPushButton("Start round")
        self.btn_start.setProperty("cssClass", "accent")
        self.btn_close = QPushButton("Close picks")
        self.btn_spin = QPushButton("Start spin")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_cancel = QPushButton("Cancel round")
        self.btn_cancel.setProperty("cssClass", "danger")
        for button in (
            self.btn_game,
            self.btn_session,
            self.btn_start,
            self.btn_close,
            self.btn_spin,
            self.btn_pause,
            self.btn_resume,
            self.btn_cancel,
        ):
            row.addWidget(button)
        self.mode = QComboBox()
        self.mode.addItems(["manual", "automatic"])
        self.next_bonus = QComboBox()
        self.next_bonus.addItems(["none", "double_points", "gold_bonus"])
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Auto mode"))
        controls.addWidget(self.mode)
        controls.addWidget(QLabel("Next-round bonus"))
        controls.addWidget(self.next_bonus)
        apply_mode = QPushButton("Apply mode")
        apply_bonus = QPushButton("Apply bonus")
        controls.addWidget(apply_mode)
        controls.addWidget(apply_bonus)
        grid = QGridLayout()
        grid.addWidget(self.state, 0, 0)
        grid.addWidget(self.countdown, 0, 1)
        grid.addWidget(self.counts, 1, 0, 1, 2)
        grid.addWidget(self.players, 2, 0)
        grid.addWidget(self.bonus, 2, 1)
        grid.addWidget(self.lag, 3, 0)
        grid.addWidget(self.jobs, 3, 1)
        self.body.addLayout(grid)
        self.body.addLayout(row)
        self.body.addLayout(controls)
        hint = QLabel("Make your pick. Predictions open until picks locked. Closing the console does not stop the backend.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        self.body.addWidget(hint)
        self.btn_game.clicked.connect(self._create_game)
        self.btn_session.clicked.connect(self._create_session)
        self.btn_start.clicked.connect(self._start)
        self.btn_close.clicked.connect(self._close)
        self.btn_spin.clicked.connect(self._spin)
        self.btn_pause.clicked.connect(lambda: self._vm.write("POST", "/api/v1/admin/session/pause", self._sid(), job_id="pause"))
        self.btn_resume.clicked.connect(lambda: self._vm.write("POST", "/api/v1/admin/session/resume", self._sid(), job_id="resume"))
        self.btn_cancel.clicked.connect(self._cancel)
        apply_mode.clicked.connect(self._apply_mode)
        apply_bonus.clicked.connect(self._apply_bonus)
        vm.snapshot_changed.connect(self._render)
        vm.health_changed.connect(self._health)
        vm.source_changed.connect(self._source)
        vm.stale_changed.connect(lambda _: self._enable())
        vm.role_changed.connect(lambda _: self._enable())
        vm.connected_changed.connect(lambda _: self._enable())
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._enable()

    def _sid(self) -> dict[str, str]:
        return {"session_id": self._vm.session_id or ""}

    def _create_game(self) -> None:
        self._vm.write("POST", "/api/v1/admin/games", {"name": "Color Rush Live"}, job_id="create-game")

    def _create_session(self) -> None:
        if not self._vm.game_id:
            self.set_error("Create a game first.")
            return
        self._vm.write(
            "POST",
            "/api/v1/admin/sessions",
            {"game_id": self._vm.game_id, "mode": self.mode.currentText(), "source_mode": "simulation"},
            job_id="create-session",
        )

    def _start(self) -> None:
        if not self._vm.session_id:
            self.set_error("Create a session first.")
            return
        self._vm.write("POST", "/api/v1/admin/rounds/start", self._sid(), job_id="start-round")

    def _close(self) -> None:
        if not self._vm.round_id:
            return
        self._vm.write("POST", f"/api/v1/admin/rounds/{self._vm.round_id}/close", self._sid(), job_id="close")

    def _spin(self) -> None:
        if not self._vm.round_id:
            return
        self._vm.write("POST", f"/api/v1/admin/rounds/{self._vm.round_id}/spin", self._sid(), job_id="spin")

    def _cancel(self) -> None:
        if not self._vm.round_id:
            return
        if not confirm_action(
            self,
            "Cancel round",
            "Cancel the current round before an outcome is committed? No points will be awarded.",
        ):
            return
        body = {**self._sid(), "reason": "operator_cancel"}
        self._vm.write("POST", f"/api/v1/admin/rounds/{self._vm.round_id}/cancel", body, job_id="cancel")

    def _apply_mode(self) -> None:
        self._vm.write(
            "PATCH",
            "/api/v1/admin/session/auto-mode",
            {**self._sid(), "mode": self.mode.currentText()},
            job_id="auto-mode",
        )

    def _apply_bonus(self) -> None:
        self._vm.write(
            "PUT",
            "/api/v1/admin/next-round-bonus",
            {**self._sid(), "bonus": self.next_bonus.currentText(), "gold_reward": 28},
            job_id="bonus",
        )

    def _render(self, envelope: dict) -> None:
        data = envelope.get("data") or {}
        state = str(data.get("state") or "waiting").upper()
        self.state.setText(state)
        counts = data.get("counts") or {}
        self.counts.setText(
            f"<span style='color:{RED}'>Red {counts.get('red', 0)}</span>    "
            f"<span style='color:{GOLD}'>Gold {counts.get('gold', 0)}</span>    "
            f"<span style='color:{GREEN}'>Green {counts.get('green', 0)}</span>"
        )
        total = int(counts.get("red") or 0) + int(counts.get("gold") or 0) + int(counts.get("green") or 0)
        self.players.setText(f"Active participants: {total}")
        bonus = str(data.get("next_bonus") or data.get("rules", {}).get("bonus") or "none")
        self.bonus.setText(f"Next bonus: {bonus.replace('_', ' ')}")
        paused = bool(data.get("paused"))
        self.status.setText("Paused after round" if paused else f"Round {data.get('round_number') or '—'}")
        self.set_empty(None if self._vm.session_id else "No session yet. Create a game and session to begin.")
        self._enable()

    def _health(self, payload: dict) -> None:
        jobs = payload.get("jobs") or {}
        self.jobs.setText(f"Queue: {jobs}")

    def _source(self, payload: dict) -> None:
        lag = payload.get("lag_ms")
        health = payload.get("health") or "unknown"
        self.lag.setText(f"Source {health}; lag {lag if lag is not None else '—'} ms")

    def _tick(self) -> None:
        data = (self._vm.snapshot or {}).get("data") or {}
        closes = data.get("closes_at")
        server = (self._vm.snapshot or {}).get("server_time")
        if not closes or not server:
            self.countdown.setText("--")
            return
        try:
            end = datetime.fromisoformat(str(closes).replace("Z", "+00:00"))
            now = datetime.fromisoformat(str(server).replace("Z", "+00:00"))
            remaining = (end - now).total_seconds()
            self.countdown.setText(f"{max(int(remaining), 0)}s")
        except ValueError:
            self.countdown.setText("--")

    def _enable(self) -> None:
        writable = self._vm.can("rounds.write")
        pause = self._vm.can("pause")
        sessions = self._vm.can("sessions.write")
        state = self._vm.round_state
        self.btn_game.setEnabled(sessions)
        self.btn_session.setEnabled(sessions)
        startable = writable and (state in {"waiting", "cooldown", "settled", "cancelled"} or not self._vm.round_id)
        self.btn_start.setEnabled(startable)
        self.btn_close.setEnabled(writable and state == "open")
        self.btn_spin.setEnabled(writable and state == "locked")
        self.btn_pause.setEnabled(pause)
        self.btn_resume.setEnabled(pause)
        self.btn_cancel.setEnabled(writable and state in {"open", "draining", "locked"})
        self.mode.setEnabled(writable)
        self.next_bonus.setEnabled(writable)
