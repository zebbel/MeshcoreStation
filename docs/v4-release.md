# MeshcoreStation 4.3.1 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.3.1` (prerelease, not latest stable). V3 main is unchanged.

Added Neighbor Communication Map directly after Performance's Network Connectivity
chart. It reuses the saved Analyzer reach snapshot and shared Leaflet loader,
repeater names, dashboard styles and direction/confidence interpretation.

- Blue selected repeater; geographical neighbor markers; green two-way, red
  one-way, gray insufficient/conflicting evidence. One-way counts are derived
  from actual directional observations, not subtraction.
- Dashed low-confidence links are hidden initially, with a checkbox to show them.
  Markers/statistics still include those neighbors. Unknown confidence is dotted.
- Neighbor popups contain names, distances, directional counts, confidence and
  public-key details. Unlocated neighbors remain in a list below the map.
- Explicit saved 24-hour window/timestamp: longer Performance periods cannot
  reconstruct historical neighbor maps. Relationships are inferred, not verified
  direct radio links. Unavailable snapshots do not become zero activity.

Existing overview, four line charts, traffic comparisons, assessment, journal,
technical statistics, automatic collection, cache and radio/security protections
remain intact. No additional Analyzer refresh, polling or radio traffic is added.

Validation is intentionally targeted: Performance/API and new map unit tests,
shared direction/confidence checks, installation smoke check, and two real Chromium
cases (desktop light/mobile dark) covering vector lines, markers/popups, filtering,
missing coordinates, zoom/pan, resize/reopen and repeater switching. No extended
regression matrix is required for this isolated change. Other CI changes retain
full checks unless this exact release and the reviewed file scope match.
