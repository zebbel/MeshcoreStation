# Repeater Performance

Open Repeater Optimizer → Repeater Performance above Repeater Statistics. All
subsections share the managed repeater selection, readable names and dashboard
appearance. The overview answers: Is it active? How does it contribute? Is its
observed activity changing? Choose 24 hours, 7 days or 30 days.

## Automatic history collection

While the MeshcoreStation service is running, a server worker collects Analyzer
data for every managed repeater every 12 hours, independently of dashboard use.
It starts after the application initializes its databases and stops with the
service. No additional radio commands, subscriptions or transmissions are made.
The existing HTTPS client, validation, five-minute cache and request lock are
shared with Network Monitoring. Manual Refresh Now and loading on opening remain
available; the browser itself does not poll. Refresh saved data in Performance
only rereads local storage. Closed panels issue no browser requests.

Schedules and last attempt/success/error information survive restarts. A missed
run is coalesced into one due run, rather than replaying every missed interval.
At most one managed repeater is processed per minute; each attempt schedules its
next run 12 hours after finishing. A crashed in-progress claim expires after 30
minutes. HTTP 403 or 429 pauses the entire scheduled queue for at least 12 hours,
including across restarts. Longer provider Retry-After values are respected.
Other failures preserve successful data and wait until the next scheduled run.
If a dashboard refresh is already using the client, collection defers one minute
without starting another external request.
No request attempts to bypass provider restrictions or impersonate a browser.

Collection requires the station service, internet connectivity and permitted
Analyzer access. It cannot collect while the station is off. A response may
recover hourly buckets still returned by the provider, but cannot reconstruct
older missing intervals. The overview shows schedule status and history coverage.
A future collection time is a schedule, not a guarantee of success.

## Dashboard reading order

1. **Mesh Contribution** — four numerical cards: Relay Activity, Two-Way Reach,
   Communication Pairs Served and Sole-Observed Route Pairs.
2. **Forwarding Activity** — Analyzer complete hourly relay events.
3. **Repeater vs. Mesh Activity** — two indexed Companion lines.
4. **Network Connectivity** — observed neighbors and bidirectional relationships,
   followed immediately by the Neighbor Communication Map.
5. **Routing Contribution** — communication pairs and sole-observed route pairs.
6. **Performance Assessment** — measured changes, coverage and interpretation.
7. **Performance Changes** — expandable journal and before/after analysis.
8. **Detailed Statistics** — expandable existing technical values and provenance.

All four main charts are visible line charts, with legends, original observation
instants, hover values and a short What does this mean? explanation. The 24h/7d/30d
selector updates history and assessment. Mobile tables scroll inside the panel;
charts resize with it and use the same dashboard theme. Nothing uses example data
or compares the selected repeater against another repeater.

## Numerical cards and periods

Cards use the latest saved Analyzer snapshot, regardless of the selected history
period. Their rolling 24-hour measurement period and retrieval timestamp are shown
explicitly. Older snapshots are marked. These values must not be interpreted as
7-day or 30-day totals, and rolling windows are never added.

- Relay Activity is the reported rolling 24-hour relay-event count, not confirmed
  message deliveries.
- Two-Way Reach is bidirectional relationships / observed repeater neighbors and
  that fraction as a percentage. With no known neighbors, the percentage is
  unavailable rather than an invented zero or success rate.
- Communication Pairs Served uses Analyzer `pairsServed`: observed pair paths
  involving this repeater, not proven deliveries.
- Sole-Observed Route Pairs uses Analyzer `pairsSole`: pairs without an alternative
  in those Analyzer observations. Other unobserved routes may exist. This is not
  a claim that the repeater is essential or irreplaceable.

The new nullable sole-pair field preserves old records unchanged. An existing
saved API response can backfill its own original retrieval instant; older
snapshots without the field remain unknown. No network lookups are added.

## Four charts and source coverage

