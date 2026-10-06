#!/usr/bin/env sh
set -eu
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p data/backups
pg="data/backups/postgres-${stamp}.sql"
docker compose exec -T postgres pg_dump -U color_rush color_rush_sim > "$pg"
docker compose exec -T redis redis-cli BGSAVE >/dev/null
echo "Wrote $pg"
echo "Restore: docker compose exec -T postgres psql -U color_rush color_rush_sim < $pg"
echo "Then: uv run python scripts/rebuild_redis.py"
