from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from color_rush.application.auth import bootstrap_owner
from color_rush.application.coordinator import Coordinator
from color_rush.application.dto import NormalizedCommand, SourceCheckpointData
from color_rush.application.ingest import append_and_process
from color_rush.application.outbox import relay_outbox
from color_rush.application.players import delete_player_data, purge_old_commands
from color_rush.application.ports import FrozenClock, SequenceRng
from color_rush.application.projections import apply_projection_jobs
from color_rush.application.reconcile import reconcile_round
from color_rush.application.settlement import settle_round
from color_rush.application.source_health import (
    should_cancel_affected_round,
    source_blocks_new_rounds,
)
from color_rush.application.ws_buffer import SnapshotClientBuffer
from color_rush.config import Settings
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import DecisionReason, PeriodType, RoundState, SessionMode, SourceHealth
from color_rush.domain.errors import FencingError, RoundBusyError
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.models import (
    CommandInbox,
    GameSession,
    LeaderboardPeriod,
    Pick,
    Player,
    PlayerStatistics,
    RoundPeriod,
    ScoreLedger,
    SourceCheckpoint,
)
from color_rush.infrastructure.persistence.models import Round as RoundModel
from color_rush.infrastructure.redis.projections import rebuild_all_leaderboards, write_score
from color_rush.infrastructure.simulation.load import unique_player_round


def _cmd(channel: str, text: str, published: datetime, message_id: str) -> NormalizedCommand:
    return NormalizedCommand(
        provider="simulation",
        provider_message_id=message_id,
        broadcast_id="m5-broadcast",
        provider_channel_id=channel,
        display_name=channel,
        command_text=text,
        command=parse_command(text),
        published_at=published,
    )


def _checkpoint(token: str, **kwargs: object) -> SourceCheckpointData:
    return SourceCheckpointData(
        broadcast_id="m5-broadcast",
        next_page_token=token,
        source_mode="simulation",
        ownership_token="owner-a",
        session_id=None,
        **kwargs,  # type: ignore[arg-type]
    )


def _open_round(coordinator: Coordinator, game_session: GameSession, token: int) -> RoundModel:
    return coordinator.start_round(game_session.id, token, RoundRules())


def _published(rnd: RoundModel) -> datetime:
    opened = rnd.opened_at
    assert opened is not None
    return opened + timedelta(seconds=1)


def _calendar_coordinator(db_session: Session, clock: FrozenClock) -> Coordinator:
    return Coordinator(
        db_session,
        clock=clock,
        rng=SequenceRng([960]),
        owner_id="m5-calendar",
        lease_ttl_seconds=86_400,
        partition_count=4,
    )


def _advance_to_settling(coordinator: Coordinator, game_session: GameSession, token: int, clock) -> None:
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    clock.set(clock.now() + timedelta(seconds=20))
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)


@pytest.mark.integration
def test_ingest_crash_before_commit_replays(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    nested = db_session.begin_nested()
    try:
        append_and_process(
            db_session,
            session_id=game_session.id,
            commands=[_cmd("crash-b", "!red", _published(rnd), "crash-before")],
            checkpoint=_checkpoint("tok-crash-before"),
        )
        raise RuntimeError("simulated crash before commit")
    except RuntimeError:
        nested.rollback()
    assert db_session.scalar(select(func.count()).select_from(CommandInbox)) == 0
    assert db_session.get(SourceCheckpoint, "m5-broadcast") is None
    result = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("crash-b", "!red", _published(rnd), "crash-before")],
        checkpoint=_checkpoint("tok-crash-before"),
    )
    assert DecisionReason.ACCEPTED_NEW in result.decisions
    assert db_session.get(SourceCheckpoint, "m5-broadcast") is not None
    assert db_session.get(SourceCheckpoint, "m5-broadcast").next_page_token == "tok-crash-before"


@pytest.mark.integration
def test_ingest_crash_after_commit_dedupes(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    first = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("crash-a", "!green", _published(rnd), "crash-after")],
        checkpoint=_checkpoint("tok-after-1"),
    )
    assert first.sequences
    replay = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("crash-a", "!green", _published(rnd), "crash-after")],
        checkpoint=_checkpoint("tok-after-2"),
    )
    assert replay.sequences == ()
    inbox = list(db_session.scalars(select(CommandInbox).where(CommandInbox.provider_message_id == "crash-after")))
    assert len(inbox) == 1
    picks = list(db_session.scalars(select(Pick)))
    assert len(picks) == 1


