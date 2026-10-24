# MeshcoreStation 4.3.0 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.3.0` (prerelease, not latest stable). V3 main is unchanged.

- Rebuilt Repeater Performance in the requested reading order: four numerical
  Mesh Contribution cards; Forwarding Activity; Repeater vs. Mesh Activity;
  Network Connectivity; Routing Contribution; Performance Assessment;
  Performance Changes; and expandable Detailed Statistics.
- Cards explicitly use the latest rolling 24-hour Analyzer window, including
  bidirectional/neighbor counts and percentage, pairs served and sole-observed
  route pairs. A nullable historical sole-pair field preserves older records.
- Four visible line charts preserve source timestamps and gaps. The indexed
  two-line comparison uses matching Companion observations and starts at 100;
  Analyzer and Companion traffic are never divided or added together. Pair and
  neighbor axes use integers. Legends, hover/raw values and explanations cover
  observed peaks, traffic context, inferred relationships and limitations.
- Added coverage-aware assessments of all four domains and a combined explanation.
  Missing observations, incomplete periods and unsupported baselines show
  Insufficient Data. Increased activity is not labeled a delivery improvement.
- Kept manual/verified markers, journal CRUD and equal 24h/3d/7d comparisons;
  before/after analysis now includes four line charts with vertical change markers,
  a source-aware assessment, overlap warnings and expandable technical values.

Automatic 12-hour collection, hourly deduplication, five-minute caching, Refresh
Now, retention, existing data, administrator protections and radio safety remain.
No additional radio traffic or individual data-lookup requests are introduced.
No performance score, delivery-success percentage or repeater ranking is added.

Limits: source access/connectivity are still required; missing historical sole-pair
values cannot be invented. Comparable Companion history needs the existing
network-wide observation stream. Sample coverage does not certify receiver uptime.
Alternative routes may exist beyond Analyzer observations. Activity and inferred
relationships do not prove delivery, direct RF links or causation.

Validation includes stored-value/card/chart checks, same-stream normalization,
ambiguous hashes, missing/partial/zero baselines, retention warnings, exact marker
boundaries, journal persistence, repeater switching and the existing 60-hour
collection simulation. Complete Python/JavaScript and real Chromium desktop/mobile
light/dark regression checks and screenshot inspection gate publication.

Validated: 531 Python tests and all 36 JavaScript suites passed. Real Chromium
verified the complete eight-part layout on desktop (1280px) and mobile (390px),
light/dark themes, numerical card values, four visible line charts, real SVG gaps
and markers, normalization, integer axes, period switching, responsive sizing,
journal CRUD/reload and before/after comparisons. Existing map/iframe regressions
passed and screenshots were inspected.
