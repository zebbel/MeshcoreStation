# V5 Repeater Statistics visualization

All views use saved per-repeater observations with a shared rolling 24-hour,
7-day or 30-day filter. The managed-only Statistics selector remains independent
of Repeater Management. Opening the section, changing a filter, or clicking
**Refresh saved view** reads local databases. There is no periodic Statistics
refresh, radio request, neighbor query or Analyzer call. Collection continues
independently in the existing passive collector.

## Observed Neighbor Map

Only adjacent hashes on observed flood paths establish directional evidence.
Direct-routing instructions, TRACE encoding and origin-only advertisements do
not establish confirmed forwarding. Both endpoints must resolve uniquely against
all current keys in knownRepeaters.db and the selected repeater must have been
unambiguous when recorded. A newly discovered hash collision can make a formerly
unambiguous historical identity uncertain; ambiguous records are never silently
promoted to confirmed observations.

Blue marks the selected repeater. Green lines show observed paths in both
directions; red shows observations in only one direction. Arrows show the observed
direction. Line/marker popups include directional reception and unique-packet
counts, last observation, names and full public keys. Neighbor identities can be
unmanaged. Missing coordinates are listed rather than invented; ambiguous or
unknown adjacent hashes appear separately and do not create confirmed map lines.
Markers use CSS divIcons and vector lines remain if background tiles fail.
Hovering over a neighbor shows a single-line resolved name (long names are
ellipsized), followed by left-aligned labels and right-aligned counts. **We hear** (incoming toward
the selected repeater) and **They hear** (outgoing toward the neighbor) reception
counts use the selected period. Tapping opens the existing detailed popup with
the same summary and full repeater name. These are observed route relationships, not RF reception
confirmation or delivery acknowledgements.

One-way observation does not prove that reverse communication is impossible.
Two-way observations do not establish a reliable direct bidirectional RF link.
Adjacent route evidence is inferred connectivity, not receiver acknowledgement.
The API limits map summaries to 1,000 direction groups with a visible limit note;
recorded history is not truncated or deleted by this display limit.

## Messages per Hour

Text payload types 2 (direct text) and 5 (group text) are included when a flood
route confidently attributes the selected repeater. A direct-text payload carried
on a flood route is different from a direct-routing instruction, which cannot
prove observed forwarding and is excluded. Collection is independent of Bot
channel and no channel decryption is required for these packet-type counts.

Unique packets are distinct saved SHA-256 payload digests within each hour.
Repeated receptions are additional receptions of those digests in that hour.
Blue unique-packet and orange repeated-reception bars appear side by side for
each hour. Long periods scroll horizontally with a fixed count axis and Start /
Latest hours controls. Hover, keyboard focus or tap shows exact values.
Missing digests remain unidentified, never assumed unique; their statistics are
preserved in the expandable exact-count table without a gray chart series.
A digest appearing in separate hours is counted independently in each hour;
these per-hour unique figures must not be summed as globally unique packets.

## Hop Count Ranking

Unique/repeated classification spans the full selected period: the earliest
confirmed reception of each packet digest is unique, ordered by observation time
then reception ID. Later confirmed copies are repeated even if the hop count
changes. Each reception belongs to its actual recorded hop category, so category
counts reconcile with confirmed period totals. Unidentified digests remain
separate; ambiguous or currently unresolved observations do not consume a
confirmed unique packet. Stored history is read only.

Columns are ordered by increasing numeric hop count. Each category uses
the complete recorded flood-route hop count, not estimated transmissions or
hops to a destination. Each category has side-by-side blue unique-packet
and orange repeated-reception columns. Unidentified payloads remain in the
expandable exact-count table; column heights show only identified receptions. Ambiguous, direct-routing
and TRACE evidence is excluded from confirmed totals.

## Most Active Neighbors

Up to 20 neighbors are sorted by combined incoming and outgoing route observations.
Horizontal grouped bars show blue **We hear** (incoming) and orange **They hear**
(outgoing), with names, exact counts and hover/focus/tap details. Managed and
unmanaged known neighbors are included, including those without coordinates.
Ambiguous identities are excluded from this ranking and remain in the map's
separate uncertain-evidence list. The existing 1,000 direction-group response
limit also bounds this ranking; a visible warning appears when reached. Observed
volume is not evidence of RF reception reliability.

