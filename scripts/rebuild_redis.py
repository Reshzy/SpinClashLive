"""Rebuild Redis leaderboard generations from PostgreSQL.

  $env:COLOR_RUSH_ENV = "simulation"
  uv run python scripts/rebuild_redis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sqlalchemy import select  # noqa: E402

from color_rush.composition import build_container  # noqa: E402
from color_rush.infrastructure.persistence.db import session_scope  # noqa: E402
from color_rush.infrastructure.persistence.models import Game  # noqa: E402
from color_rush.infrastructure.redis.projections import rebuild_all_leaderboards  # noqa: E402


def main() -> int:
    container = build_container()
    if container.redis is None:
        print("redis unavailable")
        return 1
    with session_scope(container.session_factory) as session:
        games = list(session.scalars(select(Game)))
        if not games:
            print("no games")
            return 0
        for game in games:
            generations = rebuild_all_leaderboards(container.redis, session, game.id)
            print(f"game {game.id}: {generations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
