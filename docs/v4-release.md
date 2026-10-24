# MeshcoreStation 4.0.5 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.0.5` (prerelease, not latest stable). V3 main is unchanged.

- Removed the Network Monitoring Experimental heading and outdated live-integration
  status following operator confirmation of working live monitoring. API metadata
  no longer labels monitoring experimental or supplies an obsolete verification flag.
- Matched Optimization Analysis to the rendered Repeater Statistics background.
  The iframe element, document root, body and main content now share that surface;
  palette and color-scheme synchronization covers light/dark changes and reopening.
  Content-based resizing, responsive geometry and existing spacing are preserved.
- Updated current README/help documentation. Experimental optimization suggestions,
  administrator authentication, confirmation/readback safeguards and configuration
  controls are unchanged.

Monitoring retains on-demand loading, five-minute caching, manual Refresh Now,
request validation/timeouts, rate limits, stale-data retention and normal API/access
errors. Relationships remain inferred observations rather than verified direct
radio links. No additional requests, polling or radio traffic are introduced.

Validation includes complete Python and JavaScript regression suites plus real
Chromium desktop/mobile light/dark checks, including live theme changes, parent
palette overrides, closed/reopened sections and iframe resizing. Screenshots are
reviewed before publication. Offline tests establish behavior rather than provider
permission or guaranteed availability on every installation.
