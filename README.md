# Color Rush Live

YouTube livestream color-prediction game. The Python backend owns rules, rounds, picks, results, and scores. This repository root is the project root.

Milestone 1 delivers the domain, PostgreSQL durability, settlement, health API, and a simulation demo. The desktop console and OBS overlay are skeletons until later milestones.

## Prerequisites

- Python 3.12 (install via `uv python install 3.12`)
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop + WSL 2 (for PostgreSQL, Redis, and backend containers)

## Setup (Windows PowerShell)

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv python install 3.12
uv sync --extra dev
Copy-Item .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
```

Run tests:

```powershell
uv run ruff check backend/src backend/tests
uv run mypy
uv run pytest backend/tests/domain
# requires Compose PostgreSQL
$env:COLOR_RUSH_TEST_DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_test"
uv run pytest
```

Demo (simulation database):

```powershell
$env:COLOR_RUSH_ENV = "simulation"
$env:DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_sim"
uv run alembic upgrade head
uv run python -m color_rush.demo
```

API (no scheduler inside Uvicorn):

```powershell
uv run python -m uvicorn color_rush.api.app:app --host 127.0.0.1 --port 8000
```

Worker (separate process):

```powershell
$env:COLOR_RUSH_WORKER_ROLE = "all"
uv run python -m color_rush.workers
```

Full stack:

```powershell
docker compose up --build
```

## Setup (POSIX)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv sync --extra dev
cp .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run pytest
uv run python -m color_rush.demo
```

## Layout

See `MASTER_YOUTUBE_LIVE_GAME.md`. Progress and requirement evidence live in `docs/`.
