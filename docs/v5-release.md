# MeshcoreStation 5.7.0 — Automatic Repeater Clock Synchronization

Adds an expandable Automatic Clock Synchronization panel in Repeater Management.
The feature is disabled by default and independently configured for each managed
repeater. Supported intervals are 1, 3, 6, 12, 24, 48, 72 and 168 hours; default
24 hours. Settings, schedules, attempt results, errors and clock offsets persist
in the existing application database through an additive schema.

A dedicated background worker reuses the Companion's administrator ACL access
without reading browser passwords or storing credentials. It verifies host NTP
synchronization, Companion time, exact repeater identity and fresh login clock
observations. Only clocks demonstrably more than five seconds behind are
corrected, using one clock sync command followed by authenticated readback.
Clocks ahead are never moved backwards. Inconclusive latency-limited readings
are reported without setting the clock.

The worker shares the existing radio control lock, handles disconnection and
configuration revocation, processes repeaters sequentially and paces startup.
Uncertain writes are persistently fenced against automatic retries, including
after restart. Manual clock verification and explicit confirmation are required
to resume them. Removing a managed repeater disables its schedule. Existing
manual synchronization and historical statistics are preserved.

Local validation: 334 Python tests, 25 JavaScript suites and fresh-install smoke
checks passed before release preparation. Release validation reruns the complete
suite and Chromium desktop/mobile acceptance, including the new settings panel,
before publishing. Physical repeater synchronization has not been verified here.
The host must expose a positive timedatectl NTP synchronization status; otherwise
clock setting fails closed. See docs/v5-clock-sync.md for safety and scheduling.

This remains a V5 prerelease. Branches main, V3 and V4 are unchanged.
