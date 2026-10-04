from __future__ import annotations

from typing import Any
from uuid import uuid4

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal

from color_rush_desktop.api_client.errors import ApiError, HttpJob, TokenBundle
from color_rush_desktop.api_client.keyring_store import KeyringStore
from color_rush_desktop.api_client.rest import RestClient
from color_rush_desktop.api_client.websocket import AdminWebSocket
from color_rush_desktop.api_client.worker import HttpWorker
from color_rush_desktop.config import DesktopConfig
from color_rush_desktop.roles import can


class SessionViewModel(QObject):
    snapshot_changed = Signal(dict)
    health_changed = Signal(dict)
    source_changed = Signal(dict)
    sessions_changed = Signal(dict)
    error_occurred = Signal(str, str)
    connected_changed = Signal(bool)
    stale_changed = Signal(bool)
    busy_changed = Signal(bool)
    role_changed = Signal(str)
    env_changed = Signal(str)
    action_ok = Signal(str, object)
    compatibility_warning = Signal(str)
    _job = Signal(object)
    _login = Signal(str, str)
    _refresh = Signal()
    _logout = Signal()
    _set_refresh = Signal(str)

    def __init__(
        self,
        config: DesktopConfig,
        parent: QObject | None = None,
        client: RestClient | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.role = "observer"
        self.user_id = ""
        self.connected = False
        self.stale = True
        self.env = "simulation"
        self.snapshot: dict[str, Any] = {}
        self.health: dict[str, Any] = {}
        self.source: dict[str, Any] = {}
        self.session_id: str | None = None
        self.game_id: str | None = None
        self.revision: int | None = None
        self.round_id: str | None = None
        self.round_state = "waiting"
        self._store = KeyringStore(config)
        self._access_token = ""
        self._thread = QThread(self)
        self._worker = HttpWorker(client or RestClient(config))
        self._worker.moveToThread(self._thread)
        self._job.connect(self._worker.run_job, Qt.ConnectionType.QueuedConnection)
        self._login.connect(self._worker.login, Qt.ConnectionType.QueuedConnection)
        self._refresh.connect(self._worker.refresh_tokens, Qt.ConnectionType.QueuedConnection)
        self._logout.connect(self._worker.logout, Qt.ConnectionType.QueuedConnection)
        self._set_refresh.connect(self._worker.set_refresh_token, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.tokens_updated.connect(self._on_tokens)
        self._thread.start()
        self._ws = AdminWebSocket(self)
        self._ws.snapshot_received.connect(self.apply_snapshot)
        self._ws.connected_changed.connect(self._on_ws_connected)
        self._ws.protocol_warning.connect(self.compatibility_warning)
        self._pending = 0
        self._poll = QTimer(self)
        self._poll.setInterval(4000)
        self._poll.timeout.connect(self.refresh_aux)

    def can(self, permission: str) -> bool:
        return can(self.role, permission) and self.connected and not self.stale

    def can_role(self, permission: str) -> bool:
        return can(self.role, permission)

    def shutdown(self) -> None:
        self._poll.stop()
        self._ws.stop()
        self._worker.cancel_all()
        self._thread.quit()
        self._thread.wait(3000)

    def login(self, username: str, password: str) -> None:
        self._bump_busy(True)
        self._login.emit(username, password)

    def logout(self) -> None:
        self._poll.stop()
        self._ws.stop()
        self._logout.emit()
        self._store.clear()
        self.connected = False
        self.stale = True
        self.connected_changed.emit(False)
        self.stale_changed.emit(True)

    def restore_session(self) -> bool:
        saved = self._store.load()
        if not saved:
            return False
        self.role = saved.get("role") or "observer"
        self.user_id = saved.get("user_id") or ""
        self._bump_busy(True)
        self._set_refresh.emit(saved["refresh_token"])
        self._refresh.emit()
        return True

    def apply_snapshot(self, envelope: dict[str, Any]) -> None:
        data_obj = envelope.get("data")
        data: dict[str, Any] = data_obj if isinstance(data_obj, dict) else {}
        sequence = int(envelope.get("snapshot_sequence") or 0)
        previous = int(self.snapshot.get("snapshot_sequence") or -1)
        if sequence < previous and envelope.get("session_id") == self.snapshot.get("session_id"):
            return
        self.snapshot = envelope
        self.session_id = str(envelope.get("session_id") or "") or None
        self.round_id = str(envelope.get("round_id") or "") or None
        self.round_state = str(data.get("state") or "waiting")
        if data.get("session_revision") is not None:
            self.revision = int(data["session_revision"])
        self.game_id = str(data.get("game_id") or self.game_id or "") or self.game_id
        if self.connected:
            self.stale = False
            self.stale_changed.emit(False)
        self.snapshot_changed.emit(envelope)

    def refresh_aux(self) -> None:
        self.get("/api/v1/admin/health", job_id="health")
        if self.session_id:
            self.get("/api/v1/admin/source", job_id="source", params={"session_id": self.session_id})
        self.get("/api/v1/admin/sessions", job_id="sessions")

    def get(self, path: str, *, job_id: str | None = None, params: dict[str, Any] | None = None) -> str:
        return self._enqueue(HttpJob(job_id=job_id or str(uuid4()), method="GET", path=path, params=params))

    def write(self, method: str, path: str, body: dict[str, Any] | None = None, *, job_id: str | None = None) -> str:
        return self._enqueue(
            HttpJob(
                job_id=job_id or str(uuid4()),
                method=method,
                path=path,
                json_body=dict(body or {}),
                admin_write=True,
                expected_revision=self.revision,
            )
        )

    def _enqueue(self, job: HttpJob) -> str:
        self._bump_busy(True)
        self._job.emit(job)
        return job.job_id

    def _on_tokens(self, bundle: object) -> None:
        if isinstance(bundle, TokenBundle):
            self.role = bundle.role
            self.user_id = bundle.user_id
            self._access_token = bundle.access_token
            self.role_changed.emit(self.role)
            self._store.save(bundle, self.config.api_base)
            self._start_streams(bundle.access_token)

    def _start_streams(self, access_token: str) -> None:
        self.connected = True
        self.stale = False
        self.connected_changed.emit(True)
        self.stale_changed.emit(False)
        ws_url = self.config.api_base.replace("http://", "ws://").replace("https://", "wss://") + "/ws/v1/admin"
        self._ws.start(ws_url, access_token)
        self.get("/api/v1/admin/sessions", job_id="sessions")
        self.get("/api/v1/admin/health", job_id="health")
        self.get("/api/v1/game/snapshot", job_id="snapshot")
        self._poll.start()

    def _on_ws_connected(self, ok: bool) -> None:
        if not ok:
            self.stale = True
            self.stale_changed.emit(True)
            return
        self.get("/api/v1/game/snapshot", job_id="snapshot")

    def _on_finished(self, job_id: str, payload: object) -> None:
        self._bump_busy(False)
        data = payload if isinstance(payload, dict) else {}
        if job_id in {"login", "refresh"}:
            return
        if job_id == "health":
            self.health = data
            self.env = str(data.get("env") or self.env)
            self.env_changed.emit(self.env)
            self.health_changed.emit(data)
            return
        if job_id == "source":
            self.source = data
            self.source_changed.emit(data)
            return
        if job_id == "sessions":
            items = data.get("items") or []
            if items and not self.session_id:
                first = items[0]
                self.session_id = str(first.get("id") or "") or None
                self.game_id = str(first.get("game_id") or "") or None
                if first.get("revision") is not None:
                    self.revision = int(first["revision"])
            self.sessions_changed.emit(data)
            return
        if job_id == "snapshot" or data.get("type") == "snapshot":
            self.apply_snapshot(data)
            return
        if job_id.startswith("create-session") and data.get("id"):
            self.session_id = str(data["id"])
            if data.get("revision") is not None:
                self.revision = int(data["revision"])
        if job_id.startswith("create-game") and data.get("id"):
            self.game_id = str(data["id"])
        self.action_ok.emit(job_id, data)
        self.get("/api/v1/game/snapshot", job_id="snapshot")
        self.get("/api/v1/admin/sessions", job_id="sessions")

    def _on_failed(self, job_id: str, error: object) -> None:
        self._bump_busy(False)
        if isinstance(error, ApiError):
            if error.code == "cancelled":
                return
            if error.status == 401:
                self.stale = True
                self.connected = False
                self.connected_changed.emit(False)
                self.stale_changed.emit(True)
            self.error_occurred.emit(error.code, error.message)
            return
        self.error_occurred.emit("client_error", str(error))

    def _bump_busy(self, starting: bool) -> None:
        self._pending += 1 if starting else -1
        self._pending = max(self._pending, 0)
        self.busy_changed.emit(self._pending > 0)
