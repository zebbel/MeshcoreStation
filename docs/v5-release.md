# MeshcoreStation 5.6.2 — Regional Traffic Readability and Paired Bars

Fixes unreadable black region names and numerical labels on dark backgrounds.
The regional chart's nested SVG now uses scoped dashboard theme variables for
all text. Its responsive SVG sizing also applies inside the plot wrapper; wide
charts scroll inside their panel on mobile. Other chart and Leaflet styles are
unchanged.

Every region now has two separate horizontal bars on a shared numerical scale:
blue unique messages above orange repeated receptions. Both series remain
present regardless of the Show all messages (including duplicates) checkbox.
Zero counts are labeled without inventing nonzero traffic.

The checkbox defaults to unchecked. Unchecked ranks regions and calculates totals
and shares from unique packet digests within each region, while still displaying
repeated receptions for context. Checked ranks regions and calculates totals and
shares from all included confirmed receptions. Changing ranking mode immediately
updates order, totals and percentages without refetching data. Bar counts and
scale remain consistent. Tooltips support hover, keyboard focus and tap, with
exact unique, repeated, total and unidentified counts.

Unscoped, Unknown and existing regional attribution are preserved. Unidentified
payloads stay separate from unique/repeated bars while remaining included in
all-reception totals and the exact-count table. Ambiguous and unverified evidence
keeps its existing exclusions. No historical observation or database schema is
changed; packet deduplication, collection, caching and radio behavior are unchanged.

Validation includes 20 relevant Python aggregation tests, 24 JavaScript suites,
nested SVG theme checks, fresh-install smoke checks, and required full Python
regression plus Chromium desktop/mobile acceptance in the release workflow.
This remains a V5 prerelease. Branches main, V3 and V4 remain unchanged.
