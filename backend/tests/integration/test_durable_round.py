from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from color_rush.application.coordinator import Coordinator
from color_rush.application.dto import NormalizedCommand, SourceCheckpointData
from color_rush.application.ingest import append_and_process
from color_rush.application.periods import finalize_period
from color_rush.application.ports import FrozenClock, SequenceRng
from color_rush.application.settlement import settle_partition, settle_round
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import Color, DecisionReason, PeriodType, SessionMode
from color_rush.domain.errors import FencingError, IllegalTransitionError, RoundBusyError, SettlementError
from color_rush.domain.ranking import RankKey, sort_entries
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import database_clock
from color_rush.infrastructure.persistence.models import (
    CoordinatorLease,
    GameSession,
    LeaderboardPeriod,
    LeaderboardScore,
    Pick,
    PlayerStatistics,
    ScoreLedger,
    Season,
    SettlementJob,
    SourceCheckpoint,
)
from color_rush.infrastructure.persistence.models import (
    Round as RoundModel,
)


def _cmd(channel: str, text: str, published: datetime, message_id: str) -> NormalizedCommand:
    return NormalizedCommand(
        provider="simulation",
        provider_message_id=message_id,
        broadcast_id="itest",
        provider_channel_id=channel,
        display_name=channel,
        command_text=text,
        command=parse_command(text),
        published_at=published,
    )


def _pin_deadline(rnd: RoundModel, opened_at: datetime, scheduled_closes_at: datetime) -> None:
    rnd.opened_at = opened_at
    rnd.scheduled_closes_at = scheduled_closes_at


def _expire_deadline(db_session: Session, rnd: RoundModel) -> None:
    rnd.scheduled_closes_at = database_clock(db_session)


@pytest.mark.integration
def test_complete_simulated_round(db_session: Session, coordinator: Coordinator, clock: FrozenClock) -> None:
    game = coordinator.create_game()
    game_session = coordinator.create_session(game.id, mode=SessionMode.MANUAL)
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    commands = [
        _cmd("p1", "!red", opened + timedelta(seconds=1), "a"),
        _cmd("p2", "!gold", opened + timedelta(seconds=2), "b"),
        _cmd("p2", "!gold", opened + timedelta(seconds=3), "c"),
        _cmd("p3", "!green", opened + timedelta(seconds=4), "d"),
    ]
    result = append_and_process(session=db_session, session_id=game_session.id, commands=commands, checkpoint=None)
    assert DecisionReason.ACCEPTED_NEW in result.decisions
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    spun = coordinator.spin(game_session.id, token)
    assert spun.result == Color.GOLD.value
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    settled = coordinator.mark_settled(game_session.id, token)
    assert settled.state == "settled"
    ledgers = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert len(ledgers) == 3
    gold_row = next(row for row in ledgers if row.points_delta == 14)
    assert gold_row.correct is True
    zeros = [row for row in ledgers if row.points_delta == 0]
    assert len(zeros) == 2
    periods = list(db_session.scalars(select(LeaderboardPeriod).where(LeaderboardPeriod.game_id == game.id)))
    assert {item.period_type for item in periods} == {
        PeriodType.DAILY.value,
        PeriodType.WEEKLY.value,
        PeriodType.SEASON.value,
        PeriodType.ALL_TIME.value,
    }


@pytest.mark.integration
def test_duplicate_and_old_sequence_and_change_limit(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    db_session.autoflush = False
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    first = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!red", opened + timedelta(seconds=1), "dup")],
        checkpoint=SourceCheckpointData("itest", "tok-1", "simulation", "owner"),
    )
    replay = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!green", opened + timedelta(seconds=2), "dup")],
        checkpoint=SourceCheckpointData("itest", "tok-2", "simulation", "owner"),
    )
    assert replay.sequences == ()
    checkpoint = db_session.get(SourceCheckpoint, "itest")
    assert checkpoint is not None
    assert checkpoint.next_page_token == "tok-2"

    colors = ["!green", "!gold", "!red", "!green", "!gold", "!red"]
    extra = [
        _cmd("p1", text, opened + timedelta(seconds=3 + index), f"chg-{index}")
        for index, text in enumerate(colors)
    ]
    result = append_and_process(db_session, session_id=game_session.id, commands=extra, checkpoint=None)
    assert DecisionReason.REJECTED_CHANGE_LIMIT in result.decisions
    assert first.sequences
    picks = list(db_session.scalars(select(Pick).where(Pick.round_id == rnd.id)))
    assert len(picks) == 1


