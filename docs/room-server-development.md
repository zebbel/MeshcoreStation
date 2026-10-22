# Independent room server

The room server is included in stable **MeshcoreStation 3.1.2** on `main`.
See [V3 release notes](v3-review.md) for changes and validation. Enabling a room
does not flash the companion.

## What runs

MeshcoreStation hosts native MeshCore room identities on the Pi. The connected
companion carries the encrypted packets using raw RX logs and
`CMD_SEND_RAW_PACKET` (65). This command and unconditional raw RX logging were
verified in `zebbel/MeshCore`, branch `meshcoreStation`, commit
`286a4506920250e13a6f79220de47ab3dac08af7`.

No companion identity, channels, radio settings, OLED pages or bot command handlers
are changed. There is one USB owner. Room traffic uses the existing serialized
command API at low radio priority, with at least 1.2 seconds between host sends.
An independent bounded queue and worker contain room failures. Sharing the radio
still shares airtime: heavy room use can delay other radio traffic.

The feature supports up to four independent Android-visible rooms, each with its
own persistent Ed25519 identity. Rooms start disabled and require a password before enabling. Successful logins
automatically enroll participants with writer access, up to 64 public keys per
room. Existing participants retain their assigned reader or writer access. Administrative changes are local to the
dashboard; a room member cannot run repeater CLI commands or administer the host.
Only the selected bot room executes configured commands; other rooms remain boards.

Implemented protocol features:

- Signed room advertisements, sent on enable/reconnect and hourly while enabled.
- Native encrypted login with a room password and automatic participant enrollment.
- MeshCore Ed25519 key exchange, AES-128 ECB and truncated HMAC packet protection.
- Encrypted text posting, duplicate suppression and persistent replay checks.
- Flooded path return with embedded login response and learned direct reply paths.
- No room scope setting or incoming scope filter. Flooded login requests
  receive flooded encrypted PATH responses with the request's path embedded,
  retaining the incoming path-hash width. Responses to known scoped floods use
  a matching saved scope key; unknown scopes fall back to unscoped flood, which
  may be blocked by repeater policies. Learned reversed paths are still used
  for direct room traffic. Advertisements are unscoped.
- Original author prefixes in room pushes, client synchronization cursors,
  keep-alive replies and pending-message counts.
- Any room can be selected as the MeshcoreStation bot channel. Newly received room posts are matched against the existing configured bot commands and replies are posted back into the same room. Selecting a normal companion channel switches the bot back.
- Recognized room bot commands are also recorded in the dashboard's existing
  `logger` command history. The entry records the room name and ID, the
  authenticated sender public key and saved position, incoming SNR/RSSI,
  hop/path information, packet scope, received command, and only the reply
  parts actually accepted by local room storage. `command_status` records
  `processing`, `completed`, `no reply`, `partial`, or `failed`.
  Existing history and original channel history are preserved via an
  additive SQLite schema migration. Room message-board posts that do not
  match a configured command are not added to command history.
- Room bot commands carry metadata from their **own** authenticated RF packet:
  signed RSSI in dBm, signed quarter-dB SNR, flood repeater hash count/path,
  and the matching scope name when its transport key is saved under Scopes.
  Unscoped floods show `unscoped`. Direct-routed room messages display
  `direct` for hops and scope, without pretending that their forward-hop
  history is known. When both the sender and station have saved coordinates,
  direct-route distance uses the same straight-line value as direct distance;
  otherwise, the distance stays `unknown`. Unrecognized scoped floods are
  explicitly labeled rather than guessed. Route distance on a flood still
  needs valid sender, repeater and station coordinates. A room sender's authenticated public key
  identifies its saved position even when its displayed nickname differs.
  The RX log may omit oversized packets; no measurement is invented in that case.
- Matching delivery ACKs, up to three delivery attempts, fair per-member polling
  and session expiry after one hour without authenticated activity. Logging in or
  sending a keep-alive resumes synchronization after failed attempts.
- Reconnect/restart lifecycle, failure status and manual room-worker restart.

This is a private message-board server, not an emulation of every administrative,
radio-statistics or telemetry command in standalone room-server firmware. It does
not provide remote CLI administration.

## Set up and verify a room

Install or update main using the [update guide](web-version-switching.md).
The room server is part of the stable application; no feature-branch switch is
needed. Verify delivery with your companion and Android app after setup.

