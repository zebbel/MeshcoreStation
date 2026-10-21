# Repeater Optimizer · Specification / implementation (3.0.3rc2)

## Operation

The Repeater Optimizer replaces the old Recommendation Advisor tab in Repeater
Management and analyzes only flood.max and flood.max.unscoped. Repeater role is
stored per repeater: local, regional connector, hybrid or unknown.

Opening the screen, fetching or analyzing observations, changing role,
saving storage settings and comparing history never transmit over LoRa.
Manual "Read flood settings" and "Read neighbors now" buttons initiate radio
requests. Manual "Apply" requires an explicit selection, administrator
confirmation, preflight reads and verified write-back.

Neighbor polling is Manual by default. The user can opt in to 24h or 12h per
repeater. Each scheduled attempt reads only one page (max 15 entries), uses
the companion's existing ACL with a blank login, and is NOT retried or
caught up after downtime. No admin password or browser token is stored.
Changing schedule is authorized through the live admin session, without
radio traffic.

## Passive statistics and disk protection

From the RX_LOG_DATA event stream on the MeshcoreStation companion,
the network-wide collector records every suitable flood packet, even if
the chosen repeater is absent from its path. Metadata: timestamp, kind,
scope classification, path hash size and encoded route, hop count, payload
fingerprint, optional RSSI/SNR. It stores no message text or payload data.
Hash collisions and missing receptions are always possible.

Default detailed retention is 60 days, daily counts 365 days, neighbor
snapshots 90 days. The 200,000-observation cap has been removed. The
detailed database is budgeted to 3072 MiB by default; the reserve of
4096 MiB free disk space protects the Pi. All limits are configurable.
SQLite can reuse deleted pages even when file size does not immediately
shrink. Ingestion pauses on insufficient space.

## Analysis

Two independent findings cover scoped flooding (flood.max) and unscoped
flooding (flood.max.unscoped). Minimum evidence includes 3 active days,
enough matching samples, low route-hash ambiguity, known selected repeater
role, and a recent complete neighbor snapshot.

Candidate reductions are experimental: p90 hop count + a role-dependent
safety margin, never below the maximum route length already observed in
the sample. No candidate is offered if evidence is inadequate or the
candidate is not below the current manually read value. This does NOT
prove reachability or optimize the entire German mesh. A regional bridge
may need more hops than the companion can observe.

German scoped forwarding practices are context, never fixed universal
values. Lower unscoped limits may reduce flooding while also removing
legitimate channel or discovery reachability.

## Before and after

For verified flood changes compare the 24-hour preceding window with
24 hours starting one hour after the change. Ratios for repeated payload
fingerprints, unscoped and advert traffic are reported only if both
periods have enough, reasonably comparable observations. They are
descriptive, not proof of improved delivery or causality. Overlapping
changes are flagged.

The registered web endpoints are /repeater-optimizer and
/api/repeater-optimizer. Old advisor routes are not registered.

## Release rules

Only publish after explicit instruction; check main and merge updates
into the feature branch first. Keep stable base version aligned with
main and increment only the rc number.


## UI cleanup and history deletion

The optimizer's embedded screen no longer shows a separate "Back to
Configurations" control or the introductory radio-policy warning. Button
labels no longer include "LoRa"/"no LoRa" suffixes; existing radio-request
restrictions remain unchanged.

Database budget and free-space reserve are presented in GB, allowing
quarter-GB steps, while existing values and storage validation remain
stored internally in MiB: 3 GB displayed is 3072 MiB, and 4 GB is 4096 MiB.

"Clear verified changes and comparisons" requires explicit user confirmation
and current local administrator authorization. It deletes only verified
flood.max / flood.max.unscoped changes for the selected repeater. The
before/after calculations are derived from these change records, so they
disappear as well. Passive packet observations, neighbor snapshots,
other repeaters, pending/failed writes and unrelated setting history remain.
No LoRa transmission is triggered by history deletion.


## Neighbor prefix compatibility fix (unpublished draft)