## Traffic Activity Heatmap

Calendar days form the rows and hours 00–23 form the columns. The continuous, data-adaptive blue intensity scale uses square-root interpolation
between five color stops, with more than 20 distinguishable colors when the
available range supports them. Colors are display values only: exact counts and
original precision remain unchanged. A continuous legend shows light (low) to
dark (high) traffic; zero and unknown intervals retain their separate styles.
The scale uses counts of confidently attributed flood-path receptions across all packet
types, excluding full-key advertisement origins. It therefore covers more packet
types than Messages per Hour, which remains text-only.

Cells distinguish observed traffic, complete recorded zero intervals, incomplete
coverage (dashed outline/lower bound), and unknown recording gaps (hatching).
Cells outside the rolling period or without a clock hour are also marked unknown,
with their reason in the tooltip. Hover, focus or tap reveals the exact count,
original interval and recorded/expected seconds. Date labels follow the dashboard
preferences and calendar boundaries follow its configured time zone, including
fractional-hour offsets. Repeated daylight-saving hours share a cell with summed
reception counts and both original intervals in the details; skipped hours never
receive invented zeros. Partial boundary hours remain visually incomplete.

## Packet Type Distribution

The donut shows recorded MeshCore packet codes individually, including reserved
or unknown codes by numeric identifier. Categories are ordered by descending
unrounded percentage (equivalently reception count), with numeric code as a
stable tie-breaker. Legend entries and donut segments share this order; colors
remain attached to packet codes, regardless of ranking.
Counts and percentages describe included receptions, including repeated copies,
not a forwarding-success or delivery rate. The legend, interactive segments and
exact table retain precise values. Only recorded packet types are included.

Full-key advertisement-origin evidence is included as a separate evidence class,
never classified as forwarding in this new distribution. Advertisement route
observations involving the selected repeater are separately labeled flood-path
evidence; these are not independent forwarding-event confirmations. The advertisement legend shows both origin and path counts;
the exact table separates evidence classes and preserves unique, repeated and
unidentified counts. Ambiguous/unverified routes remain excluded, while an
independently identified full-key origin is not lost due to a route-hash collision.
An origin reception is counted only once in this distribution. The existing
forwarding totals and original observation history are unchanged.

The new aggregates reuse the single source scan and compact disposable SQLite
facts. The activity view adds bounded local-calendar bins, and packet distribution
adds a grouped query over those facts; raw route histories are not scanned again.
The isolated worker, cache invalidation and timeouts remain unchanged.

## MeshCore Regional Traffic Ranking

Each region has two separate horizontal bars: blue unique messages above orange
repeated receptions. Both remain visible in either checkbox mode and share a
single numerical scale across all regions. Their counts and lengths do not
change when only the ranking mode changes. A zero count remains zero, without
inventing a visible nonzero bar. Hover, keyboard focus or tap shows exact unique,
repeated, total and unidentified counts with the active share.

The **Show all messages (including duplicates)** checkbox defaults to unchecked.
Unchecked ranks regions and calculates totals/percentages using unique packet
digests within each region; repeated receptions remain visible for context.
Checked ranks and calculates totals/percentages using all included confirmed
receptions, including duplicates and forwarded copies. Ranking and shares update
immediately from the saved response, with no API request or recalculation.
The choice persists across period/repeater refreshes. Unknown digests are
excluded from unique/repeated bars but retained in all-reception totals and the
exact-count table. Ambiguous/unverified observations keep their exclusions.

Regional SVG names, counts and headers inherit `--text` through a scoped nested
SVG selector, so they remain readable in both light and dark themes. The chart
scrolls horizontally inside its panel on narrow screens; other chart and Leaflet
SVG styles are unchanged.

