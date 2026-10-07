# MeshcoreStation

MeshcoreStation is a single-process MeshCore station application for a Raspberry Pi. It combines the MeshCore companion connection, configurable chat commands, repeater/contact tools, battery monitoring, maps, and the web dashboard in one Python process and one systemd service.

Current application version: **2.0.0**.

## Raspberry Pi installation

MeshcoreStation targets Raspberry Pi OS / Debian with systemd and Python 3.12 or newer. Run the installer as your normal user; it requests `sudo` only for system changes.

For a GitHub installation, clone the public repository rather than downloading a ZIP. Replace `OWNER` with the GitHub account or organization that hosts the repository:

```bash
git clone https://github.com/OWNER/MeshcoreStation.git
cd MeshcoreStation
bash install.sh
```

Choose **Install / repair** and select the web port. Port 80 is the default. The installer:

- installs required Debian build/runtime packages and Git;
- creates `.venv/` and installs `requirements.txt`;
- creates `meshcorestation.env`;
- installs and enables `meshcorestation.service`;
- installs the `meshcorestation` control command in `/usr/local/bin`;
- adds the service user to `dialout` for serial access;
- starts the application.

After installation, open the Pi's address in a browser, then use **Settings** to select the companion serial port and **Channels** to select the bot channel.

## Manual GitHub updates

Updates are deliberately manual. MeshcoreStation does not poll GitHub and does not install updates automatically.

Run:

```bash
meshcorestation update
```

or choose **Update from GitHub** in `bash install.sh`.

The updater uses the current checkout's configured upstream Git remote; no GitHub username or repository URL is hard-coded into the application. It requires:

- an installation made from a Git clone;
- a checked-out branch with an upstream tracking branch;
- a clean Git working tree;
- a fast-forward update.

The update fetches the upstream branch, stops the service if it was running, fast-forwards the source, installs any changed Python requirements, runs the offline installation smoke check, refreshes the systemd unit and control command, and restarts the service if it was running before the update.

Local changes intentionally block `meshcorestation update`. Commit, stash, or remove them first rather than letting an update overwrite them.

## Service commands

```bash
meshcorestation start
meshcorestation stop
meshcorestation restart
meshcorestation status
meshcorestation recent
meshcorestation logs
meshcorestation update
```

The interactive setup menu also provides install/repair, update, web-port changes, service controls, logs, and uninstall.

## Configuration and data

The installer creates `meshcorestation.env` with these settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `MESHCORESTATION_DATA_DIR` | Database, lock, and logs directory | `<project>/data` |
| `MESHCORESTATION_HOST` | Web listen address | `0.0.0.0` |
| `MESHCORESTATION_PORT` | Web port | `80` |
| `MESHCORESTATION_TIMEZONE` | Dashboard timezone | `Europe/Berlin` |

Persistent application data is stored under `data/`. The main SQLite database is:

```text
data/meshcorestation.db
```

It contains bot settings, repeaters, positions, scopes, configurable commands, command/message history, battery samples, and report state. Rotating application logs are under `data/logs/`.

The web port and process-level path/timezone settings are in `meshcorestation.env`, not SQLite. No legacy-installation migration or compatibility layer is built into MeshcoreStation.

The following are ignored by Git and therefore are not overwritten by normal source updates:

```text
.venv/
data/
meshcorestation.env
meshcorestation.env.backup-*
requirements-installed.txt
```

## Main features

- One MeshCore companion serial connection shared by the bot and dashboard.
- Configurable bot commands stored in SQLite.
- Reply, sender-position, and add-scope command actions.
- Reply placeholders for sender, route, signal, distance, companion, battery, statistics, network, and time data.
- Saved reply scopes and channel-aware replies.
- Contact synchronization and detailed contact information.
- Repeater status/configuration management through supported MeshCore CLI commands.
- Repeater and packet maps with saved coordinates.
- Battery sampling, history, charts, guest telemetry, and scheduled reports.
- Runtime serial/channel configuration through the web dashboard.

Fresh databases include the mandatory `?` help command plus `status` and `ping` defaults.

## Source layout

| Path | Responsibility |
| --- | --- |
| `meshcorestation/__main__.py` | Process lifecycle and single-instance lock |
| `meshcorestation/config.py` | Paths and web configuration |
| `meshcorestation/runtime.py` | Radio session and reconnect lifecycle |
| `meshcorestation/bridge.py` | Web-to-radio event-loop bridge |
| `meshcorestation/radio/` | Companion, bot, contacts, channels, repeater control, telemetry |
| `meshcorestation/commands/` | Command templates, placeholders, and actions |
| `meshcorestation/storage/` | SQLite schema and persistence |
| `meshcorestation/web/` | Dash application and HTTP APIs |
| `meshcorestation/web/assets/` | Browser JavaScript, CSS, maps, and local assets |
| `install.sh` | Install/repair/update/uninstall menu |
| `scripts/meshcorestation` | Installed service/update command |
| `scripts/check_install.py` | Offline installation smoke check |
| `tests/` | Python and browser-DOM regression tests |

## Development and tests

Create a virtual environment and install the runtime plus test dependencies:

```bash
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 -m pip install pytest
PYTHONPATH=. .venv/bin/python3 -m pytest -q
```

JavaScript DOM tests require Node.js and `jsdom`.

`VALIDATION.md` records the validation performed for the current source tree and any hardware/browser limitations.

## Uninstall

Run:

```bash
bash install.sh --uninstall
```

The uninstall action removes the systemd service, `/usr/local/bin/meshcorestation`, and `.venv/`. By default it leaves the source, SQLite database, logs, and environment configuration in place. A separate `DELETE` confirmation removes the stored data/configuration as well.
