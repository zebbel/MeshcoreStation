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

## Repeater Statistics development follow-up

A managed-only passive collection backend and minimal independent dashboard section
are prepared after the 5.0.0 milestone release. The two core stores remain unchanged
in ownership; relevant managed-repeater observations now create separate WAL files
beneath `repeaterStatistics/`. No charts, Analyzer or performance features are added.
See [collection architecture and limitations](v5-repeater-statistics.md).

This follow-up is included in the authorized **5.1.0** V5 prerelease.
Publication is gated on regression, fresh-install and Chromium acceptance checks.
Its tests cover all client packet types, membership removal/re-addition (including
queued packets), full-registry collisions, repeated receptions, multi-target writes,
disk/database failures, queue overflow, off-loop writes, persistence, safe status
reads and independent status-view interactions. Physical radio reception remains
unverified. The release workflow runs the existing desktop/light and mobile/dark browser
acceptance with a focused managed-only Statistics status check.

Follow-up validation: **189 Python tests passed**, **16 JavaScript suites passed**,
isolated fresh-install smoke passed, and `git diff --check` passed. The fresh
installation still creates only the two core databases until a relevant managed
observation arrives. No RF commands were sent by these tests.


## Statistics visualization — 5.2.0

The existing Statistics section now includes a shared 24h/7d/30d period,
Observed Neighbor Map, Messages per Hour, Hop Count Ranking and MeshCore Regional
Traffic Ranking (including Unscoped). Aggregation is SQLite-based and uses saved
observations only. Configurable region names/keys are local display attribution
settings, separate from Bot reply scope configuration. Healthy local collection
windows support future gap detection; older history without coverage stays unknown.
See [visualization semantics](v5-statistics-visualization.md).

Validation: 198 Python tests, 17 JavaScript suites, fresh-install smoke and a running
local HTTP fixture. JavaScript uses real Leaflet vector overlays with remote tiles
replaced for deterministic checks. The actual Chromium test includes chart/map checks and is a mandatory CI gate
before the authorized 5.2.0 prerelease can publish. Chromium is unavailable locally;
local test counts above do not include that browser run. Physical RF collection
is not verified here. V3/V4 are not publication targets.


## Saved-view performance correction — 5.2.1

The repeated wide-row JSON queries and shared browser deadline were replaced by
one source scan, compact disposable SQL facts, bounded route reuse and independent
status/view requests. Per-stage diagnostics, typed errors, a small invalidated cache
and calculation backpressure preserve status availability and passive recording.
The eight-second server budget is unchanged. No source history migration, deletion,
radio polling or extra radio request is introduced.

See [performance report](v5-statistics-performance.md) for root-cause evidence,
all sizes/periods, CPU/RSS measurements, changed files and limitations. The synthetic
2,292-row workload succeeds, but the device-specific field timeout was not reproduced
without the user's original database/hardware. This correction is included in the
authorized 5.2.1 prerelease; publication is gated on regression, scale, fresh-install
and Chromium validation. V3/V4 are not publication targets.


## Service-context classification timeout — 5.2.2

The user's actual 2,517-row query completes in 0.8568 seconds outside the service,
while its HTTP calculation still times out. A busy-interpreter reproduction shows
the threaded calculation failing during classify after 8.461 seconds, while one
isolated read-only worker completes in 0.173–0.204 seconds under the same modeled
contention. This identifies a reproducible failure mode; the particular busy
thread on the user's device has not been identified.

The saved view now runs in one bounded fresh worker interpreter. Recording/status,
radio handles and management remain in the application. Core eight-second query,
parent nine-second execution and browser ten-second saved-view budgets stay bounded.
Shutdown/timeout reap the child, source data/schema are preserved, and failure
diagnostics survive the default WARNING threshold. Actual-device confirmation is
still required after installation. See [service-context evidence](v5-statistics-service-context.md).

Local validation: 218 Python tests, 18 JavaScript suites and fresh-install smoke.
The authorized publication still requires the existing Chromium release gate.

## Statistics UI improvements — 5.2.3

Frontend changes on V5 add neighbor hover balloons and equivalent summaries in
existing tap/click popups: We hear is incoming toward the selected repeater;
They hear is outgoing toward the neighbor. Counts are saved route observations,
not RF reception confirmation or delivery acknowledgements.

