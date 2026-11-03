# MeshcoreStation 5.2.4 — Repeater Statistics UI Enhancements

Neighbor balloons keep the repeater name and each directional count on one line,
with left-aligned labels and right-aligned values. Exceptionally long balloon
names use an ellipsis; detailed touch/click popups retain full names.
We hear is incoming toward the selected repeater; They hear is outgoing.
These counts describe observed packet routes, not RF reception confirmations.

Hop Count Ranking now uses side-by-side blue unique-packet and orange repeated-
reception columns, ordered numerically with exact counts retained in details.
Three saved-data views have been added:

- Most Active Neighbors: top 20 neighbors by combined incoming/outgoing route
  observations, including unmanaged neighbors and neighbors without coordinates.
- Traffic Activity Heatmap: local calendar days and hours, explicit observed
  traffic, complete recorded zeros, incomplete lower bounds and unknown gaps.
  Fractional-offset time zones and repeated/skipped daylight-saving hours are
  handled without inventing observations.
- Packet Type Distribution: group messages, direct text, advertisements and other
  packet types, with counts and percentages. Full-key advertisement origins are
  explicitly separated from flood-path evidence and never claimed as forwarding.
  Unique, repeated and unidentified counts remain available in details.

All views follow the independent managed-repeater selector and 24h/7d/30d filter.
New aggregates reuse the existing one-pass classification and compact disposable
SQLite facts. No additional raw-route scans, radio requests, active polling,
history deletion or source schema migrations are introduced. The passive collector,
isolated worker, caching and request budgets remain unchanged.

Local validation: 222 Python tests, 18 JavaScript suites, fresh-install smoke,
JavaScript syntax and whitespace checks passed. The scale suite covers up to
100,000 observations; additional synthetic local measurements took 3.77–4.46s at
100,000 observations across all periods, within the unchanged eight-second budget.
These timings are not a device-specific performance guarantee. The existing
Chromium desktop/light and mobile/dark acceptance gate runs in CI before publication.

V5 remains a prerelease. V3 main and V4 v4.0.0 are unchanged.
