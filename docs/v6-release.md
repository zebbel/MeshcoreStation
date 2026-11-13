# MeshcoreStation 6.0.2 — Repeater Comparison Fix

- Repeater Statistic Comparison clears its loading state on success, failure, timeout, or cancellation. Previous results remain visible until a new comparison succeeds.
- Comparison classifies the combined before-and-after span once. Each half still has independent counts, SNR, neighbor relationships, and recording coverage. A repeated comparison can reuse the bounded classification cache.
- The eight-second server budget is unchanged. If classification saves progress before a timeout, the dashboard explains how to resume.

Single-core timings on a synthetic 100,000-observation history, measured against V6.0.1:

| Period | V6.0.1 cold / repeat | V6.0.2 cold / repeat |
| --- | ---: | ---: |
| 24 hours | 0.66 / 0.54 s | 0.44 / 0.09 s |
| 7 days | 2.24 / 2.19 s | 1.70 / 0.37 s |
| 30 days | 2.48 / 2.27 s | 1.72 / 0.41 s |

All repeat runs for V6.0.2 classified zero rows on this fixture. Live hardware and production databases were outside the benchmark.