Unscoped is a normal category, ranked alongside named regions. Unknown covers
scoped traffic without a uniquely verified local region match. Percentages use
the sum of per-region counts in the selected mode. Deduplication uses packet
identity, never decoded message text. The same identity seen in distinct regions
can count once in each; per-region unique counts are not globally unique traffic.
The exact-count table preserves the original saved reception/unique/repeated/
unidentified counts, with shares for the active counting mode.

In **Configure known region names**, enter one name per line, for example
`de-he` or `rhein-neckar`. An optional 32-hex scope key can follow the name after
a space. Without a custom key, the standard MeshCore hashtag key is derived.
Names/keys are local attribution preferences in meshcorestation.db; saving sends
no hardware commands and does not change repeater regions or Bot scopes.
Existing configured Bot reply scopes are also checked. Unknown and Unscoped are
reserved category names. No example regions are automatically installed.

Names are accepted only when the packet's transport code matches a configured
scope key using the saved packet type and payload. A transport code is not a
static region ID. The algorithm follows MeshCore's
[TransportKeyStore.cpp](https://github.com/meshcore-dev/MeshCore/blob/main/src/helpers/TransportKeyStore.cpp):
HMAC-SHA256 of payload type plus payload, with reserved-code remapping. Wildcard
transport code zero and ordinary non-scoped floods are Unscoped. Multiple matching
names, missing codes/payloads and unknown keys remain Unknown. Short codes can
collide; a unique match among configured keys is not absolute network identity.
Stored metadata names alone are not trusted as evidence. Region configuration
reads/writes use the existing local-dashboard request protections; raw keys are
not included in chart/map aggregation responses.

## Coverage and limitations

The 5.1.0 history did not record collection uptime. Empty historical hours with
no uptime evidence are unknown gaps, not zero traffic. Positive observations from
such hours remain visible as dashed, translucent bars/lower bounds. Unknown
intervals use hatched gaps, while a recorded complete zero is explicitly labeled. Zero is shown only for
an interval fully covered by saved healthy, connected collection windows. Hours
use UTC boundaries and labels use the dashboard's date/time preferences.

The collector now records lightweight local coverage windows for existing managed
statistics files, without creating files for idle/unmanaged repeaters. Coverage
resets on disconnect, queue/write loss, invalid events or clock jumps, and does
not bridge restarts. The local heartbeat sends no radio traffic. Coverage tracks
application recording uptime, not RF reception completeness or packet delivery.
Collection files, raw observations and existing history are preserved.

A single indexed source scan classifies observations once and writes compact,
disposable SQLite facts for exact aggregation. The browser receives bounded hourly
series and grouped neighbors/rankings, not complete packet histories. Calculations
have an unchanged eight-second budget, with per-stage timing diagnostics that never
log packet contents. One expensive calculation runs at a time; unchanged results
can be reused for two seconds. New writes, identity/settings changes and membership
changes invalidate the cache. This is a local application cache, not active polling.

Recording status has an independent five-second browser timeout. Saved statistics
get a fresh ten-second browser budget after status appears. Browser timeout, server
query timeout, database errors and calculation overload are distinct. Loading marks
previous charts as stale, with an explicit snapshot label. Unavailable or corrupt
databases produce errors, not zero-filled charts. Scratch work preserves the local
collector free-space reserve and never modifies original observation history.
See the [performance measurements and regression report](v5-statistics-performance.md). Scope edits can
reclassify saved observations when the view is refreshed. No performance score,
delivery percentage, automatic data deletion or active neighbor collection is
introduced.


The service-context correction runs saved-view calculation in one bounded
read-only worker interpreter, preserving the eight-second calculation budget.
Recording, status and radio handles remain in the main application. See
[worker isolation and lifecycle](v5-statistics-service-context.md).

## 5.4 corrections

Healthy queued processing preserves coverage. Genuine loss/failure gaps remain,
and partial boundary hours are evaluated using elapsed time, without backfilling
legacy gaps. Solid borderless hourly bars retain coverage tooltips. The donut
uses individual stored packet codes with numeric reserved categories. The square
map supports local one-way visibility filtering. Names are ingested before chart
rendering and refresh locally when identities change. Monitoring settings and
recording explanations are collapsed separately, without stopping collection.
