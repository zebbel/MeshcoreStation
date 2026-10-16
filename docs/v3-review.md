# V3 release notes and validation

Stable version: **3.0.0**. Release branch: **main**.
V3 originated from room-server 2.8.0rc9, commit `f5c6b77`. The former feature
branches are retired; follow the [update guide](web-version-switching.md).

This is an incremental internal rewrite retaining working protocols and existing
features. It does not replace the UI framework or rewrite radio cryptography.
Those changes would add migration risk without demonstrated benefit on the Pi.

## Changes

| Area | Change | Effect |
| --- | --- | --- |
| Bot | Remove six unused hard-coded help/status/ping/position/scope/distance handlers | One configured command engine remains |
| Replies | Shared splitting, spacing, accepted text and status | Same accounting for channel and room replies; channel failures now get explicit status |
| Rooms | Separate bounded bot command consumer | Slow async commands no longer hold the room packet loop; 32 waiting commands maximum |
| Room authorization | Recheck queued work before execution | Changed password, disabled room, reader permission or different selection prevents stale execution |
| HTTP | Common local-host, origin and control-header policy | Seven entry points use one implementation; existing response conventions retained |
| Room dashboard | Reuse connection-free service; one read transaction for all panels | No per-poll schema initialization; one snapshot connection rather than one per room plus listing |
| Geometry | Shared haversine function | Bot and maps use the same distance implementation |
| Updates | Dynamic GitHub branch discovery and validated branch names | All remote branches appear; compatibility is checked before switching |
| Documentation | New overview, operations, user guide, architecture and rollout instructions | Clear separation of setup, use and development |

No runtime dependency change, no destructive database migration, no firmware
flash and no automatic companion update are required for the V3 upgrade.

## Limits and risks

- Packet worker and command consumer share an event loop. CPU-bound crypto or a
  synchronous database operation can still block it; this is not hard real-time.
- Overload is bounded and visible: commands beyond the limit remain room posts
  but are not executed or automatically replayed after restart.
- A password change invalidates waiting commands and room sessions. It cannot
  undo side effects from a command that already started.
- Room position/telemetry actions inherit channel-oriented acknowledgment and
  sender lookup code. Treat that combination as an open compatibility issue;
  hardware verification and a transport-aware action refactor are still needed.
- The inherited direct-room route placeholder uses straight-line distance when
  coordinates exist. This is not the traveled multi-hop route. Packet paths are
  consumed during direct routing; V3 adds no protocol extension to recover them.
- No claim is made about Pi CPU, memory or update-time improvement until measured
  on the target Pi. Database connection counts and queue behavior are testable here.

## Validation

Run Python regression tests, room and updater JavaScript tests, installation smoke
check and whitespace checks. Keep dependency versions unchanged. New tests cover
shared HTTP rejection, accepted/partial/cancelled delivery, a single-connection
room snapshot without secrets, queue bounds/shutdown, stale-command rejection and
V3 branch validation.

Recommended checks after upgrading, with a stopped-service backup available:

1. Restore existing station and room data; confirm identities, settings and history.
2. Test channel commands, room commands, bad/good passwords and permission changes.
3. Run a slow command while another peer logs in and exchanges room traffic.
4. Check battery report destinations, OLED rotation and radio reconnect.
5. Test scopes, flood paths and direct paths over actual repeaters.
6. Check application update and rollback. Check device-specific firmware offers;
   flash only deliberately with the appropriate compatible firmware.
7. Measure idle CPU/RAM, command latency and queue counts on the Pi Zero.

## Local validation result

The V3 code passed **280 Python tests** and statistics UI checks before its
promotion to main. Earlier checks covered room, update and firmware UI behavior,
installation smoke checks and whitespace checks. Hardware flashing and radio
interoperability were not tested in this development environment. Stable release
labeling does not change the known limitations listed above.

## UI consistency pass

Room styles are now scoped to `.rooms-page`; loading them as Dash assets no longer
changes other forms, sections or controls. The standalone room page loads the
shared dashboard theme and supports the same light/dark palette. Form padding,
focus states, statistics colors and disabled buttons are aligned. The OLED editor
uses the shared fixed-header/scrollable-body dialog structure.

Room and OLED interaction checks, stylesheet-isolation checks and affected Python
layout/API tests pass. Screenshot review is still pending: this environment has
no installed browser and its attempted Chromium download failed. Check desktop
and mobile layouts in both color schemes on your installation.

## Faster code-only updates

Unchanged `requirements.txt` now skips the repeated dependency scan as well as pip
installation. Editing that file is the explicit signal for a new module or version.
The startup smoke test, backups of code/data/settings and health-check rollback
remain. Dependency-changing updates retain wheel preparation, virtual-environment
backup and post-install validation. Pi timing improvements have not been measured.

## Dynamic branch selector

The selector discovers all advertised GitHub branch heads instead of maintaining
an allowlist. It refreshes on initial page load or **Check for updates**, not during
progress polling. Branch names are rendered as text and validated before Git use.
The repository remains fixed; target-commit checks, clean checkout checks and
web-switch compatibility checks still apply. Older selectors still need an update
to gain discovery; changing V3 does not change already installed older versions.

## Companion firmware sources

The firmware panel now offers Custom MeshcoreStation and Official MeshCore.
Checking saves the selected source and filters releases for the connected device.
Changing source invalidates the release selection, and the backend rejects an
installation using a stale source. Currently only Heltec V4 OLED USB is supported.

Official application and merged images require GitHub SHA-256 digests. The merged
image supplies a verified partition table; only the application is flashed after
the existing installed-layout and boot-slot checks. No full backup or repartition
is performed. Official firmware can lack custom OLED and room transport features.
The real official `companion-v1.18.0` Heltec V4 USB assets passed preparation and
validation locally. Hardware flashing and cross-firmware data compatibility have
not been tested.

After these changes, all 279 Python tests, the firmware UI test, installation
smoke check and whitespace check passed locally.

## Dashboard and statistics fixes

The room subtitle and Period selector align with their surrounding controls.
Battery settings group monitoring and daily reports separately. Repeated route
JSON is aggregated before decoding, reducing work on long observation histories.
The statistics panel allows 60 seconds and pauses automatic retries after an
error; select a shorter period or press Refresh to retry. A local synthetic test
with 30,000 repeated observations ran about 3.8 times faster; this is not a Pi
hardware measurement.
