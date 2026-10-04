# Color Rush Live — Progress

Working product name: Color Rush Live  
Repository root: this folder (`SpinClashLive`)  
Current milestone: 1 — Foundation, authoritative rules and durable scoring

## Environment

| Tool | Status |
| --- | --- |
| uv | Installed 0.12.23 at `%USERPROFILE%\.local\bin` |
| Project Python | 3.12.11 via `uv python install 3.12` (pinned in `.python-version`) |
| Host Python 3.14 | Present, not used |
| Lockfile | `uv.lock` resolved 2026-10-04 |
| Ruff | 0.16.10 |
| mypy | 1.20.0 (strict on `color_rush`) |
| Docker client | 29.8.1 at `%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe` |
| Docker Compose | v5.5.1 |
| Docker engine | **Blocked** — `docker info` returns `Docker Desktop is unable to start` (WSL is not installed; `wsl --install` requires Administrator) |
| PostgreSQL / Redis | Not running locally; Compose services defined |

## Commands that actually ran

```text
uv python install 3.12
uv lock
uv sync --extra dev
uv run ruff check backend/src backend/tests
# All checks passed
uv run mypy
# Success: no issues found in 38 source files
uv run pytest backend/tests
# 37 passed, 11 skipped in ~1.3s
docker compose config --quiet
# success after .env.example copy / optional env_file
docker info
# Error response from daemon: Docker Desktop is unable to start
```

Skipped tests are `backend/tests/integration/*` because `COLOR_RUSH_TEST_DATABASE_URL` / a reachable PostgreSQL is missing.

## Milestone status

| Milestone | Status |
| --- | --- |
| 1 Foundation, rules, durable scoring | Implementation complete. Domain/quality gates passed. PostgreSQL integration, Alembic-on-fresh-DB, and CLI demo are **blocked** on Docker/WSL. |
| 2 YouTube ingest, API, realtime projections | Not started — wait until the commands below pass |
| 3 PySide6 operator console | Not started |
| 4 OBS overlay | Not started |
| 5 Reliability, scale, packaging | Not started |

## Runnable verification after Docker starts

Windows PowerShell:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:Path"
# Install WSL as Administrator first: wsl --install
docker compose up -d postgres redis
$env:COLOR_RUSH_ENV = "simulation"
$env:COLOR_RUSH_TEST_DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_test"
$env:DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_sim"
uv run alembic upgrade head
uv run pytest
uv run python -m color_rush.demo
uv run python -m uvicorn color_rush.api.app:app --host 127.0.0.1 --port 8000
# separate terminal
uv run python -m color_rush.workers
```

POSIX equivalents are in `README.md`.

## Changed modules (milestone 1)

- `backend/src/color_rush/domain/` — commands, rules, RNG, picks, streaks, states, eligibility, periods, ranking
- `backend/src/color_rush/application/` — ingest lock protocol, coordinator, settlement, periods
- `backend/src/color_rush/infrastructure/persistence/` — SQLAlchemy models and DB helpers
- `backend/src/color_rush/api/app.py` — `/health/*` and simulation-gated endpoints
- `backend/src/color_rush/workers/` — explicit worker entry (`python -m color_rush.workers`)
- `backend/src/color_rush/demo.py` — deterministic CLI demo
- `backend/migrations/versions/0001_initial.py` — Alembic schema
- `compose.yaml`, `deployment/*.Dockerfile`, `pyproject.toml`, `uv.lock`
- `desktop/`, `overlay/` skeletons only

## Architectural decisions

See `docs/DECISIONS.md`. Highlights: session advisory lock + `clock_timestamp()`; fencing token; ledger `ON CONFLICT DO NOTHING`; occupying-round unique index; Redis relay deferred to milestone 2.

## Remaining external prerequisites

1. Administrator `wsl --install` (or enable WSL2) so Docker Desktop can start.
2. `docker compose up -d postgres redis`
3. `uv run alembic upgrade head` on a fresh database
4. `uv run pytest` including integration tests
5. `uv run python -m color_rush.demo`

Never treat those as passed until they are executed.

## Can milestone 2 begin?

**No.** Milestone 1 code is in place, but the durable PostgreSQL verification required by prompt 1 has not run. Start milestone 2 only after the integration suite and demo succeed against real PostgreSQL.
