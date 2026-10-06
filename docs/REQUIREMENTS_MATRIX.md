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
| R2.7 | One final pick; eligible commands may change it | M1 | `domain/picks.py`, `application/ingest.py` | pick tests + PG ingest (`test_duplicate_and_old_sequence_and_change_limit`) passed |
| R2.8 | Five actual color changes; same-color repeats free | M1 | `apply_pick` | `test_five_changes_then_sixth_rejected` passed |
| R2.9 | Streak increment/reset/unchanged rules | M1 | `domain/streaks.py` + settlement | streak tests + PG retry passed |
| R2.10 | Internal UUID + provider channel ID; name not identity | M1 | `players` model | schema + PG integration passed |
| R2.11 | Default timings 30/5/6/5/3 | M1 | `RoundRules` defaults | rules validation passed |
| R2.12 | Validated versioned config frozen at OPEN | M1 | `configuration_versions` + `rules_snapshot` | `alembic upgrade head` + round tests passed |
| R2.13 | Manual and automatic modes; isolated simulation | M1 | `SessionMode`, `COLOR_RUSH_ENV` | config + worker loop present |
| R2.14 | Approved vocabulary; Double Points / Gold Bonus | M1 domain; M3/M4 UI | `BonusType` | `test_double_points_bonus`, `test_gold_bonus` passed |
| R2.15 | One bonus, declared before open, immutable | M1 | `RoundRules.bonus` | bonus tests passed |

## Master §3 Scope

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R3.1 | Independent backend, migrations, workers | M1 | package + Alembic + worker entry | `alembic upgrade head` + `pytest` 74 passed |
| R3.2 | Secure operator API | M2 | `api/routes.py`, JWT, roles, idempotency | `test_auth_roles_and_overlay_ticket` passed |
| R3.3 | Simulation source + real YouTube source | M2 | `SimulationChatSource`, `YouTubeChatSource` | sim source + YouTube fixture tests passed; private/unlisted live OAuth + inbox **passed** 2026-10-06; public/production API-use **not cleared** |
| R3.4 | OBS overlay | M4 | `overlay/` Vite app served at `/overlay` | Vitest 10 passed; Playwright 6 passed; live `/overlay` + overlay WS **passed** |
| R3.5 | Manual/auto, durable ingest, scoring, pause/cancel, bonuses | M1 | application services | integration tests |
| R3.6 | Four leaderboards, ranks, archives, champions | M1 SQL; M2 Redis; M4 display | settlement + rotating snapshot board | period tests; overlay board rotation |
| R3.7 | Operator console pages | M3 | `desktop/src/color_rush_desktop` nine pages + login | `pytest desktop/tests` 9 passed |
| R3.8 | Prestige badges from finalized periods | M2/M4 | champion records in M1 | archive tests |
| R3.9 | Backpressure, metrics, load, packaging, ops docs | M5 | observability metrics, Locust harness, `docs/OPERATIONS.md`, PyInstaller spec, `.gitlab-ci.yml` | ruff/mypy/pytest 118 passed; load subset/burst/2k unique measured — master 1k/5k/100k **not met** (see `docs/CAPACITY_REPORT.md`) |
| R3.10 | Later extensions documented, not built | M1 docs | DECISIONS + this matrix | review |

