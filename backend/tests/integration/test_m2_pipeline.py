from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.api.app import create_app
from color_rush.application.auth import bootstrap_owner
from color_rush.application.coordinator import Coordinator
from color_rush.application.dto import NormalizedCommand
from color_rush.application.ingest import append_and_process
from color_rush.application.moderation import set_moderation
from color_rush.application.outbox import relay_outbox
from color_rush.application.overlay_tickets import create_overlay_ticket
from color_rush.application.players import player_ranks
from color_rush.application.projections import apply_projection_jobs
from color_rush.application.settlement import settle_round
from color_rush.composition import build_container, set_runtime_container
from color_rush.config import Settings
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import DecisionReason, RoundState
from color_rush.domain.errors import FencingError
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.models import GameSession, Pick, Player
from color_rush.infrastructure.redis.projections import rank_of, redis_available, top_n, write_score
from color_rush.infrastructure.simulation.source import SimulationChatSource


def _cmd(channel: str, name: str, text: str, published: datetime, message_id: str) -> NormalizedCommand:
    return NormalizedCommand(
        provider="simulation",
        provider_message_id=message_id,
        broadcast_id="m2-broadcast",
        provider_channel_id=channel,
        display_name=name,
        command_text=text,
        command=parse_command(text),
        published_at=published,
    )


@pytest.fixture
def redis_client() -> Redis:
    url = os.environ.get("COLOR_RUSH_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    client = Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except RedisError as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    client.flushdb()
    return client


@pytest.mark.integration
def test_set_next_bonus_requires_fence(coordinator: Coordinator, started_session: tuple[GameSession, int]) -> None:
    from color_rush.domain.enums import BonusType

    game_session, _token = started_session
    with pytest.raises(FencingError):
        coordinator.set_next_bonus(game_session.id, 999999, BonusType.DOUBLE_POINTS)


@pytest.mark.integration
def test_blocked_player_rejected_during_drain(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    published = clock.now()
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("ch-block", "Blocked", "!red", published, "b1")],
        checkpoint=None,
    )
    player = db_session.scalar(select(Player).where(Player.provider_channel_id == "ch-block"))
    assert player is not None
    from color_rush.application.auth import bootstrap_owner
    from color_rush.config import Settings

    actor = bootstrap_owner(db_session, Settings(bootstrap_owner_username="mod-actor"), published)
    set_moderation(
        db_session,
        player_id=player.id,
        scope_key=f"session:{game_session.id}",
        blocked=True,
        reason="test",
        actor_id=actor.id,
        now=published,
    )
    db_session.flush()
    pick = db_session.scalar(select(Pick).where(Pick.round_id == rnd.id, Pick.player_id == player.id))
    assert pick is None
    coordinator.close_ingress(game_session.id, token, early=True)
    locked = coordinator.complete_drain(game_session.id, token)
    assert locked.state == RoundState.LOCKED.value


@pytest.mark.integration
def test_lookup_and_help_cooldown(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    coordinator.start_round(game_session.id, token, RoundRules())
    published = clock.now()
    first = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("ch-a", "Ann", "!score", published, "s1")],
        checkpoint=None,
    )
    second = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("ch-a", "Ann", "!score", published, "s2")],
        checkpoint=None,
    )
    assert DecisionReason.IGNORED_LOOKUP in first.decisions
    assert DecisionReason.THROTTLED_LOOKUP in second.decisions
    help1 = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("ch-a", "Ann", "!help", published, "h1")],
        checkpoint=None,
    )
    help2 = append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("ch-b", "Ben", "!help", published, "h2")],
        checkpoint=None,
    )
    assert DecisionReason.IGNORED_HELP in help1.decisions
    assert DecisionReason.HELP_COOLDOWN in help2.decisions


