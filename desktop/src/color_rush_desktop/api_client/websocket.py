from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket


class AdminWebSocket(QObject):
    snapshot_received = Signal(dict)
    connected_changed = Signal(bool)
    protocol_warning = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._socket: QWebSocket | None = None
        self._token = ""
        self._url = ""
        self._last_sequence = -1
        self._session_id: str | None = None
        self._reconnect_ms = 1000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._open)
        self._wanted = False

    def start(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._wanted = True
        self._reconnect_ms = 1000
        if self._socket is None:
            socket = QWebSocket()
            socket.connected.connect(self._on_connected)
            socket.disconnected.connect(self._on_disconnected)
            socket.textMessageReceived.connect(self._on_text)
            self._socket = socket
        self._open()

    def stop(self) -> None:
        self._wanted = False
        self._timer.stop()
        if self._socket is not None:
            self._socket.close()

    def _open(self) -> None:
        if not self._wanted or self._socket is None:
            return
        self._socket.open(QUrl(self._url))

    def _on_connected(self) -> None:
        self._reconnect_ms = 1000
        self.connected_changed.emit(True)
        if self._socket is not None:
            self._socket.sendTextMessage(json.dumps({"token": self._token}))

    def _on_disconnected(self) -> None:
        self.connected_changed.emit(False)
        if self._wanted:
            self._timer.start(self._reconnect_ms)
            self._reconnect_ms = min(self._reconnect_ms * 2, 15_000)

    def _on_text(self, message: str) -> None:
        try:
            payload: dict[str, Any] = json.loads(message)
        except json.JSONDecodeError:
            self.protocol_warning.emit("invalid websocket payload")
            return
        schema = payload.get("schema_version")
        if schema not in (None, 1):
            self.protocol_warning.emit(f"unsupported schema_version {schema}")
        sequence = int(payload.get("snapshot_sequence") or 0)
        session_id = payload.get("session_id")
        if isinstance(session_id, str) and self._session_id and session_id != self._session_id:
            self._last_sequence = -1
        if sequence < self._last_sequence:
            return
        self._last_sequence = sequence
        if isinstance(session_id, str):
            self._session_id = session_id
        self.snapshot_received.emit(payload)