## Master §4 Stack

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R4.1 | Python 3.12 baseline + lockfile | M1 | `pyproject.toml`, `uv.lock` | `uv lock` / `uv run` |
| R4.2 | PySide6 desktop | M3 | `desktop/src/color_rush_desktop` | `uv run pytest desktop/tests` **9 passed** (offscreen); native PyInstaller artifact optional |
| R4.3 | FastAPI / Pydantic | M1 health+sim; M2 full API | `color_rush.api` | OpenAPI export + route tests passed |
| R4.4 | PostgreSQL, SQLAlchemy 2, Alembic | M1 | models + migrations | `alembic upgrade head` to `0002_m2_auth_source` on `color_rush_sim` / fresh `color_rush_test` |
| R4.5 | Redis projections/streams | M2 | `infrastructure/redis` | `test_stale_projection_cannot_overwrite`, `test_zero_score_tie_order_matches_sql_policy`, `test_outbox_pending_recovery_dead_letters` passed |
| R4.6 | Vite/TS/GSAP overlay | M4 | `overlay/` + GSAP npm, no CDN | `npm run test` 10 passed; `npm run build` |
| R4.7 | Docker Compose backend | M1 | `compose.yaml`, Dockerfiles | `docker compose up -d postgres redis` healthy |
| R4.8 | pytest, Qt tests, Vitest, Playwright, Locust | M1–M5 | Locust extra + `scripts/load/` | pytest 118 passed / 1 skipped; Vitest 10; Playwright 6; Locust 2.46.7; subset/burst/2k unique ran — 1k/5k/100k **not met** |
| R4.9 | Ruff + typecheck | M1 | Ruff/mypy config | `ruff` / `mypy` |
| R4.10 | No SQLite for concurrency tests | M1 | PG-only integration | `test_deadline_closure_race` passed |

## Master §5 Architecture

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R5.1 | API process + separate worker; no scheduler in Uvicorn | M1 | Compose commands | process inspection |
| R5.2 | Domain imports no Qt/FastAPI/SQLAlchemy/Redis/YouTube | M1 | `domain/` + lance test | `test_domain_purity` |
| R5.3 | Ports/interfaces; one composition root | M1 | `application/ports.py`, `composition.py` | import tests |
| R5.4 | Roles: ingest, coordinator, settlement, projection, gateway, console | M1 first three; M2+ rest | `COLOR_RUSH_WORKER_ROLE` coordinator\|ingest\|settlement\|outbox\|projection\|gateway\|retention\|all | workers consume roles |
| R5.5 | Single-session serialized ingest/control boundary | M1 | advisory lock | `test_deadline_closure_race` passed |

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
| R6.9 | Outbox same transaction; Redis relay + sweeper | M1 outbox rows; M2 relay | `outbox.py` + Redis Streams | `test_sim_source_to_settlement_and_redis`, `test_sql_scores_survive_without_redis` passed |
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
| R8.1 | All listed tables, constraints, indexes | M1 | `models.py` + `0001_initial` | `test_alembic_upgrade_created_schema` passed; `ex_seasons_no_overlap` present |

## Master §9 Settlement

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R9.1 | Freeze `round_periods` at closure | M1 | coordinator close | period-assign tests |
| R9.2 | Ledger for every participant including zero | M1 | settlement service | zero-point tests |
| R9.3 | Stats/streaks/four aggregates only on new ledger rows | M1 | settlement service | retry tests |
| R9.4 | Projection/outbox/cursor same transaction | M1 | settlement service | commit tests |
| R9.5 | SETTLED only when all partitions complete | M1 | settlement service + `mark_settled` | `test_mark_settled_requires_all_partitions` passed |
| R9.6 | No next same-session round before SETTLED | M1 | coordinator start | start-guard tests |
| R9.7 | Redis absolute ZADD + rebuild | M2 | `infrastructure/redis/projections.py` | stale-version and zero-score tie tests passed |

## Master §10 Periods and lookup

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R10.1 | Daily/weekly/season/all-time half-open rules | M1 | `periods.py` | clock tests |
| R10.2 | Attribution by `score_effective_at`; midnight/Monday edges | M1 | period service | boundary tests |
| R10.3 | CLOSING until attributed rounds done; idempotent finalize | M1 | period finalizer | finalize tests |
| R10.4 | Top 100 archive + unique champion; empty = no champion | M1 | period finalizer | archive tests |
| R10.5 | Tie policy displayed in help | M2 help card; M1 domain order | `ranking.py` | ranking tests |
| R10.6 | Redis key layout and tie encoding | M2 | `encoded_score` / generation keys | `test_tie_encoding_and_safe_names`, `test_zero_score_tie_order_matches_sql_policy` passed |
| R10.7 | Overlay rotation / lookup queue / help cooldown | M2/M4 | rotating snapshot board; lookup/help throttle | `test_lookup_and_help_cooldown`; overlay board Playwright |

