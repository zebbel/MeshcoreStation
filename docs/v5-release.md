# MeshcoreStation 5.4.0 — Statistics Coverage and Interface Improvements

Known identities are ingested before chart rendering and labels update locally
when additional names become available. Prefix ambiguity safeguards remain.
Healthy queued packet processing no longer breaks coverage. Real losses,
disconnections, write failures and clock changes remain gaps; historical unknown
periods are not backfilled. Boundary-hour coverage uses actual elapsed duration.

Packet distribution displays individual recorded MeshCore types and numeric
reserved codes. Advertisement origins remain separate from flood-path evidence;
existing direct-route, ambiguous and uninterpreted TRACE exclusions remain.
Hourly bars are solid and borderless; coverage remains in tooltips/details and
unknown intervals remain hatched.

The neighbor map is square and resizes on expansion. Show one-way connections
defaults on; switching it off locally hides red lines/arrows/exclusive markers
without changing counts, zoom or stored observations. No radio requests result.
Statistics controls share a responsive desktop row. Monitoring controls and
Recording Details are independently collapsed with compact visible summaries.
Monitoring configuration, scheduled collection and saved histories are preserved.

V5 remains a prerelease. V3 main and V4 are unchanged. Publication remains gated
on Python/JavaScript, fresh-install and Chromium desktop/mobile validation.
