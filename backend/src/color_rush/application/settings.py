from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from color_rush.domain.errors import ConflictError, NotFoundError
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.models import ConfigurationVersion, GameSession


def get_settings(session: Session, game_id: UUID) -> ConfigurationVersion:
    row = session.scalar(
        select(ConfigurationVersion)
        .where(ConfigurationVersion.game_id == game_id)
        .order_by(ConfigurationVersion.version.desc())
    )
    if row is None:
        raise NotFoundError("settings not found")
    return row


def put_settings(
    session: Session,
    *,
    game_id: UUID,
    configuration: dict[str, object],
    actor_id: UUID | None,
    now: datetime,
    session_id: UUID | None = None,
    expected_revision: int | None = None,
) -> ConfigurationVersion:
    RoundRules.from_snapshot(configuration)
    current = get_settings(session, game_id)
    if expected_revision is not None and current.version != expected_revision:
        raise ConflictError("stale settings revision")
    max_version = session.scalar(
        select(func.max(ConfigurationVersion.version)).where(ConfigurationVersion.game_id == game_id)
    )
    next_version = (max_version or 0) + 1
    row = ConfigurationVersion(
        id=uuid4(),
        game_id=game_id,
        version=next_version,
        configuration=configuration,
        activation_boundary="next_round",
        actor_id=actor_id,
        created_at=now,
    )
    session.add(row)
    if session_id is not None:
        game_session = session.get(GameSession, session_id)
        if game_session is None:
            raise NotFoundError("session not found")
        game_session.config_version = next_version
        game_session.revision += 1
        game_session.updated_at = now
    session.flush()
    return row
