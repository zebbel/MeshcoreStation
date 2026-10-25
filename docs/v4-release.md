# MeshcoreStation 4.4.1 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.4.1` (prerelease, not latest stable). V3 main is unchanged.

- Kept the existing radio-airtime calculation and protocol timeout:
  `1.2 × (0.5 + 16 × packet airtime in seconds)` (firmware millisecond estimate).
- Retry waits now use `max(protocol timeout, minimum) + uniform random 0–5s`.
  The minimum is 20 seconds for zero-hop requests and 30 seconds for multi-hop
  requests. A fresh jitter is drawn for each wait, including queue deferrals.
  Longer protocol timeouts are preserved.
- Retained zero-hop original + one retry, multi-hop original + up to three
  retries, and no retries for unknown hops. Normal multi-hop attempt times are
  approximately 30–35, 60–70 and 90–105 seconds after initial submission, plus
  any queue/lock/serial overhead. Pending attempt timestamps reflect the actual
  chosen wait, not just the protocol timeout.
- Forwarding cancellation, original saved reply text/channel/scope, unique packet
  timestamps, asynchronous scheduling, locks, queue/airtime safeguards, shutdown
  and configuration cancellation, persistent tracking and command deduplication
  are unchanged. No firmware changes. Receiver delivery remains unconfirmed;
  missing forwarding evidence does not establish delivery failure.

Focused validation covers minimums, protocol precedence, jitter endpoints,
per-attempt redraws, cumulative simulated timings, scheduled timestamps and
existing retry limits/cancellation/sending. Essential installation/version/release
checks remain; no browser or unrelated regression suites are added.
Tests use simulated time/Companion responses, not live RF delivery.