Forwarding retains every complete hourly Analyzer bucket and timestamp at every
selected period length. Explicit zero buckets remain zero; absent hours break the
line. Traffic peaks or quiet periods may reflect network demand or observer
coverage, not a change in delivery quality.

Repeater vs. Mesh Activity derives **both** series from the same
`network_observations` Companion stream, with the same time boundaries and existing
collision-aware path matching. It never divides Analyzer counts by Companion
traffic or mixes the managed Statistics stream into this chart. Each line starts
at index 100 in the first complete bucket with positive repeater and mesh counts:
`100 × current count / that series' baseline count`. Hover/details preserve raw
counts. A recorded zero after the baseline is a valid zero involvement count among
observed paths; missing buckets stay gaps. A zero/unknown baseline has no index.
Ambiguous short hashes invalidate the involvement bucket instead of guessing.

Companion buckets are hourly (24h), six-hourly (7d) or daily (30d). Partial boundary
buckets cannot establish an index. If Optimization Analysis did not save the
network-wide stream, comparable history may be unavailable even when the separate
Repeater Statistics stream has records. The latter remains in Detailed Statistics;
its copies are never added to duplicate observations in the network-wide store.

Connectivity and routing charts keep the latest actually recorded snapshot in
each 12-hour collection interval, at its original retrieval timestamp. They do not
carry values into empty intervals. Neighbor and pair axes use integer labels;
these are inferred relationships and rolling-window observations, not time-weighted
radio guarantees. The original graph degree, betweenness and rank remain technical
details; they are not used to rank repeater performance.

## Assessment and limitations

Assessment compares equally sized earlier/later halves of the selected history.
Each domain shows measured means, changes and available/expected intervals. Only
complete source intervals wholly contained in each half enter the calculation;
straddling boundary intervals are excluded equally. Hourly forwarding requires
all expected hourly buckets; sampled connectivity/routing require a value in each
expected 12-hour interval; comparable traffic requires received observations and
unambiguous involvement counts in every expected Companion bucket. Missing values,
ongoing windows, zero relative baselines and Companion retention/collection
warnings produce **Insufficient Data**, rather than a guessed trend.

The relative assessment compares repeater and mesh percentage changes from the
same Companion stream. It explains whether observed involvement rose faster,
tracked observed traffic, or declined relatively. The combined assessment only
interprets all four domains when each has sufficient coverage. Stable/higher
connectivity and routing together with increased relative involvement suggest
increased **observed contribution**, not proven delivery improvement.

Available intervals mean intervals with observations, not certified receiver
uptime. Companion reception completeness was not historically recorded. Observer
coverage, traffic demand, path changes and source retention can affect all values.
No arbitrary score, delivery-success percentage, causal conclusion or comparison
against other repeaters is made. Inferred relationships do not prove direct RF links.

## Performance Changes

The separate, secondary Performance Changes section preserves the local journal.
Log Change accepts 1–500 characters and current server time or a manually selected
browser-local date/time. Displays follow dashboard timezone settings. Text-only
edits preserve the exact timestamp. Save/edit/delete only change local annotations;
they never contact or configure a repeater.

Readback-verified configuration audits with matching requested/actual values
create markers automatically, including backfill of retained verified audits.
Pending, failed or mismatched readbacks do not. Original audit details remain
available; annotation edits do not change protected configuration records.
Deletion leaves a tombstone preventing automatic resurrection. Markers remain
until individually deleted or the managed repeater is removed. Optimizer history
resets retain the separate journal/archive. Removing/re-adding a repeater starts
fresh and rejects stale in-flight writes. Include this database in normal backups.

Vertical chart lines are clickable/tappable and keyboard accessible. Compare in
the journal provides the same action. Before/after analysis shows four line charts
with vertical change markers: forwarding, indexed Companion activity, connectivity
and routing contribution. Its separate assessment applies the same source and
coverage rules as the main dashboard. Detailed legacy comparison values remain
expandable; they use hourly sampled Analyzer means and exact Companion windows,
whereas the dashboard connectivity/routing trends sample once per 12-hour interval. Choose equal 24-hour, 3-day or 7-day windows
(7 days default). Elapsed durations remain equal across daylight-saving changes.