1. Open the collapsible **Room server** section on the dashboard (or visit `/rooms`).
2. Create a room. It remains disabled until explicitly enabled.
3. Set a room password (1–15 UTF-8 bytes, matching the companion protocol).
   Passwords are stored as salted hashes and are never returned by the API.
4. Enable the room. Check that the worker remains ready without an error. A
   companion that rejects raw TX stops only the room worker; the bot continues.
5. Use **Show room QR code** and scan it on Android, or use **Copy contact
   link**. The contact has room type 3 and the room's key, which is different
   from the station companion's key. Share the password separately; it is not
   included in the QR code.
6. Log in with the room password. There is no need to enter a member beforehand.
   New participants appear automatically with write access. Each participant has
   a **Read / Write** control and a **Remove** button. **Update contact** refreshes
   names from companion contacts; unknown participants show shortened keys.
7. Send a message and verify another participant receives it. Post a message from
   the dashboard and verify receipt and synchronization after reconnecting.
8. Test over a repeater, not just directly. Confirm the normal bot still responds
   while the room is active. Disable the room and confirm its radio traffic stops.

No hardware radio test has been performed in this development environment.
Successful unit tests and wire-compatible crypto are not proof of Android or
multi-hop interoperability on the deployed devices.

Changing the password ends current sessions; participants must log in again.
Removing a participant ends their access, but they can join again if they know the
password. Change the password if you need to exclude a previous participant.

Existing rooms created before password support are disabled on migration. Set a
password and enable them again. Their identities, posts and participant roles are
preserved. There is no blank-password bypass for previously approved members.

## Storage and rollback

The independent `data/rooms.db` (or `MESHCORESTATION_DATA_DIR/rooms.db`) stores room
identities, password hashes, participants, posts, replay counters and delivery cursors. File permissions
are 0600 because it contains private identity seeds. Seeds are never returned by
the HTTP API. Keep backups private. The latest 100 posts are displayed; older
posts remain available for client synchronization.

Stop the station before copying this database for a consistent backup. Retain it
when switching branches; losing it creates different room identities. Neither
room initialization nor operation changes the bot database schema.

To stop room traffic, disable the rooms in the dashboard. The stable application
uses `rooms.db`; switching to main does not disable rooms. For recovery, stop
MeshcoreStation and restore a matching saved installation, configuration and data.
There is no room-specific firmware migration to undo.

## Validation

The tests cover independent storage, permissions, disabled behavior, persistence,
cryptographic interoperability, multi-byte paths, scoped floods, login, post ACKs,
retries, push ACKs, keep-alives, revocation, malformed input, HTTP origin protection
and room-worker failure isolation. The Ed25519 fixtures were generated by compiling
the firmware's C sources at the commit above and comparing public keys, shared
secrets and signatures to the host implementation.

## Scheduled repeater battery reports

In **Battery history / settings**, select **Send battery reports to**:

- **Follow bot chat / room** (default, including upgrades from previous versions).
- **Chat: ...** — a named private channel on the connected companion, independent of the bot chat.
- **Room: ...** — an enabled room served locally by this station, independent of the bot chat.

The selected target is saved as `voltage_config.report_target`. Channel
reports use the companion's default transmit scope, as before. Room reports
are queued as local room posts and delivered by the existing worker to
authenticated members. Both kinds of report attempt are logged in Recent
report attempts; queued never means guaranteed receipt. A missing/disabled
room or missing/nonprivate/ambiguous channel causes an explicit failed
attempt, never an automatic fallback to another destination. The migration
preserves existing schedules and defaults the target to the bot chat/room.

V3 runs recognized room commands through a separate bounded worker. See
[architecture](architecture.md) for queue, cancellation and permission semantics.

## Deleting a room

Select a room and, if it is enabled, use **Disable room** first. If it is the
selected bot channel, switch the bot to a normal companion channel or a different
room before deleting. If a managed repeater uses this room as its battery report destination,
change that destination in **Repeater management** first. Click **Delete room** and confirm. This permanently deletes
the room identity, password hash, participant permissions, posts, cursors, and
replay history, so previous room contact links stop working. Other rooms are
unaffected. This is irreversible; back up `rooms.db` if history must be retained.
