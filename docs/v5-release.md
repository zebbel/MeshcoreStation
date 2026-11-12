# MeshcoreStation 5.9.1 — Statistics and Command History Performance

- Repeater Statistics reuses saved packet classifications across overlapping time windows. New receptions are classified separately, and registry or scope changes invalidate affected results.
- Large classification scans can save progress for the next refresh. The eight-second query budget remains in place.
- Bot Command History reads display preferences once per refresh and skips rebuilding the table when its content is unchanged.
- Existing observations, traffic counts, and recording behavior are preserved.

In a single-core benchmark, a seven-day view with 70,000 receptions loaded in 5.40 seconds with an empty cache and 1.29 seconds with reuse. A cold 30-day view can still time out. See the [performance verification report](v5-performance-verification.md) for measurements and limitations.
