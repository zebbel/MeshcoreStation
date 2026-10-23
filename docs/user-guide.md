# Using MeshcoreStation

This guide covers stable **3.4.0** on `main`, including the bot, room server,
repeater monitoring and dashboard. For upgrades from a former feature branch,
see [Updates and branch migration](web-version-switching.md).

## Bot conversations

Choose a private companion channel or select **Use as bot channel** on a local
room. There is one active bot conversation. Selecting a room stops command
handling on the previously selected channel; selecting a channel switches back.
Other rooms continue as message boards.

Commands are configured under **Commands**: trigger, help text, action and success
or failure reply. Actions include reply only, update sender position and add scope.
Templates can use sender name/key, signal measurements, hop/path information,
distance, scope, battery, uptime, date/time and command list. The editor validates
placeholders. Missing values are shown as unavailable rather than invented.

Sender position accepts coordinates in the command (latitude, longitude); without
coordinates the existing action requests telemetry. Channel telemetry requests
acknowledge the command first and use its received scope. Room position/telemetry
routing still needs dedicated hardware validation; do not assume a room's login
password grants telemetry access to the sender companion.

## Rooms

Create a room, set its password (1–15 UTF-8 bytes), then enable it. Import the QR
contact in Android and log in with that password. The QR does not contain the
password. New participants receive write access automatically; optional member
controls assign read-only access. Changing the password clears sessions.
Removing a participant alone does not prevent rejoining with the known password.

Rooms have their own persistent identities. Up to four share the station radio.
There is no room scope requirement; forwarding through repeaters still depends
on the network. Manage rooms in the web dashboard, not Android remote management.
A dashboard post is stored locally, then delivered to logged-in participants by
the room worker. Offline peers synchronize later; acceptance is not delivery proof.

## History, maps and measurements

Command history combines channel and room commands. Expand a row for packet
measurements, sender information, route maps and reply status. Unrecognized room
conversation remains in room history and is not treated as a bot command.

Flood paths carry repeater hashes. Unknown and ambiguous repeaters limit distance
accuracy; geographic route estimates are not physical RF propagation distances.
Direct-routed packets have consumed their route by arrival: `direct` does not prove
zero repeater hops. The inherited room reply currently substitutes straight-line
distance for route distance in this case; use the direct-distance value as a
geographic separation, not evidence of the traveled route. Route reconstruction
needs additional protocol information and is not added by this refactor.

Outgoing reply observations report overheard evidence. They cannot prove that
all repeaters or the final recipient received a message.

## Repeater telemetry and statistics

Open **Repeater management** and use **Add repeater from map** to save each
repeater to the station's managed list. The dropdown controls the displayed
battery history, statistics and management popup. The list is shared across
browsers; each browser remembers which repeater it last viewed.

Each repeater has separate sampling intervals, telemetry channel, report times,
timezone and destination. New repeaters start with battery polling disabled;
enable it in that repeater's **Telemetry history / settings**. Disabling one
repeater does not affect the others. Manual reads target the selected repeater.
Polling is serial, with one due read per worker cycle, so heavy schedules may
run later than their nominal interval.

Adding a repeater starts passive metadata collection for it without transmitting.
Use **Pause collection** / **Start collection** to control only that repeater;
others keep collecting. Existing observations remain available when paused.

Select a repeater and save its battery settings. Configure sampling,
report times and **Send battery reports to**: follow the bot, a named private
channel, or an enabled local room. The target is independent of the monitored
repeater. Daily reports use the last successful stored battery reading and its
original timestamp, without requesting an extra telemetry read. Failed reads do
not replace that value. If no successful reading exists, the report attempt is
logged as failed. Regular scheduled and manual sampling continue unchanged.
A missing target fails visibly instead of silently changing destination.

Passive repeater statistics and usefulness summaries describe traffic the station
observed. Reception conditions and missing observations limit conclusions about
whole-mesh coverage. Repeater management and guest telemetry require compatible
firmware and permissions.

## OLED and firmware

The OLED editor provides text, data variables and graphs, page layouts, graph
ranges, rotation interval and button hold time. OLED commands apply only after
capability detection for supported custom firmware. The station's custom display
worker recovers its display mode when refreshes are interrupted.

Choose **Custom MeshcoreStation** or **Official MeshCore** in the companion
firmware source dropdown, then press **Check firmware releases**. Switching back
to official firmware requires a matching partition layout. Custom OLED and room
transport features may be unavailable with official firmware. Checks are requested
explicitly; active installations are polled for progress. Only assets for the
supported connected device are offered. See the
[firmware guide](companion-firmware-updates.md) before flashing or migrating a
partition layout. Application updates and companion firmware updates are separate.

## Room participant controls

Participants appear automatically after password login. Contact names are loaded
once when the room page opens; **Update contact** refreshes them on demand.
Known participants and message authors show their names; unknown keys are
shortened, with the full key available on hover. Contact refresh does not add
members or change permissions.

Use the participant's **Read / Write** dropdown to change permission: Read allows
receiving messages, while Write also allows posting. Changes save immediately.
**Remove** disconnects a participant, but they can rejoin if they still know the
room password. Change the password to prevent that.

For configuration coverage and the remote Console tab, see [Repeater management](repeater-management.md).

