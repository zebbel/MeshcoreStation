# Firmware-calculated neighbor SNR averages

MeshcoreStation supports the hardware-independent custom `0x70`, version 1
protocol. The first firmware implementation is XIAO, but selection uses valid
protocol responses, never hardware names or firmware strings. Standard repeaters
retain existing `0x06` last-heard monitoring.

Use the existing **Automatic neighbor SNR monitoring** checkbox per managed
repeater. It remains disabled by default, with a suggested 30-minute interval and
allowed 5–1440 minute settings. There is one scheduler, no additional enable
switch and no Companion firmware change. The repeater must permit authenticated
blank-password guest login. No browser password is read or stored.

## Transport and detection

The installed Python client exposes public `send_binary_req`. The adapter uses
standard Companion command `0x32` and response `0x8C`, sending the 28-byte request
without another embedded tag. It subscribes before submission to capture early
replies, validates the exact full-key contact/login identity and matches replies
to the Companion's four-byte expected tag. Generic pushes expose no separate
sender field: the Companion validates the encrypted reply and its echoed tag
binds the outstanding request.

The isolated decoder validates the 64-byte header and zero/one 76-byte record,
including little-endian fields, signed quarter-dB min/max, signed 64-bit sum,
unsigned sample count, clock flags, snapshot ceiling and cursor progress. Unknown
versions, reserved fields and malformed records are not interpreted as samples.
Cipher padding is ignored after the validated response length.

Capability is cached separately per repeater. Failed/unsupported probes are
normally rechecked after six hours. A firmware protocol-level change or
**Recheck SNR protocol at next collection** also requests rechecking. The button
does not enable monitoring, advance its schedule or send a radio request.
Timeouts, malformed responses and disconnects never permanently mark a repeater
unsupported. Unknown capability retains legacy monitoring. Once aggregate pages
are validated, collection failures preserve continuation rather than mixing
sources mid-cycle. Later capability checks also allow recovery after a downgrade
to standard firmware.

## Snapshots, budgets and retention

A diagnostics-only request opens a boot-session snapshot with a fixed ceiling.
Subsequent data requests retain that session/ceiling and exclusive cursor. Evidence
commits before the checkpoint advances, so a crash can replay a page safely.
Pending snapshots continue before later snapshots are opened. Boot/session
mismatch is reported and starts a fresh snapshot at a later configured poll.

Each cycle retrieves at most 32 records within a 180-second work budget. Requests
reuse five-second pacing and the Companion control lock shared with management,
telemetry and automatic clock synchronization. Valid pages survive subsequent
errors. Configuration/membership is checked before queued requests and commits;
shutdown/disconnect cancels requests. There are no immediate timeout retries,
acknowledgments or remote record deletion.

Reference firmware retains completed records for only two hours after window
end. Large populations or long intervals can exceed safe collection capacity.
Outstanding snapshots continue at the configured interval; polling frequency is
never silently increased. The panel reports duration, retrieved records,
completeness, sequence range, warnings and cumulative expiry/eviction/drop
counters. Expiry may concern records already saved locally. Missing sequence
ranges are persisted without claiming every gap originated in the current poll.

## Evidence, UTC and statistics

Capability/checkpoints use new additive tables in `meshcorestation.db`.
Immutable aggregates, raw record bytes, collections and gap ranges use indexed
WAL tables in the existing `data/repeaterStatistics/<public-key>.db` architecture.
Only managed repeaters with relevant validated responses create files. Viewing
settings does not create a statistics file. Existing history is never deleted.

Record identity is `(repeater key, boot session, sequence)`; neighbor/window and
original contents must agree on replay. Different boots remain distinct.
Original monotonic/UTC fields, validity/discontinuity flags, last reception,
sum/count and min/max are retained. Means use `sum / (4 × count)` and period means
use `Σsum / (4 × Σcount)`, not an unweighted mean of window means.

Windows are 1800-second boot-relative intervals, not UTC-aligned half-hours.
Only flagged valid UTC is used. Invalid UTC remains NULL: polling time is never
substituted as a historical sample date. Discontinuities and overflow remain
quality limitations. Firmware clock validity indicates continuity after a set,
not independent wall-clock accuracy. Existing manual/automatic clock sync can
establish time for future windows without changing its schedule or safety; an
invalid past window is not backfilled.

The 24-hour, 7-day and 30-day views include whole UTC-valid completed windows.
Boundary-crossing windows cannot be split and are excluded with warnings.
Undated records are reported without assigning them to a selected period.
Names use full public keys and knownRepeaters.db; unknown full keys stay
identifiable without invented names. Legacy ambiguity rules are preserved.

For a neighbor with firmware data in a selected period, that source takes
precedence over legacy estimates, which are not blended into its mean. Legacy
history remains available for other neighbors and older periods. The table
identifies source, actual sample count, available min/max and latest valid time.
Before/after comparisons retain dB differences and matched-neighbor medians;
source changes are shown separately and excluded from deltas/median. No SNR
percentage-change calculations are added.

These are repeater-side observations, not delivery-success rates. Reference
firmware samples qualifying direct repeater advertisements/discovery responses,
not every radio packet. Automated tests use vectors generated from the unmodified
release header and fake serial transport; they do not certify physical RF behavior.

[Protocol specification](https://github.com/zebbel/MeshCore/blob/meshcoreStation-v1.0.20/docs/xiao-neighbour-snr.md).
