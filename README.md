# MeshcoreStation V5 — 5.0.0 milestone 1

A fresh Companion-connected channel bot and repeater-management application.
Development branch: **`V5`**. Version **5.0.0** is the first V5 milestone prerelease.
V3 `main` and V4 `v4.0.0` are separate and unchanged. V4.4.1 supplies the protocol and dialog
reference; the supplied V5 design package supplies the dashboard arrangement.

The first row has exactly **MeshcoreStation**, **Connected Companion**, and
**Known Repeaters**. The cards stack in that order on mobile. The V4 logo,
theme variables, typography and fixed footer are retained. The footer shows
version/branch, connected firmware/build or unavailable, and an asynchronous
installed-branch update check. V5 updates cannot switch to an incompatible branch
and never install automatically.

Below the cards, **Bot** contains only **Bot Settings** and **Command History**,
independently collapsible. **Repeater Management** follows as a separate section.
There is no Optimizer, Analyzer, Performance, Network Monitoring or Room Server.

## Fresh storage only

Use a **new, empty V5 data directory**. V3/V4 databases are not migrated or
supported. The application refuses a main database containing the former
known-repeater registry rather than modifying it.

| File | Ownership |
| --- | --- |
| `meshcorestation.db` | Application display/serial preferences, bot channel and commands, reply scopes, persistent command/reception/reply history, managed membership and local telemetry configuration/history, management audit |
| `knownRepeaters.db` | The single canonical repeater registry, full public-key identity, name/location, discovery metadata, actual advertisement counts and timestamps |

The main database has **no persistent repeater registry**. Included protocol
readers access a read-only temporary view of the attached canonical registry;
the view stores no identities. Contact imports do not increment advertisement
counts. Actual advertisements do. Removing management or deleting a hardware
contact leaves the saved known identity intact. Both files are created by the
running user with private permissions. SQLite may create ordinary WAL/SHM journal
sidecars; these are not additional application databases.

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
- Known Repeaters: saved count and map work while disconnected. Only valid saved
  coordinates are plotted; ambiguous short path hashes remain unidentified.

## Run locally for review

Python 3.12+, Node.js for UI tests. From this checkout:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt pytest
MESHCORESTATION_DATA_DIR="$PWD/data-v5" MESHCORESTATION_HOST=127.0.0.1 MESHCORESTATION_PORT=8050 .venv/bin/python -m meshcorestation
```

Choose the USB serial port in Companion Settings. Without hardware, the dashboard,
preferences, saved history and known-repeater map remain available; hardware
operations show an offline/error state. Do not run V3/V4 and V5 against the same
USB device or data directory. No live radio success is inferred from mock tests.

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
```

See [milestone validation and limitations](docs/v5-milestone.md). Publishing,
committing, pushing or deploying requires separate explicit authorization.
