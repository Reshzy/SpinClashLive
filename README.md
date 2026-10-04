# Color Rush Live

YouTube livestream color-prediction game. The Python backend owns rules, rounds, picks, results, and scores. This repository root is the project root.

Milestone 3 delivers the native PySide6 operator console against `/api/v1`. The OBS overlay remains a milestone 4 surface; `/overlay` currently serves a placeholder page.

## Prerequisites

- Python 3.12 (install via `uv python install 3.12`)
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop + WSL 2 (for PostgreSQL, Redis, and backend containers)

## Setup (Windows PowerShell)

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv python install 3.12
uv sync --extra dev --extra desktop
Copy-Item .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
```

If host port 5432 is already a different PostgreSQL, use Compose port **5433** in `DATABASE_URL` / `COLOR_RUSH_TEST_DATABASE_URL` (Compose publishes both).

Run tests:

```powershell
uv run ruff check backend/src backend/tests desktop/src desktop/tests
uv run mypy
uv run pytest backend/tests/domain
# requires Compose PostgreSQL
$env:COLOR_RUSH_TEST_DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_test"
$env:COLOR_RUSH_TEST_REDIS_URL = "redis://127.0.0.1:6379/15"
$env:QT_QPA_PLATFORM = "offscreen"
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

API examples (after bootstrap):

```powershell
# login
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/auth/login -ContentType application/json -Body '{"username":"owner","password":"change-me-owner"}'
# overlay WS (ticket from POST /api/v1/admin/overlay-tickets)
# ws://127.0.0.1:8000/ws/v1/overlay?ticket=<secret>
# admin WS
# ws://127.0.0.1:8000/ws/v1/admin  then send {"token":"<access_token>"}
```

Export contracts:

```powershell
uv run python scripts/export_contracts.py
uv run python scripts/check_contracts.py
```

Worker (separate process):

```powershell
$env:COLOR_RUSH_WORKER_ROLE = "all"
uv run python -m color_rush.workers
```

Desktop console (does not stop the backend when closed):

```powershell
uv sync --extra desktop
$env:COLOR_RUSH_API_BASE = "http://127.0.0.1:8000"
uv run python -m color_rush_desktop
```

Packaging (Windows):

```powershell
uv run pyinstaller desktop/packaging/color_rush_desktop.spec
```

Full stack:

```powershell
docker compose up --build
```

## Setup (POSIX)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv sync --extra dev --extra desktop
cp .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run pytest
uv run python -m color_rush.demo
```

## Layout

See `MASTER_YOUTUBE_LIVE_GAME.md`. Progress and requirement evidence live in `docs/`.
