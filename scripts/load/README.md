# Load harness

Internal pipeline generator. Uses production `append_and_process` and real PostgreSQL. Requires `COLOR_RUSH_ENV=simulation`.

```powershell
uv sync --extra load
$env:COLOR_RUSH_ENV = "simulation"
uv run python scripts/load/run_harness.py --profile subset
uv run locust -f scripts/load/locustfile.py --headless -u 1 -r 1 -t 15s
```

Profiles in `run_harness.py`: `subset` (200/s for 15s), `burst` (5000/s for 10s), `sustained` (1000/s for 10 min), `unique` (`--players`, default 2000; pass 100000 for the master target).

HTTP optional: `scripts/load/locustfile_http.py` against `/simulation/commands/batch`.
