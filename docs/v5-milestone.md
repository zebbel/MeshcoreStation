# V5 first milestone review

Version: **5.0.0**. Local branch: **V5**, based on the V4.4.1 reference commit
`bb9056f6bf63e58887b811e9eb3507a95b877788`. No V3/V4 compatibility layer or migration.
The two supplied design archives are identical; the HTML and desktop/mobile/dialog
references were inspected before implementation. Example records from the design
were not added to the production database or dashboard.

## Architecture

`Database` initializes only the two V5 stores. Canonical repeater writes go through
`storage/registry.py`, keyed by complete lowercase public key. Main connections
attach `knownRepeaters.db` read-only and expose a connection-local temporary view
for shared V4 readers. Membership and telemetry stay in the main store. Display
preferences are SQLite records, not a JSON settings file. Main tables never store
hardware channel slots, private channel keys, device-contact lists or passwords.

The retained V4 protocol components have explicit V5 wiring. No imports or routes
activate Optimizer, Analyzer, Room Server, passive analysis collection or scheduled
neighbor polling. The radio runtime owns one connection and cancels outstanding
work on reconnect/shutdown. Telemetry monitoring is an explicit opt-in (default
settings do not send telemetry or reports). Guest management reads only happen
on user action; configuration writes require administrator access, current values,
confirmation and readback. A readback mismatch is reported as a failure, with a
safe local audit entry. Secret values are omitted from audits and HTTP results.

Retries retain the V4.4.1 behavior: original + one for zero hops, original + up to
three for multi-hop, none for unknown hops. Delay is the larger of the radio-derived
protocol timeout and the 20/30s minimum, plus independent 0–5s jitter. Authenticated
forwarding cancels multi-hop retries; it never proves receiver delivery. All
retry limits, locks, channel/scope preservation, queue checks and airtime bounds
remain covered by regression tests.

## Validation

The Python suite includes the applicable V4 clock, command, template, reception,
reply/retry, console and permission tests, adapted to the fresh V5 boundary, plus
V5 foundation tests. Checks cover:

- Exactly two application DB files, private ownership, no main-store registry.
- Canonical contact upserts versus actual advertisement counts; full-key validation.
- Contacts duplicate/identity checks, delete/add validation and failed readback.
- Channel capacity/revisions, private-key nonpersistence, Bot selection/deletion protection.
- Companion setting validation, current-value conflicts and rejected readback.
- Mocked connection/reconnection and orderly teardown; no physical USB involved.
- 200/400-row paging, filters, ordering, and history survival after reopening storage.
- Offline registry map, membership removal without identity deletion, app preferences.
- Protected help, action templates, scopes, command deduplication and retry semantics.
- Guest/admin configuration permissions, confirmations, readback and secret-free audit.
- V5 route exclusions and exactly three cards / two nested Bot subsections.

JavaScript regression checks cover existing maps, marker clusters, telemetry charts,
reception/reply details, managed selection and safe management console interactions.
A dedicated V5 test exercises actual dialog scripts in JSDOM: separate app settings,
Companion-only serial controls, Contacts Manage, protected Bot channel, secure key
generation, both Commands entry points, scopes, and pause-on-parent-collapse history.

The fresh-install smoke runs in an isolated temporary directory and checks
imports, two-store creation and included/excluded route registration without RF.
The V5 workflow repeats these checks and runs actual desktop/mobile Chromium
acceptance before the explicitly authorized 5.0.0 prerelease can be published.
Publication is gated on successful validation; deployment is not included.

## Remaining verification and limitations

- Physical Companion/repeater behavior and RF delivery have not been tested here.
  Hardware/firmware-dependent unsupported responses remain unavailable; mock data
  is never presented as proof of live operation.
- Actual desktop/mobile rendering and modal checks run in the Chromium CI gate.
  Local Playwright has no Chromium executable; local test results below do not
  include browser acceptance. The two-case fixture uses no live radio hardware.
- Background OSM tiles depend on external availability. Saved coordinates and
  marker/path evidence do not constitute verified direct RF links.
- Remote firmware capabilities constrain available management fields. Password
  changes can be acknowledged but are not read back as cleartext. CLI timeouts
  remain uncertain, with a two-minute cooldown and no automatic write retry.
- Companion firmware flashing, OLED editing and other unrelated V4 features are
  outside this milestone. Connected firmware identity is still shown in the footer.
- Update checks can report that the service/branch is unavailable; no update is
  installed automatically. Updates
  remain constrained to `V5`, use existing confirmation/backup/rollback mechanisms,
  and do not provide a path to open these databases with V3/V4.

The 5.0.0 prerelease is authorized for publication on V5 only. V3/V4 branches
are not publication targets. No deployment or hardware operation is performed.

## Local results (2 November 2026)

- Python regression suite: **158 passed**.
- JavaScript regression suites: **15 passed**, including the dedicated V5 host/
  Contacts/Channels/history interaction suite.
- Isolated V5 fresh-install smoke: **passed** (two stores, routes and imports,
  no radio opened).
- `git diff --check`: **passed**.
- Actual desktop/mobile Chromium acceptance: required separately in CI before release.
- Live USB/RF hardware: **not tested**. Guest/admin/readback/timeout and reconnect
  coverage use protocol fakes.