@pytest.mark.integration
def test_historical_and_deadline(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[
            _cmd("old", "!red", opened - timedelta(seconds=5), "hist"),
            _cmd("ok", "!green", opened + timedelta(seconds=1), "live"),
        ],
        checkpoint=None,
    )
    _expire_deadline(db_session, rnd)
    closed = coordinator.close_ingress(game_session.id, token, early=False)
    assert closed.score_effective_at == closed.scheduled_closes_at
    late = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("late", "!gold", opened + timedelta(seconds=32), "late")],
        checkpoint=None,
    )
    assert DecisionReason.REJECTED_AFTER_CUTOFF in late.decisions or DecisionReason.REJECTED_NOT_OPEN in late.decisions


@pytest.mark.integration
def test_stale_fence_and_two_starts(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    game_session, token = started_session
    coordinator.start_round(game_session.id, token, RoundRules())
    with pytest.raises(RoundBusyError):
        coordinator.start_round(game_session.id, token, RoundRules())
    with pytest.raises(FencingError):
        coordinator.close_ingress(game_session.id, token + 99, early=True)
    other = Coordinator(
        db_session,
        clock=coordinator.clock,
        rng=SequenceRng([1]),
        owner_id="intruder",
        partition_count=4,
    )
    other.claim_lease(game_session.id)
    with pytest.raises(FencingError):
        coordinator.spin(game_session.id, token)


@pytest.mark.integration
def test_restart_after_outcome_and_settlement_retry(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock: FrozenClock
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!gold", opened + timedelta(seconds=1), "g1")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    first = coordinator.spin(game_session.id, token)
    second = coordinator.spin(game_session.id, token)
    assert first.result == second.result
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    stats_before = list(
        db_session.scalars(select(PlayerStatistics).where(PlayerStatistics.game_id == game_session.game_id))
    )
    jobs = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    settle_round(db_session, rnd.id, clock.now())
    stats_after = list(
        db_session.scalars(select(PlayerStatistics).where(PlayerStatistics.game_id == game_session.game_id))
    )
    assert len(jobs) == 1
    assert stats_before[0].rounds_played == stats_after[0].rounds_played
    assert stats_before[0].lifetime_points == stats_after[0].lifetime_points


@pytest.mark.integration
def test_zero_point_retry_and_ties(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock: FrozenClock
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[
            _cmd("z1", "!red", opened + timedelta(seconds=1), "z1"),
            _cmd("z2", "!green", opened + timedelta(seconds=2), "z2"),
        ],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    ledgers = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert all(row.points_delta == 0 for row in ledgers)
    period_ids = list(
        db_session.scalars(select(LeaderboardPeriod.id).where(LeaderboardPeriod.game_id == game_session.game_id))
    )
    scores = list(
        db_session.scalars(select(LeaderboardScore).where(LeaderboardScore.period_id.in_(period_ids)))
    )
    ordered = sort_entries([RankKey(row.points, row.player_id) for row in scores])
    assert ordered[0].player_id < ordered[-1].player_id or len(ordered) == 1


@pytest.mark.integration
def test_midnight_attribution_and_idempotent_finalize(
    db_session: Session, clock: FrozenClock
) -> None:
    coordinator = Coordinator(
        db_session,
        clock=clock,
        rng=SequenceRng([960]),
        owner_id="boundary-worker",
        partition_count=2,
        lease_ttl_seconds=86_400,
    )
    game = coordinator.create_game()
    game_session = coordinator.create_session(game.id)
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules(prediction_window_s=30))
    opened = datetime(2026, 1, 4, 15, 59, 30, tzinfo=UTC)
    scheduled = datetime(2026, 1, 4, 16, 0, tzinfo=UTC)
    _pin_deadline(rnd, opened, scheduled)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("edge", "!gold", opened + timedelta(seconds=1), "edge")],
        checkpoint=None,
    )
    closed = coordinator.close_ingress(game_session.id, token, early=False)
    assert closed.score_effective_at == scheduled
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    daily = db_session.scalar(
        select(LeaderboardPeriod).where(
            LeaderboardPeriod.game_id == game.id,
            LeaderboardPeriod.period_type == PeriodType.DAILY.value,
            LeaderboardPeriod.local_identity == "2026-01-05",
        )
    )
    assert daily is not None
    first = finalize_period(db_session, daily.id, datetime(2026, 1, 6, 16, 0, tzinfo=UTC))
    second = finalize_period(db_session, daily.id, datetime(2026, 1, 7, 16, 0, tzinfo=UTC))
    assert first is not None and second is not None
    assert first.finalized_at == second.finalized_at


