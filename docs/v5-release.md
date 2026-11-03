# MeshcoreStation 5.3.0 — Neighbor SNR Monitoring and Dashboard Accordions

Repeater Management resolves neighbor prefixes against the complete known repeater
registry on Refresh, Load more and every page. Unique identities carry their full
public key to the shared name display; collisions and unknown prefixes are explicit.
Names are resolved locally without extra radio requests.

Repeater Statistics adds opt-in automatic neighbor SNR monitoring per managed
repeater, disabled by default with a suggested 30-minute interval (5–1440 allowed).
The worker runs while the dashboard is closed, shares the existing control lock,
paces requests, retrieves neighbor pages, skips disconnected Companions and avoids
immediate retries. Settings and next due times persist; shutdown/configuration and
membership changes cancel or invalidate queued work. Blank-password guest access
and an existing Companion repeater contact are required.

Raw polling responses and deduplicated measurements are retained in each existing
repeater statistics database. Overlapping equal-SNR last-heard estimates count once.
Neighbor SNR — Average shows separate identified-neighbor means, valid samples and
estimated Last Heard, with unknown/ambiguous prefixes separate. No reception IDs or
packet-delivery rates are invented. Original histories remain preserved.

Bot, Management and Statistics are exclusive main accordions. Statistics has eight
exclusive visualization subsections in the requested order, initially collapsed.
Global Statistics controls remain visible. Local expansion resizes saved maps and
charts without initiating radio requests or extra saved-view calculations. Main
panels use 16 px spacing. Voltage and temperature charts are always visible inside
expanded Management and retain the shared history selector and interactions.

Passive recording, current V5 data, telemetry, Bot, authentication and protected
configuration readback are preserved. Schema additions are non-destructive. No
automatic historical deletion is introduced. See docs/v5-neighbor-snr.md for timing,
identity and deduplication limitations.

Validation uses focused simulated-radio/storage tests, Python and JavaScript
regressions, fresh-install smoke and the existing Chromium desktop/mobile release
gate. Physical repeater guest access and firmware behavior still require actual
hardware confirmation; the test fixtures send no mesh traffic.

V5 remains a prerelease. V3 main and V4 v4.0.0 remain unchanged.
