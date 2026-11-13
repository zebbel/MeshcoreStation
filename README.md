# MeshcoreStation V6 — 6.0.3

A fresh Companion-connected channel bot and repeater-management application.
Version **6.0.3** on branch **`V6`** automatically resumes Repeater Statistic Comparison when a worker saves progress before timing out. Select **Language / Sprache** in MeshcoreStation Settings. See [Dashboard languages](docs/v6-localization.md) and the [comparison release notes](docs/v6-release.md).
V3 `V3` and V4 `V4` are maintained separately. V4.4.1 supplies the protocol and dialog
reference; the supplied V5 design package supplies the dashboard arrangement.

The first row has exactly **MeshcoreStation**, **Connected Companion**, and
**Known Repeaters**. The cards stack in that order on mobile. The V4 logo,
theme variables, typography and fixed footer are retained. The footer shows
version/branch, connected firmware/build or unavailable, and an asynchronous
installed-branch update check. In **Settings → Updates / version**, you can
check and switch between `V5` and `V6`. Installation requires confirmation.

Below the cards, **Bot** contains only **Bot Settings** and **Command History**,
independently collapsible. **Room Server** follows Bot, then **Repeater Management**.
An independent **Repeater Statistics** section follows Management, with a managed-only
selector, recording status and saved-data visualizations. There is no Optimizer, Analyzer, Performance,
or Network Monitoring. The Room Server is described below.

## Fresh storage only

For a fresh installation, use an empty data directory. V6 retains the V5 database
format. V3/V4 databases are not migrated or supported. The application refuses a main database containing the former
known-repeater registry rather than modifying it.

| File | Ownership |
| --- | --- |
| `meshcorestation.db` | Application display/serial preferences, bot channel and commands, reply scopes, persistent command/reception/reply history, managed membership and local telemetry configuration/history, management audit |
| `knownRepeaters.db` | The single canonical repeater registry, full public-key identity, name/location, discovery metadata, actual advertisement counts and timestamps |

The main database has **no persistent repeater registry**. Included protocol
readers access a read-only temporary view of the attached canonical registry;
the view stores no identities. Contact imports do not increment advertisement
counts. Actual advertisements do. Removing management or deleting a hardware
contact leaves the saved known identity intact. The two core files are created by the running user with private permissions.
Passive statistics additionally use `data/repeaterStatistics/<full-public-key>.db`
for managed repeaters only, created on their first relevant observation. SQLite
may create ordinary WAL/SHM journal sidecars. Removing management preserves these
statistics files; re-adding resumes recording without restoring queued old packets.

Actual contacts, channel slots/keys, radio settings and remote configuration
remain authoritative on hardware. Private channel keys and management passwords
are not stored server-side. Remember-password is optional browser-local storage,
off by default, with the V4 unencrypted-storage warning.

## Included functions

- Application Settings: persisted date/clock preferences and Updates / Version.
- Companion Settings: serial selection/reconnect, identity, location picker,
  transmit power, radio parameters and supported path/default-scope settings.
  Writes validate identity/current state and verify hardware readback.
- Contacts / Channels: V4 dialogs, refresh/add/delete, validation, stale-state
  checks and mutation readback. Contact Manage opens guest/admin repeater
  management; Bot Channel selection activates and protects the selected slot.
- Bot commands: protected `?`, configurable templates, add/edit/delete/preview,
  Reply / Update Sender Position / Add Scope actions and editable reply scopes.
  Commands execute once. Replies preserve channel/scope, use distinct packet
  timestamps and keep V4.4.1's asynchronous hop-limited retries: minimum 20/30s
  waits, adaptive flood timeout and independent 0–5s jitter. Queue, forwarding,
  configuration, shutdown and airtime safeguards remain. Acceptance/forwarding
  is never receiver delivery confirmation.
- Command History: persistent oldest-to-newest window, command filter, 200-record
  Load Older, Jump to Latest, scroll preservation, details, reception paths,
  packet-route map, RSSI/SNR and outgoing attempts. Refresh pauses when either
  the parent Bot section or History is collapsed, or the page is hidden.
- Repeater Management: selection/add/remove, V4 guest/admin sessions and Status,
  Configurations and Console tabs. Includes system/clock/battery/radio counters,
  telemetry and paged neighbors, configuration groups, read/confirm/write/readback,
  safe CLI with searchable reference, sensitive-value redaction and timeout
  cooldown. Configuration readback mismatches report failure. Local audits never
  store password values. Optional telemetry monitoring and report functions are
  disabled by default and use the main database; no Analyzer or neighbor poller
  is started.
- Automatic repeater clock synchronization: disabled by default, per-repeater
  intervals and saved status, Companion administrator ACL access, verified
  forward-only corrections and persistent protection against uncertain-write
  retries. See [clock synchronization safety and scheduling](docs/v5-clock-sync.md).
- Known Repeaters: saved count and map work while disconnected. Only valid saved
  coordinates are plotted; ambiguous short path hashes remain unidentified.

