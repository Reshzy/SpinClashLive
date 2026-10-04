from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.domain.enums import ChampionAwardType, PeriodStatus, PeriodType
from color_rush.domain.periods import PeriodWindow, month_window, windows_for
from color_rush.domain.ranking import RankKey, ordinal_ranks
from color_rush.infrastructure.persistence.models import (
    ChampionAward,
    LeaderboardArchive,
    LeaderboardPeriod,
    LeaderboardScore,
    Round,
    RoundPeriod,
    Season,
)


def ensure_covering_season(
    session: Session,
    game_id: UUID,
    instant: datetime,
    timezone: str,
) -> Season:
    tz = ZoneInfo(timezone)
    existing = session.scalars(
        select(Season).where(
            Season.game_id == game_id,
            Season.starts_at <= instant,
            Season.ends_at > instant,
        )
    ).first()
    if existing is not None:
        return existing
    window = month_window(instant, tz)
    assert window.ends_at is not None
    season = Season(
        id=uuid4(),
        game_id=game_id,
        name=f"Season {window.local_identity}",
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        status=PeriodStatus.OPEN.value,
    )
    session.add(season)
    session.flush()
    return season


def _upsert_period(
    session: Session,
    game_id: UUID,
    window: PeriodWindow,
    timezone: str,
    season_id: UUID | None,
) -> LeaderboardPeriod:
    existing = session.scalar(
        select(LeaderboardPeriod).where(
            LeaderboardPeriod.game_id == game_id,
            LeaderboardPeriod.period_type == window.period_type.value,
            LeaderboardPeriod.local_identity == window.local_identity,
            LeaderboardPeriod.timezone_version == timezone,
        )
    )
    if existing is not None:
        return existing
    row = LeaderboardPeriod(
        id=uuid4(),
        game_id=game_id,
        period_type=window.period_type.value,
        starts_at=window.starts_at,
        ends_at=window.ends_at,
        timezone_version=timezone,
        season_id=season_id if window.period_type is PeriodType.SEASON else None,
        status=PeriodStatus.OPEN.value,
        local_identity=window.local_identity,
        finalized_at=None,
    )
    session.add(row)
    session.flush()
    return row


def ensure_periods_for(
    session: Session,
    game_id: UUID,
    instant: datetime,
    timezone: str,
) -> list[LeaderboardPeriod]:
    tz = ZoneInfo(timezone)
    season = ensure_covering_season(session, game_id, instant, timezone)
    season_window = PeriodWindow(
        period_type=PeriodType.SEASON,
        starts_at=season.starts_at,
        ends_at=season.ends_at,
        local_identity=season.name,
        season_id=str(season.id),
    )
    created: list[LeaderboardPeriod] = []
    for window in windows_for(instant, tz, season_window):
        sid = season.id if window.period_type is PeriodType.SEASON else None
        created.append(_upsert_period(session, game_id, window, timezone, sid))
    return created


def assign_round_periods(
    session: Session,
    *,
    game_id: UUID,
    round_id: UUID,
    effective_at: datetime,
    timezone: str,
) -> list[RoundPeriod]:
    existing = session.scalars(select(RoundPeriod).where(RoundPeriod.round_id == round_id)).all()
    if existing:
        return list(existing)
    periods = ensure_periods_for(session, game_id, effective_at, timezone)
    assigned: list[RoundPeriod] = []
    for period in periods:
        row = RoundPeriod(
            id=uuid4(),
            round_id=round_id,
            period_type=period.period_type,
            period_id=period.id,
        )
        session.add(row)
        assigned.append(row)
    session.flush()
    return assigned


def begin_period_closing(session: Session, period: LeaderboardPeriod, now: datetime) -> None:
    if period.status == PeriodStatus.FINALIZED.value:
        return
    if period.ends_at is not None and now >= period.ends_at:
        period.status = PeriodStatus.CLOSING.value


def attributed_rounds_unresolved(session: Session, period_id: UUID) -> bool:
    rows = session.scalars(select(RoundPeriod).where(RoundPeriod.period_id == period_id)).all()
    for link in rows:
        rnd = session.get(Round, link.round_id)
        if rnd is None:
            continue
        if rnd.state not in {"settled", "cancelled", "cooldown"}:
            return True
    return False


def finalize_period(session: Session, period_id: UUID, now: datetime) -> LeaderboardPeriod | None:
    period = session.get(LeaderboardPeriod, period_id)
    if period is None:
        return None
    if period.status == PeriodStatus.FINALIZED.value:
        return period
    if period.ends_at is None:
        return period
    if now < period.ends_at:
        return period
    period.status = PeriodStatus.CLOSING.value
    if attributed_rounds_unresolved(session, period_id):
        return period
    scores = list(
        session.scalars(select(LeaderboardScore).where(LeaderboardScore.period_id == period_id)).all()
    )
    if not scores:
        period.status = PeriodStatus.FINALIZED.value
        period.finalized_at = now
        return period
    keys = [RankKey(points=row.points, player_id=row.player_id) for row in scores]
    score_by_player = {row.player_id: row for row in scores}
    already = session.scalars(
        select(LeaderboardArchive).where(LeaderboardArchive.period_id == period_id)
    ).first()
    if already is None:
        for rank, key in ordinal_ranks(keys):
            if rank > 100:
                break
            src = score_by_player[key.player_id]
            session.add(
                LeaderboardArchive(
                    id=uuid4(),
                    period_id=period_id,
                    player_id=key.player_id,
                    final_rank=rank,
                    points=src.points,
                    correct_picks=src.correct_picks,
                    rounds_played=src.rounds_played,
                    gold_wins=src.gold_wins,
                    best_streak=src.best_streak,
                )
            )
    if scores and session.scalar(
        select(ChampionAward).where(
            ChampionAward.period_id == period_id,
            ChampionAward.award_type == ChampionAwardType.CHAMPION.value,
        )
    ) is None:
        champion = ordinal_ranks(keys)[0][1]
        session.add(
            ChampionAward(
                id=uuid4(),
                period_id=period_id,
                award_type=ChampionAwardType.CHAMPION.value,
                player_id=champion.player_id,
                display_title="Champion",
                created_at=now,
            )
        )
    period.status = PeriodStatus.FINALIZED.value
    period.finalized_at = now
    session.flush()
    return period


def finalize_due_periods(session: Session, game_id: UUID, now: datetime) -> int:
    periods = session.scalars(
        select(LeaderboardPeriod).where(
            LeaderboardPeriod.game_id == game_id,
            LeaderboardPeriod.status.in_((PeriodStatus.OPEN.value, PeriodStatus.CLOSING.value)),
        )
    ).all()
    count = 0
    for period in periods:
        before = period.status
        finalize_period(session, period.id, now)
        if period.status == PeriodStatus.FINALIZED.value and before != PeriodStatus.FINALIZED.value:
            count += 1
    return count
