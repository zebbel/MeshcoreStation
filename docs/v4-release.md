# MeshcoreStation 4.0.2 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.0.2` (prerelease, not latest stable). V3 main is unchanged.

- Reusable full-key name resolution across selectors, telemetry, statistics,
  analysis, packet patterns and map popups. Known/managed records, existing cached
  information and Analyzer names are reused without individual network lookups.
  Full keys stay in tooltips/details; duplicate names have distinguishing suffixes.
  Unknown keys get safe labels and unresolved prefixes are never guessed.
- Matching expanded-content wrappers for all three optimizer subsections, with
  one desktop/mobile gutter and no fixed-height nested analysis scrollbar.
- Relationship maps use image-free selected/neighbor markers and outlined dashed
  links supported by coordinate/directional evidence. Chart SVG selectors no longer
  affect Leaflet overlays. Resize, cleanup/reopen and tile-failure handling remain
  separate from the on-demand request/cache lifecycle.

Internal identifiers, route order, counts and timestamps are preserved. No schema
or dependency changes are required. Authentication, confirmations, readback, the
local optimizer switch and all radio safeguards are unchanged. Network Monitoring
retains its five-minute cache, manual refresh, timeout/403/429 handling and absence
of background polling; no activation gate or additional radio traffic is added.

Validation includes the full Python/JavaScript suite plus real bundled Leaflet SVG
DOM tests. The release workflow additionally runs real Chromium at desktop/mobile
sizes in light/dark themes, checks projected SVG geometry and marker DOM, exercises
zoom/pan/resize/reopen/switching, and captures screenshots before release approval.
484 Python tests and all 34 JavaScript suites passed. Real Chromium passed all
four viewport/theme cases (1280px desktop and 390px mobile, light and dark).
Rendered screenshots were inspected for marker/link visibility, shared gutters,
responsive forms/cards and absence of nested analysis scrollbars. Initial map
fitting is non-animated so overlays are not temporarily scaled on first display.
Captured ISO path/history timestamps now use the existing shared date formatter
without changing their values or timezone conversion.

Live Analyzer access and physical radio/mobile hardware remain unverified. Browser
checks use captured fixtures and simulated tile outages; they establish rendering
behavior, not provider permission or present network coverage.
