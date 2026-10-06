"""Development-only load helpers. Drive production ingest/settlement against real PostgreSQL."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.coordinator import Coordinator
from color_rush.application.dto import NormalizedCommand, SourceCheckpointData
from color_rush.application.ingest import append_and_process
from color_rush.application.ports import SecureRng, SystemClock
from color_rush.application.reconcile import reconcile_round
from color_rush.application.settlement import settle_round
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import SessionMode
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.models import GameSession

COLORS = ("!red", "!gold", "!green")


def _command(channel: str, text: str, published: datetime, message_id: str, broadcast_id: str) -> NormalizedCommand:
    return NormalizedCommand(
        provider="simulation",
        provider_message_id=message_id,
        broadcast_id=broadcast_id,
        provider_channel_id=channel,
        display_name=channel[:24],
        command_text=text,
        command=parse_command(text),
        published_at=published,
    )


def ingest_batch(
    session: Session,
    session_id: UUID,
    *,
    count: int,
    broadcast_id: str,
    start_index: int,
    published: datetime,
    unique_prefix: str = "u",
) -> int:
    commands = [
        _command(
            f"{unique_prefix}-{start_index + offset}",
            COLORS[offset % 3],
            published,
            f"{unique_prefix}-m-{start_index + offset}-{uuid4().hex[:8]}",
            broadcast_id,
        )
        for offset in range(count)
    ]
    if count > 3:
        commands.append(
            _command(
                f"{unique_prefix}-{start_index}",
                COLORS[1],
                published,
                f"{unique_prefix}-change-{start_index}-{uuid4().hex[:8]}",
                broadcast_id,
            )
        )
        commands.append(
            _command(
                f"{unique_prefix}-{start_index}",
                COLORS[1],
                published,
                f"{unique_prefix}-dup-{start_index}",
                broadcast_id,
            )
        )
        commands.append(
            _command(
                f"{unique_prefix}-lookup-{start_index}",
                "!score",
                published,
                f"{unique_prefix}-score-{start_index}-{uuid4().hex[:8]}",
                broadcast_id,
            )
        )
    checkpoint = SourceCheckpointData(
        broadcast_id=broadcast_id,
        next_page_token=f"tok-{start_index}",
        source_mode="simulation",
        ownership_token="load-harness",
        session_id=session_id,
    )
    result = append_and_process(session, session_id=session_id, commands=commands, checkpoint=checkpoint)
    return len(result.sequences)


def run_rate_window(
    session: Session,
    session_id: UUID,
    *,
    broadcast_id: str,
    commands_per_sec: int,
    duration_s: float,
    batch_size: int = 50,
) -> dict[str, float]:
    published = datetime.now(tz=UTC)
    sent = 0
    started = time.perf_counter()
    deadline = started + duration_s
    index = 0
    latencies: list[float] = []
    while time.perf_counter() < deadline:
        batch_started = time.perf_counter()
        sent += ingest_batch(
            session,
            session_id,
            count=batch_size,
            broadcast_id=broadcast_id,
            start_index=index,
            published=published,
        )
        index += batch_size
        latencies.append((time.perf_counter() - batch_started) * 1000)
        expected = started + (sent / max(commands_per_sec, 1))
        sleep_for = expected - time.perf_counter()
        if sleep_for > 0:
            time.sleep(sleep_for)
    elapsed = time.perf_counter() - started
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0.0
    return {
        "sent": float(sent),
        "elapsed_s": elapsed,
        "achieved_per_sec": sent / elapsed if elapsed else 0.0,
        "batch_p95_ms": p95,
        "batches": float(len(latencies)),
    }


def unique_player_round(
    session: Session,
    *,
    player_count: int,
    broadcast_id: str = "load-broadcast",
) -> dict[str, object]:
    clock = SystemClock()
    coordinator = Coordinator(
        session,
        clock=clock,
        rng=SecureRng(),
        owner_id="load-harness",
        lease_ttl_seconds=3600,
        partition_count=8,
    )
    game = coordinator.create_game("load")
    game_session = coordinator.create_session(
        game.id, mode=SessionMode.MANUAL, source_mode="simulation", broadcast_ref=broadcast_id
    )
    token = coordinator.claim_lease(game_session.id).fencing_token
    rnd = coordinator.start_round(game_session.id, token, RoundRules())
    opened = rnd.opened_at or datetime.now(tz=UTC)
    ingest_started = time.perf_counter()
    remaining = player_count
    index = 0
    while remaining > 0:
        chunk = min(500, remaining)
        ingest_batch(
            session,
            game_session.id,
            count=chunk,
            broadcast_id=broadcast_id,
            start_index=index,
            published=opened,
            unique_prefix="p",
        )
        index += chunk
        remaining -= chunk
    ingest_s = time.perf_counter() - ingest_started
    drain_started = time.perf_counter()
    coordinator.close_ingress(game_session.id, token, early=True)
    coordinator.complete_drain(game_session.id, token)
    drain_s = time.perf_counter() - drain_started
    coordinator.spin(game_session.id, token)
    settle_started = time.perf_counter()
    coordinator.advance_after_spin(game_session.id, token)
    coordinator.advance_after_spin(game_session.id, token)
    settle_round(session, rnd.id, clock.now())
    coordinator.mark_settled(game_session.id, token)
    settle_s = time.perf_counter() - settle_started
    report = reconcile_round(session, rnd.id, None)
    report.update(
        {
            "players_requested": player_count,
            "ingest_s": ingest_s,
            "drain_s": drain_s,
            "settle_s": settle_s,
            "session_id": str(game_session.id),
            "round_id": str(rnd.id),
        }
    )
    return report


def ensure_open_session(session: Session, broadcast_id: str = "load-broadcast") -> tuple[GameSession, int]:
    existing = session.scalar(select(GameSession).order_by(GameSession.created_at.desc()))
    coordinator = Coordinator(
        session,
        clock=SystemClock(),
        rng=SecureRng(),
        owner_id="load-harness",
        lease_ttl_seconds=3600,
    )
    if existing is None:
        game = coordinator.create_game("load")
        existing = coordinator.create_session(
            game.id, mode=SessionMode.MANUAL, source_mode="simulation", broadcast_ref=broadcast_id
        )
    token = coordinator.claim_lease(existing.id).fencing_token
    if existing.active_round_id is None:
        coordinator.start_round(existing.id, token, RoundRules())
    return existing, token
