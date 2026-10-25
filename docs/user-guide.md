# Using MeshcoreStation V4

Start with Bot Status to check companion connectivity. Known Repeaters opens the
clustered map; search reveals the selected marker. A failed map asset or request
shows progress/error feedback and retry controls rather than a silent blank map.

Expand Command History to see commands oldest first, filter them or load older
entries. Command Details lists distinct reception paths and their available RSSI,
SNR and time. Selecting a path changes route lines, arrows, hops and distance while
keeping the same map. Unknown or ambiguous prefixes remain labeled. Recorded
replies are not proof of delivery. Outgoing replies groups original sends and
protocol-timed retries, with timestamps, Companion acceptance, forwarding evidence
and the final retry status. Commands execute once; retries resend only saved text.
See [Channel-command reply retries](bot-reply-retries.md) for limits and safety
behavior. Receiver delivery remains unconfirmed.

In Repeater Management, add repeaters from the map and choose one in the dropdown.
The selection drives telemetry and all four optimizer subsections. Removing a
repeater deletes its monitoring settings and local telemetry/statistics/history
according to the removal confirmation, but leaves its Known Repeaters map entry.
Its external snapshot is deleted too; other repeaters are unaffected.

Telemetry displays the latest saved voltage and temperature with separate charts.
Choose 24 hours, 7 or 30 days; tap/click to select the nearest recorded value inside
a chart. Configure LPP channels and per-repeater read/report settings in Telemetry
history / settings. Temperature is optional and shares the voltage request. Report
templates support placeholders, validation and live preview. Daily reports reuse
the latest successful sample with its original timestamp.

Repeater Optimizer contains four independent disclosures:

- Repeater Performance: numerical relay, two-way reach and routing-contribution
  cards, then four line charts and a coverage-aware Performance Assessment.
  Choose 24h/7d/30d history. Cards retain the latest explicitly labeled rolling
  24-hour Analyzer window. Performance Changes holds the journal and before/after
  line charts; Detailed Statistics is last. Logging never sends radio commands.
  Analyzer collection continues every 12 hours while the station service runs.
  See [Performance and comparisons](repeater-performance.md).
- Repeater Statistics: local passive evidence, collection pause/resume, periods,
  charts, route counts and usefulness. Closed panels do not load data.
- Optimization Analysis: passive analysis and comparisons. Protected actions require
  an administrator session. Connect, then return to the analysis using the button
  in management; read, review and explicitly confirm any recommendation. Disconnect
  when finished. Neighbor radio polling stays opt-in.
- Repeater Network Monitoring: external analyzer evidence, available without activation.
  Opening reads the cache; stale or missing snapshots refresh automatically, using a five-minute cache. Refresh Now
  is manual, with no continuous polling. Errors preserve the last successful data.

Room Server loads only when expanded. Create/enable rooms, manage access and inspect
posts. Use the room's normal login password; remote repeater management credentials
are a separate permission system. A room may supply the bot channel.

Settings group companion controls in one disclosure. Station updates and display
preferences remain separate. German/ISO/US dates and 12/24-hour display settings
persist across browsers; timezone conversion and report schedules are independent.
See the specialized companion firmware, OLED, room protocol and operations guides
for those procedures.

The four optimizer subsections share dashboard typography, cards, controls and
status styling. Analysis grows with its content rather than using an internally
scrolling fixed-height iframe. Provider access failures remain visible in monitoring. Analysis uses the same background
as Repeater Statistics, synchronized across the iframe in light and dark modes.

Repeater identities display names where full-key records are available. Hover or
open details for technical keys. Identical names get key suffixes; unknown keys
use Unknown Repeater and short unresolved prefixes remain labeled as unresolved.
Packet Path Patterns preserves sequence/count/time while displaying readable names.
The four optimizer disclosures share matching content gutters on small and large
screens. Observable Relationships uses S/R markers and an English line legend.
Green means bidirectional observations, red means one observed direction, and gray
means unknown direction. Solid lines indicate medium/high analyzer confidence;
dashed lines indicate low confidence, and dotted lines indicate unknown confidence.
Tap a line for named endpoints, directional counts, confidence, distance and keys.
Missing background tiles do not remove overlays.
Relationships are inferred from analyzer observations and do not necessarily represent verified direct radio links.
