# V3 architecture

## Ownership

`Runtime` owns the radio session and starts/stops companion control, voltage,
OLED and room workers. Reconnect closes the old workers before reopening serial.
Firmware updates pause the session before esptool takes ownership of USB.

`Companion` owns the serial connection and serialized command API. The control
lock coordinates bot commands and dashboard mutations; the reply lock protects
scope changes paired with channel sends. These locks serve different purposes.

The Flask/Dash server serves the UI in its own thread. `bridge` submits radio
operations to the event loop. HTTP code never opens a second USB connection.

## Commands and delivery

The command catalog lives in `command_store`. `Bot.match_command` selects a
configured trigger, `commands.actions` performs the action, `commands.context`
collects only requested values, and `commands.templates` renders the answer.
There is no second hard-coded help/ping/status/position engine.

`commands.delivery.ReplyDelivery` handles UTF-8 splitting, spacing and accepted
parts for both transports. Channel acceptance means submission to the companion;
room acceptance means insertion in local room storage. Neither confirms receipt
by every peer. Partial, failed and cancelled sends preserve only accepted text.
Both handlers finalize the shared command history.

Room packets are authenticated by `rooms.server.RoomEndpoint`. The radio worker
handles login, acknowledgments, synchronization and retries independently from
slow bot commands. Recognized commands enter a FIFO of 32 waiting items; a single
command consumer uses the companion control lock. It rechecks room enablement,
password revision, sender permission and selected bot room before execution.
Overload drops execution, retains the original room post, and increments the
visible dropped-command count. Shutdown cancels work and drains the queue.
This is an in-memory queue, not a durable job system: restart does not replay it.

## Persistence and HTTP

`storage/database.py` owns the existing station schema. `rooms/service.py` owns
`rooms.db`. Its service object is connection-free; operations open and close
SQLite connections locally, so the HTTP thread never shares an event-loop
connection. The room API initializes a service once per configured database path.
A panel snapshot reads all rooms on one connection inside a read transaction.

`web/http.py` is the single local-host/origin/control-header policy. These checks
are network/browser protections, not account authentication. Operate the dashboard
on a trusted network. Uncached JSON helpers preserve local API error shapes.
`geometry.py` supplies the shared haversine distance used by bot and maps.

## Development

Install runtime requirements into a virtual environment and install pytest for
Python tests. The JavaScript tests use Node.js and jsdom in a separate test setup.

```bash
python -m pytest -q tests
node tests/test_rooms_ui.cjs
node tests/test_updates_ui.cjs
python -m scripts.check_install
```

Tests use fake radios and temporary databases. Add tests for lifecycle, migration,
message handling and authorization changes. Hardware tests remain necessary for
Android interoperability, radio timings, firmware flashing and Pi Zero resource use.
Never test flashing or service installation against an unrelated host device.

## Dependency-change contract

`requirements.txt` is the updater's signal for new modules or changed versions.
Every change that adds an external import must declare the corresponding runtime
package there. The updater compares this file at the installed and target commits,
including branch switches. Identical files skip package checks, downloads,
installation and virtual-environment backup. Changed files stage binary wheels
before stopping the station, back up the virtual environment, install and validate.
The application smoke test and dashboard health check run on both paths.

This fast path does not repair an environment modified outside the updater. Use
Install / repair for broken dependencies. Do not introduce nested requirements or
external dependency manifests without extending the comparison to cover them.
