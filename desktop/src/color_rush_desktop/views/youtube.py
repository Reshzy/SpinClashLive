from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from color_rush_desktop.viewmodels.session import SessionViewModel
from color_rush_desktop.widgets.status import PageFrame


class YouTubePage(PageFrame):
    def __init__(self, vm: SessionViewModel, parent: QWidget | None = None) -> None:
        super().__init__("YouTube", parent)
        self._vm = vm
        self.video = QLineEdit()
        self.video.setPlaceholderText("Video ID or supported YouTube URL")
        self.status_label = QLabel("Not connected")
        self.oauth_label = QLabel("OAuth: unknown")
        row = QHBoxLayout()
        self.connect_btn = QPushButton("Connect broadcast")
        self.connect_btn.setProperty("cssClass", "accent")
        self.disconnect_btn = QPushButton("Disconnect")
        self.auth_btn = QPushButton("Authorize in browser")
        self.revoke_btn = QPushButton("Revoke Google credential")
        self.poll_btn = QPushButton("Refresh OAuth status")
        for widget in (self.connect_btn, self.disconnect_btn, self.auth_btn, self.revoke_btn, self.poll_btn):
            row.addWidget(widget)
        self.body.addWidget(QLabel("Operator login is separate from Google authorization."))
        self.body.addWidget(self.video)
        self.body.addLayout(row)
        self.body.addWidget(self.status_label)
        self.body.addWidget(self.oauth_label)
        note = QLabel(
            "Simulation sessions need no Google key. Production chat uses a backend-owned API key "
            "and optional OAuth (youtube.readonly). Game blocking is not a YouTube chat ban."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        self.body.addWidget(note)
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(
            lambda: vm.write("POST", "/api/v1/admin/youtube/disconnect", {"session_id": vm.session_id}, job_id="yt-disconnect")
        )
        self.auth_btn.clicked.connect(self._oauth)
        self.revoke_btn.clicked.connect(self._revoke)
        self.poll_btn.clicked.connect(self._status)
        vm.source_changed.connect(self._source)
        vm.action_ok.connect(self._action)
        vm.stale_changed.connect(lambda _: self._enable())
        vm.role_changed.connect(lambda _: self._enable())
        self._enable()

    def _connect(self) -> None:
        self._vm.write(
            "POST",
            "/api/v1/admin/youtube/connect",
            {"session_id": self._vm.session_id, "video_ref": self.video.text().strip()},
            job_id="yt-connect",
        )

    def _oauth(self) -> None:
        if not self._vm.game_id:
            self.set_error("Create a game first.")
            return
        self._vm.write("POST", "/api/v1/admin/youtube/oauth/start", {"game_id": self._vm.game_id}, job_id="yt-oauth-start")

    def _revoke(self) -> None:
        if not self._vm.game_id:
            return
        self._vm.write("POST", "/api/v1/admin/youtube/oauth/revoke", {"game_id": self._vm.game_id}, job_id="yt-oauth-revoke")

    def _status(self) -> None:
        if not self._vm.game_id:
            return
        self._vm.get("/api/v1/admin/youtube/oauth/status", job_id="yt-oauth-status", params={"game_id": self._vm.game_id})

    def _source(self, payload: dict) -> None:
        mode = payload.get("source_mode")
        health = payload.get("health")
        resync = payload.get("resync_required")
        self.status_label.setText(
            f"Source {mode} · health {health} · resync {resync} · chat {payload.get('live_chat_ref') or '—'}"
        )

    def _action(self, job_id: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if job_id == "yt-oauth-start" and data.get("authorization_url"):
            QDesktopServices.openUrl(QUrl(str(data["authorization_url"])))
            self.oauth_label.setText("Browser opened. Waiting for Google consent…")
            self._status()
        if job_id == "yt-oauth-status":
            connected = data.get("connected")
            self.oauth_label.setText(f"OAuth connected={connected} revoked={data.get('revoked')}")

    def _enable(self) -> None:
        ok = self._vm.can("youtube")
        self.connect_btn.setEnabled(ok)
        self.disconnect_btn.setEnabled(ok)
        self.auth_btn.setEnabled(ok)
        self.revoke_btn.setEnabled(ok)
