from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.domain.enums import PeriodStatus
from color_rush.domain.errors import ConflictError, NotFoundError
from color_rush.infrastructure.persistence.models import Season


def list_seasons(session: Session, game_id: UUID) -> list[Season]:
    return list(
        session.scalars(select(Season).where(Season.game_id == game_id).order_by(Season.starts_at.desc()))
    )


def create_season(
    session: Session,
    *,
    game_id: UUID,
    name: str,
    starts_at: datetime,
    ends_at: datetime,
) -> Season:
    overlap = session.scalars(
        select(Season).where(
            Season.game_id == game_id,
            Season.starts_at < ends_at,
            Season.ends_at > starts_at,
        )
    ).first()
    if overlap is not None:
        raise ConflictError("season intervals cannot overlap")
    row = Season(
        id=uuid4(),
        game_id=game_id,
        name=name[:120],
        starts_at=starts_at,
        ends_at=ends_at,
        status=PeriodStatus.OPEN.value,
    )
    session.add(row)
    try:
        session.flush()
    except Exception as exc:
        raise ConflictError("season intervals cannot overlap") from exc
    return row


def get_season(session: Session, season_id: UUID) -> Season:
    row = session.get(Season, season_id)
    if row is None:
        raise NotFoundError("season not found")
    return row
