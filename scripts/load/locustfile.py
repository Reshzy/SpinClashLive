"""Locust pipeline harness for Color Rush Live.

Drives `append_and_process` against real PostgreSQL. Not an in-memory shortcut.

  uv sync --extra load
  $env:COLOR_RUSH_ENV = "simulation"
  uv run locust -f scripts/load/locustfile.py --headless -u 1 -r 1 -t 15s
  uv run python scripts/load/run_harness.py --profile subset
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from locust import User, between, task

from color_rush.composition import build_container
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.simulation.load import ensure_open_session, ingest_batch


class PipelineUser(User):
    wait_time = between(0.01, 0.05)

    def on_start(self) -> None:
        if os.environ.get("COLOR_RUSH_ENV", "simulation") != "simulation":
            raise RuntimeError("load harness refuses production COLOR_RUSH_ENV")
        self.container = build_container()
        with session_scope(self.container.session_factory) as session:
            game_session, _token = ensure_open_session(session)
            self.session_id = game_session.id
            self.broadcast_id = game_session.broadcast_ref or "load-broadcast"
        self._index = 0

    @task
    def ingest(self) -> None:
        batch = int(os.environ.get("LOAD_BATCH_SIZE", "50"))
        begin = datetime.now(tz=UTC)
        try:
            with session_scope(self.container.session_factory) as session:
                count = ingest_batch(
                    session,
                    self.session_id,
                    count=batch,
                    broadcast_id=self.broadcast_id,
                    start_index=self._index,
                    published=begin,
                    unique_prefix=f"l{id(self) % 10_000}",
                )
            self._index += batch
            self.environment.events.request.fire(
                request_type="INGEST",
                name="append_and_process",
                response_time=(datetime.now(tz=UTC) - begin).total_seconds() * 1000,
                response_length=count,
                exception=None,
                context={},
            )
        except Exception as exc:
            self.environment.events.request.fire(
                request_type="INGEST",
                name="append_and_process",
                response_time=(datetime.now(tz=UTC) - begin).total_seconds() * 1000,
                response_length=0,
                exception=exc,
                context={},
            )