## Master §11 YouTube and simulation

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R11.1 | Official streamList + list fallback | M2 | `infrastructure/youtube/` + vendored proto | `test_youtube_contracts.py` fixture shapes passed; private/unlisted live ingest **passed** 2026-10-06 (source healthy, inbox `red`) |
| R11.2 | Simulation implements same source interface | M2 | `ChatSource` + `SimulationChatSource` | `test_simulation_source_covers_required_shapes` passed |
| R11.3 | Isolated sim data/config | M1 | env + DB URL | config tests |
| R11.4 | API data vs game data, retention, deletion | M2 `SECURITY_AND_DATA.md` | docs + delete-data route | `test_sql_scores_survive_without_redis`; production API-use review **recorded 2026-10-06 — production not cleared** |

## Master §12 REST and realtime

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R12.1 | Versioned `/api/v1` endpoints | M2 | `api/routes.py` | `test_health_and_versioned_routes_registered`; `scripts/check_contracts.py` ok |
| R12.2 | Auth, idempotency, overlay tickets, WS | M2 | JWT, overlay tickets, `/ws/v1/*` | `test_auth_roles_and_overlay_ticket` passed (idempotency replay + 409) |

## Master §13 Console

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R13.1 | Dark sidebar console, 9 pages, orange accent | M3 | `desktop/src/color_rush_desktop/views` | `test_login_error_and_shell_pages` passed |
| R13.2 | Nonblocking QThread+httpx; GUI-thread mutations | M3 | `api_client/worker.py`, `viewmodels/session.py` | `test_slow_network_keeps_ui_clickable` passed |
| R13.3 | Real authenticated actions, no optimistic round state | M3 | Dashboard/YouTube/… pages | `test_failed_action_keeps_round_state` passed |
| R13.4 | Login/refresh/keyring; Google via system browser | M3 | login + YouTube page + backend OAuth routes | OAuth unit tests passed; live Google browser consent **passed** 2026-10-06 (`auth_mode=oauth`) |
| R13.5 | Players/leaderboards pagination, ranks, champions | M3 | players/leaderboards pages + cursor APIs | Qt + route registration tests |
| R13.6 | Overlay tickets, OBS URL, 1080/720 instructions | M3/M4 | overlay_setup page; `docs/OBS_SETUP.md` | ticket exchange live; Playwright 1080/720 |
| R13.7 | Roles hide and server-enforce | M3 | `roles.py` + backend WRITE_ROLES | `test_moderator_cannot_save_settings` passed |
| R13.8 | Close console does not stop backend | M3 | no process kill; documented | `test_operator_smoke_against_running_api` + `test_shutdown_cancels_worker` |
| A9 | Console stays responsive | M3 | QThread worker | `test_slow_network_keeps_ui_clickable` passed |

## Master §14 Overlay

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R14.1 | 1920×1080 / 1280×720 composition | M4 | `overlay/src` stage scale | Playwright 1080/720 screenshots |
| R14.2 | Strip + center marker, three columns, board, help | M4 | original Color Rush Live UI | `overlay/tests/e2e/screenshots/` |
| R14.3 | Authoritative snapshot client | M4 | `transport/` + `state/reducer.ts` | Vitest seq reject; live overlay WS |
| R14.4 | GSAP strip from `animation_plan` | M4 | 40-tile layout + `animation/strip.ts` | landing error < 8px; domain slot tests |
| R14.5 | Award pending vs committed | M4 | snapshot `award_status` | Playwright gold RESULT: Updating scores |
| R14.6 | Safe names; no wagering UI; audio off | M4 | `textContent` + sanitize | unsafe-name Playwright |
| R14.7 | Overlay-only credentials | M4 | fragment → short-lived WS JWT | overlay secret → admin 401 |