@pytest.mark.integration
def test_cannot_start_before_settled(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    game_session, token = started_session
    coordinator.start_round(game_session.id, token, RoundRules())
    with pytest.raises(RoundBusyError):
        coordinator.start_round(game_session.id, token, RoundRules())


@pytest.mark.integration
def test_lease_row_exists(started_session: tuple[GameSession, int], db_session: Session) -> None:
    game_session, _token = started_session
    lease = db_session.get(CoordinatorLease, game_session.id)
    assert lease is not None
    assert lease.fencing_token >= 1


@pytest.mark.integration
def test_pause_cancel_and_next_bonus(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    from color_rush.domain.enums import BonusType

    game_session, token = started_session
    coordinator.pause(game_session.id, token)
    with pytest.raises(RoundBusyError):
        coordinator.start_round(game_session.id, token, RoundRules())
    coordinator.resume(game_session.id, token)
    coordinator.set_next_bonus(game_session.id, token, BonusType.DOUBLE_POINTS)
    rnd = coordinator.start_round(game_session.id, token)
    assert rnd.rules_snapshot["bonus"] == BonusType.DOUBLE_POINTS.value
    cancelled = coordinator.cancel(game_session.id, token, "operator")
    assert cancelled.state == "cancelled"
    nxt = coordinator.start_round(game_session.id, token, RoundRules())
    assert nxt.number == rnd.number + 1


@pytest.mark.integration
def test_drain_timeout_cancels(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    coordinator.close_ingress(game_session.id, token, early=True)
    loaded = db_session.get(RoundModel, rnd.id)
    assert loaded is not None
    loaded.drain_deadline_at = datetime(2000, 1, 1, tzinfo=UTC)
    cancelled = coordinator.complete_drain(game_session.id, token)
    assert cancelled.state == "cancelled"
    assert cancelled.cancel_reason == "drain_timeout"


@pytest.mark.integration
def test_alembic_upgrade_created_schema(pg_engine: Engine) -> None:
    with pg_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        seasons = conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'seasons'")
        ).scalar_one()
        constraint = conn.execute(
            text("SELECT conname FROM pg_constraint WHERE conname = 'ex_seasons_no_overlap'")
        ).scalar_one()
        overlay = conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'overlay_tickets'")
        ).scalar_one()
    assert version == "0002_m2_auth_source"
    assert seasons == 1
    assert overlay == 1
    assert constraint == "ex_seasons_no_overlap"


@pytest.mark.integration
def test_mark_settled_requires_all_partitions(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock: FrozenClock
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!gold", opened + timedelta(seconds=1), "part")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    with pytest.raises(SettlementError):
        coordinator.mark_settled(game_session.id, token)
    jobs = list(db_session.scalars(select(SettlementJob).where(SettlementJob.round_id == rnd.id)))
    settle_partition(db_session, jobs[0].id, clock.now())
    with pytest.raises(SettlementError):
        coordinator.mark_settled(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    settled = coordinator.mark_settled(game_session.id, token)
    assert settled.state == "settled"


@pytest.mark.integration
def test_settlement_crash_before_commit_then_retry(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock: FrozenClock
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!gold", opened + timedelta(seconds=1), "crash")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    nested = db_session.begin_nested()
    settle_round(db_session, rnd.id, clock.now())
    assert db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)).first() is not None
    nested.rollback()
    assert db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)).first() is None
    settle_round(db_session, rnd.id, clock.now())
    ledgers = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert len(ledgers) == 1
    stats = db_session.scalars(
        select(PlayerStatistics).where(PlayerStatistics.game_id == game_session.game_id)
    ).all()
    assert len(stats) == 1
    assert stats[0].rounds_played == 1
    coordinator.mark_settled(game_session.id, token)


@pytest.mark.integration
def test_restart_before_outcome_then_idempotent_spin(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int]
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!gold", opened + timedelta(seconds=1), "pre")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    assert rnd.state == "locked"
    assert rnd.result is None
    restarted = coordinator.claim_lease(game_session.id)
    spun = coordinator.spin(game_session.id, restarted.fencing_token)
    assert spun.result == Color.GOLD.value
    again = coordinator.claim_lease(game_session.id)
    second = coordinator.spin(game_session.id, again.fencing_token)
    assert second.result == spun.result
    assert second.result_draw == spun.result_draw


