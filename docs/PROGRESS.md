# Color Rush Live — Progress

Working product name: Color Rush Live  
Repository root: this folder  
Current milestone: 5 — Reliability, scale, packaging — **implemented and verified locally; master load targets not met on this laptop; private YouTube ingest passed; production API-use and GitLab CI still blocked**

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

Native PyInstaller artifact: **operator reported built** (`uv run pyinstaller desktop/packaging/color_rush_desktop.spec`). Not re-run this handoff.

OBS Studio Browser Source: **operator reported done** (`docs/OBS_SETUP.md`). Not re-run this handoff.

Live YouTube private-stream + OAuth: **passed 2026-10-06** on DB `color_rush` + Redis DB 1. Browser OAuth, connect, source healthy, inbox `!red` (`rejected_not_open` — no OPEN round). Public/production use is **not** cleared; see `docs/SECURITY_AND_DATA.md`.

GitLab CI pipeline: **blocked**. Origin is GitHub only (`origin/init-laptop`). `.gitlab-ci.yml` was not executed on a GitLab runner.

## Milestone status

| Milestone | Status |
| --- | --- |
| 1 Foundation, rules, durable scoring | **Complete.** |
| 2 YouTube ingest, API, realtime projections | **Complete** locally. Private/unlisted live ingest **passed** 2026-10-06. Production API-use review **recorded, not cleared**. |
| 3 PySide6 operator console | **Complete** locally. |
| 4 OBS overlay | **Complete** locally (browser + API). OBS Studio **operator reported done**. |
| 5 Reliability, scale, packaging | **Implemented and locally verified.** Master 1k/5k/100k load targets **not met** on this laptop. GitLab CI **blocked** (GitHub-only remote). |

## Milestone 5 delivered

- API and worker structured logs: `configure_logging()` in FastAPI `create_app` / lifespan and worker entry
- Low-cardinality Prometheus metrics, log redaction, expanded admin health, WS snapshot coalesce/drop (`send_or_reset_buffer`)
- Redis rebuild script + `POST /api/v1/admin/projections/rebuild`
- Fault tests in `backend/tests/integration/test_m5_faults.py` (**passed** against Compose PG/Redis)
- Locust + `scripts/load/run_harness.py` through `append_and_process` (subset, burst, 2k unique measured)
- Production Compose worker joins `edge` + `internal` so YouTube ingest can egress; Postgres/Redis stay unpublished
- `docs/OPERATIONS.md`, `docs/CAPACITY_REPORT.md`, TLS Compose example, backup scripts, `.gitlab-ci.yml` (contracts check added)
- Scrubbed live Google credentials from `.env.example`
- Worker YouTube ingest now refreshes the stored OAuth token and passes `access_token` into `YouTubeChatSource` (required for private/unlisted chat)

## Remaining external validation

- GitLab pipeline on a GitLab runner with Docker services (skipped this session; GitHub-only remote)
- Production API-use follow-ups in `docs/SECURITY_AND_DATA.md`: privacy/ToS links, 30-day identifier refresh/unlink, viewer deletion path, unresolved III.F.3.c chat-command scoring
- Master load targets on stronger hardware (this laptop measured ~150–225 cmd/s). Do not start the scaling list in `docs/OPERATIONS.md` until a bigger box remeasures the bottleneck.
- Public live broadcast — **blocked** until the API-use follow-ups are closed. Private technical ingest is not production clearance.

Do not treat blocked items as passed. Do not treat M5 as production-ready.
