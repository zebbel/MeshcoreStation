# Repeater management

Open a repeater on the map and choose management. Connect using its admin
password, or leave the password blank to use existing permissions or guest access.
**Remember password** optionally saves the login password for this repeater in
this browser on this device and fills it in on the next login. It is off by
default; only a successful login saves the entered password. Uncheck it to
remove the saved password. Browser storage is not encrypted by MeshcoreStation;
use this option only on a trusted device. Session tokens are never saved.

Status is available to guests where the repeater permits it. Configuration and
console operations require administrator rights, checked again for each request.

## Configuration coverage

The configuration form covers:

| Section | Settings |
| --- | --- |
| Basic | Name, admin password, guest password |
| Radio | Frequency, bandwidth, spreading factor, coding rate, TX power, RX gain, external FEM RX/TX gain, channel activity detection |
| Location | Latitude, longitude, map selection |
| Advertisements | Local and flood advertisement intervals |
| Routing | Forwarding, general/unscoped/advertisement flood-hop limits, forwarding regions |
| Access | Guest access and companion permissions |
| Owner | Owner information |
| Advanced | Path hash size, loop detection, duty cycle, multi-ACKs, flood/direct TX delay, receive delay, interference threshold, AGC reset interval, battery ADC multiplier, power saving |
| GPS | GPS enabled and advertisement location source |
| Bridge | Enabled, packet source, delay, serial baud rate, ESP-NOW channel and secret |

Read each section before editing. Unsupported or unreadable values remain
disabled; support depends on the repeater's firmware, radio and board. Passwords
are write-only. Each ordinary save checks the current value, sends the change,
and reads it back. The firmware remains the authority on supported values.
AGC reset accepts 0–1020 seconds in steps of four; multi-ACKs accepts 0 or 1.
The serial bridge form covers the default firmware baud limit of 115200.

The Actions area provides advert transmission, clock synchronization and reboot.
Status includes telemetry, neighbors and the repeater's reported clock when
supported.

## Console

The Console tab provides a remote command input and a timestamped reply history.
Use **Commands…** to open the searchable command popup. Each entry explains its
purpose. Selecting one fills the input without sending it and selects the first
placeholder for replacement. Replace all `<values>` before pressing Send.
The list includes configuration commands from the same schema as the settings
form; availability still depends on firmware and hardware.
For example, send `get name`, `ver`, `board`, or `clock`. Commands that may change
settings require confirmation. Commands are sent once, with no automatic retry.
Reboot and power-off commands are shown as sent, not confirmed, and end the local
management session.

The console also exposes firmware-specific operations without a dedicated form:
`get extra.sf` / `set extra.sf ...` on supported LR2021 builds, dynamic sensor
configuration, GPS diagnostics and synchronization, temporary radio settings,
additional region operations, legacy settings and firmware diagnostics. Consult
the documentation for the repeater's exact firmware before using these commands.
A console command clears cached form values: read the section again before saving.

Commands must fit within 147 UTF-8 bytes and cannot contain newlines or control
characters. Replies are displayed as text. Password, bridge-secret and private-key
commands and their replies are hidden in the history. History is held only in the
open management window and can be cleared; it is not saved to the database.

Some commands are serial-only in firmware, including reading the private key and
flash erase. A remote console cannot bypass that restriction. It also cannot
provide a continuous serial log stream. The console is not a terminal connected
to the Raspberry Pi.

If a request times out, a change may already have applied. Wait two minutes,
then read the value before retrying. Firmware may truncate long responses.

## Coverage audit

The additions were checked against the upstream and custom firmware command
handlers and upstream CLI documentation:

- [Upstream CLI documentation](https://github.com/meshcore-dev/MeshCore/blob/main/docs/cli_commands.md)
- [Upstream CommonCLI](https://github.com/meshcore-dev/MeshCore/blob/main/src/helpers/CommonCLI.cpp)
- [Custom CommonCLI](https://github.com/zebbel/MeshCore/blob/meshcoreStation/src/helpers/CommonCLI.cpp)

These sources evolve. Settings compiled only for particular hardware cannot be
assumed to exist on every repeater. Automated tests cover validation, permission
checks, special response formats, command dispatch and browser behavior; physical
radio and board-specific behavior still require testing on the connected hardware.
