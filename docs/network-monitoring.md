# Repeater Network Monitoring

The V4 Analyzer client is read-only and available automatically for the managed
repeater selected in the dashboard. No activation switch or environment setting
is required. Opening the subsection reads cached data and refreshes stale/missing
data. The eight Firefox bodies captured on 24 October 2026 verify formats only;
live operation has been confirmed by the operator. Offline tests do not independently
verify provider access for every installation.

## External access limitations

Availability in MeshcoreStation does not grant access rights to the provider.
Respect the provider's usage conditions and restrictions. An HTTP success does
not establish permission, while an HTTP 403 is a real access failure and is never
converted to zero activity. The application does not impersonate a browser,
reuse cookies, or attempt to defeat Cloudflare restrictions.

Direct development requests previously returned HTTP 403 / Cloudflare 1010.
There is no bypass or impersonation implementation. Do not supply browser
cookies, copied browser identities or alternate proxy URLs. Requests use a fixed
HTTPS host, fixed endpoint templates and strictly validated 64-digit public keys.
Redirects are refused. Responses have a 2 MiB cap, bounded socket/body waits and a
25-second refresh budget. One short retry is allowed for transient gateway
502/503/504 failures; other failures are not immediately retried. 403 and 429
establish a shared cooldown of at least five minutes, including manual refreshes
and other keys; longer Retry-After values are respected and cooldowns survive restarts.

## Loading and storage

Opening the subsection reads the saved snapshot first. If stale (or missing), it starts one refresh. Fresh data is cached for five minutes.
Refresh Now explicitly refreshes within access/cooldown limits. Closing the
section or parent aborts/ignores the browser request; an already dispatched
server request can finish. No new browser refresh is scheduled while closed. Separately, the server collects
history for managed repeaters every 12 hours, regardless of dashboard visibility.
Provider blocks/rate limits pause the scheduled queue for at least 12 hours. Repeater changes invalidate old UI
responses. One refresh at a time is allowed per application process.

`data/analyzer-cache.db` stores the last successful complete snapshot and retrieval
time per public key, along with ETag/Last-Modified validators when returned.
304 responses reuse the saved endpoint body. Updates replace rolling values and
historical buckets; they never increment totals or combine overlapping windows.
A partial refresh failure preserves the previous complete snapshot. Existing V3
station, passive-statistics, optimizer and room records are not migrated or deleted
by this feature. Removing a managed repeater deletes its external snapshot and invalidates any
in-flight cache write. The cache may be removed while stopped without losing V3 data.

## What the interface means

| Information | Interpretation |
| --- | --- |
| Relay counts | Rolling Analyzer windows, not cumulative station counters |
| Directional weHear / theyHear / twoWay | Analyzer-derived reachability, not proof of direct RF links |
| Inferred neighbors and map edges | Inferred relationships, labeled with provenance and confidence |
| Graph degree / betweenness / rank | Graph structure, not radio signal quality |
| Path sequences | Analyzer patterns; hash prefixes can collide or be incomplete |
| Clock hash observer counts | Counts only; do not disclose individual observers or signal values |
| Empty successful arrays | No returned observations for that endpoint/window |
| Blocked, timeout, invalid JSON, HTTP failure | Unavailable source; no zero-activity conclusion |

The supplied capture has no individual heardBy observers, no direct packets,
beacons or sensor readings. Neighbor SNR values are null and remain Unknown.
The UI does not manufacture observers, RSSI or SNR. The generic record view for
future observer rows has limited fixture coverage because a nonempty shape was not captured.
The same limitation applies to nonempty direct packet, beacon and sensor arrays.

Coverage depends on participating observers. Missing observations do not prove
poor connectivity. Signal measurements on a multi-hop packet describe only the
receiver's final hop. Do not use graph relationships alone to apply radio changes.

## Offline verification

`tests/fixtures/analyzer` contains the supplied eight JSON bodies, manifest and
capture README. Tests mock access failures and transport faults. No production
code loads these fixtures and no tests require the external service.

## Integrated dashboard appearance

All four optimizer subsections share statistics cards, headings, controls,
tables and status styling from the dashboard. Long tables scroll horizontally
inside their own wrapper only when needed. Historical charts and maps resize
with the available width. The selected repeater and snapshot provenance stay
visible. Optimization Analysis resizes its same-origin iframe to its content;
the main dashboard supplies the single page scrollbar and shared theme colors.
The iframe element, document root, body and main content use the same rendered
background as Repeater Statistics, including theme changes while open or closed.

## Names and relationship maps

The display directory reuses known/managed records already returned by existing
requests, Analyzer node/neighbor/relay names, and in-memory cached information.
There are no individual name-lookup requests. Full keys are matched exactly.
Unknown identities use `Unknown Repeater (769b90b4…)`; short prefixes stay marked
unresolved, even when they match one currently known repeater. Duplicate names
receive a shortened key suffix long enough to distinguish them. Tooltips preserve
full keys or the original unresolved prefix. Internal IDs and route order do not
change when names change.

Observable Relationships uses CSS divIcon markers: S identifies the selected
repeater; R identifies a neighbor. Lines connect coordinate-bearing records from
the analyzer reach list; missing-coordinate entries remain in the tables without
invented positions. Chart sizing applies only to marked chart SVGs. Map size
observers invalidate the map after layout changes, and reopening/switching cleans
up old instances. Tile failures leave markers and overlays visible.

### Direction and confidence

Color represents directionality; line style independently represents the
analyzer's reported confidence:

| Direction | Medium/high confidence | Low confidence | Missing/unknown confidence |
| --- | --- | --- | --- |
| Bidirectional | Solid green | Dashed green | Dotted green |
| Unidirectional | Solid red | Dashed red | Dotted red |
| Unknown direction | Solid gray | Dashed gray | Dotted gray |

Two positive directional counts confirm observations in both directions. An
explicit `twoWay: true` also confirms both directions unless available zero counts
contradict it, in which case direction stays unknown. One positive count and an
explicit zero in the other direction, without `twoWay: true`, indicate a
unidirectional observation. Incomplete counts without confirmation remain gray.
A reach-list entry supplies relationship provenance, not invented directional or
signal evidence. Missing observations do not prove that communication in the
other direction is impossible. Unknown confidence is dotted and explicitly
labeled; it is never silently treated as medium/high or low confidence.

The visible English legend includes line samples. Clicking/tapping a line shows
the selected and connected repeater names, direction, `weHear` and `theyHear`
counts, original analyzer confidence and available distance. `weHear` means the
selected repeater hears the connected repeater; `theyHear` means the connected
repeater hears the selected repeater. Tooltips and expandable details retain the
original public keys. Unknown values remain Unknown; no measurements are invented.

Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.

All application labels are English. Proper names, repeater names and externally
supplied or user-generated content are preserved in their original form. These
visual changes reuse the existing snapshot without additional external requests.

## Saved performance measurements

A successful complete refresh also saves compact, timestamped measurements for
[Repeater Performance](repeater-performance.md). Cache reads do not generate new
measurements; opening Performance may import the existing saved snapshot using its
original retrieval timestamp. Historical samples survive cache replacement.
Original complete hourly relay buckets are deduplicated by repeater and UTC hour;
later corrections replace values. Rolling counts are not added together. The
server collector operates every 12 hours with persistent scheduling and no radio
traffic; see Performance documentation for restart, retention and gap semantics. A history-write failure leaves monitoring
available and displays a warning. Access failures do not create zero-valued samples.
