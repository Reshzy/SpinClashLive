# Color Rush Live — Requirements matrix

Every master V1 requirement is assigned to one primary milestone. Evidence is filled as implementation lands. External checks that cannot run are labeled **blocked** with a command, never passed.

Legend: M1 foundation · M2 ingest/API/realtime · M3 desktop · M4 overlay · M5 hardening.

## Master §2 Product rules

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R2.1 | Colors RED/GOLD/GREEN | M1 | `backend/src/color_rush/domain/enums.py` | `backend/tests/domain/test_rng_scoring.py` passed |
| R2.2 | Commands `!red !gold !green !score !rank !help` | M1 | `backend/src/color_rush/domain/commands.py` | `test_commands.py` passed |
| R2.3 | Trim, case-insensitive, exact tokens only | M1 | `parse_command` | `test_commands.py` passed |
| R2.4 | Weights 475/475/50 totaling 1000 | M1 | `RoundRules` | `test_weight_boundaries` passed |
| R2.5 | Rewards +2/+14/+2; incorrect +0 | M1 | `domain/scoring.py` | `test_base_rewards` passed |
| R2.6 | Free play; no stakes, money, or negative points | M1 | scoring + `ck_ledger_points_nonnegative` | scoring tests passed |
| R2.7 | One final pick; eligible commands may change it | M1 | `domain/picks.py`, `application/ingest.py` | pick tests passed; PG ingest **blocked** |
| R2.8 | Five actual color changes; same-color repeats free | M1 | `apply_pick` | `test_five_changes_then_sixth_rejected` passed |
| R2.9 | Streak increment/reset/unchanged rules | M1 | `domain/streaks.py` + settlement | streak tests passed; PG retry **blocked** |
| R2.10 | Internal UUID + provider channel ID; name not identity | M1 | `players` model | schema present; PG **blocked** |
| R2.11 | Default timings 30/5/6/5/3 | M1 | `RoundRules` defaults | rules validation passed |
| R2.12 | Validated versioned config frozen at OPEN | M1 | `configuration_versions` + `rules_snapshot` | code present; PG **blocked** |
| R2.13 | Manual and automatic modes; isolated simulation | M1 | `SessionMode`, `COLOR_RUSH_ENV` | config + worker loop present |
| R2.14 | Approved vocabulary; Double Points / Gold Bonus | M1 domain; M3/M4 UI | `BonusType` | `test_double_points_bonus`, `test_gold_bonus` passed |
| R2.15 | One bonus, declared before open, immutable | M1 | `RoundRules.bonus` | bonus tests passed |

## Master §3 Scope

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R3.1 | Independent backend, migrations, workers | M1 | package + Alembic + worker entry | migrate + pytest |
| R3.2 | Secure operator API | M2 | — | — |
| R3.3 | Simulation source + real YouTube source | M2 (sim pipeline starts M1) | M1 sim uses durable path | M1 demo; M2 YouTube |
| R3.4 | OBS overlay | M4 | overlay skeleton only in M1 | — |
| R3.5 | Manual/auto, durable ingest, scoring, pause/cancel, bonuses | M1 | application services | integration tests |
| R3.6 | Four leaderboards, ranks, archives, champions | M1 SQL; M2 Redis; M4 display | settlement + periods | period tests |
| R3.7 | Operator console pages | M3 | desktop skeleton in M1 | — |
| R3.8 | Prestige badges from finalized periods | M2/M4 | champion records in M1 | archive tests |
| R3.9 | Backpressure, metrics, load, packaging, ops docs | M5 (M1 health only) | `/health/*` | health tests |
| R3.10 | Later extensions documented, not built | M1 docs | DECISIONS + this matrix | review |

