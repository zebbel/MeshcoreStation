# MeshcoreStation 5.6.1 — Statistics Counting and Visualization Improvements

Hop Count Ranking now classifies the first confirmed reception of a packet
digest across the complete selected period as unique. Later confirmed copies are
repeated even when their hop counts differ, with each reception assigned to its
recorded hop category. Observation time and reception ID provide deterministic
ordering. Unknown digests and ambiguous/unverified routes retain their exclusions
and separate counts. Hop categories reconcile with confirmed period totals.
The realistic regression fixture reproduces 2,180 receptions, 2,032 packet
identities and 148 repeats; the former per-hop calculation found only 7 repeats.

Regional Traffic Ranking defaults to unique packet digests per region. Show all
messages (including duplicates) switches immediately to all included confirmed
receptions without an API request or new calculation. Counts, shares, descending
ranks and bar lengths follow the selected mode; original saved counts remain in
the exact-count table. Region assignments, Unscoped, Unknown and colors remain.

Packet Type Distribution sorts aggregated packet types by descending unrounded
share, with numeric code as a stable tie-breaker. Donut and legend use the same
order and retain code-specific colors, precise values and advertisement-origin
versus observed-flood-path details.

The Traffic Activity Heatmap uses a continuous, data-adaptive interpolated blue
scale, tested with 40 count values and at least 20 distinct colors. Exact observation counts remain intact;
recorded zero, incomplete coverage and unknown gaps remain distinct. Telemetry
scales are unchanged.

Supporting Observations in Repeater Statistic Comparison adds Change (%) beside
the absolute Difference, calculated as (After - Before) / Before * 100, with one
decimal and signed changes. Zero baselines show N/A and missing values remain
unavailable. Neighbor SNR values, sample counts and dB differences are unchanged;
no SNR percentage comparison is introduced.

No observation history is modified or deleted, no database migration is required,
and no collection, polling or radio behavior changes. The isolated statistics
worker, caching and timeout budgets remain unchanged. Existing scale tests cover
2,500–100,000 observations across 24h/7d/30d and concurrent passive recording.
Validation includes 301 Python tests, 23 JavaScript suites, fresh-install smoke
checks and the required Chromium desktop/mobile acceptance gate. Branches main,
V3 and V4 are unchanged. This remains a V5 prerelease.
