from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from color_rush.application.outbox import sweep_incomplete_jobs
from color_rush.application.source_health import checkpoint_for_session, session_source_health
from color_rush.domain.enums import ProcessingStatus, RoundState
from color_rush.infrastructure.persistence.models import CommandInbox, CoordinatorLease, GameSession, Round
from color_rush.infrastructure.redis.projections import redis_available
from color_rush.observability.metrics import (
    INBOX_BACKLOG,
    INBOX_OLDEST_AGE_S,
    OUTBOX_PENDING,
    POSTGRES_UP,
    PROJECTION_PENDING,
    REDIS_UP,
    SETTLEMENT_LAG_S,
    SOURCE_HEALTH,
    SOURCE_LAG_MS,
)


def collect_operator_health(
    session: Session,
    redis: object,
    *,
    now: datetime,
    env: str,
) -> dict[str, Any]:
    redis_ok = redis_available(redis)  # type: ignore[arg-type]
    game_session = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
    jobs = sweep_incomplete_jobs(session)
    backlog = int(
        session.scalar(
            select(func.count())
            .select_from(CommandInbox)
            .where(CommandInbox.processing_status == ProcessingStatus.PENDING.value)
        )
        or 0
    )
    oldest = session.scalar(
        select(func.min(CommandInbox.received_at)).where(
            CommandInbox.processing_status == ProcessingStatus.PENDING.value
        )
    )
    oldest_age = (now - oldest).total_seconds() if oldest is not None else 0.0
    source = "healthy"
    lag_ms = 0
    lease: dict[str, Any] | None = None
    settlement_lag = 0.0
    if game_session is not None:
        source = session_source_health(session, game_session).value
        checkpoint = checkpoint_for_session(session, game_session)
        if checkpoint is not None and checkpoint.lag_ms is not None:
            lag_ms = int(checkpoint.lag_ms)
        lease_row = session.get(CoordinatorLease, game_session.id)
        if lease_row is not None:
            lease = {
                "owner_id": lease_row.owner_id,
                "fencing_token": lease_row.fencing_token,
                "expires_at": lease_row.expires_at.isoformat(),
            }
        rnd = session.get(Round, game_session.active_round_id) if game_session.active_round_id else None
        if rnd is not None and rnd.state == RoundState.SETTLING.value and rnd.score_effective_at is not None:
            settlement_lag = max((now - rnd.score_effective_at).total_seconds(), 0.0)

    POSTGRES_UP.set(1)
    REDIS_UP.set(1 if redis_ok else 0)
    INBOX_BACKLOG.set(backlog)
    INBOX_OLDEST_AGE_S.set(oldest_age)
    SOURCE_LAG_MS.set(lag_ms)
    SETTLEMENT_LAG_S.set(settlement_lag)
    OUTBOX_PENDING.set(jobs["outbox"])
    PROJECTION_PENDING.set(jobs["projection"])
    SOURCE_HEALTH.labels(status=source).set(0 if source == "healthy" else 1)

    return {
        "postgres": True,
        "redis": redis_ok,
        "source": source,
        "source_lag_ms": lag_ms,
        "jobs": jobs,
        "backlog": backlog,
        "oldest_pending_age_seconds": oldest_age,
        "settlement_lag_seconds": settlement_lag,
        "lease": lease,
        "env": env,
    }