## Master §4 Stack

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R4.1 | Python 3.12 baseline + lockfile | M1 | `pyproject.toml`, `uv.lock` | `uv lock` / `uv run` |
| R4.2 | PySide6 desktop | M3 | skeleton in M1 | — |
| R4.3 | FastAPI / Pydantic | M1 health+sim; M2 full API | `color_rush.api` | health tests |
| R4.4 | PostgreSQL, SQLAlchemy 2, Alembic | M1 | models + migrations | fresh migrate |
| R4.5 | Redis projections/streams | M2 | Compose Redis in M1 | Compose up |
| R4.6 | Vite/TS/GSAP overlay | M4 | overlay skeleton in M1 | — |
| R4.7 | Docker Compose backend | M1 | `compose.yaml`, Dockerfiles | compose config / up |
| R4.8 | pytest, Qt tests, Vitest, Playwright, Locust | M1 pytest; later others | `backend/tests` | `uv run pytest` |
| R4.9 | Ruff + typecheck | M1 | Ruff/mypy config | `ruff` / `mypy` |
| R4.10 | No SQLite for concurrency tests | M1 | PG-only integration | integration tests |

## Master §5 Architecture

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R5.1 | API process + separate worker; no scheduler in Uvicorn | M1 | Compose commands | process inspection |
| R5.2 | Domain imports no Qt/FastAPI/SQLAlchemy/Redis/YouTube | M1 | `domain/` + lance test | `test_domain_purity` |
| R5.3 | Ports/interfaces; one composition root | M1 | `application/ports.py`, `composition.py` | import tests |
| R5.4 | Roles: ingest, coordinator, settlement, projection, gateway, console | M1 first three; M2+ rest | workers + services | integration |
| R5.5 | Single-session serialized ingest/control boundary | M1 | advisory lock | race tests |

## Master §6 Durability

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R6.1 | PostgreSQL authoritative; Redis rebuildable | M1 SQL; M2 Redis | settlement writes SQL | crash tests |
| R6.2 | Normalize commands; retain minimal source fields | M1 inbox; M2 source adapter | `command_inbox` | ingest tests |
| R6.3 | Shared session advisory lock; clock after lock | M1 | `session_lock.py` | race tests |
| R6.4 | Monotonic sequence; checkpoint after durable classify | M1 | ingest service | checkpoint tests |
| R6.5 | Eligibility: OPEN + receipt window + published_at >= opened_at | M1 | `eligibility.py` | late/history tests |
| R6.6 | DRAINING freezes cutoff; late scheduler cannot extend | M1 | coordinator close | deadline tests |
| R6.7 | Drain bound failure cancels | M1 | coordinator | drain-fail tests |
| R6.8 | LOCKED only after eligible processing; older sequences cannot overwrite | M1 | pick processor | sequence tests |
| R6.9 | Outbox same transaction; Redis relay + sweeper | M1 outbox rows; M2 relay | `outbox_events` | settlement tests |
| R6.10 | Coordinator lease + fencing token | M1 | `coordinator_leases` | stale-owner tests |
| R6.11 | At most one nonterminal round per session | M1 | unique index | two-start tests |

## Master §7 Round machine

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R7.1 | States and transitions per diagram | M1 | `states.py` + coordinator | transition tests |
| R7.2 | Pause flag; cancel before outcome; finish after SPINNING | M1 | coordinator | control tests |
| R7.3 | Manual can wait in LOCKED; deadline still closes | M1 | coordinator | mode tests |
| R7.4 | Persist outcome before SPINNING; injectable RNG | M1 | spin service | restart tests |
| R7.5 | Presentation plan stored; settlement independent of overlay | M1 | `presentation_plan` JSON | spin tests |
| R7.6 | No production force-result | M1 | sim-only override | config tests |

## Master §8 Data model

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R8.1 | All listed tables, constraints, indexes | M1 | `models.py` + `0001_initial` | models compiled; `alembic upgrade head` **blocked** (no Postgres) |

