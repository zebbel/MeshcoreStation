# Repeater Statistics performance fix — 5.2.1

Measured on 3 November 2026. Published base: V5 **5.2.0**, commit `e4790f2`.
Included in the authorized V5 **5.2.1** prerelease; publication requires the
regression, scale, fresh-install and Chromium validation gate.

## Findings and confidence

The browser used one 10-second timer for sequential status and statistics requests.
Status latency therefore consumed the chart budget. A deterministic browser-script
test reproduces this: a 3-second status request followed by an 8-second view should
succeed, but the former shared deadline expires before the response arrives.

The old backend performed four repeated confirmed-observation scans, plus a count
scan and a neighbor scan. With 512 varied routes and a 256-entry route cache,
profiling 2,292 observations showed **8,532 selected-route parse/resolution calls**
across the repeated confirmed queries, and 566,265 Python calls overall. Its
neighbor query repeatedly expanded JSON, resolved hashes and formed temporary sets.
COUNT(DISTINCT) also had to work alongside repeated wide-row processing.

The original timestamp index is used correctly (EXPLAIN QUERY PLAN confirms a
range SEARCH). Adding another permanent source index would not fix the repeated
JSON/HMAC work. The synthetic old workload was CPU-bound: CPU time was almost
identical to wall time. At 100,000 observations, every period exceeded the existing
8-second SQLite budget. Generic HTTP 503 responses did not distinguish that case
from locking, damaged databases or unavailable storage.

**The exact field timeout at 2,292 rows was not reproduced on this workstation.**
That synthetic view already completed before the fix. The user's actual DB,
device CPU/storage and request logs were unavailable, so this report does not
assert which device-specific delay pushed that request past its deadline.

## Changes

- One indexed, read-only source scan in batches of 128, with bounded route reuse.
  The equivalent 2,292-row workload now parses at most 512 route templates.
- Exact distinct/repeated counting on narrow, disposable SQLite facts and edges.
  Scope classification runs once per eligible reception, with bounded reuse.
  Neighbor directions and per-reception edge deduplication remain intact.
- Disposable covering indexes for counts/edges. No observation schema migration,
  source index build, history rewrite, truncation or deletion during view reads.
- Eight-second backend budget retained, including Python classification stages;
  reads use short lock waits. Coverage merging is streamed instead of retaining
  and rescanning all coverage windows for every hour.
- Anonymous SQLite scratch files close on success or failure. Page cache is 2 MiB;
  route reuse is capped at 1,024 entries / 8 MiB estimated heap. Scratch work
  respects the collector's free-space reserve, including index-building headroom.
- One expensive view calculation per process. Overload returns HTTP 429 promptly;
  recording/status do not take this semaphore. A two-entry, 2-second application
  cache reuses unchanged results, invalidates on source/registry/settings changes,
  and rechecks managed membership even on hits. Empty WAL creation and read-time
  ctime-only WAL permission updates do not invalidate committed-data snapshots.
- Independent frontend budgets: **5 seconds for status**, then a fresh **10 seconds
  for statistics**. Status renders before aggregation completes. Loading is explicit;
  previous charts are faded and labeled as an older snapshot until replaced.
- Distinct browser timeout, server query timeout (504), database busy/error (503),
  storage failure (503) and calculation-busy (429) messages. No automatic retry,
  radio request or active polling is added.
- Stage diagnostics log timing, completion/failure and row counts only. No packet
  payload, scope key, route, repeater name or public key enters these diagnostics.

## Before / after

Synthetic data, isolated x86-64 container, Python 3.12.14, SQLite 3.53.1.
All observations are deliberately within 24h, so 7/30-day queries exercise the same
large row count rather than winning from sparse data. Counts, digests, timestamps,
registry entries and scopes are identical between implementations. Fixture creation
is excluded from wall/CPU timings. Filesystem cache state and shared-host load can
vary; these are not cold-SD-card or Raspberry Pi guarantees.

Baseline: one pass per size/period (two for 2,292). Optimized: median of two full
calculations per size/period; the API result cache is **not used** in this matrix.

