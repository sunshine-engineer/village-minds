# Single-server, single-client prototype

The server owns the world, local villagers, model calls, player actions and saves.
The Panda3D client renders authoritative snapshots and sends input commands. The
village continues when the client closes. Reconnecting never creates a new world.

This first version runs on loopback on one machine. It supports one active client
session and one possessed bot at a time. It is a foundation for remote hosting,
not an internet multiplayer release.

## Start without a model

Run these in two terminals from the repository root. Use the existing Python
installation instructions in the README first.

Windows PowerShell, terminal 1:

```powershell
.\.venv-win\Scripts\python.exe -m village.server --demo
```

Terminal 2:

```powershell
.\.venv-win\Scripts\python.exe -m village.client
```

Linux, terminal 1:

```bash
.venv/bin/python -m village.server --demo
```

Terminal 2:

```bash
.venv/bin/python -m village.client
```

The server prints its host, port and save path when ready. It defaults to
`127.0.0.1:8765` and `saves/server-village.json`, a separate slot from ordinary
single-player saves. Restarting the server resumes that saved world, including
memories and a destroyed village. To start another attempt while retaining failure
lessons, stop the server and restart it with `--new-game`; the old save is archived.
Do not run multiple server processes against the same save file.

## Enable the local Docker model

Start the existing Ollama Docker service and install the model as described in the
README. Then launch with the compact repair profile:

```powershell
.\.venv-win\Scripts\python.exe -m village.server --config configs/server-local.json
.\.venv-win\Scripts\python.exe -m village.client --config configs/server-local.json
```

Linux uses the same arguments with `.venv/bin/python`.

[The local-server preset](../configs/server-local.json) uses volunteer requests,
compact repair choices, a 15-second model deadline and a separate save/log path.
Resource scoring, repair handoffs and urgent deliveries remain disabled by default.
Model assistance has not demonstrated a survival advantage; see
[the evaluation results](EVALUATION_GAPS.md). Use `--demo` with this preset to run
its scripted baseline instead.

Both processes must use compatible world/rule/role/plugin settings. The client
checks the server's protocol and existing save fingerprint. It uses local assets
and trusted installed extensions; it does not download executable code or models.
Different visual settings are allowed. The client never runs local physics,
inference or campaign saves. The original `python -m village` remains available.

## Controls and reconnect

The existing number keys/Tab select a bot, O releases control, movement keys walk,
action keys perform work and Enter sends dialogue. Actions and possession become
visible after acknowledgement in a server snapshot. Camera movement remains local.
Pause, speed and save keys do not modify the server; its simulation keeps running
and autosaving.

Closing the client sends a disconnect request, releases the bot and returns it to
local autonomy. If the connection is lost, movement expires after `input_seconds`
and possession expires after `lease_seconds` without a heartbeat. The client retries
automatically. A resumed unexpired session can retain possession; after expiry or a
server restart it reconnects as an observer and the player selects a bot again.
A second client receives a clear session-conflict error until the first releases
or its lease expires.

Pending commands are discarded after a connection failure. A command whose reply
was lost may already have executed; the client does not silently replay it after
reconnect. The protocol uses command sequences to prevent duplicate effects and
reject skipped/old commands. Player movement supplies only bounded direction axes;
the server controls elapsed time, speed, collisions, cooldowns and resources.

## Configuration and protocol

All transport settings are under `network` in the normal JSON configuration:

| Settings | Purpose |
| --- | --- |
| `host`, `port`, `save_path` | Loopback listener and dedicated persistent world |
| `tick_seconds` | Fixed authoritative physics step |
| `poll_seconds`, `request_seconds`, `reconnect_seconds` | Snapshot/input cadence, HTTP deadline and retry interval |
| `lease_seconds`, `input_seconds` | Possession heartbeat and movement expiry |
| `queue_capacity`, `max_commands_per_tick` | Bounded inbound/client queues and per-tick command processing |
| `max_body_bytes`, `max_state_bytes` | Request and snapshot size limits |

Explicit network save paths resolve relative to their config file. Autosave cadence
uses `runtime.autosave_seconds`. Optional server decision logs use the normal
telemetry settings or `--decision-log path`; they must differ from the save path.
`--port 0` chooses a free port for tests. `--run-seconds N` makes a bounded smoke run.

HTTP transport uses the Python standard library:

- `POST /session` obtains or resumes a random session token and returns a snapshot.
- `GET /state` returns a snapshot and refreshes the session heartbeat.
- `POST /command` sends `{sequence, command}`. Commands are `takeover`, `move`,
  `action` and `say`. Every command is validated on the simulation thread.
- `POST /disconnect` releases possession/session ownership.
- `GET /health` reports server identity and simulated time without private state.

Use `Authorization: Bearer TOKEN` after creating a session. Do not put tokens in
URLs or logs. There is no arbitrary state upload, client-controlled clock, remote
code execution, remote save overwrite or remote shutdown endpoint.

HTTP handlers only parse/enqueue requests and send replies. A bounded queue transfers
work to the simulation thread, which serializes all world changes. Inference remains
in a background scheduler with a bounded child process, so it does not hold the
simulation thread. Snapshots include the existing validated save representation
and separate server/possession metadata. Graceful shutdown releases possession and
saves; restart also restores an observer state.

## Tested scope and limits

The tests exercise real HTTP takeover, session exclusivity, command replay, invalid
input, reconnect, background snapshots, disconnect release, save/restart and retained
memories. A Windows offscreen Panda3D check renders the remote world, acquires a bot,
sends dialogue, disconnects and reconnects while the same server continues. This is
not an OS keyboard test or a human multiplayer playtest.

This version uses [configurable position interpolation](CLIENT_SMOOTHING.md) for
villagers, monsters, animation and the follow camera. It adds a default 200 ms
presentation buffer while keeping the latest server state authoritative. It has
no movement prediction, delta snapshots, multiple players, account authentication,
TLS, LAN/internet hosting or remote asset sync. Snapshots are full-state. Session tokens
prevent accidental cross-client control; they are not an internet security design.
Only one server process should write a save. There is no simulation catch-up for
time when the server itself is stopped. Abrupt termination can lose progress since
the last autosave; ordinary client disconnect does not stop the server.


## Responsive movement exchange (protocol 2)

By default the client wakes its worker on changed movement input or a queued
command. A movement POST to `/exchange` replaces the separate movement POST plus
snapshot GET. HTTP handlers still enqueue requests; the simulation thread validates
sequence/session and input, advances the normal tick, then returns authoritative
state with the acknowledgement. The acknowledgement therefore includes a completed
physics tick; accepting the intent alone is not treated as rendered movement.

If another queued command disconnects/replaces the session in the same tick, the
pending exchange returns 401 and cannot expose the replacement session's snapshot.
Duplicate sequences retain command idempotence; an exchange snapshot may reflect
a newer tick. Movement expiry, leases and maximum commands/tick remain enforced.
The renderer still interpolates confirmed states and does not predict movement.

`network.exchange_motion` and `network.wake_on_input` both default to `true`.
Set both to `false` to reproduce the legacy transport for measurement. These are
transport settings and do not invalidate world saves. Client and server must use
the same wire-protocol version; older clients/servers are rejected during handshake.
See [responsiveness measurement](CLIENT_SMOOTHING.md) and the readiness checklist.
