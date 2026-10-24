# MeshcoreStation 4.2.1 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.2.1` (prerelease, not latest stable). V3 main is unchanged.

- Corrected the detailed graph display to preserve small nonzero betweenness
  values and updated chart help to match the original hourly series.
- Added unattended Analyzer collection every 12 hours for managed repeaters.
  Durable schedules, crash leases, one-minute repeater spacing and global provider
  cooldowns handle restarts and connectivity failures without a catch-up burst.
  No new mesh radio traffic is generated. Existing five-minute caching and manual
  Network Monitoring refresh remain available; browsers do not poll.
- Preserved original complete hourly relay buckets, deduplicated by repeater and
  UTC timestamp. Overlapping responses replace corrections rather than adding
  rolling totals. Compact snapshot history includes neighbor/bidirectional counts,
  graph metrics, reported communication pairs and returned route-pattern counts.
- Simplified Performance Overview to activity, connectivity, contribution and trend
  with explicit history coverage and collection status. Technical measurements,
  history charts and the unchanged journal are separately expandable. Sources
  remain separate, missing hours break chart lines, and neighbor axes are integers.
- Preserved manual/verified change markers and equal 24h/3d/7d comparisons. Original
  hourly buckets are preferred; missing hourly evidence withholds relay percentage
  comparisons and trend assessments. Network traffic context and missing/partial
  coverage warnings prevent interpreting activity differences as proven improvement.

The existing performance database gains additive tables; existing records and
other databases remain compatible. Measurement tables retain up to 400 days and
250,000 rows each across managed repeaters. Permanent markers are not aged out.
Existing administrator controls, explicit confirmations/readback, maps, names,
telemetry, Room Server and unrelated experimental optimization features remain.

Limits: station service/connectivity/provider access are required. Provider history
cannot recover older missing data after extended outages. Relationships are
inferred; activity changes, graph metrics and communication-pair counts do not
prove direct radio links, successful delivery or causation. Historical Companion
uptime is unknown. Screenshots/tests use captured formats and synthetic local
history, not a new verification of external API access or RF performance.

Validation: full Python and JavaScript regression suites; simulated unattended
collection across 60 hours with process restarts, overlapping hourly history,
retention, errors/cooldowns and crash leases; real Chromium desktop/mobile in both
themes, charts/gaps/marker geometry, local journal CRUD/reload, comparisons, resizing,
shared selection and existing map/iframe regressions. See release report for counts.

Validated: 514 Python tests and all 36 JavaScript suites passed. Real Chromium
checks cover desktop (1280px) and mobile (390px), light/dark themes, rendered gaps
and integer neighbor axes, overview/detail disclosures, persistent journal CRUD,
marker comparisons, resizing and shared-repeater switching. Existing network-map
and Optimization Analysis iframe regressions passed; screenshots were inspected.
