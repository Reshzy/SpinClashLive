# Color Rush Live — Progress

Working product name: Color Rush Live  
Repository root: this folder (`SpinClashLive`)  
Current milestone: 2 — YouTube ingest, secure API, realtime projections — **closed**

## Environment

| Tool | Status |
| --- | --- |
| uv | Installed 0.12.23 at `%USERPROFILE%\.local\bin` |
| Project Python | 3.12.11 via `uv python install 3.12` (pinned in `.python-version`) |
| Host Python 3.14 | Present, not used |
| Lockfile | `uv.lock` resolved 2026-10-04 |
| Ruff | 0.16.10 |
| mypy | 1.20.0 (strict on `color_rush`) |
| Docker client | 29.8.1 |
| Docker Compose | v5.5.1 |
| Docker engine | Running (WSL2) |
| PostgreSQL 16 | Compose `postgres:16-alpine`, healthy. Host port **5433** used for verification because host **5432** already has another PostgreSQL. Compose also maps 5432. |
| Redis 7 | Compose `redis:7-alpine`, healthy. Test isolation uses DB **15**. |

## Commands that actually ran (milestone 2 close-out)

```text
uv run ruff check backend/src backend/tests scripts
# All checks passed
uv run mypy
# Success: no issues found in 70 source files
docker compose up -d postgres redis
# both already Running / healthy
DATABASE_URL=postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_sim
uv run alembic upgrade head
# Running upgrade 0001_initial -> 0002_m2_auth_source
COLOR_RUSH_TEST_DATABASE_URL=postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_test
COLOR_RUSH_TEST_REDIS_URL=redis://127.0.0.1:6379/15
uv run pytest backend/tests
# 74 passed in 4.27s
uv run python scripts/export_contracts.py
# wrote contracts/openapi.json and contracts/ts/api.d.ts
uv run python scripts/check_contracts.py
# contracts ok
```

Live YouTube private-stream acceptance was **not** run. `GOOGLE_API_KEY` is unset in this environment.

```powershell
$env:GOOGLE_API_KEY = "<restricted-key>"
$env:COLOR_RUSH_ENV = "production"
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
# login as owner, POST /api/v1/admin/youtube/connect with the private video id
# confirm source health is healthy, send !red in chat, confirm an inbox row
```

**Blocked** — credentials missing. Fixture tests in `backend/tests/application/test_youtube_contracts.py` check official JSON/gRPC shapes only; they do not prove live API access.

## Milestone status

| Milestone | Status |
| --- | --- |
| 1 Foundation, rules, durable scoring | **Complete.** |
| 2 YouTube ingest, API, realtime projections | **Complete** locally (Postgres + Redis + contracts). Live YouTube **blocked** without credentials. |
| 3 PySide6 operator console | Not started |
| 4 OBS overlay | Not started |
| 5 Reliability, scale, packaging | Not started |

## Demo / API instructions

Windows PowerShell (this machine uses Compose host port 5433):

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin;$env:Path"
docker compose up -d postgres redis
$env:COLOR_RUSH_ENV = "simulation"
$env:DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_sim"
$env:COLOR_RUSH_TEST_DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_test"
$env:COLOR_RUSH_TEST_REDIS_URL = "redis://127.0.0.1:6379/15"
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
uv run pytest
uv run python -m uvicorn color_rush.api.app:app --host 127.0.0.1 --port 8000
# other terminal:
$env:COLOR_RUSH_WORKER_ROLE = "all"
uv run python -m color_rush.workers
```

If host 5432 is free, the same URLs with port 5432 also work.

## Changed modules (milestone 2 close-out)

- Alembic `0002_m2_auth_source`: overlay tickets, Google credentials, idempotency keys, source-health columns, player deletion fields
- ChatSource port + `SimulationChatSource` + official YouTube gRPC `streamList` / HTTP `list` fallback
- Authenticated `/api/v1` + overlay/admin WebSockets, JWT+refresh, overlay tickets, idempotency
- Outbox relay to Redis Streams `outbox.game` / `outbox.projections`, pending recovery, DLQ, SQL sweeper
- Absolute ZADD projections with `-points` tie encoding and `score_version` CAS; 4 Hz snapshots
- Moderation OPEN-pick removal, settings versions, seasons, lookup/help, source-health pause/cancel, retention/deletion
- Docs: `docs/YOUTUBE_SETUP.md`, `docs/SECURITY_AND_DATA.md`

## Architectural decisions

See `docs/DECISIONS.md`.

## Remaining external prerequisites

- Live YouTube private-stream script: **blocked** until a restricted API key / OAuth client exists
- YouTube API-use and retention review still required before production (`docs/SECURITY_AND_DATA.md`)

## Can milestone 3 begin?

**Yes**, for the operator console. Backend contracts are exported. Do not treat live YouTube as verified.
