# MeshcoreStation 4.3.4 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.3.4` (prerelease, not latest stable). V3 main is unchanged.

- Fixed Repeater vs. Mesh Activity discarding confirmed path observations whenever
  another match in the bucket had an ambiguous hash prefix. Confirmed counts are
  retained; ambiguous matches remain excluded and are reported in explanations,
  hover values and measured-value tables. Counts with uncertainty are lower bounds.
- Relative assessments exclude uncertain buckets and withhold trend conclusions
  for incomplete required coverage. Positive shared baselines still normalize both
  Companion series to 100 using their own counts from the same bucket/stream.
- Without a shared positive baseline, display raw confirmed repeater and mesh
  Companion counts independently, with integer axes and missing buckets as gaps.
  Analyzer counts are never combined with Companion traffic. Stored observations,
  timestamps, history and all existing V4 collection/refresh behavior are unchanged.

Focused calculation/chart tests reproduce mixed unambiguous/ambiguous hash sizes,
exclude unrelated tracked copies, verify normalization and independent mesh
history, preserve original rows, and withhold unsupported relative assessments.
Essential installation/version/publication checks remain. This isolated read-only
calculation release does not run unrelated browser/screenshot or map suites.

The deployed Companion database was not supplied in this workspace. The failure
path is reproduced against stored-format observations; no assertion is made about
the number of affected buckets in the operator's deployment.
