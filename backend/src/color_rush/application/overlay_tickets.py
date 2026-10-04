from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.domain.errors import AuthError, NotFoundError
from color_rush.infrastructure.persistence.models import OverlayTicket
from color_rush.infrastructure.security import create_overlay_ws_token, hash_secret, new_token


def create_overlay_ticket(
    session: Session,
    *,
    game_id: UUID,
    session_id: UUID | None,
    label: str,
    now: datetime,
    ttl_seconds: int,
) -> tuple[OverlayTicket, str]:
    secret = new_token()
    row = OverlayTicket(
        id=uuid4(),
        game_id=game_id,
        session_id=session_id,
        secret_hash=hash_secret(secret),
        label=label[:80],
        revoked_at=None,
        expires_at=now + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row, secret


def revoke_overlay_ticket(session: Session, ticket_id: UUID, now: datetime) -> OverlayTicket:
    row = session.get(OverlayTicket, ticket_id)
    if row is None:
        raise NotFoundError("overlay ticket not found")
    row.revoked_at = now
    return row


def resolve_overlay_ticket(session: Session, secret: str, now: datetime) -> OverlayTicket:
    hashed = hash_secret(secret)
    row = session.scalar(select(OverlayTicket).where(OverlayTicket.secret_hash == hashed))
    if row is None or row.revoked_at is not None:
        raise NotFoundError("overlay ticket not found")
    if row.expires_at is not None and row.expires_at <= now:
        raise NotFoundError("overlay ticket expired")
    return row


def list_overlay_tickets(session: Session, game_id: UUID) -> list[OverlayTicket]:
    return list(session.scalars(select(OverlayTicket).where(OverlayTicket.game_id == game_id)))


def exchange_overlay_ws_ticket(
    session: Session,
    *,
    secret: str,
    secret_key: str,
    now: datetime,
    ttl_seconds: int,
) -> tuple[str, OverlayTicket]:
    if not secret.strip():
        raise AuthError("overlay ticket required")
    row = resolve_overlay_ticket(session, secret.strip(), now)
    token = create_overlay_ws_token(
        secret_key=secret_key,
        ticket_id=row.id,
        game_id=row.game_id,
        session_id=row.session_id,
        ttl_seconds=ttl_seconds,
        now=now,
    )
    return token, row
