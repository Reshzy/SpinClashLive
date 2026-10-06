"""Run Locust profiles and unique-player rounds against simulation PostgreSQL.

Examples:
  uv run python scripts/load/run_harness.py --profile subset
  uv run python scripts/load/run_harness.py --profile unique --players 2000
  uv run locust -f scripts/load/locustfile.py --headless -u 1 -r 1 -t 15s --tags subset
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from color_rush.composition import build_container  # noqa: E402
from color_rush.infrastructure.persistence.db import session_scope  # noqa: E402
from color_rush.infrastructure.simulation.load import (  # noqa: E402
    ensure_open_session,
    run_rate_window,
    unique_player_round,
)


def _hardware() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "node": platform.node(),
        "time": datetime.now(tz=UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Color Rush Live load harness")
    parser.add_argument("--profile", choices=("subset", "sustained", "burst", "unique"), default="subset")
    parser.add_argument("--players", type=int, default=2000)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if os.environ.get("COLOR_RUSH_ENV", "simulation") != "simulation":
        raise SystemExit("refusing to run load harness with COLOR_RUSH_ENV=production")
    container = build_container()
    report: dict[str, object] = {"hardware": _hardware(), "profile": args.profile}
    with session_scope(container.session_factory) as session:
        if args.profile == "unique":
            report["result"] = unique_player_round(session, player_count=args.players)
        else:
            game_session, _token = ensure_open_session(session)
            if args.profile == "subset":
                report["result"] = run_rate_window(
                    session,
                    game_session.id,
                    broadcast_id=game_session.broadcast_ref or "load-broadcast",
                    commands_per_sec=200,
                    duration_s=15,
                    batch_size=50,
                )
            elif args.profile == "burst":
                report["result"] = run_rate_window(
                    session,
                    game_session.id,
                    broadcast_id=game_session.broadcast_ref or "load-broadcast",
                    commands_per_sec=5000,
                    duration_s=10,
                    batch_size=250,
                )
            else:
                report["result"] = run_rate_window(
                    session,
                    game_session.id,
                    broadcast_id=game_session.broadcast_ref or "load-broadcast",
                    commands_per_sec=1000,
                    duration_s=600,
                    batch_size=50,
                )
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