**Remove repeater** stops its monitoring and collection and permanently deletes
its battery settings, readings, report history and collected statistics. The
confirmation names the selected repeater. Other repeaters are unaffected. Its
known map/contact entry remains available so it can be added again with fresh
settings. The remembered management password is cleared in the current browser.

### Repeater map groups

Nearby repeaters are grouped into numbered circles in the known-repeaters map
and repeater picker. Zoom in or click a group to expand it. Repeaters at the same
location spread apart when the group is expanded so each can be selected.
Show on map reveals the selected repeater even inside a group. Packet-route
maps retain individual numbered hops.


## Display preferences and battery report messages

In Settings, **Date and time display** selects German (`DD.MM.YYYY`), ISO
(`YYYY-MM-DD`) or US (`MM/DD/YYYY`) dates and a 12- or 24-hour clock. Defaults are
German dates and 24-hour time. **Save and reload** persists these choices for the
application, including embedded room/optimizer pages, maps and command history.
Other open browsers use the saved preferences after reloading. This controls
presentation only; each report timezone and its `HH:MM` schedule are unchanged.

In Repeater management, select a repeater and open **Telemetry history / settings**.
The **Report message template** editor inserts placeholders at the cursor,
validates supported fields and shows an example preview without sending radio
traffic. Save settings to apply the template only to the selected repeater.
**Use default message** restores `Battery {repeater_name}: {reading} | {sample_time}`.
Placeholders include repeater identity, the last read battery voltage/percentage,
reading date/time and report timezone. Numeric fields support `.0f` through `.4f`,
for example `{battery_voltage:.2f}`; `{{` and `}}` represent literal braces.
Templates use one line and up to 512 UTF-8 bytes. Missing numeric values show
`unknown`; reports still require a successful saved reading. The default
`sample_time` retains the previous `DD.MM HH:MM` on-air text. Longer reports split
into bounded radio messages without changing report slots or destinations.

Dashboard sections start closed and fetch their detailed content when opened.
Command Details shows saved route information before map scripts or background
tiles finish. Recent map results are cached for up to 30 seconds (32 results per
browser page); reopening after that refreshes saved positions. Discovery maps
load clustering only when needed. Background tiles still require Internet access.


## Temperature and chart selection

Open **Repeater telemetry → Telemetry history / settings** to choose the voltage
and temperature LPP channels. The temperature channel defaults to **1** and can
be set to **0–255** to match the repeater's reported temperature sensor. Voltage
and temperature come from the **same** guest telemetry response; temperature does
not cause additional radio requests. Temperature is stored in °C with the same
read timestamp, including zero and negative readings. Missing, ambiguous or
invalid temperature is shown as unavailable while voltage monitoring continues.

Both the dashboard telemetry section and the history/settings window have
separate voltage and temperature charts. The period selector supports **24
hours**, **7 days** and **30 days**. Histories are filtered by their respective
sensor channels. Legacy battery records remain intact and have no invented
temperature. Missing readings break chart lines. Voltage keeps its fixed
3.0–4.2 V scale; temperature uses a scale fitted to the recorded values.

Click with the mouse or tap either chart to highlight the nearest recorded
measurement. The selected value appears **inside that chart**, for example
`3.92 V` or `24.6 °C`, with no popup or selected timestamp. Selecting another point
replaces the value. Selection survives an ordinary background refresh while the
point remains in the displayed history. Keyboard users can focus the chart and
use Enter and the arrow keys to select measurements.

Battery report templates can optionally include `{repeater_temperature}` or
`{repeater_temperature:.1f} °C`. The placeholder is the temperature from the same
stored reading used by the report and the currently configured temperature
channel; unavailable values show `unknown`. It adds no radio request. Templates
that omit it produce their existing messages, on the existing schedule and to
the existing destination.


### Repeater temperature in command replies

The command editor also offers `{repeater_temperature}` under **Repeater
telemetry**, including numeric formatting such as `{repeater_temperature:.1f} °C`.
It reads the last successful saved temperature of the **default repeater**: the
first managed repeater in the server's management list. The selection in an
individual browser does not change this source. With multiple repeaters, the
placeholder does not choose whichever repeater was heard most recently.

Only the configured temperature LPP channel is used. Missing readings show
`unknown`; failed later reads do not replace the last successful value. This
placeholder adds no telemetry or status radio request to command processing.
The editor preview uses example data, as with other command placeholders.


## Multiple command reception paths

Command Details lists each distinct recorded **reception path**, with hop count,
RSSI, SNR and the first reception time. The first recorded path is selected by
default. A reception count indicates repeated copies on that same path; each
copy's measurements and time are retained in the database. Duplicate receptions
do not execute the command or send another reply.

Choose another path to update the repeater markers, route lines, arrows and
route distance immediately. The sender and bot markers, map view and background
tile layer stay in place. Initial bounds include all recorded routes. Unknown,
incomplete, ambiguous and unlocated hops are marked explicitly; unresolved
routes never invent repeater coordinates. Consumed direct routes remain unknown.

Channel paths are correlated using authenticated channel content and configured
scope keys. Unidentifiable or ambiguous scope associations are not guessed.
Room paths come only from authenticated, replay-checked room posts. Reception
recording adds no radio traffic and does not change reply routing. Only receptions
exposed by the companion's RX log can be recorded. Older history retains its
original saved single path; paths from before this update cannot be recovered.
