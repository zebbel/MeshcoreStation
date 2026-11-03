# MeshcoreStation 5.2.1 — Repeater Statistics Performance Fix

Fixes redundant aggregation work and separates recording-status and statistics
request deadlines. One indexed source scan classifies saved observations into
compact disposable SQL facts, reusing route decoding and exact distinct counts.
The backend's 8-second limit is unchanged; original history is never rewritten,
truncated or deleted by the view.

Recording status appears immediately, with its own 5-second browser budget.
Saved statistics receive a fresh 10-second budget. Loading/stale snapshots and
browser timeout, server query timeout, database/storage errors and overload are
clearly distinguished. Bounded calculation concurrency and a small invalidated
cache protect status responsiveness; passive WAL writes continue independently.

Synthetic 24-hour measurements on the development workstation:

| Observations | Before | After |
| --- | --- | --- |
| 2,292 | 0.195s | 0.074s |
| 2,500 | 0.257s | 0.077s |
| 10,000 | 1.031s | 0.309s |
| 50,000 | 5.964s | 1.506s |
| 100,000 | 8s timeout | 4.468s |

All 24-hour, 7-day and 30-day scale cases pass. These are synthetic container
measurements, not guarantees for the user's device. The exact field timeout at
2,292 observations was not reproduced without the original database/hardware.
Per-stage timings log no sensitive packet contents.

Validation: 208 Python tests, 18 JavaScript suites, scale/concurrency tests,
isolated fresh-install smoke and the mandatory existing Chromium desktop/light
and mobile/dark release gate. Directional neighbors, missing coordinates,
ambiguity, message counts, hop/scope rankings and coverage gaps are preserved.
No new radio requests, active polling or automatic data deletion are introduced.

See [the full performance report](https://github.com/zebbel/MeshcoreStation/blob/v5.2.1/docs/v5-statistics-performance.md).

V5 remains a prerelease. Live RF operation and user-device performance are
unverified. V3 main and V4 v4.0.0 are unchanged. No deployment is performed.
