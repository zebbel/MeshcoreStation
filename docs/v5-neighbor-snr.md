# Managed repeater neighbor SNR monitoring

Neighbor monitoring is separate from passive Companion RX_LOG_DATA recording.
It is **disabled by default** for every managed repeater. In Repeater Statistics,
select the repeater, enable automatic neighbor SNR monitoring, choose an interval
and save. The suggested interval is 30 minutes; allowed whole-minute intervals
are 5–1440. Settings persist in meshcorestation.db. Enabling authorizes active,
read-only guest neighbor queries over the mesh even when the dashboard is closed.
Disabling does not delete history or change passive recording.

The repeater must already be an unambiguous Repeater contact in the Companion and
allow blank-password guest login and neighbor reads. The worker does not guess
passwords, change permissions or silently change remote configuration. Unreachable
or unsupported repeaters report an error. No physical-device verification is
claimed by the simulated tests.

## Scheduling and safety

The worker polls all enabled managed repeaters, independently of UI selection and
telemetry settings. Each operation shares the Companion control lock with existing
management, telemetry and reply operations. Requests are paced at least five
seconds apart, with one repeater serviced per scheduler tick and oldest-due first.
The saved contact route is retained; flooding/path resets are not forced.

All neighbor pages are requested using the existing MeshCore protocol, 15 entries
per page. A 128-page safety bound prevents malformed pagination from generating
unbounded radio traffic; reaching it reports an incomplete poll rather than
claiming a complete list. Valid readings from earlier pages remain saved.
Disconnected Companions are skipped. Timeouts do not trigger immediate retries;
attempt times/next due times survive restarts, and completion also enforces an
interval before another poll. Shutdown/disconnect cancels in-flight collection;
configuration and membership are rechecked before every queued operation and write.
Removing/re-adding a managed repeater invalidates old queued work. Historical files
are never automatically deleted.

## Stored evidence and averages

Successful responses are stored in the existing per-repeater file:
`data/repeaterStatistics/<full-public-key>.db`. Schema additions are non-destructive;
WAL, indexed timestamps and transactions are used. No file is created for an
unmanaged repeater, and merely viewing or saving settings creates no statistics
file. Writes run outside the radio event loop and preserve the collector's disk
space reserve.

Each raw poll reading retains the prefix, resolved full key/status, SNR, reported
`secs_ago`, poll time and a reference to its deduplicated measurement. Polls record
completion/error state. Missing or invalid SNR/age readings remain raw evidence
but are excluded from means.

The protocol supplies an age, not a reception ID. A source last-heard time is
bounded by request start/response arrival, allowing one second for age rounding.
Overlapping intervals with the same identity and SNR are conservatively counted
once, even as `secs_ago` increases on subsequent polls. Non-overlapping source
intervals or changed SNR values yield new measurements. Thus equal-SNR receptions
too close to distinguish within timing uncertainty may be combined; the interface
does not claim exact RF-event IDs. Original polls are retained for inspection.

The **Neighbor SNR — Average** table uses the shared 24h/7d/30d filter over estimated
source last-heard times. It shows a separate mean, distinct valid sample count and
latest estimated Last Heard for each uniquely identified neighbor. Single samples
are labeled as insufficient history for trends. Unknown and ambiguous prefixes
appear separately. Registry collisions are checked again at display time, and
historically ambiguous identities are never silently upgraded to confirmed ones.
These are repeater-side SNR observations, not packet-delivery percentages or RF
link reliability scores.

## Identity and dashboard behavior

Repeater Management Neighbors resolves every page against all knownRepeaters.db
identities, including unmanaged repeaters. Only a unique prefix receives a full
key and resolved name; collisions show Ambiguous repeater, and missing identities
show Unknown Repeater with the original prefix. Resolution sends no radio requests.

Bot, Repeater Management and Repeater Statistics are mutually exclusive main
accordions, initially collapsed. Statistics has its own independent accordion:
Observed Neighbor Map, Most Active Neighbors, Traffic Activity Heatmap, Packet Type
Distribution, Messages per Hour, Hop Count Ranking, MeshCore Regional Traffic
Ranking and Neighbor SNR — Average. Subsections start collapsed; opening them
resizes saved maps/charts without fetching radio data or recalculating history.
Controls, periods, saved content and monitoring configuration survive collapse.
Main panels have 16 px gaps. Management telemetry's voltage and temperature charts
remain visible whenever that main panel is open, with the existing shared period.
