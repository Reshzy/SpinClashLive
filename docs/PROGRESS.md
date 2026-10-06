# Color Rush Live — Progress

Working product name: Color Rush Live  
Repository root: this folder  
Current milestone: 5 — Reliability, scale, packaging — **implemented and verified locally; master load targets not met on this laptop; some external checks blocked**

## Environment (this session)

| Tool | Status |
| --- | --- |
| uv | 0.12.23 |
| Project Python | 3.12.15 via `uv python install 3.12` |
| Node | 26.5.0 (Vitest 5, Playwright 1.63, Vite 8) |
| Locust | 2.46.7 (`uv sync --extra load`) |
| Docker / Compose Postgres+Redis | **Healthy.** `postgres:16-alpine` + `redis:7-alpine`. Host :5432 already occupied; `.env` uses Compose **5433**. Redis :6379. |
| Overlay lock | `overlay/package-lock.json` |

## Commands that actually ran (milestone 5)

```text
Copy-Item .env.example .env
# DATABASE_URL and COLOR_RUSH_TEST_DATABASE_URL switched to port 5433
docker compose up -d postgres redis
# both healthy; published 5432+5433 and 6379
python -m uv sync --extra dev --extra desktop --extra load --python 3.12
$env:DATABASE_URL = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_sim"
python -m uv run alembic upgrade head
# 0001_initial -> 0002_m2_auth_source
python -m uv run python -m color_rush.bootstrap
# owner ready: owner (owner)
python -m uv run ruff check backend/src backend/tests desktop/src desktop/tests scripts
# All checks passed
python -m uv run mypy
# Success: no issues found in 105 source files
python -m uv run python scripts/secret_scan.py
# secret scan clean
python -m uv run python scripts/check_contracts.py
# contracts ok
$env:COLOR_RUSH_TEST_DATABASE_URL = "...5433/color_rush_test"
$env:COLOR_RUSH_TEST_REDIS_URL = "redis://127.0.0.1:6379/15"
$env:QT_QPA_PLATFORM = "offscreen"
python -m uv run pytest -q
# 118 passed, 1 skipped (desktop smoke needs a running API)
python -m uv run python -m color_rush.demo
# Predictions open → gold → settled; four-scope scores
cd overlay
npm ci
npm run typecheck
npm test
# 10 passed
npx playwright install chromium
npm run test:e2e
# 6 passed (one gold-result screenshot flaked once, passed on retry)
npm run build
# vite production build ok
$env:COLOR_RUSH_ENV = "simulation"
python -m uv run python scripts/load/run_harness.py --profile subset
python -m uv run python scripts/load/run_harness.py --profile burst
python -m uv run python scripts/load/run_harness.py --profile unique --players 2000
```

Load numbers: see `docs/CAPACITY_REPORT.md`. Sustained 1k/10min and 100k unique **not run** after burst peaked at ~225 cmd/s.

Native PyInstaller artifact **not built** (command remains `uv run pyinstaller desktop/packaging/color_rush_desktop.spec`).

OBS Studio Browser Source: **not executed**.

Live YouTube private-stream + OAuth: **blocked** (no Google secrets in `.env`).

GitLab CI pipeline: **not executed** (file `.gitlab-ci.yml` includes ruff, secret scan, contracts, mypy, pytest, overlay).

## Milestone status

| Milestone | Status |
| --- | --- |
| 1 Foundation, rules, durable scoring | **Complete.** |
| 2 YouTube ingest, API, realtime projections | **Complete** locally. Live YouTube **blocked**. |
| 3 PySide6 operator console | **Complete** locally. |
| 4 OBS overlay | **Complete** locally (browser + API). OBS Studio **blocked**. |
| 5 Reliability, scale, packaging | **Implemented and locally verified.** Master 1k/5k/100k load targets **not met** on this laptop; live YouTube/OBS/GitLab/PyInstaller remain external. |

## Milestone 5 delivered

- API and worker structured logs: `configure_logging()` in FastAPI `create_app` / lifespan and worker entry
- Low-cardinality Prometheus metrics, log redaction, expanded admin health, WS snapshot coalesce/drop (`send_or_reset_buffer`)
- Redis rebuild script + `POST /api/v1/admin/projections/rebuild`
- Fault tests in `backend/tests/integration/test_m5_faults.py` (**passed** against Compose PG/Redis)
- Locust + `scripts/load/run_harness.py` through `append_and_process` (subset, burst, 2k unique measured)
- Production Compose worker joins `edge` + `internal` so YouTube ingest can egress; Postgres/Redis stay unpublished
- `docs/OPERATIONS.md`, `docs/CAPACITY_REPORT.md`, TLS Compose example, backup scripts, `.gitlab-ci.yml` (contracts check added)
- Scrubbed live Google credentials from `.env.example`

## Remaining external validation

- Native Windows PyInstaller build
- OBS Browser Source (`docs/OBS_SETUP.md`)
- Live YouTube private stream (`docs/YOUTUBE_SETUP.md`)
- YouTube API-use / retention review (`docs/SECURITY_AND_DATA.md`)
- GitLab pipeline on a runner with Docker services
- Master load targets on stronger hardware (this laptop measured ~150–225 cmd/s)

Do not treat blocked items as passed.
