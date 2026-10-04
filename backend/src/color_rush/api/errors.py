from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from color_rush.domain.errors import (
    AuthError,
    ConflictError,
    DrainFailedError,
    FencingError,
    ForbiddenError,
    IllegalTransitionError,
    InvalidCommandError,
    InvalidRulesError,
    NotFoundError,
    RoundBusyError,
    SettlementError,
)


def request_id_of(request: Request) -> str:
    header = request.headers.get("x-request-id")
    return header or str(uuid4())


def error_body(code: str, message: str, request_id: str, retry: bool | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if retry is not None:
        payload["retry"] = retry
    return payload


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = request_id_of(request)
    mapping: list[tuple[type[Exception], int, str]] = [
        (AuthError, 401, "auth_error"),
        (ForbiddenError, 403, "forbidden"),
        (NotFoundError, 404, "not_found"),
        (ConflictError, 409, "conflict"),
        (FencingError, 409, "stale_fence"),
        (RoundBusyError, 409, "round_busy"),
        (IllegalTransitionError, 409, "illegal_transition"),
        (SettlementError, 409, "settlement_error"),
        (DrainFailedError, 409, "drain_failed"),
        (InvalidRulesError, 422, "invalid_rules"),
        (InvalidCommandError, 422, "invalid_input"),
    ]
    for exc_type, status, code in mapping:
        if isinstance(exc, exc_type):
            return JSONResponse(status_code=status, content=error_body(code, str(exc), rid, retry=status == 409))
    return JSONResponse(status_code=500, content=error_body("internal", "internal error", rid))


def http_error(status: int, code: str, message: str, request_id: str) -> HTTPException:
    return HTTPException(status_code=status, detail=error_body(code, message, request_id))


def parse_uuid(value: str, request_id: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise http_error(422, "invalid_uuid", "invalid id", request_id) from exc
