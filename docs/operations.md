# Install and operate MeshcoreStation

## Installation

Use Raspberry Pi OS / Debian, systemd and Python 3.12 or newer. Clone the stable `main` branch, then run `bash install.sh` as your normal user. Choose
**Install / repair** and the web port (default 80). The installer creates `.venv`,
installs dependencies, writes `meshcorestation.env`, installs the service and
adds serial access through `dialout`.

The installer displays the hardware model, architecture and Python interpreter bitness.
It removes an existing systemd mask for `meshcorestation.service` before installing
its unit, and validates that the service is enabled and that the local dashboard
responds before reporting success. If startup fails, it prints systemd diagnostics.
On a Pi 3 B+, compatible wheels depend on the running Python and OS (32/64-bit);
the ARMv6 wheel exception is only for Pi Zero with an ARMv6 interpreter.

Open the Pi's address in your browser. Select the companion port in **Settings**.
Select a private channel in **Channels**, or create a room and choose **Use as bot
channel**. The companion must already have the desired channel configured.

On Pi Zero, use wheels that actually run on that device. Installation checks
validate native imports; an ARMv7 wheel label alone is not proof of compatibility
or incompatibility. Do not copy an x86 virtual environment onto a Pi. Web updates
reuse unchanged, validated dependencies; they do not require recompiling the
application. If a manual build exhausts a RAM-backed `/tmp`, use an SD-backed
temporary directory with sufficient space.

## Service and logs

```bash
meshcorestation status
meshcorestation restart
meshcorestation logs
journalctl -u meshcorestation -n 80 --no-pager
journalctl -u meshcorestation-update -n 80 --no-pager
```

`meshcorestation start`, `stop`, `recent` and `update` are also available.
Use the setup menu to change the web port or uninstall. Manual updates require a
clean Git checkout, configured upstream and a fast-forward revision.

## Data and backup

| Location | Contents |
| --- | --- |
| `meshcorestation.env` | Service configuration |
| `data/meshcorestation.db` | Station settings, history and monitoring data |
| `data/rooms.db` | Room identities, password hashes, members and posts |
| `data/logs/` | Application logs |
| `.updates/` | Update state and retained rollback backups |

`MESHCORESTATION_DATA_DIR` overrides the data directory.
`MESHCORESTATION_HOST` defaults to `0.0.0.0`; `MESHCORESTATION_PORT` defaults to 80.
`MESHCORESTATION_TIMEZONE` defaults to `Europe/Berlin`.
`MESHCORESTATION_CONTROL_HOSTS` allows additional dashboard hostnames.

Stop the station before copying databases. Back up the complete data directory,
configuration and known working revision. Room identity seeds and settings are
private; do not publish backups. Keep backups until you have confirmed restore.
Web updates keep backup directories rather than deleting them automatically.

## Troubleshooting

- Dashboard works, radio offline: check USB port, permissions and other programs
  using the device. Companion time is synchronized on connection.
- Room login fails: enable the room, set its password and use normal room login.
  Android remote management requires RF admin support, which these rooms do not provide.
- Room command queue fills: inspect dropped-command count and slow telemetry
  requests. Original posts remain in room history; dropped executions are not replayed.
- Firmware check finds no files: select the intended firmware source and check
  again. Custom releases need a matching manifest and application binary; official
  releases need matching application and merged binaries with GitHub checksums.
- Statistics time out: select 24 hours or press Refresh to retry. Automatic refresh
  pauses after an error; the panel uses stored observations, not radio telemetry.
- Update fails: read the updater journal and dashboard progress. Preserve rollback
  backups. Repair interrupted Debian package installation separately from Python
  dependencies; do not start concurrent apt or pip jobs.

The startup health check confirms application availability, not radio delivery or
compatibility of every peripheral. Test the real companion after an update.
