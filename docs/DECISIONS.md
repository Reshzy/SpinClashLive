# Color Rush Live — Decisions

Ordinary choices resolved during milestone 1. Update when a decision changes a contract, fairness rule, storage shape, or operations path.

## Product and repository

| Decision | Choice | Why |
| --- | --- | --- |
| Product name | Color Rush Live | Master working name |
| Python package | `color_rush` | Master layout |
| Repository root | Current folder (`SpinClashLive`) | Authorized; do not nest `youtube-live-game/` |
| Python baseline | 3.12 (`requires-python = ">=3.12,<3.13"`) | Master baseline; host 3.14 is not used for lock or images |
| Package manager | uv + `uv.lock` | Master lockfile suggestion |
| Type checker | mypy (strict on `color_rush`) | Master quality gate |
| Linter/formatter | Ruff | Master quality gate |

## Fairness and domain

| Decision | Choice | Why |
| --- | --- | --- |
| Weight ranges | `0-474` RED, `475-949` GREEN, `950-999` GOLD | Integer weights 475/475/50 totaling 1000; GREEN occupies the second 475 block |
| Production RNG | `secrets.randbelow(1000)` behind `Rng` port | Master; injectable for tests |
| Command parse | Trim + casefold; exact token only (`!red`, etc.) | Master; no prefix/substring match |
| Change allowance | Count only when the new color differs from the stored pick | Same-color repeats are free |
| Bonus exclusivity | Exactly one of NONE, DOUBLE_POINTS, GOLD_BONUS per rules snapshot | Master; frozen at OPEN |
| Double Points | Multiply every correct reward by 2 | Master |
| Gold Bonus | Replace Gold reward with configured integer (default 28); Red/Green unchanged | Master |
| Tie order | Points descending, then canonical player UUID ascending | Master; stable champion |
| Period identity | Local calendar date (daily) and Monday-start local date (weekly) in the configured IANA zone | Avoids ISO week-year ambiguity |
| Attribution instant | `score_effective_at` | Late settlement does not move the period |
| Default timezone | `Asia/Manila` | Master; stored as `timezone_version` on sessions/periods |
| Pause | Session flag, not a round state | Ongoing rounds complete; next OPEN is withheld |
| Next round | Forbidden until current same-session round is SETTLED or CANCELLED | Preserves streak order |

## Storage and concurrency

| Decision | Choice | Why |
| --- | --- | --- |
| Authoritative store | PostgreSQL 16 | Master; SQLite forbidden for concurrency tests |
| ORM | SQLAlchemy 2.x mapped classes | Master |
| Migrations | Alembic revision `0001_initial` with explicit PostgreSQL DDL | Fresh-DB verification; not `create_all` |
| Season overlap | GiST `EXCLUDE` on `tstzrange(starts_at, ends_at, '[)')` per `game_id` (`btree_gist`) | Master: prevent overlapping season intervals |
| SETTLED gate | `mark_settled` raises unless every `settlement_jobs` row is complete | Caller checks are not sufficient |
| Host Postgres port | Compose publishes 5432 and 5433 | This host already had another PostgreSQL on 5432 |
| Advisory lock | `pg_advisory_xact_lock(lock_key)` where `lock_key` is the signed 64-bit mix of the session UUID | Serializes inbox append and ingress closure |
| Clock in transactions | `SELECT clock_timestamp()` after lock acquisition | Deadline protection when scheduler is late |
| Sequence allocation | `game_sessions.next_inbox_sequence` incremented under the same lock | Monotonic per session |
| Coordinator fencing | `coordinator_leases.fencing_token` monotonic; every write checks token + expiry | Redis locks are insufficient |
| One active round | Partial unique index: at most one nonterminal round per session | Database-enforced |
| Settlement partitions | `hashtext(player_id::text) % partition_count`; default 8 partitions | Retry-safe batches |
| Ledger insert | `INSERT ... ON CONFLICT DO NOTHING` returning inserted ids | Zero-point retries must not restreak |
| Outbox in M1 | SQL `outbox_events` + `projection_jobs` written in the settlement transaction | Redis relay is milestone 2 |
| Outbox relay | Unpublished SQL rows → Redis Streams `outbox.game` and `outbox.projections`; consumer groups with XPENDING/XCLAIM; DLQ `outbox.dlq` | Crash after XADD may duplicate; `event_id` is idempotent; SQL sweeper republishes if Redis is down |
| Redis scores | `ZADD` of `-points` so `ZRANGE` ascending matches points desc + UUID asc | Master tie encoding; include zeros |
| Projection CAS | `score_version` on `leaderboard_scores`; skip writes if incoming version is older | Stale workers cannot overwrite |
| Overlay tickets | Hashed secret in `overlay_tickets`; WS ticket exchange | Read-only; never operator logs |
| Operator auth | JWT access + hashed refresh in `admin_sessions`; PBKDF2 password hashes | Separate from Google OAuth |
| Google secrets | Fernet(SECRET_KEY) encrypted payloads in `google_credentials` | Least scope `youtube.readonly` |
| YouTube transport | gRPC `streamList` primary; HTTP `liveChatMessages.list` fallback | Official 2026-10-04 docs |
| Simulation isolation | `COLOR_RUSH_ENV=simulation` and a separate `DATABASE_URL` | Production scores never mix |

## Process topology

| Decision | Choice | Why |
| --- | --- | --- |
| API process | Uvicorn + FastAPI `/api/v1` + `/ws/v1`; no scheduler in Uvicorn | Console/overlay clients |
| Worker process | `python -m color_rush.workers` with `COLOR_RUSH_WORKER_ROLE` | coordinator,ingest,settlement,outbox,projection,gateway,retention,all |
| Compose services | `api`, `worker`, `postgres`, `redis` | Redis required for projections/WS |
| Desktop / overlay | PySide6 console in M3; overlay still M4 | Console is API client only |
| Desktop networking | QThread + httpx REST; QWebSocket on GUI thread | Master: one nonblocking strategy; all widget updates on GUI thread |
| Desktop secrets | OS keyring service `color-rush-live` stores refresh token + API base | Never Google tokens or SQL/Redis |
| Desktop packaging | PyInstaller spec `desktop/packaging/color_rush_desktop.spec` | Exclude .env and simulation data |

## Vocabulary

Interfaces use “Make your pick,” “Predictions open,” “Picks locked,” “Players,” “Points earned,” “Recent results,” “Double Points,” and “Gold Bonus.” No betting or financial language.