| Saved observations | Filter | Before | After |
| --- | --- | --- | --- |
| 2,292 | 24h | 0.195s | 0.074s |
| 2,292 | 7d | 0.194s | 0.069s |
| 2,292 | 30d | 0.188s | 0.070s |
| 2,500 | 24h | 0.257s | 0.077s |
| 2,500 | 7d | 0.248s | 0.076s |
| 2,500 | 30d | 0.253s | 0.089s |
| 10,000 | 24h | 1.031s | 0.309s |
| 10,000 | 7d | 0.826s | 0.287s |
| 10,000 | 30d | 0.728s | 0.307s |
| 50,000 | 24h | 5.964s | 1.506s |
| 50,000 | 7d | 5.461s | 1.794s |
| 50,000 | 30d | 5.699s | 1.606s |
| 100,000 | 24h | Timeout (~8s) | 4.468s |
| 100,000 | 7d | Timeout (~8s) | 3.444s |
| 100,000 | 30d | Timeout (~8s) | 3.491s |

The two final 100,000-row/24h calculations were 4.481s and 4.455s;
CPU times were 4.414s and 4.408s. Repeated larger-period calculations
also stayed below the unchanged budget. Process peak RSS plateaued at about
40.7 MiB from 10,000 through 100,000 rows, including fixture generation and
Python/SQLite overhead; this is a process high-water mark, not per-query allocation.
Unchanged repeat requests perform one calculation followed by cache hits in the
functional cache test; a new saved observation forces a new result immediately.

Representative 100,000-row / 24h stage measurements:

| Stage | Elapsed |
| --- | --- |
| metadata | 6.4 ms |
| classify | 3569.0 ms |
| indexes | 356.0 ms |
| totals | 25.9 ms |
| hourly | 129.6 ms |
| hops | 153.6 ms |
| regions | 178.8 ms |
| neighbors | 55.0 ms |
| coverage | 0.0 ms |
| render_series | 0.1 ms |

Detailed measured records: [statistics-performance-results.json](statistics-performance-results.json).

## Verification

- Full Python suite: **208 passed**, including the 2,500/10,000/50,000/100,000
  matrix over all three periods and the 2,292-row acceptance workload.
- JavaScript suites: **18 passed**, including independent virtual-time deadlines,
  immediate status display, typed failures, stale marking and request cancellation.
- Baseline/optimized comparison on 2,500 varied observations: all hourly/ranking
  counts, neighbor directions, ambiguous connections and coverage match exactly
  (ignoring new diagnostics and candidate-count metadata).
- Real Leaflet JavaScript tests preserve colors, arrows, popups, missing-coordinate
  lists, ambiguous relationships, tile-failure overlays, resizing and cleanup.
- Actual collector WAL writes commit while a 100,000-row aggregation is active;
  16 queued passive observations are saved with no collector error/drop.
- Concurrent expensive requests return promptly while recording status returns 200.
- Repeated requests reuse one result, write invalidation works, and unmanaged keys
  cannot use cached views. Source observation count, IDs and recorded timestamps
  remain unchanged by aggregation. Low-space failure preserves source history.
- Fresh-install smoke and diff whitespace checks pass. The existing desktop/light
  and mobile/dark Chromium checks are mandatory before release publication.
  Physical RF and the user device/database remain unverified.

Reproduce with `PYTHONPATH=. python scripts/benchmark_statistics.py --output
/tmp/statistics-after.json`. The script supports `--module /tmp/baseline_view.py`
for a saved copy of the v5.2.0 module, plus `--sizes`, `--periods`, `--repeats` and
`--profile`. It creates synthetic temporary stores only and sends no RF.

## Changed files

- `meshcorestation/storage/statistics_view.py` — single-pass classification,
  compact SQL aggregation, query budget, diagnostics and storage guard.
- `meshcorestation/web/statistics_service.py` — bounded calculation/cache service.
- `meshcorestation/web/statistics_api.py` — typed HTTP failures.
- `meshcorestation/web/assets/repeater_statistics.js` — independent requests,
  immediate status and errors; `statistics_visuals.js` — stale snapshots.
- `meshcorestation/web/layout.py`, `web/assets/zzzzz_v5.css` — progress/error UI.
- `scripts/benchmark_statistics.py`, `tests/test_statistics_performance.py`,
  `tests/test_statistics_requests_ui.cjs` — scale, concurrency and timing coverage.
- Relevant README/V5 documentation and this measured report.
