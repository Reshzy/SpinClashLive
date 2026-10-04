# Color Rush Live — Progress

Working product name: Color Rush Live  
Repository root: this folder (`SpinClashLive`)  
Current milestone: 4 — OBS overlay — **closed locally**

## Environment

| Tool | Status |
| --- | --- |
| uv | Installed 0.12.23 at `%USERPROFILE%\.local\bin` |
| Project Python | 3.12.11 via `uv python install 3.12` |
| Node | v26.2.0 / npm 11.13.0 |
| Overlay lock | `overlay/package-lock.json` (Vite 8, GSAP 3.15, Vitest 5, Playwright 1.63) |
| Docker / Postgres / Redis | Compose postgres + redis healthy. Host Color Rush DB **5433**. |

## Commands that actually ran (milestone 4)

```text
uv run pytest backend/tests/domain/test_presentation.py backend/tests/application/test_snapshot_overlay.py backend/tests/application/test_api_routes.py
# 11 passed
uv run python scripts/export_contracts.py
uv run python scripts/check_contracts.py
# contracts ok
cd overlay
npm ci
npm run test
# 10 passed
npx playwright install chromium
npm run test:e2e
# 6 passed
npm run build
```

Live API (this machine, simulation, Postgres 5433):

```text
GET /health/live -> ok
GET /overlay -> 200, Vite index + /overlay/assets/
POST /api/v1/overlay/ws-ticket -> short-lived ticket
overlay secret against /api/v1/admin/health -> 401
WS /ws/v1/overlay first-message ticket -> snapshot (simulation, weights present)
```

OBS Studio Browser Source: **not executed** (no OBS in this environment).

## Milestone status

| Milestone | Status |
| --- | --- |
| 1 Foundation, rules, durable scoring | **Complete.** |
| 2 YouTube ingest, API, realtime projections | **Complete** locally. Live YouTube **blocked**. |
| 3 PySide6 operator console | **Complete** locally. |
| 4 OBS overlay | **Complete** locally (browser + API). OBS Studio **blocked**. |
| 5 Reliability, scale, packaging | Not started. |

## Overlay surface

Brand, countdown, 40-tile strip with center marker and 47.5/47.5/5 labels, Red/Gold/Green columns, rotating leaderboard, lookup/champion cards, chat instruction. Audio off. No operator controls. Awards show “Updating scores” until `award_status=committed`.

## Remaining external prerequisites

- Live YouTube private-stream + real OAuth consent: **blocked**.
- YouTube API-use / retention review (`docs/SECURITY_AND_DATA.md`).
- OBS Studio Browser Source on a machine with OBS: **blocked**. Command: paste Overlay Setup URL into a 1920×1080 Browser Source (`docs/OBS_SETUP.md`).
- Milestone 5 load/ops/packaging.

## Can milestone 5 begin?

**Yes.** Overlay is backend-connected and tested in a browser. Do not treat OBS or live YouTube as done.
