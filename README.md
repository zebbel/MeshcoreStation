# MeshcoreStation V3

MeshcoreStation connects a USB MeshCore companion to a Raspberry Pi and serves a
web dashboard, configurable command bot, repeater monitoring and local room
servers. The radio stays in the companion; the station runs the application.

**Stable version: 3.3.1. Branch: `main`.** V3 includes the room server and all
previous V3 improvements. The former feature branches have been retired.

## Changes in 3.3.1

- Improve tapped/clicked chart values with a thinner outline and stronger font
  weight while retaining the original 18px text size. Keep labels inside the chart.

## Changes in 3.3.0

- Repeater Battery is now **Repeater telemetry**. Voltage and optional temperature
  in °C are saved together from one telemetry response; each has an LPP channel
  setting. Missing temperature does not interrupt battery monitoring or reports.
- Separate voltage and temperature charts show 24-hour, 7-day and 30-day history.
  Click or tap either chart to highlight the nearest recorded measurement and
  show just its value inside the chart, such as `3.92 V` or `24.6 °C`.
- Battery report templates optionally support `{repeater_temperature}` (without
  a unit). Existing templates, schedules, destinations and voltage history are
  preserved by an additive database migration.

## Changes in 3.2.0

- Show bot status, known repeater count and the latest command in the initial
  dashboard. Closed history, room and repeater panels defer work; hidden tabs
  pause dashboard refreshes. Map assets load when a map is opened.
- Show Command Details route information before the map engine loads. Route maps
  load Leaflet without clustering, draw overlays before tiles, and reuse up to
  32 recently opened map results for 30 seconds.
- Configure a separate battery report message template for each repeater with
  insertion buttons, validation and live preview. Existing text remains the
  default; schedules, destinations and use of the last successful reading stay
  unchanged. Longer reports use bounded radio message parts.
- Save application-wide date and clock display preferences in Settings. Defaults
  are DD.MM.YYYY and 24-hour time; ISO/US dates and 12-hour time are available.
  Report timezones and schedules remain separate from display preferences.

## Changes in 3.1.2

- Keep Updates / version inside the scrollable Settings content, removing the large gap.
- Speed up optimizer data loading by aggregating packets in SQLite and checking
  repeater hash collisions once per hash width instead of once per packet.

## Changes in 3.1.1

- Fix room login over multi-hop floods: return the encrypted login result via a
  flooded PATH packet rather than a direct packet sent over the guessed reverse path.
- Use the incoming flood's path-hash width and matching saved scope key for replies;
  keep existing direct login behavior. Add protocol regression tests.

## Changes in 3.1.0

- Introduce the Repeater Optimizer with passive flood-traffic analysis, per-repeater
  roles and experimental scoped/unscoped hop-limit suggestions.
- Add manual neighbor snapshots, optional 12h/24h neighbor polling, and
  before/after reports for explicitly approved, verified flood-setting changes.
- Add an independent optimizer enable switch, confirmed storage reset, loading
  feedback, and bounded retention with disk-space safeguards. Disabling or
  clearing the optimizer removes its data for all repeaters, but preserves battery
  history and general repeater statistics.
- Flood settings are never applied automatically; review reachability and keep
  backups before upgrading.

## Changes in 3.0.8

- Group companion controls in one collapsible Companion settings section,
  closed by default. Station updates remain directly accessible in Settings.

## Changes in 3.0.7

- Reduced repeater grouping distance from 55 to 30 pixels so markers stay
  separate more often and groups split sooner when zooming in.

## Changes in 3.0.6

- Nearby repeaters form numbered map groups that split when zooming in.
- Click a group to expand it; overlapping repeaters spread apart for selection.
- Works in the known-repeaters map and repeater picker, including search.

## Changes in 3.0.5

- Collapsible Room server and Repeater management sections on the dashboard.
- Multiple independently configured repeaters, battery monitoring and passive
  statistics, with confirmed removal of associated monitoring history.
- Permanent deletion of disabled, non-bot rooms after confirmation. Rooms used
  as battery-report destinations must be reassigned before deletion.
- First startup migrates existing single-repeater monitoring settings. **Back up
  the station database before upgrading**; rolling back requires that backup
  as well as the older code.

## Choose your workflow

- [Installation and operation](docs/operations.md): setup, settings, backups and troubleshooting.
- [Using the station](docs/user-guide.md): bot commands, rooms, maps and battery reports.
- [V3 release notes and validation](docs/v3-review.md): what changed, validation and rollout.
- [Architecture and development](docs/architecture.md): ownership, data flow and tests.
- [Version switching](docs/web-version-switching.md): updating on main and moving from retired branches.
- [Companion firmware](docs/companion-firmware-updates.md) and [OLED pages](docs/companion-oled.md).
- [Room protocol and storage](docs/room-server-development.md).

## Main capabilities

- Select a private companion channel or a local room as the bot conversation.
- Configure command triggers, actions, help text and reply templates in the dashboard.
- View command history, packet measurements, maps and outgoing reply observations.
- Monitor repeater voltage and send scheduled reports to the bot conversation,
  another private channel or an enabled local room.
- Host password-protected rooms with independent identities and automatic enrollment.
- Design OLED pages when a supported custom companion reports the required capabilities.
- Check and install application or device-compatible companion updates from the dashboard.

## Requirements

Raspberry Pi OS / Debian with systemd, Python 3.12+, and a USB serial MeshCore
companion. Rooms need the custom firmware's raw RX/TX support. OLED support is
capability-gated. Firmware assets must match the connected device.

For a new installation:

```bash
git clone --branch main https://github.com/zebbel/MeshcoreStation.git
cd MeshcoreStation
bash install.sh
```

Use a separate Pi for a parallel running installation. Two processes must not own
the same USB companion or write the same live station database. For an existing
installation, follow the [version switching guide](docs/web-version-switching.md).

No new Python runtime dependencies are introduced by this V3 refactor. Existing
station and room databases remain in place. Keep a stopped-service backup before
upgrading, and retain it until the station is working correctly on your hardware.

See [Repeater management](docs/repeater-management.md) for supported configuration controls and the remote Console tab. See the [Repeater Optimizer guide](docs/README-repeater-optimization.de.md) for the optimizer's evidence limits and storage behavior.
