#!/usr/bin/env bash
set -euo pipefail
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. See https://docs.astral.sh/uv/" >&2
  exit 1
fi
uv python install 3.12
uv sync --extra dev
if [ ! -f .env ]; then
  cp .env.example .env
fi
echo "Next: docker compose up -d postgres redis"
echo "Then: uv run alembic upgrade head"
