# Companion OLED pages

MeshcoreStation 2.5.0 automatically probes the private MCOD v1 extension on the
existing USB companion connection. It supports the text and graphics protocol in
`zebbel/MeshCore`, branch `feature/usb-oled-control`, documented in
`docs/usb-oled-control.md`. Upstream/unsupported firmware keeps its normal screen.

Select a repeater in the dashboard's **Repeater battery** settings. The OLED uses
that selection, its voltage channel and the already stored measurements:

- Repeater name (printable ASCII, shortened to fit).
- Latest voltage and approximate 1S LiPo percentage, using the dashboard curve.
  Out-of-range voltages show `--%`; old readings say `stale`; failed or missing
  latest readings say `No current reading`.
- Last 24 hours of voltage, with a fixed 3.0–4.2 V range and time
  endpoints. Failures and long sampling gaps interrupt the line. A single sample
  is a point. Values outside the range are clipped to the graph edges; the
  numeric voltage reading still shows the measured value.

The scene refreshes every 10 seconds. No extra radio telemetry is requested.

With firmware advertising button reporting (CAPABILITIES bit 2), a short press
of the onboard user/PRG button cycles between two pages:

1. The repeater battery and 24-hour graph, fixed at 3.0–4.2 V.
2. The three latest received commands, newest first, each with local receive
   time, sender and command text. Long names/messages are shortened to fit the
   128×64 display. An empty history shows `No commands yet`.

A recognized short press requests a redraw without waiting for the periodic
refresh. Long, double and triple presses have no assigned action. The battery
page is selected after reconnecting. Firmware without button reporting keeps
the existing battery screen.

After BEGIN the host enables BUTTON_SUBSCRIBE (operation 10). It handles
unsolicited operation 0x80 separately from command replies, rejects malformed
events and ignores duplicate/old sequences using 16-bit wraparound arithmetic.
The reader only selects a page and wakes the display worker; it never sends a
display command while handling a notification. Repeated subscription is
idempotent and restores reporting if a lease was reacquired.
Graphics firmware supports LINE/POLYLINE; earlier text-only MCOD firmware shows
battery text and `Graph FW required`. Firmware without MCOD is probed once per
connection and otherwise left alone. Check `data/logs/logs.log` for detection or
protocol errors. Set `MESHCORESTATION_OLED=0` in `meshcorestation.env` and restart
the service to disable the feature.

The screen has a 60-second lease. Every complete refresh renews it; release on
shutdown restores the normal UI. If the process or connection disappears, lease
expiry restores the normal display. Errors stop this display worker until the
next connection, without stopping the radio. Reconnecting after a firmware update
probes again. The normal firmware UI/buttons are suppressed while the lease is
active, as defined by the firmware protocol.

There is one USB connection and one framing parser. A small reader adapter handles
MCOD replies and button events, forwards normal radio notifications, and matches request ID
and operation. Display and normal commands share the serial command lock; each
reply is awaited before the next command. Graphics are staged with BEGIN and
shown atomically with SHOW; append commands are never blindly retried. Tests cover
reply matching, interleaved gestures, sequence wrap, page cycling, history layout,
unsupported firmware, graph scaling/gaps and polyline limits.
Physical OLED/radio coexistence still needs validation on the Heltec.
