# V4 architecture and regression workflow

The bot/radio runtime, bridge, SQLite storage and Flask/Dash dashboard remain one
application. Radio operations flow through the existing authenticated management
bridge; the Analyzer integration never imports the radio runtime or dispatches a
bridge command.

Dashboard layout is defined in `web/layout.py`. Native details disclosures keep
collapsed panels light. Managed repeater selection is shared by JavaScript events.
Statistics live in their own optimizer subsection; passive Optimization Analysis
uses the existing optimizer document and authenticated parent message bridge.
Protected operations retain admin checks, manual confirmation, compare-before-write
and readback verification. The external subsection is independent of admin login.

`analyzer.py` implements fixed URLs, key validation, transport limits, response
validation, persistent snapshots, conditional requests, a five-minute cache,
per-process single-flight protection and failure cooldowns. `web/analyzer_api.py`
exposes only local-dashboard reads behind the existing same-origin control policy.
`network_monitoring.js` handles cache-first rendering, manual refresh, cancellation,
selection races, evidence labeling, tables/charts and lazy maps. No timer or worker
polls the Analyzer. `optimization_analysis.js` loads its iframe only when open.

Storage remains backward compatible. The new Analyzer cache is a separate SQLite
file with idempotent schema creation. Existing V3 migrations remain covered by
regressions for command paths, room history, telemetry and report settings. Snapshots
are replaced atomically, avoiding double-counting rolling data. Failures never
replace a successful snapshot with empty values.

## Verification

Install `requirements.txt` plus pytest in a clean Python 3.12 environment and jsdom
for Node. Run `python -m pytest -q`, then every `tests/*.cjs`, and
`python -m scripts.check_install`. CI runs the full suite on `v4.0.0` and `main`.
The offline installation smoke check validates imports, fresh database creation,
registered routes and HTTP startup; it does not simulate apt/systemd or a radio.

Tests retain the existing protocol, permissions, telemetry, reporting, routes,
700/703/1,000/2,000 marker and migration regressions. V4 adds real captured Analyzer
formats, null/empty data, HTTP/timeout/malformed faults, cache/restart/conditional
reads, single-flight, activation-free access and cross-repeater race coverage. UI tests
exercise the actual JavaScript under jsdom, including resize/theme messaging and
responsive CSS isolation. They do not verify rendered Chromium or physical mobile devices. Do not describe those as hardware/browser validation.

Do not delete old tests solely to get a pass. Update assertions when V4 intentionally
changes layout, retaining their behavior coverage. Test fixtures remain test-only.

The three views reuse `repeater_statistics.css`. Analysis-specific CSS contains
structural layout only. Its same-origin iframe sends measured content heights;
the parent validates origin, frame identity and finite bounded dimensions before
resizing. Parent theme variables are sent through the same authenticated-origin
message boundary. A ResizeObserver handles data changes and narrow viewports.
The external client has no application enable/disable gate; the local optimizer's
separate storage/collection switch and administrator controls are unchanged.
