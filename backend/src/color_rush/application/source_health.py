from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from color_rush.domain.enums import CANCELABLE_STATES, ProcessingStatus, RoundState, SourceHealth
from color_rush.infrastructure.persistence.models import CommandInbox, GameSession, Round, SourceCheckpoint

UNHEALTHY_FOR_NEW_ROUNDS = frozenset(
    {
        SourceHealth.RESYNC,
        SourceHealth.DISABLED,
        SourceHealth.ENDED,
        SourceHealth.QUOTA,
        SourceHealth.PERMISSION,
        SourceHealth.DEGRADED,
    }
)
CANCEL_ON_FAIRNESS = frozenset(
    {
        SourceHealth.DISABLED,
        SourceHealth.ENDED,
        SourceHealth.QUOTA,
        SourceHealth.PERMISSION,
        SourceHealth.RESYNC,
    }
)


def _health_from_checkpoint(row: SourceCheckpoint | None) -> SourceHealth:
    if row is None:
        return SourceHealth.HEALTHY
    if row.resync_required:
        return SourceHealth.RESYNC
    if row.error_class:
        try:
            return SourceHealth(row.error_class)
        except ValueError:
            return SourceHealth.TRANSIENT
    return SourceHealth.HEALTHY


def checkpoint_for_session(session: Session, game_session: GameSession) -> SourceCheckpoint | None:
    if game_session.broadcast_ref:
        row = session.get(SourceCheckpoint, game_session.broadcast_ref)
        if row is not None:
            return row
    if game_session.live_chat_ref:
        return session.get(SourceCheckpoint, game_session.live_chat_ref)
    return None


def session_source_health(session: Session, game_session: GameSession) -> SourceHealth:
    if game_session.source_mode == "simulation":
        row = checkpoint_for_session(session, game_session)
        return _health_from_checkpoint(row)
    return _health_from_checkpoint(checkpoint_for_session(session, game_session))


def source_blocks_new_rounds(
    session: Session,
    game_session: GameSession,
    *,
    lag_pause_ms: int = 8000,
    backlog_pause: int = 2000,
) -> bool:
    health = session_source_health(session, game_session)
    if health in UNHEALTHY_FOR_NEW_ROUNDS:
        return True
    checkpoint = checkpoint_for_session(session, game_session)
    if checkpoint is not None and checkpoint.lag_ms is not None and checkpoint.lag_ms >= lag_pause_ms:
        return True
    pending = session.scalar(
        select(func.count())
        .select_from(CommandInbox)
        .where(
            CommandInbox.session_id == game_session.id,
            CommandInbox.processing_status == ProcessingStatus.PENDING.value,
        )
    )
    return int(pending or 0) >= backlog_pause


def should_cancel_affected_round(health: SourceHealth) -> bool:
    return health in CANCEL_ON_FAIRNESS


def record_source_health(
    session: Session,
    broadcast_id: str,
    *,
    health: SourceHealth,
    lag_ms: int | None = None,
) -> None:
    row = session.get(SourceCheckpoint, broadcast_id)
    if row is None:
        return
    row.error_class = None if health is SourceHealth.HEALTHY else health.value
    row.resync_required = health is SourceHealth.RESYNC
    if lag_ms is not None:
        row.lag_ms = lag_ms


def cancelable_active_round(session: Session, game_session: GameSession) -> Round | None:
    if game_session.active_round_id is None:
        return None
    rnd = session.get(Round, game_session.active_round_id)
    if rnd is None:
        return None
    if RoundState(rnd.state) in CANCELABLE_STATES:
        return rnd
    return None
