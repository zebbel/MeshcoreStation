# Statistics service-context timeout — 5.2.2

Base: published V5 5.2.1. Included in the authorized 5.2.2 follow-up; publication
is gated on the existing regression, scale, fresh-install and Chromium checks.

## Field evidence

The user ran both synthetic and actual-data diagnostics on the affected aarch64,
four-CPU device. The synthetic 2,292-row case completed in 0.8532 seconds. The
actual 24-hour view, with 2,517 saved observations, completed in 0.8568 seconds
outside the running web service; classification took 677.975 ms. Actual data had
842 known identities, four saved scope keys, 1,647 parsed routes, mean route JSON
length 1,221 bytes and maximum 5,168 bytes. None of those runs timed out. The HTTP
view still reported the eight-second classify timeout.

This narrows the failure to service context. It does not identify which running
thread is responsible or exclude every possible device-specific I/O difference.

## Reproduced contention failure

A local 2,517-row test completed in 0.104 seconds without contention. With another
Python thread continuously busy in the same interpreter, the unchanged threaded
calculation failed after 8.461 seconds during classify. SQLite's frequent GIL
release/reacquisition in the thread-based path exposes it to large scheduling
penalties even when the query is fast in a separate CLI process.

Using the new isolated worker, two runs of the same contention case completed in
0.204 and 0.173 seconds (including process startup and IPC). This is a workstation
reproducer, not a claim that the correction has already been verified on the user
device or that a particular radio thread has been identified as the cause.

## Correction

The existing calculation executes in a fresh, read-only Python interpreter.
Only one expensive request can launch a worker at a time; the short unchanged-data
cache and request backpressure remain. The worker imports the storage/view code,
not Companion, Runtime or MeshCore radio code. stdin is closed and unrelated file
descriptors are not inherited. It makes no serial or network requests.

The core calculation keeps its eight-second budget. The parent bounds worker
startup/calculation/result handling to nine seconds and reaps the child after a
parent timeout. The browser still has separate five-second recording-status and
ten-second view budgets. WebServer shutdown terminates/reaps an active worker;
restart permits a fresh worker. No persistent extra database, schema rewrite,
history deletion or migration is introduced. Anonymous query scratch is removed
when the calculation ends.

Result size is capped at 8 MiB. The worker exits after each calculation, so query
memory is reclaimed instead of accumulating. There is one additional interpreter
only while a saved view is calculated; recording/status remain in the application
process. Worker CPU, RSS and roundtrip timings are returned as numeric diagnostics.
Original observations, current-registry ambiguity checks, regional matching,
coverage and all chart semantics use the existing aggregation implementation.

Failure summaries now use WARNING instead of being hidden by the application's
default WARNING log threshold. Query timeouts carry safe row counts and stage,
elapsed and CPU timings. No packet payload, route, name or scope key is logged.

## Verification

Focused checks cover same-interpreter contention, worker import isolation, parent
timeout/reaping, shutdown, damaged-database handling, exact source preservation,
cache behavior and concurrent passive writes. The 100,000-row worker case runs
all three filters and confirms 16 passive observations commit while the worker is
still calculating. The existing directional-map, chart and coverage regressions
remain applicable. Physical RF operation and the user-device fix remain unverified
until the updated service is tested there.

`scripts/diagnose_statistics.py` is a standalone actual-data profiler compatible
with published 5.2.1. It reads observations without modifying them, reads the data
path as data from meshcorestation.env, reports counts/timing only, and restores its
process-local instrumentation on failure. If several repeaters are managed it
requires an explicit numbered selection. It sends no radio/network requests.

Validation: 218 Python tests, including worker contention/lifecycle, all three
large-data periods and simultaneous passive recording; 18 JavaScript suites and
fresh-install smoke. Actual browser validation is required by the release gate.
