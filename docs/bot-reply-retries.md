# Channel-command reply retries

A channel command executes once. Only each saved reply part is retransmitted;
a retry never runs the command, telemetry request or configuration action again.
Room replies and private messages are not handled by this retry mechanism.

| Incoming command hops | Maximum submissions per reply part |
| --- | --- |
| 0 | Original + 1 retry |
| 1–63 | Original + 3 retries |
| Unknown/invalid | Original only |

Retries preserve the original channel slot/key and resolved flood scope. An
unresolved scope is never retried. The packet timestamp increases on each
submission, even during same-second sends or host clock rollback, so a repeat
of the saved text has a distinct packet identity. Command reception deduplication
remains separate and persistent.

## Timing and radio safety

The delay is `1.2 × (500 + 16 × estimated_airtime_ms) / 1000` seconds, following
MeshCore's flood timeout and the installed Python client's safety multiplier.
There are no fixed 60/120/240-second retry intervals. The packet estimate includes
UTF-8 sender prefix and reply text, timestamp/type bytes, AES block padding,
channel hash/MAC, packet header/path-length byte and scoped transport codes.
It uses reported Companion SF, bandwidth in kHz and coding-rate denominator.

The LoRa model uses explicit headers and CRC, automatic low-data-rate optimization
and MeshCore's 16-symbol preamble (32 at SF ≤ 8 in current firmware). On older
firmware with a shorter low-SF preamble this is conservative. Alternate firmware
PHY settings not exposed by the Companion protocol cannot be inferred. Missing
identity/radio information or an estimated packet airtime over ten seconds disables
retries; the original send behavior remains available.

Waiting happens asynchronously, outside the send/control locks. Before a retry,
the same existing locks serialize a fresh local Companion self-info read, queue
check and scope-select/send/reset sequence. The queue must report empty. A busy
or unavailable queue defers at the calculated flood interval, at most three times,
then cancels. These are USB/serial queries, not mesh radio requests.

At most 32 reply parts can have pending retry work. Additional retry transmissions
are limited to an estimated 60 seconds of airtime per rolling hour within the
radio session, including rejected/uncertain submissions conservatively. These
limits bound extra load; they are not a claim of regulatory duty-cycle compliance.
Original reply splitting/spacing remains unchanged. Serial acceptance and rejection
are recorded independently for every attempt. A lost result stays uncertain.

Disconnect, shutdown, firmware maintenance, bot-destination changes and relevant
Companion configuration requests cancel pending work. Identity/name/radio changes
found in readback also cancel it. A submission already in progress cannot be
recalled. Pending work is not replayed after restart, and saved history is retained.

## Forwarding evidence and command details

For multi-hop commands, an authenticated matching forwarded copy of any attempt
stops remaining retries for that reply part. Matching requires the original
channel key, exact sender-prefixed text, packet timestamp and flood scope, and a
nonempty observed forwarding path. Invalid MACs, unrelated text, other channels,
other scopes and zero-path copies do not stop retries. The existing five-minute
observation window applies independently to each attempt. A zero-hop command
still has its one allowed retry even if forwarding is heard.

**Outgoing replies** groups attempts beneath each saved reply part, showing
submission and packet timestamps, Companion acceptance, forwarding observations,
retry status/reason and the next pending time. Legacy records remain visible;
new metadata is added without replacing the station database or previous history.
The command's original completion status describes its first execution/submission;
subsequent radio attempts are shown separately in Outgoing replies.

Channel messages have no receiver delivery ACK. Forwarding evidence means the
packet was observed on a repeated route. **Receiver delivery is not confirmed.**
No forwarding observation is not proof of delivery failure.

Protocol references: [MeshCore Companion timeout and channel send](https://github.com/meshcore-dev/MeshCore/blob/main/examples/companion_radio/MyMesh.cpp),
[group text framing](https://github.com/meshcore-dev/MeshCore/blob/main/src/helpers/BaseChatMesh.cpp),
[RadioLib wrapper/preamble](https://github.com/meshcore-dev/MeshCore/blob/main/src/helpers/radiolib/RadioLibWrappers.h),
and [LoRa airtime calculation](https://github.com/jgromes/RadioLib/blob/master/src/modules/SX126x/SX126x.cpp).
