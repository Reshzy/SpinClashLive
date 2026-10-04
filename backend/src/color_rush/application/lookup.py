from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from color_rush.domain.enums import DecisionReason
from color_rush.infrastructure.persistence.models import GameSession, Player

LOOKUP_COOLDOWN = timedelta(seconds=10)
HELP_COOLDOWN = timedelta(seconds=30)
LOOKUP_QUEUE_MAX = 20
LOOKUP_TTL = timedelta(seconds=60)


def classify_lookup(session: Session, player_id: UUID, session_id: UUID, now: datetime) -> DecisionReason:
    del session_id
    player = session.get(Player, player_id)
    if player is None:
        return DecisionReason.IGNORED_LOOKUP
    if player.last_lookup_at is not None and now - player.last_lookup_at < LOOKUP_COOLDOWN:
        return DecisionReason.THROTTLED_LOOKUP
    player.last_lookup_at = now
    return DecisionReason.IGNORED_LOOKUP


def classify_help(session: Session, game_session: GameSession, now: datetime) -> DecisionReason:
    del session
    if game_session.last_help_at is not None and now - game_session.last_help_at < HELP_COOLDOWN:
        return DecisionReason.HELP_COOLDOWN
    game_session.last_help_at = now
    return DecisionReason.IGNORED_HELP
