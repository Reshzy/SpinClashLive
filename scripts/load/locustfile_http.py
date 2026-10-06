"""Locust HTTP transport (optional). PipelineUser in locustfile.py is the primary generator.

  $env:LOAD_SESSION_ID = "<uuid>"
  uv run locust -f scripts/load/locustfile_http.py --headless -u 10 -r 10 -t 15s
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

from locust import HttpUser, between, task


class SimulationHttpUser(HttpUser):
    wait_time = between(0.02, 0.05)
    host = os.environ.get("COLOR_RUSH_API_BASE", "http://127.0.0.1:8000")

    def on_start(self) -> None:
        if os.environ.get("COLOR_RUSH_ENV", "simulation") != "simulation":
            raise RuntimeError("load harness refuses production COLOR_RUSH_ENV")
        self.session_id = os.environ.get("LOAD_SESSION_ID", "")
        if not self.session_id:
            raise RuntimeError("LOAD_SESSION_ID is required for HTTP locust")

    @task
    def batch(self) -> None:
        now = datetime.now(tz=UTC).isoformat()
        commands = [
            {
                "session_id": self.session_id,
                "broadcast_id": "load-broadcast",
                "provider_channel_id": f"http-{uuid4().hex[:10]}",
                "display_name": "load",
                "text": "!red",
                "published_at": now,
                "message_id": uuid4().hex,
            }
            for _ in range(25)
        ]
        self.client.post(
            "/simulation/commands/batch",
            json={"session_id": self.session_id, "broadcast_id": "load-broadcast", "commands": commands},
        )
