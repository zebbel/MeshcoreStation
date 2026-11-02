# MeshcoreStation 5.0.0 — first V5 milestone

Fresh V5 dashboard with three top cards, nested Bot Settings and Command History,
and separate Repeater Management. Retains V4 Contacts/Channels interactions,
protected Bot channel selection, command templates/scopes, persistent history,
hop-aware reply retries, guest/admin management and configuration readback.

Uses exactly two fresh application databases: meshcorestation.db and
knownRepeaters.db. Known repeater identities remain available while disconnected.
Includes application preferences, branch-specific update checking and fixed footer.

Validation: Python and JavaScript regression suites, isolated fresh-install smoke,
and actual Chromium desktop/light and mobile/dark acceptance gate.

This is a prerelease. Use a new empty V5 data directory: no V3/V4 migration or
compatibility is provided. Physical Companion/repeater and RF delivery are not
verified by the protocol fakes. Hardware-dependent failures remain explicit.
Optimizer, Analyzer, Performance and Room Server are excluded from this milestone.
V3 main and V4 v4.0.0 are unchanged. Nothing is deployed automatically.