MeshCore Python v2.3.14 defaults to 4-byte repeater neighbor prefixes,
represented by 8 hex characters. The original snapshot parser rejected
prefixes shorter than 12 hex characters and silently saved zero rows for
valid results. The corrected parser accepts whole-byte hex prefixes
(2–64 characters) without falsely resolving them to full identities.
If the radio response reports or contains neighbors but parsing yields
zero entries, the app rejects the snapshot rather than mislabeling it
a verified empty neighbor list.

Snapshot display now distinguishes entries saved versus the repeater's
reported total, shows saved prefixes with SNR and last-heard age, and
flags old zero-entry snapshots as unreliable when the repeater reported
a nonzero count. Re-reading is never triggered automatically by this
fix; it requires the existing manual button or separately opted-in
scheduled polling. Existing old snapshots remain unchanged in storage.


## Neighbor persistence visibility and stale embedded view (unpublished fix)

The Status and Repeater Optimizer tabs use the same LoRa neighbor request.
Previously the optimizer iframe only fetched local snapshot history on its
initial load. A later Status read could store new neighbor entries without
refreshing the still-loaded optimizer, leaving "0 listed" in view.

Returning to Optimizer now triggers a local HTTP-only snapshot refresh. A
"Refresh stored snapshots" button also re-reads the local database without
LoRa. Each manual remote neighbor read returns a persisted snapshot receipt
(ID, received entries, stored entries, repeater-reported total) verified by
reopening the SQLite database. Status displays this receipt; Optimizer
checks it against its new GET response and warns on a mismatch. Neither
local refresh nor receipt verification transmits any additional LoRa requests.

## 3.0.4rc8

Repeater Optimizer uses the shared dashboard stylesheet and follows the same
light/dark preference. Merged main 3.0.4, including daily battery reports using
the last stored reading.

## 3.0.5rc1 · Integration with main

The optimizer branch now includes the MeshcoreStation 3.0.5 dashboard,
room-server and multi-repeater backend. Per-repeater passive subscriptions
are combined with the optimizer's independent network-wide metadata capture,
disk budget and neighbor snapshots. Removing a managed repeater also removes
its stored optimizer role, scheduled polling, snapshots and audit history.
Network-wide observations remain because they are shared evidence.

Analysis remains local and passive. Manual radio reads, verified writes,
and explicitly opted-in 12h/24h neighbor polling retain their prior safeguards.

## 3.0.6rc1 · Known repeater downtime

In Repeater Optimizer, **Known repeater downtime** records a completed offline
period using the browser's local timezone. Enter the time it went offline and the
time it returned, then select **Record downtime**. Records are per repeater and
require the existing administrator session. This only changes local metadata;
it sends no LoRa command. Silence is never automatically classified as downtime.

Within the selected analysis window, overlapping records are combined and their
observations excluded from packet counts, path distributions, active days and
charts. The optimizer shows the excluded hours, requires at least 72 remaining
hours as well as its normal traffic/active-day checks, and requires a neighbor
snapshot newer than the recorded outage. Those remaining hours are not proof of
continuous uptime: unrecorded outages and unseen packets remain unknown.

A before/after comparison overlapping recorded downtime in either 24-hour sample
or the one-hour settling interval is unavailable. It is not shortened or
rescaled, which could misleadingly attribute outage effects to a setting change.
Old comparisons outside these periods remain available.

Packet observations are retained. **Remove entry** corrects an incorrectly marked
period and permits reanalysis of those records. Overlapping entries count time
only once; remove all overlapping entries to fully restore a period. Maximum:
100 records per repeater. Removing the managed repeater also removes its downtime
records. An ongoing outage can be entered once its end time is known. Ordinary
battery history and general dashboard statistics are not rewritten by this feature.

This release includes main 3.0.6 and its repeater map clustering. Known downtime can now be excluded from optimizer evidence and before/after comparisons.

## 3.0.7rc1 · Integration with main

Includes main 3.0.7 with reduced repeater map clustering distance, preserving optimizer functionality and known-downtime exclusions.