@pytest.mark.integration
def test_second_coordinator_invalidates_stale_token(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    other = Coordinator(
        db_session,
        clock=clock,
        rng=coordinator.rng,
        owner_id="second-owner",
        lease_ttl_seconds=30,
        partition_count=4,
    )
    stolen = other.claim_lease(game_session.id)
    with pytest.raises(FencingError):
        coordinator.start_round(game_session.id, token, RoundRules())
    rnd = other.start_round(game_session.id, stolen.fencing_token, RoundRules())
    assert rnd.state == RoundState.OPEN.value


@pytest.mark.integration
def test_db_outage_does_not_fake_success(clock) -> None:
    engine = create_engine(
        "postgresql+psycopg://color_rush:color_rush@127.0.0.1:1/missing",
        connect_args={"connect_timeout": 1},
        pool_pre_ping=True,
        future=True,
    )
    dead = Session(engine)
    try:
        with pytest.raises(OperationalError):
            append_and_process(
                dead,
                session_id=uuid4(),
                commands=[_cmd("outage", "!red", clock.now(), "outage-1")],
                checkpoint=_checkpoint("tok-outage"),
            )
        dead_coordinator = Coordinator(
            dead,
            clock=clock,
            rng=SequenceRng([960]),
            owner_id="outage-worker",
            lease_ttl_seconds=5,
        )
        with pytest.raises(OperationalError):
            dead_coordinator.create_game("outage")
    finally:
        dead.close()
        engine.dispose()


@pytest.mark.integration
def test_source_ended_and_quota_pause_and_cancel(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    game_session.broadcast_ref = "m5-broadcast"
    db_session.add(
        SourceCheckpoint(
            broadcast_id="m5-broadcast",
            next_page_token="x",
            source_mode="simulation",
            last_success_at=clock.now(),
            ownership_token="owner-a",
            session_id=game_session.id,
            resync_required=False,
            error_class=SourceHealth.ENDED.value,
            lag_ms=0,
        )
    )
    db_session.flush()
    assert source_blocks_new_rounds(db_session, game_session) is True
    assert should_cancel_affected_round(SourceHealth.ENDED) is True
    cancelled = coordinator.cancel(game_session.id, token, "source_ended")
    assert cancelled.state == RoundState.CANCELLED.value
    checkpoint = db_session.get(SourceCheckpoint, "m5-broadcast")
    assert checkpoint is not None
    checkpoint.error_class = SourceHealth.QUOTA.value
    db_session.flush()
    with pytest.raises(RoundBusyError):
        coordinator.start_round(game_session.id, token, RoundRules())
    del rnd


@pytest.mark.integration
def test_midnight_unsettled_then_settle_stays_prior_day(
    db_session: Session, clock: FrozenClock
) -> None:
    coordinator = _calendar_coordinator(db_session, clock)
    game = coordinator.create_game()
    game_session = coordinator.create_session(game.id, mode=SessionMode.MANUAL, timezone="Asia/Manila")
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("midn", "!red", opened, "midn-1")],
        checkpoint=None,
    )
    scheduled = datetime(2026, 10, 4, 15, 59, 50, tzinfo=UTC)
    rnd.opened_at = datetime(2026, 10, 4, 15, 59, 20, tzinfo=UTC)
    rnd.scheduled_closes_at = scheduled
    db_session.flush()
    closed = coordinator.close_ingress(game_session.id, token, early=False)
    assert closed.score_effective_at == scheduled
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    clock.set(datetime(2026, 10, 4, 16, 10, tzinfo=UTC))
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    assigned = list(db_session.scalars(select(RoundPeriod).where(RoundPeriod.round_id == rnd.id)))
    daily = next(
        period
        for row in assigned
        if (period := db_session.get(LeaderboardPeriod, row.period_id)) is not None
        and period.period_type == PeriodType.DAILY.value
    )
    assert daily.local_identity == "2026-10-04"
    report = reconcile_round(db_session, rnd.id, None)
    assert report["ok"] is True
    assert report["picks"] == report["ledger"]


