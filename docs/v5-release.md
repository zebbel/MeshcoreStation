# MeshcoreStation 5.2.0 — Repeater Statistics Visualization

Adds saved-data visualizations to the independent, managed-only Statistics view:

- Observed Neighbor Map with directional arrows, green two-way and red one-way
  observations, directional counts, timestamps, names and full keys in popups.
  Includes unmanaged neighbors and separate ambiguous/missing-coordinate lists.
- Messages per Hour with unique packets, repeated receptions and unidentified
  payloads. Unknown collection periods remain gaps instead of fabricated zeros.
- Hop Count Ranking using complete observed flood-route length.
- MeshCore Regional Traffic Ranking with configurable region names/keys, verified
  transport-code matching, Unknown and normally ranked Unscoped categories.

Shared 24-hour, 7-day and 30-day filters update all four views. SQLite aggregates
saved observations without exporting complete packet histories to the browser.
Views refresh on opening, filter changes and manual saved-view refresh; no active
radio polling or extra radio requests are introduced. Existing passive collection,
managed membership, history, Bot and Repeater Management remain intact.

Adds local recording-coverage windows and local region-attribution preferences.
Historical 5.1.0 observations without uptime evidence keep unknown coverage;
observed positive counts are lower bounds in incomplete periods. Existing V5
files and observations are preserved. No automatic deletion is introduced.

Validation: 198 Python tests, 17 JavaScript suites, isolated fresh-install smoke,
local HTTP fixture and a mandatory Chromium desktop/light and mobile/dark gate
including actual SVG map lines, link colors, popups, charts and period switching.

This remains a prerelease. Physical Companion/RF operation is unverified. Direct
routing instructions and TRACE data do not establish confirmed forwarding. Scope
and hash attribution can be ambiguous; two-way observations do not prove reliable
direct RF links or delivery. Basemap tile availability is external; markers and
vector overlays remain independent of tile loading.

V3 main and V4 v4.0.0 remain unchanged. Nothing is deployed automatically.
