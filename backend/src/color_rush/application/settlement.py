from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from color_rush.domain.enums import Color, RoundState, SettlementJobStatus
from color_rush.domain.errors import SettlementError
from color_rush.domain.rules import RoundRules
from color_rush.domain.scoring import score_pick
from color_rush.domain.streaks import StreakState, apply_streak
from color_rush.infrastructure.persistence.models import (
    GameSession,
    LeaderboardScore,
    OutboxEvent,
    Pick,
    PlayerStatistics,
    ProjectionJob,
    Round,
    RoundPeriod,
    ScoreLedger,
    SettlementJob,
)


def settle_partition(session: Session, job_id: UUID, now: datetime) -> SettlementJob:
    job = session.get(SettlementJob, job_id)
    if job is None:
        raise SettlementError("unknown settlement job")
    if job.status == SettlementJobStatus.COMPLETE.value:
        return job
    rnd = session.get(Round, job.round_id)
    if rnd is None or rnd.result is None or rnd.score_effective_at is None:
        raise SettlementError("round is not ready to settle")
    game_session = session.get(GameSession, rnd.session_id)
    if game_session is None:
        raise SettlementError("session missing")
    if RoundState(rnd.state) not in {RoundState.SETTLING, RoundState.SETTLED}:
        raise SettlementError("round is not settling")

    job.status = SettlementJobStatus.IN_PROGRESS.value
    job.attempts += 1
    rules = RoundRules.from_snapshot(rnd.rules_snapshot)
    result = Color(rnd.result)
    total_jobs = len(session.scalars(select(SettlementJob).where(SettlementJob.round_id == rnd.id)).all())
    picks = session.scalars(select(Pick).where(Pick.round_id == rnd.id).order_by(Pick.player_id)).all()
    eligible = [
        pick
        for pick in picks
        if _player_partition(session, pick.player_id, total_jobs) == job.partition
    ]

    inserted_ids: list[UUID] = []
    for pick in eligible:
        outcome = score_pick(Color(pick.choice), result, rules)
        stmt = (
            insert(ScoreLedger)
            .values(
                id=uuid4(),
                round_id=rnd.id,
                player_id=pick.player_id,
                correct=outcome.correct,
                points_delta=outcome.points_delta,
                effective_at=rnd.score_effective_at,
                rules_version=rules.version,
            )
            .on_conflict_do_nothing(constraint="uq_ledger_round_player")
            .returning(ScoreLedger.id, ScoreLedger.player_id, ScoreLedger.correct, ScoreLedger.points_delta)
        )
        inserted = session.execute(stmt).all()
        for row in inserted:
            inserted_ids.append(row.id)
            _apply_new_ledger_effects(
                session,
                game_id=game_session.game_id,
                round_id=rnd.id,
                player_id=row.player_id,
                correct=row.correct,
                points_delta=row.points_delta,
                result=result,
            )

    session.add(
        ProjectionJob(
            id=uuid4(),
            job_key=f"round:{rnd.id}:partition:{job.partition}:cursor:{job.cursor + 1}",
            status="pending",
            attempts=0,
            completed_watermark=job.cursor + 1,
            payload={"round_id": str(rnd.id), "partition": job.partition, "inserted": len(inserted_ids)},
        )
    )
    session.add(
        OutboxEvent(
            id=uuid4(),
            event_id=uuid4(),
            aggregate_type="round",
            aggregate_id=rnd.id,
            aggregate_revision=rnd.revision,
            event_type="settlement.partition",
            schema_version=1,
            payload={"partition": job.partition, "inserted": len(inserted_ids)},
            created_at=now,
            published_at=None,
        )
    )
    job.cursor += 1
    job.status = SettlementJobStatus.COMPLETE.value
    job.errors = None
    session.flush()
    return job


def _player_partition(session: Session, player_id: UUID, partition_count: int) -> int:
    value = session.execute(
        text("SELECT abs(hashtext(CAST(:pid AS text)))"),
        {"pid": str(player_id)},
    ).scalar_one()
    return int(value) % max(partition_count, 1)


def _apply_new_ledger_effects(
    session: Session,
    *,
    game_id: UUID,
    round_id: UUID,
    player_id: UUID,
    correct: bool,
    points_delta: int,
    result: Color,
) -> None:
    stats = session.scalar(
        select(PlayerStatistics).where(
            PlayerStatistics.player_id == player_id,
            PlayerStatistics.game_id == game_id,
        )
    )
    if stats is None:
        stats = PlayerStatistics(
            id=uuid4(),
            player_id=player_id,
            game_id=game_id,
            lifetime_points=0,
            wins=0,
            rounds_played=0,
            current_streak=0,
            best_streak=0,
            gold_wins=0,
        )
        session.add(stats)
        session.flush()
    streak = apply_streak(StreakState(stats.current_streak, stats.best_streak), correct=correct)
    stats.lifetime_points += points_delta
    stats.rounds_played += 1
    stats.current_streak = streak.current
    stats.best_streak = streak.best
    if correct:
        stats.wins += 1
        if result is Color.GOLD:
            stats.gold_wins += 1

    period_links = session.scalars(select(RoundPeriod).where(RoundPeriod.round_id == round_id)).all()
    for link in period_links:
        score = session.scalar(
            select(LeaderboardScore).where(
                LeaderboardScore.period_id == link.period_id,
                LeaderboardScore.player_id == player_id,
            )
        )
        if score is None:
            score = LeaderboardScore(
                id=uuid4(),
                period_id=link.period_id,
                player_id=player_id,
                points=0,
                correct_picks=0,
                rounds_played=0,
                gold_wins=0,
                best_streak=0,
            )
            session.add(score)
            session.flush()
        score.points += points_delta
        score.rounds_played += 1
        if correct:
            score.correct_picks += 1
            if result is Color.GOLD:
                score.gold_wins += 1
        if streak.best > score.best_streak:
            score.best_streak = streak.best
        score.score_version += 1


def all_partitions_complete(session: Session, round_id: UUID) -> bool:
    jobs = session.scalars(select(SettlementJob).where(SettlementJob.round_id == round_id)).all()
    if not jobs:
        return False
    return all(job.status == SettlementJobStatus.COMPLETE.value for job in jobs)


def settle_round(session: Session, round_id: UUID, now: datetime) -> None:
    jobs = session.scalars(
        select(SettlementJob).where(SettlementJob.round_id == round_id).order_by(SettlementJob.partition)
    ).all()
    if not jobs:
        raise SettlementError("settlement jobs missing")
    for job in jobs:
        settle_partition(session, job.id, now)
    if not all_partitions_complete(session, round_id):
        raise SettlementError("settlement partitions incomplete")