@pytest.mark.integration
def test_monday_unsettled_then_settle_stays_prior_week(
    db_session: Session, clock: FrozenClock
) -> None:
    coordinator = _calendar_coordinator(db_session, clock)
    game = coordinator.create_game()
    game_session = coordinator.create_session(game.id, mode=SessionMode.MANUAL, timezone="Asia/Manila")
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at
    assert opened is not None
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("mon", "!red", opened, "mon-1")],
        checkpoint=None,
    )
    scheduled = datetime(2026, 1, 4, 15, 59, 50, tzinfo=UTC)
    rnd.opened_at = datetime(2026, 1, 4, 15, 59, 20, tzinfo=UTC)
    rnd.scheduled_closes_at = scheduled
    db_session.flush()
    closed = coordinator.close_ingress(game_session.id, token, early=False)
    assert closed.score_effective_at == scheduled
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    clock.set(datetime(2026, 1, 5, 16, 10, tzinfo=UTC))
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    assigned = list(db_session.scalars(select(RoundPeriod).where(RoundPeriod.round_id == rnd.id)))
    weekly = next(
        period
        for row in assigned
        if (period := db_session.get(LeaderboardPeriod, row.period_id)) is not None
        and period.period_type == PeriodType.WEEKLY.value
    )
    assert weekly.local_identity == "2025-12-29"
    report = reconcile_round(db_session, rnd.id, None)
    assert report["ok"] is True


@pytest.mark.integration
def test_delete_and_retention(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("del-me", "!red", _published(rnd), "del-1")],
        checkpoint=None,
    )
    player = db_session.scalar(select(Player).where(Player.provider_channel_id == "del-me"))
    assert player is not None
    actor = bootstrap_owner(db_session, Settings(bootstrap_owner_username="m5-actor"), clock.now())
    delete_player_data(db_session, player_id=player.id, actor_id=actor.id, now=clock.now())
    db_session.refresh(player)
    assert player.deleted_at is not None
    assert player.display_name == "[deleted]"
    old = clock.now() - timedelta(days=8)
    row = db_session.scalar(select(CommandInbox))
    assert row is not None
    row.received_at = old
    db_session.flush()
    removed = purge_old_commands(db_session, clock.now() - timedelta(days=7))
    assert removed >= 1


@pytest.mark.integration
def test_redis_loss_rebuild_reconcile(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock, redis_client
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("rb1", "!gold", _published(rnd), "rb-1")],
        checkpoint=None,
    )
    _advance_to_settling(coordinator, game_session, token, clock)
    settle_round(db_session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    apply_projection_jobs(db_session, redis_client)
    redis_client.flushdb()
    rebuild_all_leaderboards(redis_client, db_session, game_session.game_id)
    report = reconcile_round(db_session, rnd.id, redis_client)
    assert report["ok"] is True
    assert report["picks"] == report["ledger"]
    ledgers = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert len(ledgers) == 1


@pytest.mark.integration
def test_stale_projection_overwrite_and_outbox_redelivery(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock, redis_client
) -> None:
    from uuid import uuid4 as new_id

    from color_rush.infrastructure.persistence.models import LeaderboardScore

    game_session, _token = started_session
    period = db_session.scalar(select(LeaderboardPeriod).where(LeaderboardPeriod.game_id == game_session.game_id))
    assert period is not None
    player_id = new_id()
    db_session.add(
        Player(
            id=player_id,
            provider="simulation",
            provider_channel_id=f"proj-{player_id.hex[:8]}",
            display_name="proj",
            avatar_ref=None,
            profile_refreshed_at=None,
            created_at=clock.now(),
            last_seen_at=clock.now(),
            deleted_at=None,
            anonymized_at=None,
        )
    )
    db_session.flush()
    db_session.add(
        LeaderboardScore(
            id=new_id(),
            period_id=period.id,
            player_id=player_id,
            points=10,
            correct_picks=1,
            rounds_played=1,
            gold_wins=0,
            best_streak=1,
            score_version=5,
        )
    )
    db_session.flush()
    assert write_score(
        redis_client,
        game_id=game_session.game_id,
        period_id=period.id,
        player_id=player_id,
        points=10,
        score_version=5,
    )
    assert (
        write_score(
            redis_client,
            game_id=game_session.game_id,
            period_id=period.id,
            player_id=player_id,
            points=99,
            score_version=4,
        )
        is False
    )
    from color_rush.infrastructure.persistence.models import OutboxEvent

    db_session.add(
        OutboxEvent(
            id=new_id(),
            event_id=new_id(),
            aggregate_type="session",
            aggregate_id=game_session.id,
            aggregate_revision=1,
            event_type="test.redeliver",
            schema_version=1,
            payload={"ok": True},
            created_at=clock.now(),
            published_at=None,
        )
    )
    db_session.flush()
    sent = relay_outbox(
        db_session,
        os.environ.get("COLOR_RUSH_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
        now=clock.now(),
    )
    assert sent >= 1
    sent_again = relay_outbox(
        db_session, os.environ.get("COLOR_RUSH_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"), now=clock.now()
    )
    assert sent_again == 0


@pytest.mark.integration
def test_settlement_crash_before_commit_then_retry(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p1", "!gold", _published(rnd), "crash-before-settle")],
        checkpoint=None,
    )
    _advance_to_settling(coordinator, game_session, token, clock)
    nested = db_session.begin_nested()
    settle_round(db_session, rnd.id, clock.now())
    assert db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)).first() is not None
    nested.rollback()
    assert db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)).first() is None
    settle_round(db_session, rnd.id, clock.now())
    ledgers = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert len(ledgers) == 1
    stats = list(db_session.scalars(select(PlayerStatistics).where(PlayerStatistics.game_id == game_session.game_id)))
    assert len(stats) == 1
    assert stats[0].rounds_played == 1
    coordinator.mark_settled(game_session.id, token)
    report = reconcile_round(db_session, rnd.id, None)
    assert report["ok"] is True
    assert report["picks"] == report["ledger"]


