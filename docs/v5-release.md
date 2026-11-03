# MeshcoreStation 5.2.3 — Repeater Statistics UI Improvements

Neighbor markers now show resolved names and directional reception counts on
hover: We hear is incoming toward the selected repeater; They hear is outgoing
toward the neighbor. Touch/click opens the existing detailed popup with the same
summary, timestamps and public keys. Counts describe observed packet routes,
not independently confirmed RF reception or delivery acknowledgements.

Messages per Hour uses side-by-side blue unique-packet and orange repeated-
reception bars. Long ranges scroll horizontally with a fixed count axis.
Hop Count Ranking uses stacked blue/orange columns ordered by numeric hop count.
Unknown coverage remains a hatched gap, incomplete counts are dashed lower bounds,
and complete recorded zero intervals are labeled. Unidentified receptions remain
in the exact-count tables without gray circles in the hourly chart.

Shared 24-hour, 7-day and 30-day filters, map interactions and ambiguity handling
are preserved. The passive collector, saved calculations, isolated statistics
worker, caching, timeouts and historical data are unchanged. No radio requests,
active polling, schema migrations or automatic deletion are introduced.

Local validation: 218 Python tests, 18 JavaScript suites, fresh-install smoke,
JavaScript syntax and whitespace checks passed. Focused tests cover directional
hover/click summaries using real Leaflet, grouped and stacked SVG columns, numeric
hop ordering, preserved unidentified counts, coverage gaps and responsive redraw.
Local Chromium is unavailable; the existing desktop/light and mobile/dark
Chromium acceptance gate runs in CI before this prerelease is published.

V5 remains a prerelease. V3 main and V4 v4.0.0 are unchanged.
