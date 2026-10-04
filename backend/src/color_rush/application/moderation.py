from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.auth import record_admin_action
from color_rush.domain.enums import RoundState
from color_rush.domain.errors import NotFoundError
from color_rush.infrastructure.persistence.models import GameSession, Pick, Player, PlayerModeration, Round


def set_moderation(
    session: Session,
    *,
    player_id: UUID,
    scope_key: str,
    blocked: bool,
    reason: str | None,
    actor_id: UUID,
    now: datetime,
    request_id: str | None = None,
) -> PlayerModeration:
    player = session.get(Player, player_id)
    if player is None:
        raise NotFoundError("player not found")
    row = session.scalar(
        select(PlayerModeration).where(
            PlayerModeration.player_id == player_id,
            PlayerModeration.scope_key == scope_key,
        )
    )
    before: dict[str, object] | None = {"blocked": row.blocked} if row is not None else None
    if row is None:
        row = PlayerModeration(
            id=uuid4(),
            player_id=player_id,
            scope_key=scope_key,
            blocked=blocked,
            reason=reason,
            actor_id=actor_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.blocked = blocked
        row.reason = reason
        row.actor_id = actor_id
        row.updated_at = now
    if blocked:
        _remove_open_pick(session, player_id, scope_key)
    record_admin_action(
        session,
        actor_id=actor_id,
        action="moderation.block" if blocked else "moderation.unblock",
        request_id=request_id,
        reason=reason,
        before=before,
        after={"blocked": blocked, "scope": scope_key},
        now=now,
    )
    session.flush()
    return row


def _remove_open_pick(session: Session, player_id: UUID, scope_key: str) -> None:
    session_id: UUID | None = None
    if scope_key.startswith("session:"):
        session_id = UUID(scope_key.split(":", 1)[1])
    game_sessions: list[GameSession]
    if session_id is not None:
        row = session.get(GameSession, session_id)
        game_sessions = [row] if row is not None else []
    elif scope_key.startswith("game:"):
        game_id = UUID(scope_key.split(":", 1)[1])
        game_sessions = list(session.scalars(select(GameSession).where(GameSession.game_id == game_id)))
    else:
        return
    for game_session in game_sessions:
        if game_session.active_round_id is None:
            continue
        rnd = session.get(Round, game_session.active_round_id)
        if rnd is None or RoundState(rnd.state) is not RoundState.OPEN:
            continue
        pick = session.scalar(select(Pick).where(Pick.round_id == rnd.id, Pick.player_id == player_id))
        if pick is not None:
            session.delete(pick)
