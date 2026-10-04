from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from color_rush_desktop.api_client.errors import ApiError, HttpJob, TokenBundle
from color_rush_desktop.api_client.rest import RestClient


class HttpWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, object)
    tokens_updated = Signal(object)

    def __init__(self, client: RestClient) -> None:
        super().__init__()
        self._client = client
        self._cancelled = False

    @Slot(object)
    def run_job(self, job: object) -> None:
        if not isinstance(job, HttpJob):
            self.failed.emit("unknown", ApiError("invalid job"))
            return
        if self._cancelled:
            self.failed.emit(job.job_id, ApiError("cancelled", code="cancelled"))
            return
        try:
            result = self._client.execute(job)
            if self._cancelled:
                self.failed.emit(job.job_id, ApiError("cancelled", code="cancelled"))
                return
            self.finished.emit(job.job_id, result)
        except ApiError as exc:
            self.failed.emit(job.job_id, exc)

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        try:
            bundle = self._client.login(username, password)
            self.tokens_updated.emit(bundle)
            self.finished.emit("login", {"role": bundle.role, "user_id": bundle.user_id})
        except ApiError as exc:
            self.failed.emit("login", exc)

    @Slot()
    def refresh_tokens(self) -> None:
        try:
            bundle = self._client.refresh()
            self.tokens_updated.emit(bundle)
            self.finished.emit("refresh", {"role": bundle.role, "user_id": bundle.user_id})
        except ApiError as exc:
            self.failed.emit("refresh", exc)

    @Slot()
    def logout(self) -> None:
        self._client.logout()
        self.finished.emit("logout", {"status": "ok"})

    def cancel_all(self) -> None:
        self._cancelled = True
        self._client.close()
        self._cancelled = False

    def set_tokens(self, bundle: TokenBundle) -> None:
        self._client.set_tokens(bundle)

    @Slot(str)
    def set_refresh_token(self, token: str) -> None:
        self._client.refresh_token = token

    def request(self, **kwargs: Any) -> None:
        self.run_job(HttpJob(**kwargs))
