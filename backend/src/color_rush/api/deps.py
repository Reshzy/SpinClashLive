from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from color_rush.api.errors import http_error, request_id_of
from color_rush.application.auth import get_user, require_role
from color_rush.application.overlay_tickets import resolve_overlay_ticket
from color_rush.composition import AppContainer, get_runtime_container
from color_rush.domain.clock import utc_now
from color_rush.domain.enums import AdminRole
from color_rush.domain.errors import AuthError
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.persistence.models import AdminUser, OverlayTicket
from color_rush.infrastructure.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def container_dep() -> AppContainer:
    return get_runtime_container()


def db_session(container: Annotated[AppContainer, Depends(container_dep)]) -> Iterator[Session]:
    with session_scope(container.session_factory) as session:
        yield session


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(db_session)],
    container: Annotated[AppContainer, Depends(container_dep)],
) -> AdminUser:
    rid = request_id_of(request)
    if credentials is None:
        raise http_error(401, "auth_error", "missing bearer token", rid)
    try:
        payload = decode_access_token(container.settings.secret_key, credentials.credentials)
        user = get_user(session, UUID(str(payload["sub"])))
    except (AuthError, ValueError) as exc:
        raise http_error(401, "auth_error", "invalid or expired token", rid) from exc
    return user


def require_permission(permission: str) -> Callable[[AdminUser], AdminUser]:
    def _inner(user: Annotated[AdminUser, Depends(current_user)]) -> AdminUser:
        require_role(AdminRole(user.role), permission)
        return user

    return _inner


def overlay_ticket(
    request: Request,
    session: Annotated[Session, Depends(db_session)],
    x_overlay_ticket: Annotated[str | None, Header()] = None,
) -> OverlayTicket:
    rid = request_id_of(request)
    token = x_overlay_ticket or request.query_params.get("ticket")
    if not token:
        raise http_error(401, "auth_error", "overlay ticket required", rid)
    try:
        return resolve_overlay_ticket(session, token, utc_now())
    except Exception as exc:
        raise http_error(401, "auth_error", "overlay ticket invalid", rid) from exc


def expected_revision_header(if_match: Annotated[str | None, Header()] = None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match)
    except ValueError:
        return None


def check_revision(current: int, expected: int | None, request_id: str) -> None:
    if expected is not None and current != expected:
        raise http_error(409, "conflict", f"stale revision; current={current}", request_id)


def now() -> datetime:
    return utc_now()
