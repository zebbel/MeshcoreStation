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
No request attempts to bypass provider restrictions or impersonate a browser.

Collection requires the station service, internet connectivity and permitted
Analyzer access. It cannot collect while the station is off. A response may
recover hourly buckets still returned by the provider, but cannot reconstruct
older missing intervals. The overview shows schedule status and history coverage.
A future collection time is a schedule, not a guarantee of success.

## Simple overview

- **Mesh Activity:** forwarding in the latest recorded Analyzer hour and Companion
  path involvement over the selected period. A zero in one recorded hour does
  not imply a repeater is faulty or permanently inactive.
- **Network Reach:** neighboring repeaters and bidirectional relationships inferred
  from Analyzer observations. Retrieval time and older snapshots are identified.
- **Mesh Contribution:** reported communication pairs served, distinct Companion
  packet IDs and route patterns where available. Pairs are rolling-window counts;
  they are not individual delivery confirmations. Returned Analyzer route counts
  may be truncated by the provider.
- **Performance Trend:** higher/lower/unchanged hourly forwarding between equally
  sized, completed halves of the selected period, only when both halves have all
  hourly buckets. Missing hours withhold a trend. Higher activity is not
  automatically better performance. Companion network traffic over the same
  periods supplies separately labeled context; different source coverage prevents
  attributing changes to the repeater.

Data completeness states the available/expected complete hourly buckets, first
and latest original hourly timestamps, and automatic collection status. An hour
still in progress is excluded. The two comparison halves exclude an unmatched
oldest hour when the number of completed hours is odd. No arbitrary score,
unverified delivery rate or reliable improvement claim is derived from gaps.

## Details and charts

Detailed Statistics and Performance History are independently expandable below
the overview. The former includes raw values and graph degree, betweenness and
rank. The latter separates Companion received packet counts, Analyzer hourly
forwarding, and sampled network reach/optimizer neighbor observations.

Hourly Analyzer points retain original UTC instants and counts at all selected
period lengths. Absent hours break the line; they are never filled with zero.
An explicitly returned complete zero-count bucket remains zero. Neighbor axes
use integers. Companion display buckets are hourly (24h), six-hourly (7d) or daily
(30d); first/last buckets can be partial. Reach/optimizer curves use the latest
snapshot per display interval. Blank intervals mean missing observations. Hover
points or open Show measured values for timestamps and values.

The managed repeater's Repeater Statistics stream is preferred per requested
window, including with the separate Optimizer disabled. Otherwise the existing
collision-aware Optimization Analysis network stream is used. Copies appearing
in both stores are never added. Companion and Analyzer counts are never added
together. Companion uptime/reception completeness was not historically recorded;
packet rows cannot certify continuous coverage. Existing Companion retention and
pauses can cause gaps. Short ambiguous path hashes remain excluded, and public
keys remain unchanged internally.

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
the journal provides the same action. Choose equal 24-hour, 3-day or 7-day windows
(7 days default). Elapsed durations remain equal across daylight-saving changes.

Companion packet/route counts use exact window boundaries. Analyzer relay means
prefer original fully contained hourly buckets, deduplicated by timestamp. Older
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
