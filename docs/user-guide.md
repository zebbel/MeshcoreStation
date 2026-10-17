# Using MeshcoreStation

This guide covers stable **3.0.2** on `main`, including the bot, room server,
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

## Repeater battery and statistics

Select a repeater from the map and save battery settings. Configure sampling,
report times and **Send battery reports to**: follow the bot, a named private
channel, or an enabled local room. The target is independent of the monitored
repeater. A missing target fails visibly instead of silently changing destination.

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
