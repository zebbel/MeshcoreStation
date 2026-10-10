# Companion OLED page editor

From MeshcoreStation 2.6.0, open **Settings → OLED pages → Open screen editor**.
The companion needs the private MCOD v1 extension from
`zebbel/MeshCore`, branch `feature/usb-oled-control`.
Graphics require LINE or POLYLINE support. Short-press navigation requires
the button-reporting capability. Unsupported firmware keeps its normal screen.

## Design pages

The editor starts with editable Battery and Commands pages. Existing battery
selection and stored readings are used; no additional telemetry is requested.

- Add, duplicate, rename, reorder, enable or delete pages (up to 12).
- Add **Text**, **Database value** or **Graph** elements (up to 16 per page).
- Drag an element to move it. Drag its blue bottom-right corner to resize it.
- Use X, Y, Width and Height for exact placement. Arrow keys move a focused
  element by one pixel; Shift + arrow moves eight pixels.
- Text uses the firmware's small 6×8 or large 12×16 font. Text is converted to
  printable ASCII and shortened to its box, up to 21 characters. It does not wrap.
- Database values have an optional label, units and 0–4 decimal places.
- Graphs have editable minimum, maximum, width, height and 1–720 hour time range.
  Out-of-range samples are clipped; axes are drawn inside the box.
  Add text elements if you want visible range or axis labels.

The editor offers these named sources, without custom SQL:

| Database values | Graph series |
| --- | --- |
| Selected battery repeater name, voltage and approximate 1S percentage | Selected battery voltage or percentage |
| Known repeater count and received command count | Received-command RSSI, SNR and hop count |
| Latest three commands: sender, message, receive time, RSSI, SNR and hop count | |

Battery sources follow the dashboard's selected battery repeater and voltage
channel. Command times use the station's configured dashboard timezone. Missing
values show `--`. Stored samples can be old; values do not trigger fresh requests.
Percentage is an approximate 1S LiPo estimate and unavailable outside 3.0–4.2 V.

The default battery graph stays fixed at **3.0–4.2 V over 24 hours**. You can
change these bounds in the editor. Graph data is reduced to pixel buckets in
SQLite; missing battery samples and long telemetry gaps break the line.
At most four graphs and 256 total line segments are emitted per page. On
text-only firmware, graph elements are omitted.

## Preview and save

The browser preview uses the same database renderer as the OLED, refreshing
after edits and every ten seconds. Its browser font is an approximation of the
firmware font. Blue outlines are editor guides and are not sent to the OLED.

**Save pages** persists the draft in SQLite and makes it active within ten
seconds. Invalid bounds, unsupported sources, excessive elements and changes
from another editor window are rejected. Reload before saving after a conflict.

**Preview on companion (30s)** temporarily displays the selected draft page
without saving. The OLED must already be connected and active. The preview
appears at the next refresh (within ten seconds). It expires automatically;
Stop companion preview, closing the editor or saving also restores saved pages.
The database and updater backups include saved pages.

## Buttons and lifecycle

A short press cycles enabled pages in their configured order. Long, double and
triple presses have no assigned action. Reconnecting starts on the first enabled
page. Firmware without button reporting displays the first enabled page.

The screen refreshes every ten seconds and has a 60-second lease. A recognized
short press wakes the worker early. Shutdown releases the screen; if the process
or connection disappears, firmware lease expiry restores its normal UI.
Set `MESHCORESTATION_OLED=0` in `meshcorestation.env` and restart to disable OLED
control. Errors stop the display worker until the next connection, without
stopping the radio.

The existing serial connection and framing parser are reused. Display commands
share the radio command lock. BUTTON_SUBSCRIBE (operation 10) follows BEGIN;
unsolicited operation 0x80 is handled separately from command replies, with
validation and modulo-65536 sequence deduplication. Reader callbacks never send
display commands. Normal MeshCore notifications continue to the original reader.

Automated tests cover document validation, SQL source selection, rendering
bounds, graph budgets, save conflicts, preview expiry, route protection,
button events, page cycling and browser drag/resize editing. Physical OLED and
radio coexistence require on-device testing.


## Hardware compatibility (2.6.1)

Only models identifying as **Heltec V4 OLED** or **Heltec V4.3 OLED** are
probed for the private MCOD extension. Other boards, TFT variants and unknown
models receive no OLED commands. Matching MCOD INFO dimensions and limits
confirm the custom extension before taking display control. Stock firmware on
an eligible board receives only the discovery probe and remains in normal UI.

The editor, browser preview, device preview and save API are disabled unless
that compatible companion is connected and its OLED worker is active.
Stored pages are retained when switching companions. The dashboard checks
availability every five seconds; server-side checks apply to every request.
