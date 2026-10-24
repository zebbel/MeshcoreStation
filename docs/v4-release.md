# MeshcoreStation 4.0.1 — V4 branch prerelease

Branch: `v4.0.0`. Release tag: `v4.0.1` (prerelease, not latest stable).
V3 `main` remains unchanged.

Network Monitoring is available without an application activation setting. Opening
its subsection reads the last saved snapshot and refreshes missing/stale data.
The five-minute cache, Refresh Now, cancellation, response validation, conservative
retries, timeouts, 403/429 cooldowns and stale-data preservation remain intact.
No continuous polling or radio traffic is introduced. Provider restrictions and
usage conditions still apply; live integration is not verified by fixture tests.

Optimization Analysis and Network Monitoring now reuse Repeater Statistics'
visual components and dashboard variables. Analysis retains the same authenticated
management bridge, explicit confirmation, preflight checks and readback. Its
iframe grows/shrinks with content, follows the parent theme, and avoids a second
vertical scrollbar. Charts/maps remain responsive, and long tables scroll within
their own wrappers as needed.

The dashboard order, independent disclosures, managed-repeater selection and
separate local Repeater Optimizer switch are unchanged. There are no schema or
dependency changes; existing station, room and cache databases remain compatible.

README and current help files describe the activation-free on-demand behavior
and shared styling. Validation results are recorded below.

## Validation

- 481 Python tests passed in the isolated development environment.
- All 32 JavaScript/jsdom UI suites passed, including automatic monitoring loads,
  cache reuse, manual refresh, late-response isolation, inferred-observation labels,
  administrator actions, iframe growth/shrink, theme and message-origin checks.
- Shared CSS isolation, palette usage, responsive form/grid rules, table scroll
  wrappers, and existing 700/703/1,000/2,000 marker regressions passed.
- Installation smoke, fresh/restarted app HTTP checks, health version 4.0.1,
  activation-free mocked HTTP 403 handling, Python compilation, dependency check,
  installer shell syntax and diff whitespace checks passed.
- Rendered desktop/mobile verification remains pending. A local Chromium download
  returned an unavailable page rather than a browser archive; the cloud browser
  could not reach the local server and its security policy disallowed local files.
  No rendered browser, physical mobile or radio-hardware pass is claimed.
- Live Analyzer access remains unverified. Tests use the captured formats and mock
  failures; access restrictions are respected and cannot imply zero traffic.

No schema change or destructive migration is needed. All existing migration and
V3 data-preservation regressions pass. This release is published exclusively on
v4.0.0; main remains unchanged.
