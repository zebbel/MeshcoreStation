# MeshcoreStation 4.0.0 — dedicated V4 release

Target branch: `v4.0.0`. Release tag: `v4.0.0` (prerelease, not latest stable). The V3 `main` branch is not a publication target.

V4 rearranges the dashboard into Command History, Repeater Management, Repeater
Optimizer and Room Server below the two status cards. Optimizer groups Statistics,
Optimization Analysis and experimental Network Monitoring as independent, initially
collapsed subsections following the managed repeater selection.

Network Monitoring parses the eight real Firefox response bodies captured on
24 October 2026. It supports cache-first on-demand loading, five-minute persistent
snapshots, manual refresh, conditional reads and visible failure/stale states.
It is disabled by default pending authorized deployment access. A 403/Cloudflare
1010 response means unavailable, never zero activity. Fixtures do not verify live
integration; nonempty observer/direct-packet/beacon/sensor shapes remain unverified.

The integration creates a separate cache without rewriting V3 records. Existing
telemetry/reporting, passive collection, optimizer permissions and radio safety,
command paths, clustered maps, rooms, firmware and update behavior are retained.
Installation/updater version comes from the same `meshcorestation.__version__`;
branch selection and manual installer updates already follow the checked-out branch.

README, user guide, architecture, operations, management, branch switching and
external monitoring documentation describe V4 behavior. Specialized protocol and
firmware guides remain because their operating procedures still apply.

Local validation: **481 Python tests and all 30 JavaScript/jsdom suites passed**,
including the retained 700/703/1,000/2,000-map regressions. The fixture validator,
compile check, installer shell syntax, dependency check and installation smoke check
also passed. Fresh-data startup, repeat startup, Dash layout and health API checks
confirmed version 4.0.0 on v4.0.0 with Analyzer disabled.

The Python suite ran in a fresh isolated venv installed offline from locally
available wheels and repacked snapshots of this session's installed dependencies.
This validates isolation but is not a new package-index resolution. CI repeats the
suite using clean package installation on GitHub's runner. Existing V3 migration
regressions pass; the new separate cache does not rewrite station/room databases. Live Analyzer,
physical radio, physical mobile and native systemd installation are not verified
by fixture or unit tests.

The V4 release workflow repeats the full suite in a fresh GitHub Actions environment
and publishes only after validation passes. It creates the release/tag on the V4
commit, without changing main or marking V4 as the latest stable release.
