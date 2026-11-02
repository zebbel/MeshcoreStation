# V5 Repeater Statistics — passive collection

Repeater Statistics is a separate expandable dashboard section below Repeater
Management. Its independent selector lists only managed repeaters. It displays
recording state, saved observation count, last recorded time and errors. Opening,
closing or changing this view does not start or stop collection. Status reads
refresh while the section is visible, without radio requests.

## Membership and lifecycle

`voltage_config.managed = 1` is the sole collection membership source. Telemetry
flags and Bot channel selection do not affect passive recording. A single async
collector lives across Companion reconnects; every RX_LOG_DATA callback is handed
to it before Bot/channel filtering. It performs no RF commands or external calls.

A managed-list mutation and each writer batch share a mutex. Removal commits only
after any already-running batch finishes, and no queued batch can write for the
removed repeater afterward. New membership records a nanosecond receive-time
cutoff in `statistics_since_ns`; queued packets predating addition/re-addition are
excluded. Existing V5 managed entries receive a zero cutoff when the additive
column is installed, preserving membership. This is not a V3/V4 migration.

Statistics databases are not deleted on removal. Re-adding appends new observations.
Existing local telemetry removal behavior is unchanged: its separate readings and
reports can still be deleted when management is removed. Known repeater identity
always remains in `knownRepeaters.db`.

## Files and evidence

Only a relevant observation creates a file:
`data/repeaterStatistics/<64-character-lowercase-public-key>.db`.
For a custom data directory, `repeaterStatistics` is beneath that directory.
No statistics file is created for unmanaged repeaters, dashboard reads, idle
startup or a managed repeater with no relevant observations. Directory/file
permissions are private. WAL, timestamp/digest indexes and transactional batches
are used. No identity registry is copied into these files; route candidate keys
are historical attribution evidence, resolved against knownRepeaters.db.

Every reception has a new UUID and callback receive timestamp. The same reception
UUID is used in each involved managed repeater's database. Repeated payloads,
retransmissions and repeated routes remain separate rows. Payload digests use
SHA-256(packet type + packet payload), like V4; they group evidence but do not
cause deduplication. Original client digest, raw packet bytes when supplied,
payload bytes, route bytes and decoded metadata are retained. Metadata preserves
original supplied timestamps and represents binary fields as hex. Client secret,
password and private-key fields are excluded.

Rows include packet/route type, transport-code/scoped metadata, RSSI/SNR when
available, reported hop count/hash width, full decoded route, positions,
previous/following hops, ambiguity and attribution basis. Schema supports the
client's 0–15 packet types, four route types and 1–4 byte path hashes. Missing
measurements remain null. Malformed or oversized events are counted as skipped;
they do not interfere with Bot processing.

## Attribution limitations

Hash matching checks all known repeater keys, including unmanaged repeaters.
An unambiguous match means unique among currently known identities, not
cryptographic proof or verified direct RF connectivity. Unknown repeaters can
still produce undetected hash collisions. Each segment retains its raw hash,
candidate keys and resolution status; ambiguous segments have no confirmed key.
Each managed candidate receives a record explicitly marked ambiguous.

Flood paths support observed first/middle/last position evidence. Valid full-key
repeater advertisement origins can also be recorded, including zero-hop adverts;
the origin is not a forwarding position and signatures are not authenticated here.
Direct routing paths describe routing instructions, not observed forwarding.
TRACE may use mixed path encoding unsupported by the client's general route
parser: its raw packet and possible candidate hashes are preserved as ambiguous,
uninterpreted evidence, with no confirmed forwarding positions. These records
must not be counted as confirmed repeater activity in future analyses. Packets
with no attributable managed candidate/origin are not saved. The collector does
not infer missing routes, delivery success or direct RF links.

## Reliability and limits

The receive handoff is bounded to 2,048 events. Worker batches contain up to 128
receptions and coalesce over 0.5 seconds. SQLite work is off the radio event loop;
main membership is read-only during collection. SQLite writes use short timeouts.
A failing repeater database does not prevent other repeater databases from writing.
Each repeater transaction either commits its complete batch or rolls back.

Below 64 MiB free disk space, writes pause without deleting old data or creating
new files. Successful later observations resume recording after storage recovers.
Write failures, queue overflow and skipped events are exposed in collection health;
dropped/invalid counters are session counters, not historical traffic metrics.
Queue overflow or a failed write loses those observations; no retry fabricates
missing data. Graceful shutdown drains the bounded queue. Abrupt process/power
loss can lose queued, uncommitted observations; committed SQLite history remains.
Across separate repeater files, batch commits are independent, not globally atomic.

No retention/deletion policy is implemented. Operators must monitor disk usage.
Disconnected Companions produce gaps, not zero activity. Stored observation count
and last receive/record times survive restarts; current connection/queue/error
health is in-process status. Hardware reception completeness and physical RF
operation are not proven by automated tests.
