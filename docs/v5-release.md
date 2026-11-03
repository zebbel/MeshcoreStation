# MeshcoreStation 5.2.2 — Statistics Worker Isolation

Addresses a saved-view failure specific to the running service: the user's actual
2,517-row query completed in 0.8568 seconds in a separate CLI interpreter while
its HTTP calculation still timed out during classify.

A local busy-Python-thread reproduction makes the threaded view fail after
8.461 seconds. Running the same calculation in a fresh interpreter completes in
0.173–0.204 seconds under the modeled contention. This demonstrates a failure
mode consistent with the field report; the actual busy thread/device cause has
not been independently identified.

Saved-view calculation now uses one bounded read-only worker process, launched
only for an uncached calculation. It imports no Companion/radio runtime, inherits
no radio handles, sends no radio/network requests and exits after returning.
Recording, recording status and management remain in the main application.

The eight-second core query budget remains unchanged. The parent bounds worker
startup/execution to nine seconds; the browser retains separate status/view
budgets. Shutdown and parent timeout reap the child. Result size is bounded, and
safe CPU/RSS/roundtrip diagnostics and WARNING-level failure details are available.
Original histories, schemas, scope matching, ambiguity, counts, coverage and all
visualizations are preserved. No data migration or deletion is introduced.

Validation: 218 Python tests, 18 JavaScript suites, fresh-install smoke, and the
existing desktop/light and mobile/dark Chromium release gate. Tests cover thread
contention, child import isolation, termination/reaping, corrupted-file safety,
all three periods on 100,000 observations and recording during the calculation.

Includes a read-only actual-data diagnostic script. This remains a prerelease;
the corrected running service still needs confirmation on the user's device.
V3 main and V4 v4.0.0 remain unchanged. No deployment is performed automatically.
