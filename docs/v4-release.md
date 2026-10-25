# MeshcoreStation 4.3.2 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.3.2` (prerelease, not latest stable). V3 main is unchanged.

- Refresh saved data in Repeater Performance now explicitly requests fresh Analyzer
  measurements through the existing manual Refresh Now client. Success saves the
  shared cache/history and updates cards, charts and the Neighbor Communication
  Map. Progress disables duplicate button clicks. Failed requests retain saved
  values and display meaningful errors, including HTTP 403 and rate limits.
- Ordinary opening, period changes and journal reads stay local. The five-minute
  cache for normal reads, explicit manual-refresh behavior, request timeouts,
  single-flight lock and persisted provider cooldowns remain intact. No polling,
  radio commands or access-control bypass is introduced.
- Low-confidence filtering now removes markers as well as lines, and hides related
  unlocated-neighbor entries. Checking restores them immediately without fetching
  Analyzer data. Snapshot statistics continue to describe all reported neighbors.
- Preserved the working native Leaflet drag check: it waits for zoom readiness,
  picks clear map background outside popups/controls/markers, and verifies both a
  real drag event and changed map center. Refresh/reopen tests wait for their
  request and render completion instead of relying on timing or workflow retries.

Targeted validation covers successful refresh persistence, five-minute cached
reads versus explicit refresh, HTTP failures/timeouts/malformed data, cooldowns,
retained values, refresh progress/duplicate-click prevention, immediate filtering
and existing Performance/journal behavior. Existing essential browser validation
remains enabled for desktop light/mobile dark; unrelated workflows are unchanged.
