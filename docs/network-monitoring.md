# Repeater Network Monitoring (experimental)

The V4 Analyzer client is read-only and available automatically for the managed
repeater selected in the dashboard. No activation switch or environment setting
is required. Opening the subsection reads cached data and refreshes stale/missing
data. The eight Firefox bodies captured on 24 October 2026 verify formats only;
live deployment integration remains unverified.

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
establish a shared five-minute cooldown, including manual refreshes and other keys.

## Loading and storage

Opening the subsection reads the saved snapshot first. If stale (or missing), it starts one refresh. Fresh data is cached for five minutes.
Refresh Now explicitly refreshes within access/cooldown limits. Closing the
section or parent aborts/ignores the browser request; an already dispatched
server request can finish. No new refresh is scheduled while closed and there
is no external polling worker or interval. Repeater changes invalidate old UI
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
| Inferred neighbors and dashed map edges | Inferred relationships, labeled with provenance and confidence |
| Graph degree / betweenness / rank | Graph structure, not radio signal quality |
| Path sequences | Analyzer patterns; hash prefixes can collide or be incomplete |
| Clock hash observer counts | Counts only; do not disclose individual observers or signal values |
| Empty successful arrays | No returned observations for that endpoint/window |
| Blocked, timeout, invalid JSON, HTTP failure | Unavailable source; no zero-activity conclusion |

The supplied capture has no individual heardBy observers, no direct packets,
beacons or sensor readings. Neighbor SNR values are null and remain Unknown.
The UI does not manufacture observers, RSSI or SNR. The generic record view for
future observer rows is experimental because a nonempty shape was not captured.
The same limitation applies to nonempty direct packet, beacon and sensor arrays.

Coverage depends on participating observers. Missing observations do not prove
poor connectivity. Signal measurements on a multi-hop packet describe only the
receiver's final hop. Do not use graph relationships alone to apply radio changes.

## Offline verification

`tests/fixtures/analyzer` contains the supplied eight JSON bodies, manifest and
capture README. Tests mock access failures and transport faults. No production
code loads these fixtures and no tests require the external service.

## Integrated dashboard appearance

All three optimizer subsections share statistics cards, headings, controls,
tables and status styling from the dashboard. Long tables scroll horizontally
inside their own wrapper only when needed. Historical charts and maps resize
with the available width. The selected repeater and snapshot provenance stay
visible. Optimization Analysis resizes its same-origin iframe to its content;
the main dashboard supplies the single page scrollbar and shared theme colors.
