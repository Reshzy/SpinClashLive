from __future__ import annotations

import contextlib
from datetime import datetime, timedelta

from sqlalchemy import select

from color_rush.application.auth import bootstrap_owner
from color_rush.application.ingest import append_and_process
from color_rush.application.outbox import relay_outbox, sweep_incomplete_jobs
from color_rush.application.periods import finalize_due_periods
from color_rush.application.players import purge_old_commands
from color_rush.application.projections import apply_projection_jobs
from color_rush.application.settlement import all_partitions_complete, settle_round
from color_rush.application.snapshots import build_snapshot
from color_rush.application.source_health import (
    cancelable_active_round,
    record_source_health,
    should_cancel_affected_round,
    source_blocks_new_rounds,
)
from color_rush.composition import AppContainer, build_container
from color_rush.domain.enums import RoundState, SessionMode, SourceHealth, WorkerRole
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.persistence.models import GameSession, Round, SourceCheckpoint
from color_rush.infrastructure.redis.projections import ensure_groups
from color_rush.infrastructure.simulation.source import SimulationChatSource
from color_rush.observability import configure_logging


def _tick_coordinator(container: AppContainer, session_id: object) -> None:
    from uuid import UUID

    assert isinstance(session_id, UUID)
    with session_scope(container.session_factory) as session:
        coordinator = container.coordinator(session)
        game_session = session.get(GameSession, session_id)
        if game_session is None:
            return
        token = coordinator.claim_lease(session_id).fencing_token
        if source_blocks_new_rounds(
            session,
            game_session,
            lag_pause_ms=container.settings.source_lag_pause_ms,
            backlog_pause=container.settings.source_backlog_pause,
        ):
            checkpoint = None
            if game_session.broadcast_ref:
                checkpoint = session.get(SourceCheckpoint, game_session.broadcast_ref)
            health = SourceHealth.HEALTHY
            if checkpoint and checkpoint.error_class:
                try:
                    health = SourceHealth(checkpoint.error_class)
                except ValueError:
                    health = SourceHealth.DEGRADED
            elif checkpoint and checkpoint.resync_required:
                health = SourceHealth.RESYNC
            if should_cancel_affected_round(health):
                rnd = cancelable_active_round(session, game_session)
                if rnd is not None:
                    coordinator.cancel(session_id, token, f"source_{health.value}")
            return
        rnd = session.get(Round, game_session.active_round_id) if game_session.active_round_id else None
        if rnd is None:
            if game_session.mode == SessionMode.AUTOMATIC.value and not game_session.paused:
                coordinator.start_round(session_id, token, RoundRules())
            return
        state = RoundState(rnd.state)
        if state is RoundState.OPEN:
            coordinator.maybe_close_due_rounds(session_id, token)
        elif state is RoundState.DRAINING:
            coordinator.complete_drain(session_id, token)
        elif state is RoundState.LOCKED and game_session.mode == SessionMode.AUTOMATIC.value:
            coordinator.spin(session_id, token)
        elif state in {RoundState.SPINNING, RoundState.RESULT}:
            coordinator.advance_after_spin(session_id, token)
        elif state is RoundState.SETTLING:
            settle_round(session, rnd.id, container.clock.now())
            if all_partitions_complete(session, rnd.id):
                coordinator.mark_settled(session_id, token)
        elif state is RoundState.SETTLED:
            coordinator.enter_cooldown(session_id, token)


