# MeshcoreStation 4.1.0

MeshcoreStation combines a MeshCore command bot, repeater management and telemetry,
local network analysis, and a room server in one Raspberry Pi dashboard.

**V4 development/release branch: `v4.0.0`. V3 remains on `main`.**
V4 preserves existing station and room databases. The external Analyzer feature
is **available on demand without activation**, with live operation confirmed by the operator.
Availability still depends on the external provider and deployment connectivity.
Offline fixture tests verify formats and behavior, not access permission or radio performance.

## Changes in 4.1.0

Repeater Performance is the first subsection under Repeater Optimizer. It provides
four plain-English indicators, 24h/7d/30d charts, a persistent local change journal
and equal-window before/after comparisons. It reuses Companion and optimizer
records and archives successful analyzer snapshots without adding rolling counts.
No performance score or delivery-success claim is generated. Logging changes
never sends commands; verified configuration audits create markers automatically.

See [Repeater Performance](docs/repeater-performance.md) for collection gaps,
storage bounds, comparisons and change-marker behavior.

## Installation and upgrades

Use Raspberry Pi OS / Debian with systemd and Python 3.12 or newer. Run the
installer as the normal account that owns the checkout:

```bash
git clone --branch v4.0.0 https://github.com/zebbel/MeshcoreStation.git
cd MeshcoreStation
bash install.sh
```

Choose Install / repair, select the web port, then open the Pi's address in a
browser. Under Settings, open Companion settings and choose the serial device.
Configure the bot's private channel or choose a Room Server room as bot channel.

For an existing V3 installation, first make a stopped-service backup of the
complete data directory and service environment. In **Settings → Updates / version**,
select **v4.0.0**, check the target and install. Updates follow the selected branch;
they do not merge V4 into main or flash the companion. The updater verifies the
revision, backs up code/data and restores them if startup fails.

See [operations](docs/operations.md) and [branch switching](docs/web-version-switching.md)
for manual upgrades, dependency repair and recovery.

## Dashboard

Bot Status and Known Repeaters stay at the top. The four initially collapsed
sections below them are:

1. **Command History** — saved commands, replies and all identifiable reception
   paths. Command Details switches route overlays without rebuilding the map.
2. **Repeater Management** — shared repeater selector, add/remove controls,
   remote management and telemetry with voltage and temperature charts.
3. **Repeater Optimizer** — four independent, initially collapsed subsections:
   Repeater Performance, Repeater Statistics, Optimization Analysis and Repeater
   Network Monitoring.
4. **Room Server** — room identities, membership, messages and bot integration.

Collapsed panels defer their data loading. Existing radio monitoring schedules
are independent of panel visibility. Known Repeaters maps retain clustering,
chunked loading, searchable selection, popups and error/retry feedback.

## Monitoring and analysis

All optimizer subsections follow the repeater selected in Repeater Management.
Statistics summarize metadata heard locally. Optimization Analysis retains
passive analysis, roles, neighbor snapshots, hop-limit suggestions and comparisons.
Open its Connect as administrator button for protected actions; after connecting,
use **Return to Optimization Analysis** to retain that session. Disconnect when
finished. Changes require explicit confirmation and readback verification. Nothing
is applied automatically. Existing opt-in neighbor polling remains separate from
external monitoring.

Network Monitoring displays captured-format relay windows, hourly history,
inferred neighbors, directional reachability, graph metrics, path patterns,
advertisement history and a map where coordinates exist. It makes no radio requests
and requires no repeater password. It automatically requests data when its subsection opens and the five-minute
cache is stale. There is no activation switch or environment setting. HTTP 403 / possible Cloudflare
1010 is reported as unavailable, never as zero traffic. There is no bypass,
browser impersonation, cookie reuse or continuous polling.

Snapshots are fetched only on opening the subsection or pressing Refresh Now,
cached for five minutes in a separate local database, and retained after failures.
Read [external monitoring](docs/network-monitoring.md) for source-access limits.
Captured fixture data is used only in tests, never as production fallback data.

## Existing features and settings

The command editor supports validated placeholders and preview, including
`{repeater_temperature:.1f}` from the default managed repeater's stored reading.
Per-repeater battery reports retain templates, destinations and schedules and use
the last successful reading. Voltage and optional temperature share one telemetry
request and have separate interactive 24-hour, 7-day and 30-day charts.

Settings contain companion serial/radio/network/firmware/OLED controls, optimizer
enablement and retention, date display preferences, scopes and station updates.
German `DD.MM.YYYY` and 24-hour display are defaults; ISO, US and 12-hour formats
are available. Display preferences do not change timezone or report schedules.

## Documentation and development

- [User guide](docs/user-guide.md)
- [Repeater management and protected actions](docs/repeater-management.md)
- [External monitoring: access, evidence and caching](docs/network-monitoring.md)
- [Installation, backups and recovery](docs/operations.md)
- [Architecture and tests](docs/architecture.md)
- [V4 release notes and validation](docs/v4-release.md)
- [Room protocol and development](docs/room-server-development.md)
- [Companion firmware](docs/companion-firmware-updates.md) and [OLED](docs/companion-oled.md)

Run offline regression tests without a radio or live Analyzer access:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
npm install --no-save --package-lock=false jsdom
for file in tests/*.cjs; do node "$file" || exit 1; done
.venv/bin/python -m scripts.check_install
```

See the fixture README for capture provenance and limitations. Successful tests
do not establish live API integration or physical-device compatibility.
