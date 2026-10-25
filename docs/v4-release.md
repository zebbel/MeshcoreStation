# MeshcoreStation 4.4.0 — V4 branch prerelease

Branch: `v4.0.0`. Tag: `v4.4.0` (prerelease, not latest stable). V3 main is unchanged.

- Channel-command replies retry saved text, never the command/action. Each part
  permits original + one retry for zero-hop requests, original + up to three for
  multi-hop requests, and original only for unknown hop counts.
- Delays use `1.2 × (500 ms + 16 × estimated packet airtime)` with actual reported
  SF/BW/CR and group packet framing, encryption padding and optional scope bytes.
  No fixed long-delay retry schedule. Every submission has a distinct timestamp.
- Multi-hop pending retries stop on authenticated matching forwarding evidence
  from any attempt. Channel, text, timestamp, scope and nonempty path must match;
  zero-path copies, unrelated messages and invalid authentication do not cancel.
- Preserved original channel/scope, serial/control/reply locks and split behavior.
  Local queue/connection/readback checks, bounded deferrals, 32 pending parts,
  ten-second packet-airtime limit and 60 seconds extra retry airtime per rolling
  session hour bound load. Missing identity/radio data disables retries.
- Disconnect/shutdown/configuration changes cancel pending work; restart does not
  resume old retries. Existing databases receive additive metadata only. Outgoing
  replies groups all attempts with timestamps, acceptance, forwarding evidence,
  next scheduled time and final status. Receiver delivery remains unconfirmed.
- Existing V4.3.4 Performance, cache refresh, footer, maps and other UI behavior
  remain. No private-message command handler or firmware changes were introduced.

Focused validation covers protocol timing, hop limits, saved-text/channel/scope
retention, unique timestamps, authenticated forwarding, cancellation/races, queue
and airtime limits, split parts, command deduplication, legacy storage and reply UI.
Essential installation/version/release checks remain; no unrelated browser or
screenshot suites are added. Tests use a simulated Companion, not live RF delivery.
See [Reply retry details](bot-reply-retries.md) for PHY assumptions and limitations.