Messages per Hour now uses side-by-side blue unique/orange repeated columns;
Hop Count Ranking uses stacked columns ordered numerically. Long hourly ranges
scroll with a fixed count axis. Unknown intervals remain hatched gaps, incomplete
counts are dashed lower bounds, and complete recorded zeros are labeled.
Unidentified receptions remain in expandable exact-count tables. The saved API,
worker, cache, recording and original histories are unchanged.

Local checks: 218 Python tests passed, all 18 JavaScript suites passed, and the
fresh two-database install smoke check passed. Focused real-Leaflet DOM tests cover
hover/leave/click summaries, actual SVG overlays, direction mapping, coverage,
24h/7d/30d rendering, numeric ordering, stacks and resize cleanup. The existing
Chromium desktop/mobile acceptance test was extended, but could not run because
Chromium is unavailable and its download did not complete. Actual desktop/mobile
visual verification remains outstanding. The user authorized publication as 5.2.3. The existing Chromium CI gate must pass
before the workflow creates the V5 prerelease.

## Statistics UI enhancements — 5.2.4

Neighbor balloons now keep names and each directional count on one line, with
left-aligned labels and right-aligned values. Exceptionally long balloon names
use an ellipsis; detailed popups retain full names. Hop categories now use grouped
blue unique/orange repeated columns rather than stacks.

The shared saved-data view adds Most Active Neighbors (top 20 directional grouped
bars, including neighbors without coordinates), a local-calendar Traffic Activity
Heatmap, and Packet Type Distribution. The heatmap distinguishes complete zero,
observed traffic, partial lower bounds and unknown gaps, including correct
fractional-offset and daylight-saving calendar boundaries. The donut separates
advertisement-origin evidence from observed flood-path evidence and retains unique,
repeated and unidentified counts in details. Unknown packet kinds remain Other.
All views share the independent managed-repeater selector and 24h/7d/30d filters.

Compact activity and packet-type aggregates reuse the existing one-pass source
classification and disposable SQLite facts. Original history, schemas, passive
collection, worker isolation, request budgets and cache behavior are preserved.
No radio requests, active polling or history deletion were added.

Validation: 222 Python tests, all 18 JavaScript suites, fresh-install smoke,
JavaScript syntax and whitespace checks passed. The scale suite covers 2,500,
10,000, 50,000 and 100,000 observations across all periods and recording during
aggregation. Additional local measurements: 2,500 observations took 0.073–0.078s;
100,000 took 3.77–4.46s across the three periods, below the unchanged 8s budget.
These synthetic local timings are not a device-specific guarantee. Real Leaflet
DOM tests cover marker summaries, direction mapping and preserved map overlays;
focused chart tests cover grouping, ranking limits, gaps, DST folds, empty states
and selector/stale-view handling. The existing Chromium acceptance test was
extended for the new views but has not run for these changes because local
Chromium is unavailable. Desktop/mobile visual verification remains outstanding.

Publication was explicitly authorized as 5.2.4. The existing Chromium CI gate
must pass before the workflow creates the V5 prerelease; main and V4 are unchanged.

## Neighbor monitoring and accordion dashboard — 5.3.0

Management neighbor names now use full-key results from the canonical registry,
with explicit ambiguous/unknown prefixes on all pages. A separate opt-in neighbor
SNR worker polls enabled managed repeaters without depending on UI selection or
passive recording. It reuses the control lock, paces page requests, persists due
times, and cancels or rechecks shutdown/configuration/membership changes. Raw
readings and conservative last-heard/SNR deduplication are saved in existing
per-repeater files. The new SNR table retains unidentified evidence separately.

Main sections and eight Statistics views are independent exclusive accordions,
initially collapsed. Their loaded controls/content are retained; opening local
Statistics views only resizes charts/maps. Hidden Leaflet maps initialize with a
finite view before fitting bounds when displayed. Management telemetry charts are
permanently visible within the expanded main panel. Main-section gaps are 16 px.

Local validation: 230 Python tests and 20 JavaScript suites passed; fresh-install,
syntax and whitespace checks passed. Simulated-radio cases cover pagination,
locking, timeouts, shutdown, disabled/removed/re-added repeaters, persistent
scheduling, deduplication, invalid data, historical filters and canonical names.
The Chromium desktop/mobile acceptance script was extended for accordion behavior,
local-only expansion, hidden-map resizing, spacing, telemetry and saved SNR means.
Publication is explicitly authorized through the standing handover instruction;
the existing CI gate must pass before creating the 5.3.0 prerelease. Actual-device
guest access/firmware behavior remains unverified. See [details and limitations](v5-neighbor-snr.md).
