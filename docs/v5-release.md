# MeshcoreStation 5.8.0 — Averaged Neighbor SNR Integration

Adds hardware-independent support for the MeshCore custom averaged-neighbor SNR
protocol 0x70/v1. Uses the existing Companion binary transport, authenticated
guest access and opt-in per-repeater Neighbor SNR scheduler. No Companion or
repeater firmware changes are made by this update. Standard repeaters retain
legacy 0x06 last-heard monitoring. Capability is cached and rechecked per repeater;
timeouts and malformed/unknown-version responses are not permanent unsupported
classifications.

Completed 30-minute boot-relative windows are retrieved through fixed snapshots
and durable continuation cursors, with bounded work, pacing and the existing
radio lock. Valid records survive partial failures and restarts. Record identity
uses repeater key, boot session and sequence, with immutable-content checks.
Original sums, counts, min/max, clock flags, monotonic/UTC times and raw records
are preserved in additive indexed tables in the existing databases. Historical
packet and legacy SNR observations are not deleted.

Statistics use sample-weighted firmware means, full-key name resolution, source
labels, min/max and explicit collection/retention warnings. Invalid UTC is never
replaced by polling time. Boundary-crossing windows are excluded instead of
inventing sample timing. Before/after comparisons preserve dB differences and
exclude incompatible source changes from their matched-neighbor median.

The monitoring panel reports detected protocol, collection status/duration,
retrieved records, next collection, retained sequence ranges and cumulative
firmware diagnostics. An explicit capability recheck does not enable monitoring,
advance its schedule or issue an immediate radio request. Clock synchronization
and all other existing V5 functionality remain intact.

Local validation: 374 Python tests, 25 JavaScript suites and fresh-install smoke
checks passed. Firmware vectors were generated from the unmodified
meshcoreStation-v1.0.20 release header; binary transport tests use the actual
Python client's request builder with fake serial responses, never RF hardware.
The release workflow requires the full regression suite and Chromium desktop/
mobile acceptance before publishing. Physical repeater operation remains
unverified here. Two-hour firmware retention and safe per-cycle budgets can limit
collection for large populations or long polling intervals; warnings and saved
continuation make this explicit.

See docs/v5-averaged-snr.md for protocol, source, clock and retention rules.
This is a V5 prerelease; main, V3 and V4 are unchanged.
