from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "client_error",
        request_id: str | None = None,
        status: int | None = None,
        retry: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.request_id = request_id
        self.status = status
        self.retry = retry
        self.payload = payload or {}

    @classmethod
    def from_body(cls, status: int, body: Any) -> ApiError:
        data = _unwrap(body)
        return cls(
            str(data.get("message") or data.get("detail") or f"HTTP {status}"),
            code=str(data.get("code") or "http_error"),
            request_id=str(data.get("request_id")) if data.get("request_id") else None,
            status=status,
            retry=bool(data.get("retry")),
            payload=data if isinstance(data, dict) else {},
        )


def _unwrap(body: Any) -> dict[str, Any]:
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict):
            return detail
        if isinstance(detail, str):
            return {"message": detail, "code": "http_error"}
        return body
    return {"message": str(body), "code": "http_error"}


@dataclass(slots=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    role: str
    user_id: str
    token_type: str = "bearer"


@dataclass(slots=True)
class HttpJob:
    job_id: str
    method: str
    path: str
    json_body: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    admin_write: bool = False
    expected_revision: int | None = None
    auth: bool = True