## Master §9 Settlement

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R9.1 | Freeze `round_periods` at closure | M1 | coordinator close | period-assign tests |
| R9.2 | Ledger for every participant including zero | M1 | settlement service | zero-point tests |
| R9.3 | Stats/streaks/four aggregates only on new ledger rows | M1 | settlement service | retry tests |
| R9.4 | Projection/outbox/cursor same transaction | M1 | settlement service | commit tests |
| R9.5 | SETTLED only when all partitions complete | M1 | settlement service | partition tests |
| R9.6 | No next same-session round before SETTLED | M1 | coordinator start | start-guard tests |
| R9.7 | Redis absolute ZADD + rebuild | M2 | — | — |

## Master §10 Periods and lookup

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R10.1 | Daily/weekly/season/all-time half-open rules | M1 | `periods.py` | clock tests |
| R10.2 | Attribution by `score_effective_at`; midnight/Monday edges | M1 | period service | boundary tests |
| R10.3 | CLOSING until attributed rounds done; idempotent finalize | M1 | period finalizer | finalize tests |
| R10.4 | Top 100 archive + unique champion; empty = no champion | M1 | period finalizer | archive tests |
| R10.5 | Tie policy displayed in help | M2 help card; M1 domain order | `ranking.py` | ranking tests |
| R10.6 | Redis key layout and tie encoding | M2 | — | — |
| R10.7 | Overlay rotation / lookup queue / help cooldown | M2/M4 | — | — |

## Master §11 YouTube and simulation

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R11.1 | Official streamList + list fallback | M2 | — | — |
| R11.2 | Simulation implements same source interface | M2 (M1 demo injects commands) | M1 `simulation` pipeline | demo |
| R11.3 | Isolated sim data/config | M1 | env + DB URL | config tests |
| R11.4 | API data vs game data, retention, deletion | M2 `SECURITY_AND_DATA.md` | — | — |

## Master §12 REST and realtime

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R12.1 | Versioned `/api/v1` endpoints | M2 (M1 health only) | `/health/live`, `/health/ready` | health tests |
| R12.2 | Auth, idempotency, overlay tickets, WS | M2 | — | — |

## Master §13 Console

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R13.* | All console pages and networking | M3 | desktop skeleton in M1 | — |

## Master §14 Overlay

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R14.* | Overlay composition and animation | M4 | overlay skeleton in M1 | — |

## Master §15 Security and operations

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R15.1 | Loopback default; secrets excluded | M1 | `.env.example`, `.gitignore` | file review |
| R15.2 | Overlay vs operator credentials | M2 | — | — |
| R15.3 | Compose healthchecks, least privilege | M1 | `compose.yaml`, Dockerfiles | compose config |
| R15.4 | PowerShell + POSIX setup commands | M1 | README | command rehearsal |
| R15.5 | Production TLS, backups, runbooks | M5 | — | — |

## Master §16 Scale

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R16.* | Locust harness and measured targets | M5 | — | — |

## Master §17 Acceptance

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| A1 | Simulated round chat → scores, no Google key | M1 durable; M4 strip | `demo.py` + integration tests | domain passed; demo/PG **blocked** |
| A2 | Domain purity; clients cannot mutate off-API | M1 purity; M2/M3/M4 | lance test | `test_domain_purity` |
| A3 | History/delay/duplicate/change/sequence rules | M1 | ingest + picks | domain + PG tests |
| A4 | Deadline, lease, start races | M1 | coordinator | PG race tests |
| A5 | Settlement replay / Redis loss | M1 SQL; M2 Redis | settlement | retry tests |
| A6 | Period/DST/clock tests | M1 | periods | clock tests |
| A7 | SQL/Redis ties; archives once | M1 SQL; M2 Redis | ranking + finalizer | finalize tests |
| A8 | Pause/cancel/auto/bonus/unhealthy source | M1 controls; M2 source | coordinator | control tests |
| A9 | Console responsiveness | M3 | — | — |
| A10–A11 | Overlay landing / safety | M4 | — | — |
| A12 | Token/retention tests | M2 | — | — |
| A13 | Capacity evidence | M5 | — | — |
| A14 | CI + packaging consistency | M5 (M1 local gates) | ruff/mypy/pytest | local commands |
| A15 | Final progress report | M5 (M1 updates this file) | `docs/PROGRESS.md` | review |
