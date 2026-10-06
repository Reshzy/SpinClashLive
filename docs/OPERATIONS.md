# Operations — Color Rush Live

The backend owns rounds, picks, results, and scores. The PySide6 console sends authenticated commands. The overlay is a read-only OBS Browser Source. Closing the console does not stop the API or worker.

## Start (simulation, local)

Windows PowerShell:

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
Copy-Item .env.example .env
docker compose up -d postgres redis
uv sync --extra dev --extra desktop
uv run alembic upgrade head
uv run python -m color_rush.bootstrap
$env:COLOR_RUSH_ENV = "simulation"
uv run python -m uvicorn color_rush.api.app:app --host 127.0.0.1 --port 8000
# other terminal
$env:COLOR_RUSH_WORKER_ROLE = "all"
uv run python -m color_rush.workers
# other terminal
cd overlay; npm ci; npm run build
uv run python -m color_rush_desktop
```

POSIX equivalents are in the README. Demo without a GUI: `uv run python -m color_rush.demo`.

## Stop

Stop the API and worker processes. `docker compose stop` keeps volumes. `docker compose down` stops containers; add `-v` only when you intend to destroy Postgres/Redis data.

## Reconnect

- Overlay: reload the Browser Source. It requests a snapshot; it does not own RNG or scores.
- Console: login again if the access token expired; the refresh token is in the OS keyring.
- YouTube source: use Overlay/YouTube pages; invalid continuation tokens show resync. Do not run two ingest owners for one broadcast.

## Simulation versus production

`COLOR_RUSH_ENV=simulation` enables `/simulation/*` and the simulation chat source. Use a separate `DATABASE_URL` (`color_rush_sim`). Production must not point at the simulation database. Forced outcomes exist only in simulation.

## Real broadcast auth

Operator login is not Google login. Backend-owned API key and/or OAuth live in `.env` / encrypted SQL. See [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md). Live YouTube verification is environment-dependent.

## Point rules (summary)

Free play. `!red` / `!gold` / `!green`. Weights 475/475/50. Rewards +2 / +14 / +2. Five actual color changes after the first pick. Streaks skip cancelled rounds. Next-round Double Points or Gold Bonus is frozen at OPEN. Tie order: points descending, then canonical player UUID ascending.

## Period reset and ties

Daily local midnight, weekly Monday 00:00, season interval, all-time. Attribution uses `score_effective_at`, not worker completion. Previous periods stay CLOSING until attributed rounds settle. Empty periods have no champion. Timezone changes after the first production round need a documented migration.

## Recovery runbooks

| Symptom | Action |
| --- | --- |
| Queue age / inbox backlog high | Pause new rounds (automatic if `source_backlog_pause` exceeded). Drain or cancel if fairness cannot be preserved. Do not drop overflow silently. |
| Source lag / ended / quota / disabled | New rounds pause. Eligible OPEN/DRAINING/LOCKED rounds cancel with a recorded reason. Fix credentials or wait out quota; then resume. |
| Stuck settlement | Inspect `GET /api/v1/admin/health` settlement jobs. Restart the worker. Settlement is idempotent (`ON CONFLICT DO NOTHING` ledger). Do not start the next same-session round until SETTLED. |
| PostgreSQL outage | Ingest and control stop. Do not acknowledge chat. Restore from backup; replay un-checkpointed source pages. |
| Redis restart or flush | Durable picks and ledger remain in SQL. `uv run python scripts/rebuild_redis.py` or `POST /api/v1/admin/projections/rebuild`. Overlay may show Refreshing until rebuilt. |
| Credential/quota failure | Disconnect YouTube, rotate keys in Cloud Console, reconnect. Redact secrets from logs. |
| Stale coordinator | A new owner claims a new fencing token. Old tokens get 409. |
| Overlay credential leak | Revoke the overlay ticket from Overlay Setup. |
| Rollback | Restore Postgres dump (`scripts/backup.ps1` / `scripts/backup.sh`), run migrations only forward if the dump is post-migrate, rebuild Redis, restart API+worker. |

Health: `GET /health/live`, `GET /health/ready`, `GET /api/v1/admin/health`, `GET /metrics` (loopback unless `TRUSTED_METRICS=true`).

## Backups

`scripts/backup.ps1` dumps `color_rush_sim`. Production databases need the same `pg_dump` against the production name. Deletion of player data does not erase old backups until those backups expire.

## Containers

Local: `docker compose up --build`. Production-shaped example (Postgres/Redis unpublished on `internal`; API and worker also join `edge` so YouTube ingest can egress; Caddy TLS): `deployment/compose.production.yaml` plus `deployment/caddy/Caddyfile`. One-time migrate service. Do not deploy remotely without authorization.

## Scaling extraction triggers (do not build now)

1. Measure the serialized ingest/control boundary; batch SQL first.
2. Split ingest / settlement / projection worker roles onto separate processes.
3. Tune indexes and pools.
4. Managed Postgres/Redis and API replicas for reads.
5. Partition historical inbox only after volume evidence.
6. Extract a broker (Kafka/NATS) or Redis Cluster only when the monolith’s measured limit is the blocker.

Deferred product interfaces: achievements/XP, teams, cosmetics, tournaments, public companion site, independently deployed services. Commit/reveal “provably fair” is out of V1.

## Alerts (low cardinality)

Watch `color_rush_inbox_oldest_age_seconds`, `color_rush_source_lag_ms`, `color_rush_settlement_lag_seconds`, `color_rush_outbox_pending`, `color_rush_projection_pending`, `color_rush_redis_up`, `color_rush_postgres_up`, `color_rush_ingest_decisions_total`. Never label metrics with player IDs or message IDs.
