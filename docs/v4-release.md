# MeshcoreStation 4.3.3 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.3.3` (prerelease, not latest stable). V3 main is unchanged.

- Added a fixed responsive dashboard footer with current year attribution,
  installed version/branch and connected Companion firmware/build. One page-load
  GitHub check targets the installed branch only. Update available opens the
  existing updater; explicit confirmation, backups, rollback and restart remain
  required. Unavailable services show a graceful status; nothing auto-installs.
- Optimizer history defaults to 24 hours, retaining longer periods, refresh
  selections and existing before/after comparison settings.
- Performance opens with saved observations immediately, then reuses the shared
  five-minute Analyzer cache or collects an expired/missing snapshot. Manual
  Refresh saved data keeps V4.3.2's forced-refresh behavior even inside the TTL.
  Cache/history, cards, charts, assessment and neighbor map stay synchronized;
  failed requests retain observations. Locking, timeouts, provider cooldowns and
  the existing twelve-hour collector remain. No continuous polling/radio traffic.
- Verified existing low-confidence filtering hides lines, markers and missing-
  coordinate entries immediately without any Analyzer request.

Focused checks cover automatic cache expiry, explicit refresh, retained failures,
footer current/available/error states, installed-branch handoff, updater safety,
24-hour defaults, and existing map filtering. Essential installation and existing
real-browser release checks remain; no enlarged screenshot matrix is introduced.
