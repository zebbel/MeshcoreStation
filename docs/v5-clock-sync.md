# Automatic Repeater Clock Synchronization

In **Repeater Management**, select a managed repeater and expand **Automatic
Clock Synchronization**. It is disabled by default. Choose 1, 3, 6, 12, 24, 48,
72 or 168 hours (default: 24) and save. Settings are independent for each
managed repeater and survive restarts in `meshcorestation.db`.

The panel shows the saved state, last attempt, last successful synchronization
or verification, next due time, clock offset and last error. Dates follow the
application's configured time zone. Offset means **repeater time minus host
time**: negative values indicate a clock behind the host. Loading or refreshing
this local status does not contact the repeater. The existing manual **Sync
clock** action remains available.

## Safety and authorization

Background synchronization uses an empty-password login to reuse the
Companion's existing repeater administrator ACL access. It never reads browser
passwords or stores administrator passwords. If that Companion is not an
administrator, synchronization reports administrator authorization unavailable.
Use the existing repeater management permissions to authorize the Companion;
enabling this setting does not grant permissions.

The host must have a plausible clock and `timedatectl show
--property=NTPSynchronized --value` must report `yes`. Missing systemd/NTP status
is treated as unavailable, not as permission to set a clock. The Companion RTC
must also agree with the host before correction. Check the host's NTP service
and reconnect the Companion if a clock warning is reported. Hosts without an
available synchronization-status service cannot automatically correct clocks.

Each attempt resolves the exact Companion contact, checks the authenticated
login identity and administrator flag, and reads the clock from a fresh login
response. A clock within five seconds is verified without a clock-setting
command. If it is demonstrably more than five seconds behind, the worker sends
one `clock sync` and verifies time through another fresh login response. The
comparison allows for the measured clock-command and readback latency.
A latency-limited initial comparison is reported as inconclusive rather than
claiming the clock is within tolerance. Offsets are estimates from the login
response, not subsecond clock measurements. A clock ahead of
the host is reported without attempting a backward correction. Clock changes
during the operation invalidate verification.

A missing reply, failed readback, interruption or disconnect after a write may
leave its outcome uncertain. A persistent safety fence pauses that repeater;
the worker **does not retry the write**, including after restart. Verify its
clock manually before saving enabled settings and explicitly confirming resume.
Disabling preserves this warning. No reboot, `clkreboot`, poweroff or other
disruptive command is issued.

## Scheduling

The worker operates without an open dashboard. It uses the existing Companion
radio control lock alongside manual management, telemetry and neighbor SNR
monitoring. Checks run sequentially, with a one-minute startup grace period and
at least 30 seconds between attempts. Enabling or changing settings schedules
an initial check after a one-minute grace period. Missed intervals are not
replayed: the next check is scheduled relative to the completed attempt.
Ordinary failures wait for the next configured interval. Disconnection skips
new attempts and preserves the schedule; shutdown cancels pending work.

Disabling or changing configuration revokes pending work, including work waiting
for the radio lock. Removing a managed repeater also disables its schedule.
Re-adding it does not enable synchronization. A command already submitted
cannot be recalled; if its outcome is uncertain, the safety fence remains.
Observation history, telemetry history and manual management behavior are
unaffected. This opt-in feature generates clock-management requests only when
scheduled; it does not change passive statistics or neighbor polling frequency.
