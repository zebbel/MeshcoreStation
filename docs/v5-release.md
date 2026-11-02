# MeshcoreStation 5.1.0 — Repeater Statistics

Adds a separate expandable Repeater Statistics section below Repeater Management,
with an independent managed-only selector, recording health, saved observation
count and last-recorded timestamp. No charts or performance analysis are included.

Passively collects Companion RX_LOG_DATA for every managed repeater, independently
of Bot channel, UI selection and telemetry settings. Uses bounded asynchronous
queues and off-loop batched SQLite writes without extra radio traffic.

Relevant observations create private WAL databases beneath
`data/repeaterStatistics/<full-public-key>.db`. Keeps original payload/metadata,
RSSI/SNR, route/scope evidence and attribution uncertainty. Collision matching uses
all known repeater keys; repeated receptions remain separate. A reception involving
multiple managed repeaters is recorded in each corresponding database.

Managed removal rejects queued observations and preserves statistics history.
Re-adding resumes appending without restoring stale queued packets. Handles queue
overflow, write errors, reconnects and low disk space without automatic deletion.

Validation: 189 Python tests, 16 JavaScript suites, isolated fresh-install smoke,
and the existing Chromium desktop/light and mobile/dark acceptance gate, extended
with a focused Statistics status/selector check.

V5 5.0.0 data is preserved through an additive membership-cutoff column. Core
identity remains authoritative in knownRepeaters.db. No V3/V4 migration is provided.
This remains a prerelease; physical Companion/RF operation is unverified. Direct
routes and TRACE candidates are uncertain evidence, not confirmed forwarding or
verified RF links. In-memory queued data may be lost on abrupt shutdown; dropped
or unavailable observations must not be interpreted as zero activity.

V3 main and V4 v4.0.0 remain unchanged. No deployment is performed.
