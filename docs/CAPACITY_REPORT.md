# Capacity report — Color Rush Live

Internal pipeline evidence only. This is **not** YouTube API delivery capacity. Watching a livestream does not open a connection to this backend.

## Hardware and configuration (this run)

| Item | Value |
| --- | --- |
| OS | Microsoft Windows 11 Pro (`10.0.22000`) |
| Host | Acer TravelMate P215-53G |
| CPU | Intel64 Family 6 Model 140 Stepping 1, 8 logical processors |
| RAM | 16 GiB (16948453376 bytes) |
| Python | 3.12.15 via uv |
| Locust | 2.46.7 |
| Generator | `append_and_process` batches (`scripts/load/run_harness.py`) |
| Storage | Compose PostgreSQL 16 + Redis 7 (host Postgres on :5432 already taken; app used Compose **5433**) |
| Env | `COLOR_RUSH_ENV=simulation`; production refused |

## Master targets

| Target | Status this environment | Command |
| --- | --- | --- |
| 1,000 commands/sec for 10 minutes, p95 durable processing ≤500 ms | **Not met / not run at full duration.** Burst already peaked at ~225 cmd/s on this laptop, so a 10-minute 1k/s run would not hit the target. | `uv run python scripts/load/run_harness.py --profile sustained` |
| 5,000 commands/sec burst for 10 seconds | **Ran; target not met.** 2268 commands in 10.09 s → **224.7 cmd/s**, batch p95 **1239 ms** | `--profile burst` |
| 100,000 unique-player round, settlement ≤10 s | **Not run.** 2 000-player unique round already settled in **40.7 s**; 100k would exceed the laptop budget and the 10 s settlement target. | `--profile unique --players 100000` |

## What did run

Subset (`200/s` for 15 s):

| Metric | Value |
| --- | --- |
| sent | 2385 |
| elapsed | 15.25 s |
| achieved | **156.4 cmd/s** |
| batch p95 | **363 ms** |
| batches | 45 |

Burst (`5000/s` for 10 s):

| Metric | Value |
| --- | --- |
| sent | 2268 |
| elapsed | 10.09 s |
| achieved | **224.7 cmd/s** |
| batch p95 | **1239 ms** |
| batches | 9 |

Unique round (`--players 2000`):

| Metric | Value |
| --- | --- |
| picks / ledger | 2000 / 2000 |
| reconcile | `ok: true`, no mismatches |
| ingest | 20.78 s |
| drain | **0.03 s** (≤5 s target) |
| settle | **40.74 s** (≤10 s target is for 100k; missed even at 2k) |

Additional verification this session:

- pytest **118 passed**, 1 skipped (`test_operator_smoke_against_running_api` — API not running)
- Overlay Vitest **10 passed**; Playwright **6 passed** (one gold-result screenshot flaked once, passed on retry); `npm run build` ok
- Ruff + mypy: clean (105 source files)
- Secret scan: clean
- `uv run python -m color_rush.demo` passed (gold result, four-scope scores)

Do **not** claim 100k-viewer support from watcher counts or an in-memory path.

Measured internal pipeline capacity on this laptop: about **150–225 durable commands/sec** through `append_and_process` on Compose PostgreSQL. Bottleneck is the serialized ingest/control SQL boundary on this hardware, not YouTube.

## Distinctions

- Internal injection through application services ≠ YouTube `streamList` quota or latency.
- Overlay snapshot budget remains ≤32 KiB and ≤4 Hz; not re-measured under the burst/unique loads above.
