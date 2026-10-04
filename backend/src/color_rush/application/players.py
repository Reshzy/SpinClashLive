from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.auth import record_admin_action
from color_rush.domain.enums import PeriodType
from color_rush.domain.errors import NotFoundError
from color_rush.infrastructure.persistence.models import (
    ChampionAward,
    CommandInbox,
    LeaderboardArchive,
    LeaderboardPeriod,
    LeaderboardScore,
    Player,
    PlayerStatistics,
)
from color_rush.infrastructure.security import hash_secret


def list_players(
    session: Session,
    *,
    search: str | None,
    cursor: str | None,
    limit: int = 50,
) -> tuple[list[Player], str | None]:
    stmt = select(Player).order_by(Player.id)
    if search:
        pattern = f"%{search[:64]}%"
        stmt = stmt.where(Player.display_name.ilike(pattern))
    if cursor:
        stmt = stmt.where(Player.id > UUID(cursor))
    rows = list(session.scalars(stmt.limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        next_cursor = str(rows[limit - 1].id)
        rows = rows[:limit]
    return rows, next_cursor


def player_ranks(session: Session, player_id: UUID, game_id: UUID) -> dict[str, object]:
    player = session.get(Player, player_id)
    if player is None:
        raise NotFoundError("player not found")
    stats = session.scalar(
        select(PlayerStatistics).where(
            PlayerStatistics.player_id == player_id,
            PlayerStatistics.game_id == game_id,
        )
    )
    ranks: dict[str, dict[str, object]] = {}
    for period_type in PeriodType:
        period = session.scalar(
            select(LeaderboardPeriod)
            .where(
                LeaderboardPeriod.game_id == game_id,
                LeaderboardPeriod.period_type == period_type.value,
                LeaderboardPeriod.status != "finalized",
            )
            .order_by(LeaderboardPeriod.starts_at.desc())
        )
        if period is None:
            ranks[period_type.value] = {"rank": None, "points": 0, "period_id": None}
            continue
        score = session.scalar(
            select(LeaderboardScore).where(
                LeaderboardScore.period_id == period.id,
                LeaderboardScore.player_id == player_id,
            )
        )
        points = score.points if score is not None else 0
        higher = session.scalar(
            select(LeaderboardScore).where(
                LeaderboardScore.period_id == period.id,
                LeaderboardScore.points > points,
            )
        )
        tied_before = 0
        if score is not None:
            tied_before = len(
                list(
                    session.scalars(
                        select(LeaderboardScore).where(
                            LeaderboardScore.period_id == period.id,
                            LeaderboardScore.points == points,
                            LeaderboardScore.player_id < player_id,
                        )
                    )
                )
            )
        higher_count = len(
            list(
                session.scalars(
                    select(LeaderboardScore).where(
                        LeaderboardScore.period_id == period.id,
                        LeaderboardScore.points > points,
                    )
                )
            )
        )
        del higher
        ranks[period_type.value] = {
            "rank": higher_count + tied_before + 1 if score is not None else None,
            "points": points,
            "period_id": str(period.id),
        }
    return {
        "player_id": str(player.id),
        "display_name": player.display_name,
        "stats": {
            "lifetime_points": stats.lifetime_points if stats else 0,
            "wins": stats.wins if stats else 0,
            "rounds_played": stats.rounds_played if stats else 0,
            "current_streak": stats.current_streak if stats else 0,
            "best_streak": stats.best_streak if stats else 0,
            "gold_wins": stats.gold_wins if stats else 0,
        },
        "ranks": ranks,
    }


def delete_player_data(
    session: Session,
    *,
    player_id: UUID,
    actor_id: UUID,
    now: datetime,
    request_id: str | None = None,
) -> Player:
    player = session.get(Player, player_id)
    if player is None:
        raise NotFoundError("player not found")
    original = player.provider_channel_id
    player.display_name = "[deleted]"
    player.avatar_ref = None
    player.provider_channel_id = f"anon:{hash_secret(original + str(player.id))[:24]}"
    player.deleted_at = now
    player.anonymized_at = now
    record_admin_action(
        session,
        actor_id=actor_id,
        action="player.delete_data",
        request_id=request_id,
        reason="data-request",
        before={"player_id": str(player_id)},
        after={"anonymized": True},
        now=now,
    )
    session.flush()
    return player


def list_leaderboard(
    session: Session,
    *,
    period_id: UUID,
    limit: int = 100,
    cursor: int = 0,
) -> list[dict[str, object]]:
    period = session.get(LeaderboardPeriod, period_id)
    if period is None:
        raise NotFoundError("period not found")
    scores = list(
        session.scalars(
            select(LeaderboardScore)
            .where(LeaderboardScore.period_id == period_id)
            .order_by(LeaderboardScore.points.desc(), LeaderboardScore.player_id.asc())
            .offset(cursor)
            .limit(limit)
        )
    )
    entries: list[dict[str, object]] = []
    for offset, row in enumerate(scores, start=cursor + 1):
        player = session.get(Player, row.player_id)
        entries.append(
            {
                "rank": offset,
                "player_id": str(row.player_id),
                "display_name": player.display_name if player else "[unknown]",
                "points": row.points,
                "rounds_played": row.rounds_played,
            }
        )
    return entries


def list_periods(session: Session, game_id: UUID, scope: str | None = None) -> list[LeaderboardPeriod]:
    stmt = (
        select(LeaderboardPeriod)
        .where(LeaderboardPeriod.game_id == game_id)
        .order_by(LeaderboardPeriod.starts_at.desc())
    )
    if scope:
        stmt = stmt.where(LeaderboardPeriod.period_type == scope)
    return list(session.scalars(stmt))


def list_champions(session: Session, period_id: UUID) -> list[ChampionAward]:
    return list(session.scalars(select(ChampionAward).where(ChampionAward.period_id == period_id)))


def list_archives(session: Session, period_id: UUID) -> list[LeaderboardArchive]:
    return list(
        session.scalars(
            select(LeaderboardArchive)
            .where(LeaderboardArchive.period_id == period_id)
            .order_by(LeaderboardArchive.final_rank.asc())
        )
    )


def purge_old_commands(session: Session, before: datetime) -> int:
    rows = list(session.scalars(select(CommandInbox).where(CommandInbox.received_at < before)))
    for row in rows:
        session.delete(row)
    return len(rows)
