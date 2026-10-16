# MeshcoreStation V3

MeshcoreStation connects a USB MeshCore companion to a Raspberry Pi and serves a
web dashboard, configurable command bot, repeater monitoring and local room
servers. The radio stays in the companion; the station runs the application.

**Development version: 3.0.0a1. Branch: `feature/v3`.** This is a testing branch
based on `feature/room-server` 2.8.0rc9, commit `f5c6b77`. It is not the stable
release. V3 publication and promotion to `main` are separate decisions.

## Choose your workflow

- [Installation and operation](docs/operations.md): setup, settings, backups and troubleshooting.
- [Using the station](docs/user-guide.md): bot commands, rooms, maps and battery reports.
- [V3 changes and test plan](docs/v3-review.md): what changed, validation and rollout.
- [Architecture and development](docs/architecture.md): ownership, data flow and tests.
- [Version switching](docs/web-version-switching.md): testing and returning to the previous branch.
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

After V3 is published, a separate test installation can be created with:

```bash
git clone --branch feature/v3 https://github.com/zebbel/MeshcoreStation.git
cd MeshcoreStation
bash install.sh
```

Use a separate Pi for a parallel running installation. Two processes must not own
the same USB companion or write the same live station database. For an existing
installation, follow the [version switching guide](docs/web-version-switching.md).

No new Python runtime dependencies are introduced by this V3 refactor. Existing
station and room databases remain in place. Keep a stopped-service backup before
testing, and retain it until rollback has been verified on your hardware.
