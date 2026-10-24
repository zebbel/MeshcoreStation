# Repeater Performance

Open Repeater Optimizer → Repeater Performance, above Repeater Statistics. All four
subsections share the managed repeater selection and dashboard appearance. The new
view loads local saved data on opening, on period/marker selection, or when Refresh
saved data is pressed. Closing the subsection or its parent cancels/ignores obsolete
responses. There is no interval, background polling, remote request or radio command
from this view. To collect a fresh analyzer snapshot, use Repeater Network Monitoring
and its existing on-demand/five-minute-cache/Refresh Now behavior. An open Performance
view rereads local history after a monitoring refresh finishes.

## What the four indicators mean

- **Mesh Activity:** Companion packet copies whose observed paths include the
  selected repeater, plus separately labeled analyzer rolling relay counts.
- **Network Reach:** neighboring repeaters and confirmed bidirectional observations
  reported in the saved analyzer snapshot. Optimizer neighbor receptions appear as
  a separate series; reception alone does not prove bidirectional communication.
- **Mesh Contribution:** distinct observed packet identifiers and route patterns,
  alongside all received Companion network packets as context. Packet identifiers
  are not proof of delivered messages. Counts from different stores are not added.
- **Data Quality:** latest observation time (Recent means within the past hour), saved analyzer intervals, missing data
  and uncertain path matches. Recent observations can still be incomplete.

These are measurements of observed involvement, not arbitrary performance scores,
quality rankings or verified delivery-success rates. Short path hashes can collide;
known ambiguous matches are excluded. Proper names use the shared full-key name
resolver; unknown names and ambiguous prefixes retain their safe fallbacks.

## Charts and source coverage

Choose 24 hours, 7 days or 30 days. Charts use hourly, six-hourly or daily display
buckets respectively. The first/last bucket can be partial. Companion values are
packet counts within the displayed interval, not rolling totals. Analyzer and
optimizer curves show the latest saved measurement in each display bucket. Blank
intervals mean missing observations, never proven zero activity. Hover points or
open Show measured values for timestamps and values. Vertical lines mark recorded
changes; click/tap a line or use its keyboard focus, or select Compare in the journal.

The managed repeater's Repeater Statistics observations are preferred for each
requested window, including when the separate local Optimizer is disabled. If no
such observations exist, Optimization Analysis's network-wide stream is filtered
using its existing collision-aware path policy. These sources are **never added**
together. The chosen source is displayed; comparisons warn if sources differ.
Companion counts describe received observations only. Historical collector uptime
was not recorded, so uninterrupted coverage cannot be certified from packet rows.
Existing local retention, pauses, storage limits and missing receptions cause gaps.
No new Companion collection worker, subscription or optimizer activation is added.

## Local change journal

Log Change accepts 1–500 characters and either automatic current server time or a
manual browser-local date/time. Timestamps are stored as Unix instants; displays
use the dashboard date/time policy. Equal-window comparisons use elapsed 24-hour
days, including across daylight-saving changes. Text-only edits preserve the
original timestamp exactly. Saving, editing and deleting annotations changes only
the local journal; it never configures, contacts or transmits to a repeater.

Readback-verified configuration audits with matching requested/actual values
create markers automatically. Existing verified records are backfilled on opening.
Pending, failed and mismatched readbacks do not become verified-change markers.
Automatic markers retain the original audit time and values in details. Editing a
marker changes its annotation/time only, not the protected configuration audit.
Deletion retains a tombstone so backfill cannot recreate a deleted marker.

Markers are permanent until individually deleted or the managed repeater is
explicitly removed. Removal invalidates older requests and backfill so deleted history cannot be restored
by an in-flight operation. Re-adding the repeater starts a fresh journal. Markers
are not aged out with measurements or deleted when the
separate Optimizer history is reset/cleared. Keep the usual data-directory backup
if the journal is important. Repeater removal's confirmation includes this data.

## Before/after interpretation

Select 24 hours, 3 days or 7 days before and after a marker (7 days by default).
Windows have the same elapsed duration and meet at the marker. Future portions of
an after-window remain incomplete; measured values are not extrapolated. Tables
show measured values, absolute differences and percentage differences. Percentages also wait until both requested windows have elapsed. Missing
values and zero baselines have no percentage; they do not imply a zero change.

Companion packet/route counts use exact window boundaries. Analyzer comparisons
use fully contained, non-overlapping rolling **1h** samples, spaced at least an hour
apart, and report their mean rather than a summed traffic total. Samples straddling
the change are excluded. Rolling 24h counts are displayed as current saved context,
not used for before/after totals. Reach and optimizer neighbor means are sampled
observations, not time-weighted network guarantees. Sample counts expose sparse or
uneven coverage; neighboring changes are listed as overlap warnings. Gaps, retention
and unrecorded uptime limit interpretation even where numbers are available.

A higher/lower count describes observed activity, not whether a change was good or
bad. Correlation does not prove that a configuration change caused an improvement.
Observer coverage, traffic mix, other logged/unlogged changes and external network
conditions can differ between windows. Recommendations are never applied here.

## Storage and external availability

`data/repeater-performance.db` stores markers and necessary analyzer measurements
(no packet bodies, session tokens or duplicate path histories). Successful complete
analyzer refreshes each save a measurement using the original retrieval timestamp.
Only duplicate timestamps from rereading the same cached response are ignored. Cached reads do not advance it. Snapshots survive
five-minute cache replacement; failures never become zero-traffic samples. Initial
opening can import an existing cache snapshot but cannot reconstruct earlier data.

Measurements are bounded to 400 days and a shared maximum of 250,000 rows, retaining
the newest samples. These limits can remove old intervals, which then appear as
gaps. The permanent marker journal has no automatic age-based deletion. Existing
Companion and optimizer records keep their own retention/storage settings and are
queried in place; historical detailed data cannot be reconstructed after removal.
This is an additive database file; existing V4 databases are unchanged and older
versions can ignore it. History-write failure does not disable monitoring, but is
reported. Provider access controls, timeouts, cooldowns and stale-cache warnings
remain unchanged. Live access depends on the provider and deployment connectivity.
