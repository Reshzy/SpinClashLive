from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.coordinator import Coordinator
from color_rush.application.dto import NormalizedCommand, SourceCheckpointData
from color_rush.application.ingest import append_and_process
from color_rush.application.periods import finalize_period
from color_rush.application.ports import FrozenClock, SequenceRng
from color_rush.application.settlement import settle_round
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import Color, DecisionReason, PeriodType, SessionMode
from color_rush.domain.errors import FencingError, RoundBusyError
from color_rush.domain.ranking import RankKey, sort_entries
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.models import (
    CoordinatorLease,
    GameSession,
    LeaderboardPeriod,
    LeaderboardScore,
    PlayerStatistics,
    ScoreLedger,
    SourceCheckpoint,
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


@pytest.mark.integration
def test_historical_and_deadline(
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
            _cmd("old", "!red", opened - timedelta(seconds=5), "hist"),
            _cmd("ok", "!green", opened + timedelta(seconds=1), "live"),
        ],
        checkpoint=None,
    )
    clock.set(opened + timedelta(seconds=31))
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
    stats_before = list(db_session.scalars(select(PlayerStatistics)))
    jobs = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    settle_round(db_session, rnd.id, clock.now())
    stats_after = list(db_session.scalars(select(PlayerStatistics)))
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
    scores = list(db_session.scalars(select(LeaderboardScore)))
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
    )
    game = coordinator.create_game()
    # 16:00 UTC is midnight Asia/Manila
    clock.set(datetime(2026, 10, 4, 15, 59, 30, tzinfo=UTC))
    game_session = coordinator.create_session(game.id)
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules(prediction_window_s=30))
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("edge", "!gold", opened + timedelta(seconds=1), "edge")],
        checkpoint=None,
    )
    clock.set(datetime(2026, 10, 4, 16, 0, 10, tzinfo=UTC))
    closed = coordinator.close_ingress(game_session.id, token, early=False)
    assert closed.score_effective_at == closed.scheduled_closes_at
    assert closed.scheduled_closes_at is not None
    assert closed.scheduled_closes_at < datetime(2026, 10, 4, 16, 0, tzinfo=UTC)
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
            LeaderboardPeriod.local_identity == "2026-10-04",
        )
    )
    assert daily is not None
    first = finalize_period(db_session, daily.id, datetime(2026, 10, 5, 16, 0, tzinfo=UTC))
    second = finalize_period(db_session, daily.id, datetime(2026, 10, 6, 16, 0, tzinfo=UTC))
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
    coordinator.set_next_bonus(game_session.id, BonusType.DOUBLE_POINTS)
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
    from color_rush.infrastructure.persistence.models import Round as RoundModel

    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    coordinator.close_ingress(game_session.id, token, early=True)
    loaded = db_session.get(RoundModel, rnd.id)
    assert loaded is not None
    loaded.drain_deadline_at = datetime(2000, 1, 1, tzinfo=UTC)
    cancelled = coordinator.complete_drain(game_session.id, token)
    assert cancelled.state == "cancelled"
    assert cancelled.cancel_reason == "drain_timeout"
