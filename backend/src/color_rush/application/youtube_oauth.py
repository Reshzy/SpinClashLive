from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.auth import record_admin_action
from color_rush.application.youtube_connect import revoke_google_credentials, store_google_oauth
from color_rush.config import Settings
from color_rush.domain.errors import ConfigurationError, InvalidCommandError, NotFoundError
from color_rush.infrastructure.persistence.models import Game, GoogleCredential

YOUTUBE_READONLY = "https://www.googleapis.com/auth/youtube.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
STATE_TTL_SECONDS = 600
TokenExchanger = Callable[[Settings, str], str]


def start_oauth(
    settings: Settings,
    *,
    game_id: UUID,
    user_id: UUID,
    now: datetime,
) -> dict[str, str]:
    _require_oauth_config(settings)
    state = sign_oauth_state(settings.secret_key, game_id=game_id, user_id=user_id, now=now)
    params = urlencode(
        {
            "client_id": settings.google_oauth_client_id or "",
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": YOUTUBE_READONLY,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return {"authorization_url": f"{AUTH_URL}?{params}", "state": state}


def sign_oauth_state(secret_key: str, *, game_id: UUID, user_id: UUID, now: datetime) -> str:
    expiry = int(now.timestamp()) + STATE_TTL_SECONDS
    payload = f"{game_id}|{user_id}|{expiry}"
    signature = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}|{signature}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def verify_oauth_state(secret_key: str, state: str, now: datetime) -> tuple[UUID, UUID]:
    try:
        decoded = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
        game_s, user_s, expiry_s, signature = decoded.split("|", 3)
        payload = f"{game_s}|{user_s}|{expiry_s}"
        expected = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise InvalidCommandError("invalid oauth state")
        if int(expiry_s) < int(now.timestamp()):
            raise InvalidCommandError("oauth state expired")
        return UUID(game_s), UUID(user_s)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCommandError("invalid oauth state") from exc


def complete_oauth_callback(
    session: Session,
    settings: Settings,
    *,
    code: str,
    state: str,
    now: datetime,
    token_exchanger: TokenExchanger | None = None,
) -> UUID:
    _require_oauth_config(settings)
    game_id, user_id = verify_oauth_state(settings.secret_key, state, now)
    if session.get(Game, game_id) is None:
        raise NotFoundError("game not found")
    exchanger = token_exchanger or exchange_authorization_code
    refresh_token = exchanger(settings, code)
    if not refresh_token:
        raise InvalidCommandError("google did not return a refresh token")
    revoke_google_credentials(session, game_id, now)
    store_google_oauth(session, settings, game_id=game_id, refresh_token=refresh_token, now=now)
    record_admin_action(
        session,
        actor_id=user_id,
        action="youtube.oauth",
        request_id=None,
        reason=None,
        before=None,
        after={"game_id": str(game_id), "connected": True},
        now=now,
    )
    session.flush()
    return game_id


def oauth_status(session: Session, game_id: UUID) -> dict[str, Any]:
    row = session.scalar(
        select(GoogleCredential)
        .where(GoogleCredential.game_id == game_id, GoogleCredential.auth_mode == "oauth")
        .order_by(GoogleCredential.created_at.desc())
    )
    if row is None:
        return {"connected": False, "auth_mode": None, "revoked": False}
    return {
        "connected": row.revoked_at is None,
        "auth_mode": row.auth_mode,
        "revoked": row.revoked_at is not None,
    }


def revoke_oauth(
    session: Session,
    *,
    game_id: UUID,
    actor_id: UUID,
    now: datetime,
    request_id: str | None = None,
) -> int:
    count = revoke_google_credentials(session, game_id, now)
    record_admin_action(
        session,
        actor_id=actor_id,
        action="youtube.oauth.revoke",
        request_id=request_id,
        reason=None,
        before=None,
        after={"game_id": str(game_id), "revoked": count},
        now=now,
    )
    session.flush()
    return count


def exchange_authorization_code(settings: Settings, code: str) -> str:
    response = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_oauth_client_id or "",
            "client_secret": settings.google_oauth_client_secret or "",
            "redirect_uri": settings.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise InvalidCommandError("google authorization failed")
    payload = response.json()
    refresh = payload.get("refresh_token")
    if not refresh:
        raise InvalidCommandError("google did not return a refresh token")
    return str(refresh)


def refresh_access_token(settings: Settings, refresh_token: str) -> str | None:
    try:
        response = httpx.post(
            TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_oauth_client_id or "",
                "client_secret": settings.google_oauth_client_secret or "",
                "grant_type": "refresh_token",
            },
            timeout=20.0,
        )
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    token = response.json().get("access_token")
    return str(token) if token else None


def _require_oauth_config(settings: Settings) -> None:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise ConfigurationError("Google OAuth client is not configured on the backend")
