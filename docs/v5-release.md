# MeshcoreStation 5.5.0 — Repeater Change Comparisons and Telemetry Lines

A new Repeater Statistic Comparison main accordion follows Statistics. Its managed-
repeater change journal stores full keys, descriptions and server-assigned times
in meshcorestation.db. Changes can be edited without changing timestamps and
deleted with confirmation without touching statistics. Recording a change sends
no repeater command; no manual timestamp or change-type selector is provided.

Saved-only comparisons use equal [T-D,T) and [T,T+D) windows for 24h/7d/30d.
Both windows share an immutable history snapshot and registry metadata. The primary
metric is per-neighbor SNR mean differences and the median across matched full-key
neighbors, never a frequency-weighted pooled average. Distinct samples, new/before-
only neighbors, future/incomplete periods, coverage and overlapping changes are
explicit. Missing data never receives synthetic SNR or fabricated zero traffic.

Supporting summaries include observed neighbors, unique/repeated receptions,
one-/two-way route evidence and traffic per recorded hour. The rate numerator uses
only receptions inside verified recording intervals. Correlation is not causation;
increased activity is not a delivery-success or radio-performance claim.

Comparisons reuse the existing isolated worker/cache and execution limits, without
additional radio requests or changed monitoring schedules. Schema additions preserve
existing databases, journals and statistics. Rolling Statistics views are unchanged.

Voltage and temperature histories retain their lines, scales, dimensions and gaps
without permanently visible dots. Hover/tap/keyboard selection keeps exact values,
timestamps and temporary highlights. No telemetry data or polling changes occur.

Validation includes journal/window/median/coverage regression tests, JavaScript
interaction tests, fresh-install checks and the existing Chromium desktop/mobile
release gate. See docs/v5-repeater-comparison.md for limitations. V5 remains a
prerelease; V3 main and V4 v4.0.0 remain unchanged.
