from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from color_rush.infrastructure.persistence.models import (
    LeaderboardPeriod,
    LeaderboardScore,
    Pick,
    PlayerStatistics,
    ScoreLedger,
)
from color_rush.infrastructure.redis.projections import redis_available, top_n


def reconcile_round(session: Session, round_id: UUID, redis: object | None = None) -> dict[str, Any]:
    pick_count = int(session.scalar(select(func.count()).select_from(Pick).where(Pick.round_id == round_id)) or 0)
    ledger_count = int(
        session.scalar(select(func.count()).select_from(ScoreLedger).where(ScoreLedger.round_id == round_id)) or 0
    )
    ledger_points = int(
        session.scalar(
            select(func.coalesce(func.sum(ScoreLedger.points_delta), 0)).where(ScoreLedger.round_id == round_id)
        )
        or 0
    )
    mismatches: list[str] = []
    if pick_count != ledger_count:
        mismatches.append("pick_ledger_count")
    periods = list(session.scalars(select(LeaderboardPeriod)))
    redis_ok = redis_available(redis) if redis is not None else False  # type: ignore[arg-type]
    redis_checked = 0
    if redis_ok:
        for period in periods:
            sql_top = list(
                session.scalars(
                    select(LeaderboardScore)
                    .where(LeaderboardScore.period_id == period.id)
                    .order_by(LeaderboardScore.points.desc(), LeaderboardScore.player_id.asc())
                    .limit(10)
                )
            )
            redis_top = top_n(redis, game_id=period.game_id, period_id=period.id, limit=10)  # type: ignore[arg-type]
            sql_ids = [row.player_id for row in sql_top]
            redis_ids = [item[0] for item in redis_top]
            if sql_ids != redis_ids:
                mismatches.append(f"redis_top_{period.period_type}")
            redis_checked += 1
    stats_players = int(session.scalar(select(func.count()).select_from(PlayerStatistics)) or 0)
    return {
        "round_id": str(round_id),
        "picks": pick_count,
        "ledger": ledger_count,
        "ledger_points": ledger_points,
        "stats_players": stats_players,
        "redis_checked_periods": redis_checked,
        "ok": not mismatches,
        "mismatches": mismatches,
    }
