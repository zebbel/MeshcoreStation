# V5 Repeater Statistics visualization

All four views use saved per-repeater observations with a shared rolling 24-hour,
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
Missing digests are shown separately as unidentified, never assumed unique.
A digest appearing in separate hours is counted independently in each hour;
these per-hour unique figures must not be summed as globally unique packets.

## Hop Count Ranking

Bars are ranked by confidently attributed reception count. Each category uses
the complete recorded flood-route hop count, not estimated transmissions or
hops to a destination. Each bar and expandable count table distinguishes unique
packets, repeated receptions and unidentified payloads. Ambiguous, direct-routing
and TRACE evidence is excluded from confirmed totals.

## MeshCore Regional Traffic Ranking

Unscoped is a normal category and is sorted with named regions by observed
reception count. Unknown covers scoped traffic without a uniquely verified local
region match. Each category shows reception count, percentage of all confirmed
receptions in the period, distinct digests and repeated receptions. Distinct
counts are per category and must not be summed as globally unique traffic.

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
such hours remain visible as hollow points/lower bounds. Zero is shown only for
an interval fully covered by saved healthy, connected collection windows. Hours
use UTC boundaries and labels use the dashboard's date/time preferences.

The collector now records lightweight local coverage windows for existing managed
statistics files, without creating files for idle/unmanaged repeaters. Coverage
resets on disconnect, queue/write loss, invalid events or clock jumps, and does
not bridge restarts. The local heartbeat sends no radio traffic. Coverage tracks
application recording uptime, not RF reception completeness or packet delivery.
Collection files, raw observations and existing history are preserved.

SQLite timestamp-filtered queries perform aggregation. The browser receives
bounded hourly series and grouped neighbors/rankings, not complete packet
histories. Read queries have an eight-second execution budget; unavailable or
corrupt databases produce errors, not zero-filled charts. Scope edits can
reclassify saved observations when the view is refreshed. No performance score,
delivery percentage, automatic data deletion or active neighbor collection is
introduced.