## Master §15 Security and operations

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R15.1 | Loopback default; secrets excluded | M1 | `.env.example`, `.gitignore` | file review |
| R15.2 | Overlay vs operator credentials | M2 | overlay tickets vs JWT; Google secrets Fernet | overlay ticket tests; `SECURITY_AND_DATA.md` |
| R15.3 | Compose healthchecks, least privilege | M1 | `compose.yaml`, Dockerfiles | compose config |
| R15.4 | PowerShell + POSIX setup commands | M1 | README | command rehearsal |
| R15.5 | Production TLS, backups, runbooks | M5 | `deployment/compose.production.yaml`, Caddyfile, `scripts/backup.ps1`, `docs/OPERATIONS.md` | files reviewed; remote deploy **not executed** |

## Master §16 Scale

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| R16.* | Locust harness and measured targets | M5 | `scripts/load/run_harness.py`, Locust PipelineUser via `append_and_process` | subset 156 cmd/s; burst 225 cmd/s (target 5k **not met**); 2k unique reconcile ok, settle 40.7 s; 1k/10min and 100k unique **not run** — see `docs/CAPACITY_REPORT.md` |

## Master §17 Acceptance

| ID | Requirement | Milestone | Implementation | Verification |
| --- | --- | --- | --- | --- |
| A1 | Simulated round chat → scores, no Google key | M1 durable; M4 strip | `demo.py` + integration tests | `uv run python -m color_rush.demo` passed; `test_complete_simulated_round` passed |
| A2 | Domain purity; clients cannot mutate off-API | M1 purity; M2/M3/M4 | lance test | `test_domain_purity` |
| A3 | History/delay/duplicate/change/sequence rules | M1 | ingest + picks | domain + PG ingest tests passed |
| A4 | Deadline, lease, start races | M1 | coordinator | `test_deadline_closure_race`, fence, two-start passed |
| A5 | Settlement replay / Redis loss | M1 SQL; M2 Redis | settlement + sweeper | PG retry + `test_sql_scores_survive_without_redis` passed |
| A6 | Period/DST/clock tests | M1 | periods | midnight, Monday, season PG tests passed |
| A7 | SQL/Redis ties; archives once | M1 SQL; M2 Redis | ranking + Redis ZADD | PG zero-point ties + `test_zero_score_tie_order_matches_sql_policy` passed |
| A8 | Pause/cancel/auto/bonus/unhealthy source | M1 controls; M2 source | coordinator + source_health | pause/cancel/bonus PG tests + `test_source_lag_pauses_new_rounds` passed |
| A9 | Console responsiveness | M3 | QThread + Dashboard | `test_slow_network_keeps_ui_clickable` passed |
| A10 | Overlay lands on every color; reload phases | M4 | GSAP + snapshot reconstruct | Playwright spinning/gold/reload; OBS Browser Source **operator reported done** |
| A11 | Safe overlay text; 1080/720 screenshots | M4 | sanitize + Playwright | screenshots captured; no wagering UI |
| A12 | Token/retention tests | M2 | JWT expiry, overlay tickets, 7-day command purge | `test_password_and_jwt_roundtrip`; live OAuth connect **passed**; live revoke **not run** this session |
| A13 | Capacity evidence | M5 | `docs/CAPACITY_REPORT.md` | subset/burst/2k unique recorded; master 1k/5k/100k targets **not met** on this laptop |
| A14 | CI + packaging consistency | M5 | `.gitlab-ci.yml`, PyInstaller spec, setup scripts | local ruff/mypy/pytest/overlay; native PyInstaller **operator reported built**; GitLab pipeline **blocked** (GitHub-only remote) |
| A15 | Final progress report | M5 | `docs/PROGRESS.md` | this milestone |
