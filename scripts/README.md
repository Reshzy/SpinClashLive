# Scripts

Setup, demo, contracts, YouTube stubs, Redis rebuild, backups, load, secret scan.

```powershell
uv run python -m color_rush.demo
uv run python -m color_rush.bootstrap
uv run python scripts/export_contracts.py
uv run python scripts/check_contracts.py
uv run python scripts/generate_youtube_stubs.py
uv run python scripts/rebuild_redis.py
uv run python scripts/secret_scan.py
uv run python scripts/load/run_harness.py --profile subset
.\scripts\backup.ps1
```