@pytest.mark.integration
def test_sim_source_to_settlement_and_redis(
    db_session: Session,
    coordinator: Coordinator,
    started_session: tuple[GameSession, int],
    clock,
    redis_client: Redis,
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    source = SimulationChatSource(clock=clock, broadcast_id="m2-broadcast", session_id=game_session.id, seed=3)
    source.connect()
    for batch in source.iter_batches():
        append_and_process(
            db_session,
            session_id=game_session.id,
            commands=list(batch.commands),
            checkpoint=batch.checkpoint,
        )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    clock.set(clock.now() + timedelta(seconds=20))
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    relay_outbox(db_session, os.environ.get("COLOR_RUSH_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"), now=clock.now())
    apply_projection_jobs(db_session, redis_client)
    assert redis_available(redis_client)
    first_player = db_session.scalar(select(Player))
    assert first_player is not None
    ranks = player_ranks(db_session, first_player.id, game_session.game_id)
    assert "weekly" in ranks["ranks"]


@pytest.mark.integration
def test_stale_projection_cannot_overwrite(redis_client: Redis) -> None:
    game_id = uuid4()
    period_id = uuid4()
    player_id = uuid4()
    assert write_score(
        redis_client, game_id=game_id, period_id=period_id, player_id=player_id, points=10, score_version=2
    )
    assert not write_score(
        redis_client, game_id=game_id, period_id=period_id, player_id=player_id, points=1, score_version=1
    )
    rows = top_n(redis_client, game_id=game_id, period_id=period_id, limit=10)
    assert rows[0][1] == 10
    assert rank_of(redis_client, game_id=game_id, period_id=period_id, player_id=player_id) == 1


@pytest.mark.integration
def test_zero_score_tie_order_matches_sql_policy(redis_client: Redis) -> None:
    game_id = uuid4()
    period_id = uuid4()
    low = uuid4()
    high = uuid4()
    first, second = sorted([low, high])
    write_score(redis_client, game_id=game_id, period_id=period_id, player_id=second, points=0, score_version=1)
    write_score(redis_client, game_id=game_id, period_id=period_id, player_id=first, points=0, score_version=1)
    rows = top_n(redis_client, game_id=game_id, period_id=period_id, limit=10)
    assert [row[0] for row in rows] == [first, second]


@pytest.mark.integration
def test_auth_roles_and_overlay_ticket(
    pg_engine,
    redis_client: Redis,
) -> None:
    url = pg_engine.url.render_as_string(hide_password=False)
    settings = Settings(
        database_url=url,
        secret_key="test-secret",
        color_rush_env="simulation",
        redis_url="redis://127.0.0.1:6379/15",
    )
    container = build_container(settings, redis=redis_client)
    set_runtime_container(container)
    with container.session_factory() as session:
        owner = bootstrap_owner(session, settings, datetime.now(tz=UTC))
        session.commit()
        username = owner.username
    client = TestClient(create_app(container))
    denied = client.get("/api/v1/game/snapshot")
    assert denied.status_code == 401
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": settings.bootstrap_owner_password},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    health = client.get("/api/v1/admin/health", headers=headers)
    assert health.status_code == 200
    with container.session_factory() as session:
        coordinator = container.coordinator(session)
        game = coordinator.create_game()
        game_session = coordinator.create_session(game.id)
        ticket, secret = create_overlay_ticket(
            session,
            game_id=game.id,
            session_id=game_session.id,
            label="obs",
            now=datetime.now(tz=UTC),
            ttl_seconds=3600,
        )
        session.commit()
        ticket_id = ticket.id
    created = client.post(
        "/api/v1/admin/overlay-tickets",
        headers={**headers, "Idempotency-Key": "ticket-create-1"},
        json={"game_id": str(game.id), "session_id": str(game_session.id), "label": "obs2"},
    )
    assert created.status_code == 200
    assert "secret" in created.json()
    overlay_secret = created.json()["secret"]
    exchanged = client.post("/api/v1/overlay/ws-ticket", json={"secret": overlay_secret})
    assert exchanged.status_code == 200
    ws_ticket = exchanged.json()["ticket"]
    assert exchanged.json()["ws_path"] == "/ws/v1/overlay"
    denied_secret = client.get("/api/v1/admin/health", headers={"Authorization": f"Bearer {overlay_secret}"})
    assert denied_secret.status_code == 401
    denied_ws = client.get("/api/v1/admin/health", headers={"Authorization": f"Bearer {ws_ticket}"})
    assert denied_ws.status_code == 401
    replay = client.post(
        "/api/v1/admin/overlay-tickets",
        headers={**headers, "Idempotency-Key": "ticket-create-1"},
        json={"game_id": str(game.id), "session_id": str(game_session.id), "label": "obs2"},
    )
    assert replay.status_code == 200
    assert replay.json()["ticket_id"] == created.json()["ticket_id"]
    conflict = client.post(
        "/api/v1/admin/overlay-tickets",
        headers={**headers, "Idempotency-Key": "ticket-create-1"},
        json={"game_id": str(game.id), "session_id": str(game_session.id), "label": "other"},
    )
    assert conflict.status_code == 409
    revoked = client.post(
        f"/api/v1/admin/overlay-tickets/{ticket_id}/revoke",
        headers={**headers, "Idempotency-Key": "ticket-revoke-1"},
    )
    assert revoked.status_code == 200
    del secret


@pytest.mark.integration
def test_source_lag_pauses_new_rounds(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    from color_rush.domain.errors import RoundBusyError
    from color_rush.infrastructure.persistence.models import SourceCheckpoint

    game_session, token = started_session
    db_session.add(
        SourceCheckpoint(
            broadcast_id="lag-broadcast",
            next_page_token=None,
            source_mode="simulation",
            last_success_at=clock.now(),
            ownership_token="owner",
            session_id=game_session.id,
            resync_required=False,
            error_class=None,
            lag_ms=20_000,
        )
    )
    game_session.broadcast_ref = "lag-broadcast"
    db_session.flush()
    with pytest.raises(RoundBusyError):
        coordinator.start_round(game_session.id, token, RoundRules())


@pytest.mark.integration
def test_outbox_pending_recovery_dead_letters(redis_client: Redis) -> None:
    from color_rush.infrastructure.redis.projections import (
        GROUP_PROJECTION,
        STREAM_DLQ,
        STREAM_GAME,
        ensure_groups,
        publish_outbox,
        recover_pending,
    )

    ensure_groups(redis_client)
    publish_outbox(
        redis_client, event_id="evt-dlq", event_type="round.settled", payload={}, aggregate_id="agg"
    )
    redis_client.xreadgroup(GROUP_PROJECTION, "worker-a", {STREAM_GAME: ">"}, count=10)
    recover_pending(redis_client, group=GROUP_PROJECTION, min_idle_ms=0, max_deliveries=1)
    assert redis_client.xrange(STREAM_DLQ)


@pytest.mark.integration
def test_sql_scores_survive_without_redis(
    db_session: Session, coordinator: Coordinator, started_session: tuple[GameSession, int], clock
) -> None:
    game_session, token = started_session
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    append_and_process(
        db_session,
        session_id=game_session.id,
        commands=[_cmd("ch-sql", "Sql", "!red", clock.now(), "sql-1")],
        checkpoint=None,
    )
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    coordinator.spin(game_session.id, token)
    clock.set(clock.now() + timedelta(seconds=20))
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(db_session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    assert apply_projection_jobs(db_session, None) == 0
    player = db_session.scalar(select(Player).where(Player.provider_channel_id == "ch-sql"))
    assert player is not None
    ranks = player_ranks(db_session, player.id, game_session.game_id)
    assert "weekly" in ranks["ranks"]
