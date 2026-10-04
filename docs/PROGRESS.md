# Color Rush Live — Progress

Working product name: Color Rush Live  
Repository root: this folder (`SpinClashLive`)  
Current milestone: 3 — Native PySide6 operator console — **closed locally**

## Environment

| Tool | Status |
| --- | --- |
| uv | Installed 0.12.23 at `%USERPROFILE%\.local\bin` |
| Project Python | 3.12.11 via `uv python install 3.12` (pinned in `.python-version`) |
| Host Python 3.14 | Present, not used |
| Lockfile | `uv.lock` resolved 2026-10-04 (desktop extra: PySide6, keyring, pyinstaller) |
| Ruff | 0.16.10 |
| mypy | 1.20.0 (strict on `color_rush` and `color_rush_desktop`) |
| pytest-qt | Installed with `--extra dev` |
| Docker / Postgres / Redis | Unchanged from M2. Host Postgres **5433** for Color Rush (`5432` is a different server). |

## Preflight (milestone 3)

```text
docker compose ps
# postgres + redis healthy
DATABASE_URL=postgresql+psycopg://color_rush:color_rush@127.0.0.1:5433/color_rush_sim
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
# owner ready: owner (owner)
GET http://127.0.0.1:8000/health/live -> {"status":"ok"}
POST /api/v1/auth/login owner / change-me-owner -> bearer token (role=owner)
```

Host port 5432 rejects `color_rush` (other PostgreSQL). Use **5433**.

## Commands that actually ran (milestone 3 close-out)

```text
uv sync --extra dev --extra desktop
uv run ruff check desktop/src desktop/tests
# All checks passed
uv run pytest desktop/tests
# 9 passed (QT_QPA_PLATFORM=offscreen)
uv run python scripts/export_contracts.py
uv run python scripts/check_contracts.py
# contracts ok
```

Desktop launch:

```powershell
$env:COLOR_RUSH_API_BASE = "http://127.0.0.1:8000"
uv run python -m color_rush_desktop
```

Packaging:

```powershell
uv run pyinstaller desktop/packaging/color_rush_desktop.spec
# wrote dist/ColorRushLive/ColorRushLive.exe (PyInstaller 6.22.3, Windows 11)
```

Native PyInstaller onedir **executed** on this host. `dist/` is gitignored. Visual Fusion-theme QA on a physical desktop session is still recommended (pytest used `QT_QPA_PLATFORM=offscreen`).

## Milestone status

| Milestone | Status |
| --- | --- |
| 1 Foundation, rules, durable scoring | **Complete.** |
| 2 YouTube ingest, API, realtime projections | **Complete** locally. Live YouTube **blocked**. |
| 3 PySide6 operator console | **Complete** locally (Qt tests + API smoke). Live Google consent and signed installer QA remain external. |
| 4 OBS overlay | Not started (`/overlay` is a placeholder page for URL/preview). |
| 5 Reliability, scale, packaging | Not started (desktop spec exists; backend load/ops still M5). |

## Desktop pages implemented

Dashboard, YouTube, Players, Leaderboards, Seasons, Moderation, Settings, Health/Audit, Overlay Setup. Login/refresh/logout. Role-sensitive enablement. No dead sidebar destinations.

## Architectural decisions

See `docs/DECISIONS.md` (QThread+httpx, QWebSocket, OS keyring, PyInstaller).

## Remaining external prerequisites

- Live YouTube private-stream + real OAuth consent: **blocked** until a live video is connected.
- YouTube API-use / retention review (`docs/SECURITY_AND_DATA.md`).
- Native installer visual QA on a physical Windows desktop session (offscreen grabs are not a substitute for an operator looking at Fusion styling).
- OBS overlay (milestone 4).

## Windows visual verification (when not using offscreen)

1. Start API + worker against Compose Postgres **5433**.
2. `uv run python -m color_rush_desktop`
3. Sign in as `owner` / `change-me-owner`.
4. Confirm SIMULATION banner, nine sidebar pages, Dashboard mutations disabled while disconnected, Overlay Setup copy/preview.
5. Close the console and confirm `GET /health/live` still returns ok.

## Can milestone 4 begin?

**Yes**, for the OBS overlay. Console actions work against backend services. Do not treat live YouTube or a polished overlay composition as done.
