# Color Rush Live

YouTube livestream color-prediction game. The Python backend owns rules, rounds, picks, results, and scores. Viewers use chat commands. Operators use a native PySide6 console. OBS uses a read-only browser overlay.

Closing the console does **not** stop automatic backend rounds.

## Prerequisites

- Python 3.12 (`uv python install 3.12`)
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop (PostgreSQL 16 + Redis 7)
- Node 22+ for the overlay build
- Windows for the native console (Qt tests can run offscreen)

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

If host port 5432 is already another PostgreSQL, use Compose port **5433** in `DATABASE_URL` / `COLOR_RUSH_TEST_DATABASE_URL`.

## Run (simulation)

```powershell
cd overlay; npm ci; npm run build; cd ..
$env:COLOR_RUSH_ENV = "simulation"
uv run python -m uvicorn color_rush.api.app:app --host 127.0.0.1 --port 8000
# other terminal
$env:COLOR_RUSH_WORKER_ROLE = "all"
uv run python -m color_rush.workers
# other terminal
$env:COLOR_RUSH_API_BASE = "http://127.0.0.1:8000"
uv run python -m color_rush_desktop
```

Overlay URL from Overlay Setup: `http://127.0.0.1:8000/overlay#<secret>`. See [docs/OBS_SETUP.md](docs/OBS_SETUP.md).

CLI demo (no GUI): `uv run python -m color_rush.demo`.

## Tests

```powershell
uv run ruff check backend/src backend/tests desktop/src desktop/tests scripts
uv run mypy
uv run pytest backend/tests/domain
$env:COLOR_RUSH_TEST_DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_test"
$env:COLOR_RUSH_TEST_REDIS_URL = "redis://127.0.0.1:6379/15"
$env:QT_QPA_PLATFORM = "offscreen"
uv run pytest
cd overlay; npm test; npm run test:e2e; npm run build
uv run python scripts/secret_scan.py
```

Load harness (simulation DB only): see [scripts/load/README.md](scripts/load/README.md).

## Packaging (Windows)

```powershell
uv run pyinstaller desktop/packaging/color_rush_desktop.spec
```

Native artifact build is machine-dependent. Spec excludes `.env` and backend secrets. Licenses: [desktop/packaging/LICENSES.md](desktop/packaging/LICENSES.md).

## Operations docs

| Doc | Contents |
| --- | --- |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Start/stop/reconnect, recovery, backups, scaling triggers |
| [docs/YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md) | Google project, API key, OAuth |
| [docs/OBS_SETUP.md](docs/OBS_SETUP.md) | Browser Source, overlay tickets |
| [docs/SECURITY_AND_DATA.md](docs/SECURITY_AND_DATA.md) | API data vs game data, retention |
| [docs/CAPACITY_REPORT.md](docs/CAPACITY_REPORT.md) | Measured load, blocked targets |
| [docs/PROGRESS.md](docs/PROGRESS.md) | Milestone evidence |

## Setup (POSIX)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12
uv sync --extra dev --extra desktop
cp .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
uv run pytest
uv run python -m color_rush.demo
```

Production-shaped Compose (unpublished Postgres/Redis + Caddy TLS example): `deployment/compose.production.yaml`. Do not deploy remotely without authorization.
