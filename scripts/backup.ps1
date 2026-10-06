$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path "data" "backups"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$pg = Join-Path $outDir "postgres-$stamp.sql"
docker compose exec -T postgres pg_dump -U color_rush color_rush_sim | Set-Content -Path $pg
$redis = Join-Path $outDir "redis-$stamp.rdb"
docker compose exec -T redis redis-cli BGSAVE | Out-Null
Write-Host "Wrote $pg"
Write-Host "Redis BGSAVE requested. Copy volume color_rush_redis if you need a physical dump."
Write-Host "Restore: docker compose exec -T postgres psql -U color_rush color_rush_sim < $pg"
Write-Host "Then: uv run python scripts/rebuild_redis.py"
