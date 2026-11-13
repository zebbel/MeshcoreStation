# MeshcoreStation 6.0.3 — Resumable Repeater Comparisons

Seven-day and thirty-day Repeater Statistic Comparisons can continue after a
worker reaches its eight-second budget. The dashboard continues up to five
times when the server confirms it saved progress. If it cannot continue, it
shows an error and keeps the last successful result visible.

The disposable 64 MiB classification cache stores the continuation position
and the source snapshot's ID limit. Sparse scans resume by timestamp and ID.
Dense scans resume by ID. Later appends are scanned separately so backdated
packets are included. Source edits and relevant configuration changes invalidate
cached progress. The source observation database remains read-only.
