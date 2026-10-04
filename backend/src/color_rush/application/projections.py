from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.infrastructure.persistence.models import LeaderboardPeriod, LeaderboardScore, ProjectionJob, Round
from color_rush.infrastructure.redis.projections import (
    GROUP_PROJECTION,
    ack_event,
    append_history,
    consume_group,
    project_round_counts,
    redis_available,
    write_score,
)


def apply_projection_jobs(session: Session, redis: object, *, limit: int = 50) -> int:
    if not redis_available(redis):  # type: ignore[arg-type]
        return 0
    jobs = list(session.scalars(select(ProjectionJob).where(ProjectionJob.status == "pending").limit(limit)))
    applied = 0
    for job in jobs:
        round_id = UUID(str(job.payload.get("round_id")))
        rnd = session.get(Round, round_id)
        if rnd is None:
            job.status = "complete"
            continue
        from color_rush.infrastructure.persistence.models import GameSession

        game_session = session.get(GameSession, rnd.session_id)
        if game_session is None:
            continue
        project_round_counts(redis, session, game_session.game_id, rnd.id)  # type: ignore[arg-type]
        if rnd.result:
            append_history(redis, game_session.game_id, rnd.result)  # type: ignore[arg-type]
        periods = session.scalars(select(LeaderboardPeriod).where(LeaderboardPeriod.game_id == game_session.game_id))
        for period in periods:
            scores = session.scalars(select(LeaderboardScore).where(LeaderboardScore.period_id == period.id))
            for score in scores:
                write_score(
                    redis,  # type: ignore[arg-type]
                    game_id=game_session.game_id,
                    period_id=period.id,
                    player_id=score.player_id,
                    points=score.points,
                    score_version=score.score_version,
                )
        job.status = "complete"
        applied += 1
    events = consume_group(redis, group=GROUP_PROJECTION, consumer="projection-worker")  # type: ignore[arg-type]
    seen: set[str] = set()
    for event in events:
        event_id = event["event_id"]
        if event_id and event_id not in seen:
            seen.add(event_id)
        ack_event(redis, GROUP_PROJECTION, event["id"], stream=event["stream"])  # type: ignore[arg-type]
    return applied


def project_now(session: Session, redis: object, now: datetime) -> int:
    del now
    return apply_projection_jobs(session, redis)
