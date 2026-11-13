# MeshcoreStation 6.0.4 — Repeater Comparison Timeout and Checkpoint Fix

The dashboard now waits up to 15 seconds per comparison request. It reports
browser, worker, and calculation timeouts separately and keeps the last
successful comparison visible. The calculation budget is still eight seconds,
and the worker limit is still nine seconds.

Classification leaves more time to save progress based on batch size and
processing time. Resumed runs save newly classified rows and the continuation
position in one SQLite transaction. The dashboard continues up to five times
when the server confirms it saved progress. A failed checkpoint save leaves the
previous checkpoint available.

The disposable classification cache is capped at 64 MiB. Source history and
passive recording are unaffected.
