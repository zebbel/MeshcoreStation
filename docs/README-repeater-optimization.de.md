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