@pytest.mark.integration
def test_settlement_crash_after_commit_redelivery_is_idempotent(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = _open_round(coordinator, game_session, token)
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("p2", "!gold", _published(rnd), "crash-after-settle")],
        checkpoint=None,
    )
    _advance_to_settling(coordinator, game_session, token, clock)
    settle_round(db_session, rnd.id, clock.now())
    first = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert len(first) == 1
    stats = db_session.scalar(select(PlayerStatistics).where(PlayerStatistics.game_id == game_session.game_id))
    assert stats is not None
    played = stats.rounds_played
    points = stats.lifetime_points
    settle_round(db_session, rnd.id, clock.now())
    second = list(db_session.scalars(select(ScoreLedger).where(ScoreLedger.round_id == rnd.id)))
    assert len(second) == 1
    db_session.refresh(stats)
    assert stats.rounds_played == played
    assert stats.lifetime_points == points
    coordinator.mark_settled(game_session.id, token)
    report = reconcile_round(db_session, rnd.id, None)
    assert report["ok"] is True
    assert report["picks"] == report["ledger"]


@pytest.mark.integration
def test_subset_unique_round_reconciles(
    db_session: Session,
) -> None:
    report = unique_player_round(db_session, player_count=40, broadcast_id=f"load-{uuid4().hex[:8]}")
    assert report["ok"] is True
    assert int(report["picks"]) >= 40  # type: ignore[arg-type]
    assert report["picks"] == report["ledger"]
    assert float(report["settle_s"]) < 10  # type: ignore[arg-type]
    from uuid import UUID

    recon = reconcile_round(db_session, UUID(str(report["round_id"])), None)
    assert recon["ok"] is True
    assert recon["mismatches"] == []


@pytest.mark.asyncio
async def test_slow_and_disconnected_ws_buffer() -> None:
    from fastapi import WebSocketDisconnect

    from color_rush.api.ws import send_or_reset_buffer

    class _Slow:
        async def send_text(self, _raw: str) -> None:
            import asyncio

            await asyncio.sleep(0.2)

    class _Gone:
        async def send_text(self, _raw: str) -> None:
            raise WebSocketDisconnect()

    original = SnapshotClientBuffer()
    reset = await send_or_reset_buffer(
        _Slow(),  # type: ignore[arg-type]
        {"snapshot_sequence": 7, "data": {"state": "OPEN"}},
        original,
        timeout_s=0.05,
    )
    assert reset is not original
    with pytest.raises(WebSocketDisconnect):
        await send_or_reset_buffer(
            _Gone(),  # type: ignore[arg-type]
            {"snapshot_sequence": 8, "data": {}},
            SnapshotClientBuffer(),
        )
