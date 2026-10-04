from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.infrastructure.persistence.models import OutboxEvent, ProjectionJob, SettlementJob
from color_rush.infrastructure.redis.projections import connect_redis, ensure_groups, publish_outbox, redis_available


def relay_outbox(session: Session, redis_url: str, *, now: datetime, limit: int = 100) -> int:
    client = connect_redis(redis_url)
    if not redis_available(client):
        return 0
    ensure_groups(client)
    rows = list(
        session.scalars(
            select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.created_at).limit(limit)
        )
    )
    sent = 0
    for row in rows:
        publish_outbox(
            client,
            event_id=str(row.event_id),
            event_type=row.event_type,
            payload=row.payload,
            aggregate_id=str(row.aggregate_id),
        )
        row.published_at = now
        sent += 1
    return sent


def sweep_incomplete_jobs(session: Session) -> dict[str, int]:
    pending_outbox = len(list(session.scalars(select(OutboxEvent).where(OutboxEvent.published_at.is_(None)))))
    pending_proj = len(list(session.scalars(select(ProjectionJob).where(ProjectionJob.status == "pending"))))
    pending_settle = len(
        list(session.scalars(select(SettlementJob).where(SettlementJob.status.in_(("pending", "failed")))))
    )
    return {"outbox": pending_outbox, "projection": pending_proj, "settlement": pending_settle}


def mark_projection_complete(session: Session, job_id: UUID) -> None:
    job = session.get(ProjectionJob, job_id)
    if job is not None:
        job.status = "complete"
