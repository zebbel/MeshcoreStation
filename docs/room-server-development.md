# Independent room server (experimental)

Development branch: `feature/room-server`. Stable baseline: v2.7.8 on `main`.
Development source is now 2.8.0rc5 with password-based enrollment and optional room bot-channel routing.
No companion flash is performed.

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
Bot conversations are not automatically copied into a board.

Implemented protocol features:

- Signed room advertisements, sent on enable/reconnect and hourly while enabled.
- Native encrypted login with a room password and automatic participant enrollment.
- MeshCore Ed25519 key exchange, AES-128 ECB and truncated HMAC packet protection.
- Encrypted text posting, duplicate suppression and persistent replay checks.
- Flood path return with embedded login response and learned direct reply paths.
- No room scope setting or incoming scope filter. Authenticated scoped and
  unscoped flood requests receive direct replies along the reversed received
  path, including multi-byte repeater hashes. Advertisements are unscoped.
  Repeater forwarding policies still determine which packets reach the station.
- Original author prefixes in room pushes, client synchronization cursors,
  keep-alive replies and pending-message counts.
- Any room can be selected as the MeshcoreStation bot channel. Newly received room posts are matched against the existing configured bot commands and replies are posted back into the same room. Selecting a normal companion channel switches the bot back.
- Matching delivery ACKs, up to three delivery attempts, fair per-member polling
  and session expiry after one hour without authenticated activity. Logging in or
  sending a keep-alive resumes synchronization after failed attempts.
- Reconnect/restart lifecycle, failure status and manual room-worker restart.

This is a private message-board server, not an emulation of every administrative,
radio-statistics or telemetry command in standalone room-server firmware. It does
not provide remote CLI administration.

## First hardware test

After the version selector is published to both branches, update the stable
installation once to obtain it. Then open **Settings → Updates / version**, choose
**Room server (experimental)**, click **Check for updates**, review and confirm
**Switch to Room server (experimental)**. The dashboard restarts and reloads.
Selecting **Stable** uses the same process to return. Each switch backs up data
and rolls back both branch and revision if startup fails. A target without the
selector is refused, so returning to stable cannot remove the way back.

1. Open **Room server → Open room server** in the dashboard (`/rooms`).
2. Create a room. It remains disabled until explicitly enabled.
3. Set a room password (1–15 UTF-8 bytes, matching the companion protocol).
   Passwords are stored as salted hashes and are never returned by the API.
4. Enable the room. Check that the worker remains ready without an error. A
   companion that rejects raw TX stops only the room worker; the bot continues.
5. Use **Show room QR code** and scan it on Android, or open/copy **Import room
   contact**. The contact has room type 3 and the room's key, which is different
   from the station companion's key. Share the password separately; it is not
   included in the QR code.
6. Log in with the room password. There is no need to enter a member beforehand.
   New participants appear automatically with write access. Optional contact and
   manual-key controls remain available to assign reader or writer permissions.
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

To return normally, choose **Stable** in **Settings → Updates / version**, check
and install it. The service stops during switching, which also stops room traffic.
To recover manually, stop MeshcoreStation, restore the saved stable installation
or switch to `main`, then start the service. There is no room-specific
firmware migration to undo. The stable application ignores `rooms.db`.

## Validation

The tests cover independent storage, permissions, disabled behavior, persistence,
cryptographic interoperability, multi-byte paths, scoped floods, login, post ACKs,
retries, push ACKs, keep-alives, revocation, malformed input, HTTP origin protection
and room-worker failure isolation. The Ed25519 fixtures were generated by compiling
the firmware's C sources at the commit above and comparing public keys, shared
secrets and signatures to the host implementation.

## Publication order for two-way web switching

Publish the shared selector/updater changes to **both** `main` and
`feature/room-server` when publication is authorized. Stable needs only
`meshcorestation/updater.py`, `meshcorestation/web/update_api.py`,
`meshcorestation/web/assets/updates.js` and their update tests. Do not backport the
room server, its runtime hooks or its dashboard entry to stable. Publish the full
room implementation only on the feature branch. Users first update their existing
stable installation to obtain the selector; subsequent branch switches are web-only.
Both branches must retain `WEB_SWITCH_PROTOCOL = 1` and support both choices.
