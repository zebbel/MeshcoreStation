# MeshcoreStation 4.0.4 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.0.4` (prerelease, not latest stable). V3 main is unchanged.

Observable Relationships independently encodes direction and analyzer confidence:
green for bidirectional observations, red for one observed direction, gray for
unknown direction; solid for medium/high confidence, dashed for low confidence,
and explicitly dotted for missing/unknown confidence. Incomplete or contradictory
direction fields stay neutral. Missing observations do not prove impossibility.

An English legend with line samples sits above the canvas without covering map
controls. Line popups show named endpoints, observed direction, original counts,
analyzer confidence, distance and expandable public keys. Theme colors, outlined
strokes, responsive popups and image-free markers remain legible on small screens.
Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.

Interface labels, status/error messages, help and configuration interfaces were
reviewed for English. Proper names, repeater names and external/user text remain
unchanged. Existing name resolution, route order/counts/timestamps, administrator
controls, radio safeguards, five-minute caching, on-demand loading, manual refresh
and no-background-polling behavior are preserved. No database migration or new
application dependency is required; the map uses the existing snapshot.

Validation: full Python and JavaScript regression suites, actual bundled Leaflet
SVG geometry/popups, and real Chromium desktop/mobile light/dark checks. Captured
fixtures cover realistic relationships; derived cases exercise missing/conflicting
direction fields and all color/confidence combinations. Browser screenshots are
reviewed before publication.

Live Analyzer access and physical radio hardware remain unverified. Fixture/browser
tests establish UI behavior, not provider permission or verified direct RF links.
