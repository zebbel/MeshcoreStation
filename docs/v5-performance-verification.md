# V5.9.1 performance verification

The baseline is V5.9.0 at revision `d7e159c`. The performance changes are included in V5.9.1.

## Repeater Statistics

Every saved view previously reread, decoded and classified its source observations, then rebuilt temporary facts and edges. The seven-day profile spent most of its budget reading source rows, decoding routes and matching region scope keys. Those costs recurred whenever fresh recording invalidated the short-lived response cache.

The worker now stores compact classifications for one repeater and up to 30 days in a disposable SQLite file capped at 64 MiB. It reuses overlapping classifications, classifies new receptions separately and reaggregates the exact selected window. The source snapshot tracks append progress and invalidates reuse after history edits, deletions, replacement, registry key changes or scope configuration changes. Display names and coordinates are loaded live. The current and previous neighbor and route rules, packet digests, reception ordering, and period-specific counts continue to drive the result. Legacy histories get classification tracking on the next passive write.

The cold path uses sequential reads for dense ranges, indexed reads for sparse ranges, smaller source projections, less route traversal and reused HMAC prefixes. The eight-second query budget and isolated statistics worker are preserved. Passive recording can commit concurrently. For large scans ordered by observation ID, the worker can save a finished prefix near the deadline. The next request resumes from that prefix and the first request returns a timeout, with no partial result reported as a complete view.

### Profile

Synthetic 100,000-reception fixture on one pinned Xeon core. The fixture spans 30 days, uses a mixture of scoped, unscoped and excluded evidence, eight scope keys, and intentionally varied route JSON. The same source and `scripts/diagnose_statistics.py` instrumentation were used in each case. Wall time includes the query and diagnostic instrumentation. Peak RSS is the process high-water mark during the profile series.

| Period | Rows | Baseline wall / CPU | Empty classification cache wall / CPU | Reused classifications wall / CPU | Baseline / empty / reused classification |
| --- | ---: | ---: | ---: | ---: | ---: |
| 24 hours | 12,000 | 1.37 / 1.33 s | 0.90 / 0.89 s | 0.15 / 0.15 s | 1.17 / 0.75 / 0.02 s |
| 7 days | 70,000 | 8.01 / 7.80 s, timeout | 5.40 / 5.34 s | 1.29 / 1.27 s | ~8.00 / 4.34 / 0.12 s |
| 30 days | 100,000 | 8.02 / 7.87 s, timeout | 8.01 / 7.87 s, timeout | 1.88 / 1.86 s | ~7.99 / 7.07 / 0.17 s |

An earlier baseline seven-day run completed in 6.25 s, with 5.04 s in classification. The 30-day empty-cache run finished classification before it timed out in aggregation. Reused runs fetched no raw observations for classification and parsed no routes. Peak RSS for the baseline series was about 26.4 MiB, versus about 29.5 MiB with caching. The cache occupied 19.9 MiB for seven days and 28.4 MiB for 30 days in this fixture.

A second process competing for the same core brought the reused seven-day view to 2.69 s. With one new reception it completed in 2.90 s and classified one row. The cold seven-day query reported saved progress after 56,320 rows and the retry completed in 5.01 s, classifying the remaining 13,681 rows. The reused 30-day view completed in 4.91 s under the same contention.

To profile a local history, use `python -m scripts.diagnose_statistics --days 7`. Repeat with `--reuse-classification` to exercise the disposable classification cache. The diagnostic reports counts and timings. It omits packet payloads, routes and scope keys.

## Bot Command History

The history refresh formatted timestamps through a preference lookup that opened SQLite and attached the repeater registry on every call. It also loaded the full history window every five seconds and sent the rows back inside its change-detection signature.

History now uses one read-only transaction for preferences, a compact revision token and, when required, the requested history window. An unchanged refresh reads the revision and preferences only and skips the history rows, serialization and DOM updates. The five-second timer remains active while history is visible. Row ordering, filter and pagination behavior, details, replies and scroll anchoring use the existing interface.

The history figures below include callback and Dash serialization time. The 405-entry fixture loaded 400 rows to exercise pagination.

| Saved entries | Initial wall before → after | Initial SQLite connections before → after | Unchanged refresh wall before → after | Unchanged connections before → after |
| ---: | ---: | ---: | ---: | ---: |
| 55 | 195.25 → 14.92 ms | 223 → 1 | 6.67 → 0.63 ms | 3 → 1 |
| 200 | 668.92 → 43.41 ms | 803 → 1 | 6.92 → 1.07 ms | 3 → 1 |
| 405 | 1,250.29 → 106.83 ms | 1,603 → 1 | 18.34 → 1.79 ms | 3 → 1 |

For 55 entries initial CPU time fell from 195.22 to 14.82 ms. The initial serialized callback dropped from 134,378 to 89,561 bytes. On unchanged refresh the Dash callback omits all eight outputs.

## Files

- Statistics classification, storage and diagnostics in `meshcorestation/storage/statistics_classification.py`, `meshcorestation/storage/statistics_view.py`, `meshcorestation/storage/passive_stats.py`, `meshcorestation/web/statistics_api.py`, `meshcorestation/web/statistics_service.py`, `meshcorestation/web/statistics_worker.py` and `scripts/diagnose_statistics.py`.
- Command History revision, data reads and timestamp formatting in `meshcorestation/storage/database.py`, `meshcorestation/display.py`, `meshcorestation/web/data.py` and `meshcorestation/web/callbacks.py`.
- Regression coverage in `tests/test_statistics_performance.py`, `tests/test_statistics_visualization.py` and `tests/test_v5_foundation.py`.

## Validation and limitations

All 399 Python tests, 26 JavaScript test scripts and the fresh-install smoke check passed. Chromium passed the desktop light and mobile dark acceptance flows in separate launches. A focused Chromium check also verified the live five-second refresh, stable DOM and scroll position, and paused refresh when collapsed. The 100,001-row fixture returned the same saved-view fields as V5.9.0 for all three periods, including one appended repeated reception.

The regression suites cover statistics at 2,500, 10,000, 50,000 and 100,000 observations, concurrent WAL recording, cache invalidation and resumption, history paging and timestamp formats, Repeater Management, clock synchronization, Neighbor SNR and Read now, and telemetry. Timing was measured on synthetic data and simulated CPU contention. Raspberry Pi timings, physical repeaters and the reported production database were outside the available test setup. Cold 30-day views can still hit the original budget, especially under load.
