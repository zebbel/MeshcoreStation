# Companion OLED battery screen

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
only MCOD replies, forwards normal radio notifications, and matches request ID
and operation. Display and normal commands share the serial command lock; each
reply is awaited before the next command. Graphics are staged with BEGIN and
shown atomically with SHOW; append commands are never blindly retried. Tests cover
reply matching, unsupported firmware, graph scaling/gaps and polyline limits.
Physical OLED/radio coexistence still needs validation on the Heltec.
