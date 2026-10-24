# MeshcoreStation 4.1.0 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.1.0` (prerelease, not latest stable). V3 main is unchanged.

- Added Repeater Performance above Statistics, sharing selection, dashboard styling,
  lazy loading and independently collapsible behavior. Four observed-contribution
  indicators and 24h/7d/30d charts keep Companion, optimizer and analyzer evidence
  separate, with readable names and explicit gaps rather than performance scores.
- Added a permanent per-repeater local change journal with manual timestamps,
  edit/delete controls, verified-configuration markers, chart lines and accessible
  comparison controls. Annotation writes never send radio/configuration commands.
- Added equal 24h/3d/7d before/after windows (7d default), measured values, percentage
  differences, plain-English interpretation and warnings for missing/partial data,
  overlapping changes, source differences and unknown historical collector uptime.
- Successful analyzer refreshes archive bounded 15-minute measurements separately
  from the five-minute cache. Rolling windows are never added; before/after means
  use contained non-overlapping hourly samples. Existing errors, cooldowns, last
  successful snapshots and no-background-polling behavior remain intact.

The additive repeater-performance.db file leaves existing databases compatible.
Measurements retain up to 400 days and 250,000 shared rows; markers are not aged out.
Removing a managed repeater explicitly removes its journal and measurements.
Optimizer resets retain the separate journal/archive. Administrator authorization,
confirmation/readback protections and unrelated experimental optimization features
are preserved. Correlation is not proof of causation or successful radio delivery.

Validation covers historical storage, retention, cache deduplication, source
separation, verified-marker hooks/backfill, CRUD/tombstones, timestamps, comparisons,
missing data, switching/races and local API protections. Full Python/JavaScript
regression plus Chromium desktop/mobile light/dark visual checks precede publication.
Browser tests use captured analyzer formats and synthetic local historical records;
they cannot establish historical coverage or physical radio delivery success.
