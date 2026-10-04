from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from color_rush.application.auth import record_admin_action
from color_rush.config import Settings
from color_rush.domain.errors import ConflictError, NotFoundError
from color_rush.infrastructure.persistence.models import GameSession, GoogleCredential, SourceCheckpoint
from color_rush.infrastructure.security import decrypt_secret, encrypt_secret
from color_rush.infrastructure.youtube.http import YouTubeHttpClient
from color_rush.infrastructure.youtube.video import parse_video_ref


def connect_youtube(
    session: Session,
    settings: Settings,
    *,
    session_id: UUID,
    video_ref: str,
    actor_id: UUID,
    now: datetime,
    http_client: YouTubeHttpClient | None = None,
    request_id: str | None = None,
) -> GameSession:
    game_session = session.get(GameSession, session_id)
    if game_session is None:
        raise NotFoundError("session not found")
    if game_session.source_mode == "youtube" and game_session.live_chat_ref:
        raise ConflictError("youtube source already connected")
    if game_session.source_mode == "simulation" and settings.color_rush_env == "production":
        raise ConflictError("cannot switch a production session onto another source while active")
    video_id = parse_video_ref(video_ref)
    client = http_client or YouTubeHttpClient(
        api_key=settings.google_api_key,
        access_token=_oauth_access_token(session, settings, game_session.game_id),
    )
    live_chat_id = client.resolve_live_chat_id(video_id)
    game_session.broadcast_ref = video_id
    game_session.live_chat_ref = live_chat_id
    game_session.source_mode = "youtube"
    game_session.revision += 1
    game_session.updated_at = now
    existing = session.get(SourceCheckpoint, video_id)
    if existing is None:
        session.add(
            SourceCheckpoint(
                broadcast_id=video_id,
                next_page_token=None,
                source_mode="youtube",
                last_success_at=now,
                ownership_token="",
                session_id=session_id,
                resync_required=False,
                error_class=None,
                lag_ms=None,
            )
        )
    else:
        existing.session_id = session_id
        existing.source_mode = "youtube"
    record_admin_action(
        session,
        actor_id=actor_id,
        action="youtube.connect",
        request_id=request_id,
        reason=None,
        before=None,
        after={"video_id": video_id, "live_chat_id": live_chat_id},
        now=now,
    )
    session.flush()
    return game_session


def disconnect_youtube(
    session: Session,
    *,
    session_id: UUID,
    actor_id: UUID,
    now: datetime,
    request_id: str | None = None,
) -> GameSession:
    game_session = session.get(GameSession, session_id)
    if game_session is None:
        raise NotFoundError("session not found")
    game_session.live_chat_ref = None
    game_session.source_mode = "simulation" if game_session.source_mode == "youtube" else game_session.source_mode
    game_session.revision += 1
    game_session.updated_at = now
    record_admin_action(
        session,
        actor_id=actor_id,
        action="youtube.disconnect",
        request_id=request_id,
        reason=None,
        before=None,
        after={"disconnected": True},
        now=now,
    )
    session.flush()
    return game_session


def store_google_oauth(
    session: Session,
    settings: Settings,
    *,
    game_id: UUID,
    refresh_token: str,
    now: datetime,
) -> GoogleCredential:
    payload = encrypt_secret(settings.secret_key, refresh_token)
    row = GoogleCredential(
        id=__import__("uuid").uuid4(),
        game_id=game_id,
        auth_mode="oauth",
        encrypted_payload=payload,
        scopes="https://www.googleapis.com/auth/youtube.readonly",
        created_at=now,
        revoked_at=None,
    )
    session.add(row)
    session.flush()
    return row


def revoke_google_credentials(session: Session, game_id: UUID, now: datetime) -> int:
    from sqlalchemy import select

    rows = list(session.scalars(select(GoogleCredential).where(GoogleCredential.game_id == game_id)))
    for row in rows:
        row.revoked_at = now
    return len(rows)


def _oauth_access_token(session: Session, settings: Settings, game_id: UUID) -> str | None:
    from sqlalchemy import select

    row = session.scalar(
        select(GoogleCredential).where(
            GoogleCredential.game_id == game_id,
            GoogleCredential.revoked_at.is_(None),
            GoogleCredential.auth_mode == "oauth",
        )
    )
    if row is None:
        return None
    try:
        return decrypt_secret(settings.secret_key, row.encrypted_payload)
    except Exception:
        return None