@pytest.mark.integration
def test_monday_and_season_attribution(
    db_session: Session, clock: FrozenClock
) -> None:
    coordinator = Coordinator(
        db_session,
        clock=clock,
        rng=SequenceRng([960, 960]),
        owner_id="calendar-worker",
        partition_count=2,
        lease_ttl_seconds=86_400,
    )
    game = coordinator.create_game()
    game_session = coordinator.create_session(game.id)
    token = coordinator.claim_lease(game_session.id).fencing_token
    monday_round = coordinator.start_round(game_session.id, token, RoundRules())
    monday_open = datetime(2026, 1, 4, 15, 59, 30, tzinfo=UTC)
    monday_close = datetime(2026, 1, 4, 16, 0, tzinfo=UTC)
    _pin_deadline(monday_round, monday_open, monday_close)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("cal", "!gold", monday_open + timedelta(seconds=1), "mon")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=False)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, monday_round.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    coordinator.enter_cooldown(game_session.id, token)
    weekly = db_session.scalar(
        select(LeaderboardPeriod).where(
            LeaderboardPeriod.game_id == game.id,
            LeaderboardPeriod.period_type == PeriodType.WEEKLY.value,
            LeaderboardPeriod.local_identity == "2026-01-05",
        )
    )
    assert weekly is not None
    season = db_session.scalar(
        select(LeaderboardPeriod).where(
            LeaderboardPeriod.game_id == game.id,
            LeaderboardPeriod.period_type == PeriodType.SEASON.value,
            LeaderboardPeriod.local_identity == "Season 2026-01",
        )
    )
    assert season is not None

    february = coordinator.start_round(game_session.id, token, RoundRules())
    feb_open = datetime(2026, 1, 31, 15, 59, 30, tzinfo=UTC)
    feb_close = datetime(2026, 1, 31, 16, 0, tzinfo=UTC)
    _pin_deadline(february, feb_open, feb_close)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("cal2", "!gold", feb_open + timedelta(seconds=1), "feb")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=False)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, february.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    feb_season = db_session.scalar(
        select(LeaderboardPeriod).where(
            LeaderboardPeriod.game_id == game.id,
            LeaderboardPeriod.period_type == PeriodType.SEASON.value,
            LeaderboardPeriod.local_identity == "Season 2026-02",
        )
    )
    assert feb_season is not None


@pytest.mark.integration
def test_overlapping_seasons_rejected(db_session: Session, coordinator: Coordinator) -> None:
    game = coordinator.create_game()
    coordinator.create_session(game.id)
    existing = db_session.scalars(select(Season).where(Season.game_id == game.id)).first()
    assert existing is not None
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Season(
                id=uuid4(),
                game_id=game.id,
                name="overlap",
                starts_at=existing.starts_at + timedelta(days=1),
                ends_at=existing.ends_at + timedelta(days=1),
                status="open",
            )
        )
        db_session.flush()
    db_session.add(
        Season(
            id=uuid4(),
            game_id=game.id,
            name="adjacent",
            starts_at=existing.ends_at,
            ends_at=existing.ends_at + timedelta(days=30),
            status="open",
        )
    )
    db_session.flush()


@pytest.mark.integration
def test_deadline_closure_race(pg_engine: Engine) -> None:
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False, future=True)
    setup = factory()
    clock = FrozenClock(datetime(2026, 1, 4, 8, 0, tzinfo=UTC))
    coordinator = Coordinator(
        setup,
        clock=clock,
        rng=SequenceRng([960]),
        owner_id="race-owner",
        partition_count=2,
        lease_ttl_seconds=600,
    )
    game = coordinator.create_game()
    game_session = coordinator.create_session(game.id)
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    rnd.scheduled_closes_at = datetime(2026, 1, 1, tzinfo=UTC)
    session_id = game_session.id
    setup.commit()
    setup.close()

    outcomes: list[str] = []
    barrier = Barrier(2)

    def worker() -> None:
        session = factory()
        coord = Coordinator(
            session,
            clock=clock,
            rng=SequenceRng([1]),
            owner_id="race-owner",
            partition_count=2,
            lease_ttl_seconds=600,
        )
        try:
            barrier.wait(timeout=5)
            coord.close_ingress(session_id, token, early=False)
            session.commit()
            outcomes.append("ok")
        except Exception as exc:
            session.rollback()
            outcomes.append(type(exc).__name__)
        finally:
            session.close()

    first = Thread(target=worker)
    second = Thread(target=worker)
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert outcomes.count("ok") == 1
    assert IllegalTransitionError.__name__ in outcomes
