# MeshcoreStation 5.6.0 — V4-Compatible Room Server

Restores the V4.4.1 Room Server on branch `V5`, using the existing Companion.
Up to four independent persistent Ed25519 rooms support password authentication,
automatic enrollment, up to 64 participants, Read/Write permissions, encrypted
posts, acknowledgments/retries, replay protection, advertisements, keep-alives,
session expiry and historical synchronization. New rooms start disabled.

Room Server follows Bot in the main dashboard accordion. The lazy, responsive
administration UI provides room creation/enabling/passwords, QR/contact links,
participant management and the latest 100 messages. Rooms continue operating
when the dashboard is closed. Raw packet traffic uses command 65, low priority,
serialized V5 access, bounded queues and at least 1.2 seconds between sends.
Room faults remain isolated; reconnect/shutdown clean up and restart the worker.

An enabled room can be selected as Bot destination. Only configured recognized
commands execute, with persistent deduplication and saved history, authenticated
sender/room identities and actual available RF evidence. Replies stay in the room;
normal channel selection switches back. Room permissions never grant management.
Scheduled battery reports can follow the bot or target an explicit room/private
channel. Missing/disabled/unavailable rooms fail without silent fallback, and
room deletion is blocked while configured as a managed repeater report destination.
Queued replies/reports are not confirmed recipient delivery.

Existing V4 `rooms.db` is reused without regenerating identities. Stop both apps,
back up their data, and copy only `rooms.db` into the V5 data directory; retain
V5's other databases. Preserve existing V5 rooms before replacement. Ownership
must match the service user, mode 0600. Passwords, members, posts, replay state,
cursors and selected bot room remain. Android contacts should remain valid.
See docs/room-server-development.md for setup, firmware requirements and backups.

Existing V5 settings, telemetry, passive statistics and change history are retained.
No firmware changes or extra serial connection are introduced. Live Android and
Companion interoperability has not been tested here. Release validation includes
Python/JavaScript regressions, fresh-install smoke checks and the required
Chromium desktop/mobile acceptance gate. V5 remains a prerelease. Branches main,
V3 and V4 are unchanged by this release.
