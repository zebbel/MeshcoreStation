# MeshcoreStation 5.9.0 — Manual Neighbor SNR Read Now

Adds Read now to Automatic neighbor SNR monitoring in Repeater Statistics.
It requests one collection for the viewed managed repeater even when automatic
monitoring is disabled. Automatic enablement, interval, revision, next scheduled
collection and automatic attempt/success fields are preserved.

A protected local API creates a persistent one-time grant and returns immediately
with HTTP 202. The existing neighbor worker consumes the request asynchronously,
sharing authentication, the Companion radio control lock, request pacing,
validation, timeouts, pagination, storage and deduplication with scheduled reads.
Averaged 0x70 and legacy 0x06 protocols remain supported. Only completed firmware
windows are retrieved; the active window is never finalized.

The button is disabled while work is pending. Local status polling shows Reading
neighbor SNR…, available progress, retrieved records and complete/partial/error
results. Completion refreshes saved statistics and protocol status without
resetting unsaved automatic-monitoring controls. Closing Statistics stops UI
status polling while collection continues on the server.

Manual/scheduled collections cannot overlap, and duplicate manual submissions
are rejected, including from other browsers. Removal, expiry, disconnect,
shutdown and restart revoke or interrupt one-time work without automatic replay.
Existing per-cycle/page limits remain, with a 15-minute overall authorization
bound. Valid earlier pages survive partial failures; later explicitly requested
or normally scheduled reads can resume the saved continuation. No historical
observations are deleted and no additional database type is introduced.

Validation includes the complete Python regression suite, 26 JavaScript suites,
fresh-install checks and a live local HTTP fixture using fake radio responses
and the real binary request builder. The release workflow requires Chromium
desktop/mobile acceptance before publishing. Physical radio testing remains
unverified here. See docs/v5-neighbor-snr.md for manual collection behavior.

This is a V5 prerelease. Branches main, V3 and V4 remain unchanged.
