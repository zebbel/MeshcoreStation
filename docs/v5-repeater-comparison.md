# Repeater Statistic Comparison

The fourth main dashboard accordion follows Repeater Statistics and uses its own
managed-repeater selector. It starts collapsed and is mutually exclusive with
Bot, Management and Statistics. Opening it loads the saved change journal only;
no history calculation or radio request runs until a change is compared.

## Change journal

Select a managed repeater, enter a description and click Save Change. The server
records the current timestamp and full public key in meshcorestation.db. There is
no client timestamp or change-type input. Descriptions can be edited without
altering the recorded timestamp. Deletion requires confirmation and removes only
the journal row, never the repeater's statistics. Histories persist through restarts
and upgrades; removing managed membership does not cascade-delete journal records.
Rows are ordered by recorded time and ID, with 200-row pagination. Display times
follow the dashboard's date/time preferences and configured time zone.

Logging, editing and deleting changes do not transmit repeater commands or apply
configuration. A journal marker records the user's statement, not verification
that an antenna or firmware change actually took place.

## Equal historical windows

For recorded time T and duration D (24 hours, 7 days or 30 days), the comparison
uses [T-D,T) and [T,T+D). Boundary receptions and deduplicated SNR timestamps belong
to one window only. Explicit historical bounds reuse the existing aggregation.
Both reads share one read-only SQLite history snapshot and the same registry/
scope metadata, avoiding inconsistent results while collection continues.

The requested future endpoint is displayed in full, but source reads and recording
coverage are clipped to the calculation time. Future intervals are unknown,
not zero. Each window independently shows collection coverage, expected duration
and SNR samples. The snapshot timestamp and warnings identify preliminary results,
missing history, future periods and other changes overlapping the windows.

## Neighbor SNR

Only unambiguous full-key identities are matched across windows. Existing
last-heard/SNR deduplication is preserved; a repeated polling response is not an
independent reception. Per-neighbor means, sample counts and dB differences are
shown. The overall value is the median of paired-neighbor mean differences,
not a pooled or sample-frequency-weighted mean. Newly heard and before-only
neighbors are separate lists, with no synthetic SNR assigned to missing neighbors.
Unknown/ambiguous evidence is excluded from pairing and summarized in limitations.
Single samples remain visible but are flagged as insufficient history for reliable
trend interpretation. Source last-heard times are estimates, as in Statistics.

SNR sample availability is independent of passive recording uptime. Past expected
SNR sampling coverage cannot safely be reconstructed from today's monitoring
interval, so it is not invented. Disabled or unreachable monitoring may explain
missing measurements; missing neighbors do not prove RF communication is impossible.

## Supporting traffic and relationships

Each window shows observed flood-route neighbors, confirmed reception counts,
unique/repeated/unidentified counts, one-/two-way observed relationships, and
new/after-missing route neighbors. Unavailable history is shown as unavailable.
Positive observations without complete coverage remain lower bounds. Supporting
Observations also shows **Change (%)** beside the absolute Difference:
`(After - Before) / Before × 100`, rounded to one decimal with signed positive
and negative changes. A zero Before value shows `N/A`; missing measurements
remain unavailable. Values recalculate with each selected comparison period.
Neighbor SNR means, samples and absolute dB differences are unchanged; no SNR
percentage comparison is calculated.

Traffic per recorded hour counts only confirmed receptions whose timestamps fall
inside the union of verified recording intervals. It does not divide all legacy
observations by a small known-coverage denominator. A rate is unavailable without
recorded coverage or when interval complexity exceeds the bounded calculation.
Relationship counts describe flood-route evidence, not verified direct RF links.
Existing grouped-output limits are reported rather than hidden.

Different observation coverage, network activity, routes, weather or simultaneous
changes may explain differences. Higher traffic alone is not proof of improved
radio performance. No delivery-success percentage, ranking or performance score
is produced, and correlation is never presented as causation.

## Execution limits

Journal operations use the existing protected local-dashboard request policy.
Comparison calculations share the single isolated statistics worker, semaphore,
short cache and existing execution/query limits. One bounded comparison budget
covers both windows. Large histories may require a shorter comparison period.
Raw packet histories are not loaded into the browser. No new monitoring mechanism,
radio requests, increased polling frequency, migration deletion or retention change
is introduced. Repeater Statistics rolling windows remain unchanged.

## Telemetry line charts

Voltage and temperature show clean lines without permanent measurement dots.
Valid consecutive points retain the existing gap rules, axes and scales. Hover,
tap/click or keyboard selection reveals a temporary marker, exact value and time.
Hover markers clear on pointer leave; selected markers clear with Escape or blur.
Selections survive refresh while the selected measurement is still available.
Stored telemetry, polling intervals and retention are unchanged.

## Firmware SNR aggregates

Compatible repeaters contribute sample-weighted firmware means. Only whole
UTC-valid windows inside each comparison period are included. A window crossing
the change timestamp is excluded from both periods, since its samples cannot be
split without inventing their timing. Invalid UTC and collection limits remain
explicit. The median still uses matched-neighbor differences, never pooled data
across neighbors.

For each neighbor, firmware aggregates take precedence over differently sampled
legacy estimates within a period. Legacy history is preserved. When sources
differ between periods, both values/counts are shown separately and excluded from
dB differences and the median. No SNR percentage changes are introduced. See
[aggregate source and time rules](v5-averaged-snr.md).