def _tick_ingest(container: AppContainer) -> None:
    with session_scope(container.session_factory) as session:
        sessions = list(session.scalars(select(GameSession)))
    for game_session in sessions:
        if game_session.source_mode == "youtube" and game_session.live_chat_ref:
            from color_rush.infrastructure.youtube.source import YouTubeChatSource

            checkpoint = None
            with session_scope(container.session_factory) as session:
                if game_session.broadcast_ref:
                    checkpoint = session.get(SourceCheckpoint, game_session.broadcast_ref)
            yt_source = YouTubeChatSource(
                live_chat_id=game_session.live_chat_ref,
                broadcast_id=game_session.broadcast_ref or game_session.live_chat_ref,
                ownership_token=container.worker_id,
                transport=container.settings.youtube_transport,
                api_key=container.settings.google_api_key,
                session_id=game_session.id,
                page_token=checkpoint.next_page_token if checkpoint else None,
            )
            try:
                yt_source.connect()
                for batch in yt_source.iter_batches():
                    with session_scope(container.session_factory) as session:
                        append_and_process(
                            session,
                            session_id=game_session.id,
                            commands=list(batch.commands),
                            checkpoint=batch.checkpoint,
                        )
                        record_source_health(
                            session, batch.checkpoint.broadcast_id, health=batch.health, lag_ms=batch.lag_ms
                        )
                    break
            except Exception:
                continue
            continue
        if game_session.source_mode != "simulation":
            continue
        sim_source = SimulationChatSource(
            clock=container.clock,
            broadcast_id=game_session.broadcast_ref or f"sim-{game_session.id}",
            session_id=game_session.id,
            ownership_token=container.worker_id,
        )
        sim_source.connect()
        for batch in sim_source.iter_batches():
            with session_scope(container.session_factory) as session:
                existing = session.get(SourceCheckpoint, batch.checkpoint.broadcast_id)
                stale_owner = (
                    existing is not None
                    and existing.ownership_token
                    and existing.ownership_token != container.worker_id
                    and existing.last_success_at > container.clock.now() - timedelta(seconds=15)
                )
                if stale_owner:
                    return
                append_and_process(
                    session,
                    session_id=game_session.id,
                    commands=list(batch.commands),
                    checkpoint=batch.checkpoint,
                )
                record_source_health(
                    session, batch.checkpoint.broadcast_id, health=batch.health, lag_ms=batch.lag_ms
                )
            break


def _tick_outbox(container: AppContainer) -> None:
    with session_scope(container.session_factory) as session:
        relay_outbox(session, container.settings.redis_url, now=container.clock.now())
        sweep_incomplete_jobs(session)


def _tick_projection(container: AppContainer) -> None:
    if container.redis is not None:
        ensure_groups(container.redis)
    with session_scope(container.session_factory) as session:
        apply_projection_jobs(session, container.redis)


def _tick_gateway(container: AppContainer) -> None:
    with session_scope(container.session_factory) as session:
        for game_session in session.scalars(select(GameSession)):
            build_snapshot(session, container.redis, game_session, container.clock.now())


def _tick_retention(container: AppContainer) -> None:
    cutoff = container.clock.now() - timedelta(days=container.settings.command_retention_days)
    with session_scope(container.session_factory) as session:
        purge_old_commands(session, cutoff)
        for game_session in session.scalars(select(GameSession)):
            finalize_due_periods(session, game_session.game_id, container.clock.now())
        bootstrap_owner(session, container.settings, datetime.now(tz=container.clock.now().tzinfo))


def _session_ids(container: AppContainer) -> list[object]:
    with session_scope(container.session_factory) as session:
        return list(session.scalars(select(GameSession.id)))


def run_once(container: AppContainer, role: str) -> None:
    roles = {role} if role != WorkerRole.ALL.value else {
        WorkerRole.COORDINATOR.value,
        WorkerRole.INGEST.value,
        WorkerRole.SETTLEMENT.value,
        WorkerRole.OUTBOX.value,
        WorkerRole.PROJECTION.value,
        WorkerRole.GATEWAY.value,
        WorkerRole.RETENTION.value,
    }
    if WorkerRole.COORDINATOR.value in roles or WorkerRole.SETTLEMENT.value in roles:
        for session_id in _session_ids(container):
            try:
                _tick_coordinator(container, session_id)
            except Exception:
                continue
    if WorkerRole.INGEST.value in roles:
        with contextlib.suppress(Exception):
            _tick_ingest(container)
    if WorkerRole.OUTBOX.value in roles:
        _tick_outbox(container)
    if WorkerRole.PROJECTION.value in roles:
        _tick_projection(container)
    if WorkerRole.GATEWAY.value in roles:
        _tick_gateway(container)
    if WorkerRole.RETENTION.value in roles:
        _tick_retention(container)


def run_forever() -> None:
    configure_logging()
    container = build_container()
    while True:
        run_once(container, container.settings.color_rush_worker_role)
        time_sleep = max(container.settings.drain_poll_interval_ms / 1000.0, 0.05)
        import time

        time.sleep(time_sleep)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