## Passive repeater statistics

All managed repeaters (`voltage_config.managed = 1`) are recorded automatically
from Companion `RX_LOG_DATA`, regardless of dashboard selection, Bot channel,
collapsed sections or telemetry settings. The collector sends no radio requests.
The Statistics selector changes only the displayed recording status. Shared 24-hour, 7-day and 30-day filters update the Observed Neighbor Map,
Messages per Hour, Hop Count Ranking and MeshCore Regional Traffic Ranking.
Neighbor hover/tap summaries show incoming (We hear) and outgoing (They hear)
route observations. Hourly and numerically ordered hop charts use side-by-side
unique/repeated bars. Most Active Neighbors, a calendar-hour Traffic Activity
Heatmap and Packet Type Distribution extend the same saved-data view.
Advertisement origins remain separate from forwarding. Unknown coverage remains a gap,
and exact-count tables preserve unidentified receptions.
The view refreshes on opening, filter changes or **Refresh saved view**, without
active radio polling. No performance analysis, Analyzer collection or automatic
deletion is included.

Automatic **neighbor SNR monitoring** is a separate, per-repeater opt-in setting,
disabled by default (suggested interval: 30 minutes). It sends coordinated guest
neighbor requests while the dashboard is closed and retains deduplicated SNR
history in the existing repeater statistics files. This does not change passive
recording. Compatible repeaters can supply hardware-independent firmware SNR
aggregates through `0x70`; standard repeaters retain legacy last-heard monitoring.
See [neighbor monitoring](docs/v5-neighbor-snr.md) and
[firmware aggregate integration](docs/v5-averaged-snr.md).
**Read now** performs one asynchronous neighbor SNR collection for the viewed
managed repeater, including with monitoring disabled, without changing the
automatic interval or schedule.
Main sections and Statistics views use independent accordions; telemetry charts
remain visible inside expanded Repeater Management.

See [passive statistics storage and limitations](docs/v5-repeater-statistics.md)
and [visualization and scope interpretation](docs/v5-statistics-visualization.md).
The performance correction and measured scale results are documented in
[Statistics performance report](docs/v5-statistics-performance.md).
The service-context correction is described in
[Statistics worker isolation](docs/v5-statistics-service-context.md).
Recording/status stay in the application; at most one temporary read-only worker
calculates a saved view, with no radio access.

## Run locally for review

Python 3.12+, Node.js for UI tests. From this checkout:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest
MESHCORESTATION_DATA_DIR="$PWD/data-v5" MESHCORESTATION_HOST=127.0.0.1 MESHCORESTATION_PORT=8050 .venv/bin/python -m meshcorestation
```

Choose the USB serial port in Companion Settings. Without hardware, the dashboard,
preferences, saved history and known-repeater map remain available; hardware
operations show an offline/error state. Run only one station process against a given USB device or data directory. No live radio success is inferred from mock tests.

```bash
.venv/bin/python -m pytest -q
npm install --no-save --package-lock=false jsdom playwright@1.56.1
for file in tests/*.cjs; do node "$file" || exit 1; done
.venv/bin/python -m scripts.check_install
```

The isolated browser fixture uses synthetic history and an in-memory Companion;
it never opens a serial port or sends RF:

```bash
npx playwright install chromium
PYTHONPATH=. .venv/bin/python tests/browser/serve.py
# In a second terminal:
node tests/browser/v5_milestone.cjs
node tests/browser/v6_localization.cjs
```

See [milestone validation and limitations](docs/v5-milestone.md). Publishing,
committing, pushing or deploying requires separate explicit authorization.

The **Repeater Statistic Comparison** main section stores timestamped change
notes and compares equal 24h/7d/30d windows using saved SNR and passive observations.
It shows paired-neighbor median dB changes and coverage-aware traffic summaries,
with explicit missing/future-data warnings. Journal timestamps are server-assigned;
recording a change does not transmit a command. See [comparison semantics and limits](docs/v5-repeater-comparison.md).
Voltage and temperature charts now use clean lines with temporary hover/tap/keyboard
selection markers; historical telemetry and sampling remain unchanged.


## Room Server

The Room Server accordion below Bot restores V4.4.1's four independent encrypted
MeshCore rooms using the existing Companion. New rooms start disabled and require
a password. Existing `rooms.db` identities, passwords, participants, messages,
replay protection, client synchronization state and bot-room selection are reused.
No V4 application-database migration is required or performed.

Rooms continue running while the dashboard is closed. Administration supports
QR/contact links, participant Read/Write permissions, the latest 100 messages,
local posting, and selecting an enabled room for configured Bot commands. Room
commands use shared persistent Command History; room membership grants no repeater
or host administration. Scheduled battery reports can follow the bot chat/room or
use an explicit enabled room or private Companion channel, without silent fallback.
Queued room replies/reports are not confirmed recipient delivery.

See [Room Server setup, firmware requirements, backups and troubleshooting](docs/room-server-development.md).