Companion packet/route counts use exact window boundaries. Analyzer relay means
prefer original fully contained hourly buckets, deduplicated by timestamp. Hours
straddling a window boundary are excluded from values and expected bucket counts;
reach snapshots use the same half-open before/after boundaries as Companion data. Older
archives lacking those buckets can use fully contained non-overlapping rolling
1h samples, spaced at least an hour apart; that source is identified. Rolling
24h counts are never added or used as period totals. Percent changes for hourly
relays are withheld when hourly coverage is incomplete. All percentages wait for
both windows to elapse and require present, nonzero baselines. Reach, reported
pairs and returned route-pattern means are sampled snapshots, not time-weighted
network guarantees. Measured differences remain visible with missing-data,
source-change, partial-window and overlapping-change warnings.

A higher/lower observed count is not proof that a change was good or bad.
Correlation does not prove that a configuration change caused an improvement.
Observer coverage, network traffic, routing and other changes can affect results.
No optimization recommendation is ever applied here.

## Storage and limits

The additive `data/repeater-performance.db` preserves existing V4 databases and
user data. It stores compact retrieval measurements, graph/contribution details,
hourly counts, collection state and permanent journal entries. No packet bodies,
credentials or duplicate full path histories are copied.

Each complete successful refresh keeps its original retrieval timestamp. Exact
cache rereads deduplicate. Each complete hourly bucket has a unique repeater/UTC
hour key; a later response can correct that count, replacing rather than adding
overlapping values. Current, invalid, timezone-less and non-hour-aligned buckets
are excluded. The latest retrieval provenance is retained separately from the
original hourly instant. Unknown fields remain unavailable.

Each measurement table retains up to 400 days and a shared maximum of 250,000
rows across repeaters, newest first; removal of older data appears as gaps.
Journal entries are not aged out. Existing Companion and Optimizer databases keep
their own retention limits and are read in place. Cached snapshots can seed
history after upgrade using original timestamps, but do not fabricate older data.
History-write failures preserve monitoring and show an error. HTTP failures do
not create zero-valued samples. Live availability remains provider-dependent.

## Neighbor Communication Map

The geographical map follows the Network Connectivity chart. It reads the last
successful Analyzer snapshot already saved by Network Monitoring/the 12-hour
collector, through the existing Performance request. It never refreshes Analyzer,
starts polling or sends mesh radio traffic. The reach endpoint supplies a 24-hour
window; its retrieval time is explicit. The 7-day/30-day history selector does not
widen this map because historical per-neighbor relationships are not stored.
Older/unavailable snapshots are identified; no snapshot means unavailable counts,
not zero neighbors.

The selected repeater is blue. Green lines indicate observations in both
directions; red lines require positive observations in one direction and an
explicit zero in the other. Missing/conflicting evidence stays gray. One-way
counts use this evidence, never total minus two-way. Only Analyzer-identified
repeater neighbors are included; full keys are deduplicated. Contradictory
duplicates remain unknown rather than confirmed.

Low-confidence lines are dashed and hidden initially. Show low-confidence links
reveals them; markers and statistics include those neighbors throughout. Unknown
confidence is explicitly dotted. Medium/high confidence uses solid lines.
Popups show names, distance when reported, weHear/theyHear, confidence and public
keys. The weHear count means the selected repeater hears that neighbor; theyHear
means that neighbor hears the selected repeater. Missing observations do not prove
communication in the other direction is impossible.

Neighbors lacking valid coordinates are listed beneath the map. If selected
coordinates are absent, located neighbors can still be shown without invented
connection lines. Missing background tiles leave valid markers/overlays visible.
Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.
