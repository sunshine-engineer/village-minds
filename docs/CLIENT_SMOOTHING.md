# Network client movement smoothing

The client now renders villagers, monsters and the follow camera from a bounded
buffer of confirmed snapshots. Authoritative positions, collisions, actions, health
and saves still come from the server. No client physics or movement prediction is
introduced. Single-process rendering retains its direct position/time behavior.

Previously an actor jumped to its newest position only when a packet arrived.
Walking animation also used the snapshot's frozen time. The client now advances a
presentation playhead between packets, interpolates confirmed positions, and uses
the interpolated time for leg/body animation. The camera follows exactly the same
displayed position as the selected villager.

## Buffer and correction behavior

The network worker adds a local monotonic receive timestamp and connection epoch
to each packet. These are client metadata; the wire protocol and server clock are
unchanged. Rendering uses receive-time intervals, so it does not require synchronized
clocks between the two processes.

A playhead normally trails received data by 200 ms. On a buffer underrun it holds
the most recent confirmed position; it never predicts farther into an unknown
path. When more data arrives, it resumes without jumping straight to the new
snapshot and can catch up at up to 1.1x playback speed. Network jitter can temporarily
increase the display delay. The frame history remains bounded.

Reconnects, server changes, possession changes and long receive/render gaps reset
the buffer. Old epochs and out-of-order frames are rejected. Large position
corrections snap instead of sliding across the village. Entity generations prevent
interpolation across death/respawn or reuse of a removed monster ID. New entities
and removals follow the latest snapshot immediately. Gameplay/HUD state remains the
latest authoritative snapshot, even while positions are displayed slightly behind it.

## Configure the tradeoff

All settings are under `network.interpolation` in the normal JSON config:

| Setting | Default | Purpose |
| --- | ---: | --- |
| `enabled` | `true` | Use buffered rendering; false restores direct snapshot positions |
| `delay_seconds` | `0.2` | Normal presentation delay, in addition to transport/input latency |
| `buffer_size` | `32` | Maximum retained frames; supported range 2–512 |
| `max_gap_seconds` | `0.75` | Reset after a long receive gap or paused renderer |
| `snap_distance` | `4.0` | Snap corrections larger than this many world units |
| `catch_up_rate` | `1.1` | Maximum playback speed during recovery; supported range 1–2 |
| `catch_up_threshold_seconds` | `0.05` | Extra playhead lag before catch-up activates |

Delay cannot exceed the maximum gap; gap, distance and catch-up threshold must be
positive. Ordinary type/nonfinite/range checks also apply. Restart the client after
editing these startup settings. They do not affect the save/gameplay fingerprint,
so client-only smoothing overrides can connect to the same server.

For direct rendering, save this as a client config and pass it to
`python -m village.client --config path/to/client.json`:

```json
{
  "network": {
    "interpolation": {
      "enabled": false
    }
  }
}
```

A smaller buffer delay can feel more responsive but underruns more often when
packets arrive irregularly. Smoothing does not remove network input latency.
Prediction/reconciliation and more efficient transport remain separate future work.
Interpolation connects confirmed positions; it does not run collision checks along
the displayed segment or reconstruct every intermediate server path corner.

## Validation and reproduction

The deterministic tests cover intermediate poses and animation time, packet jitter
and loss, bounded catch-up, no extrapolation, teleports, respawns, removed/reused
IDs, reconnect/server/possession changes, stale frames, long gaps, bounded memory,
disabling smoothing, frame rates 30/60/144, and unchanged gameplay fingerprints.
Configuration checks reject invalid smoothing settings.

A native Windows Panda3D fixture rendered **121 updates on a simulated 60 FPS
timeline with five snapshots/second**. This tests scene transforms at fixed time
steps; it does not measure achieved GPU frame rate. After startup buffering, maximum per-frame actor displacement
was **0.083334 units**, versus **1.0 unit** for direct snapshot positions. Assertions
also checked monster interpolation, camera/actor alignment, animation changes
between packets, and unchanged authoritative position/time. This is a controlled
straight-line rendering fixture, not a latency guarantee or human playtest.

Run the same fixture from the repository root:

```powershell
.\.venv-win\Scripts\python.exe scripts/check_client_interpolation.py
```

```bash
.venv/bin/python scripts/check_client_interpolation.py
```

It renders offscreen and writes `artifacts/client-interpolation.png` and
`artifacts/server-client/interpolation-render.json`. The recorded
[measurement trace](results/client-interpolation-render.json) includes the sampled
frame transforms. Ordinary client launch commands are unchanged; see
[server/client setup](SERVER_CLIENT.md).

The real Windows client/server smoke check also accepted movement and dialogue,
released possession, reconnected to the same running village and preserved its save.
The original single-process Windows render check passed as well. These checks use
internal input dispatch rather than OS keyboard automation.


## Historical eight-sample responsiveness diagnostic — 22 October 2026

This earlier shared-process fixture predates responsive transport. It is not the
current acceptance measurement; see the separate-process results below.

The [real loopback trace](results/client-responsiveness-v1.json) measures input
onset through the actual HTTP worker, authoritative snapshots and offscreen
Panda3D `renderFrame()` calls. Inference and regression suites were idle. Eight
samples per setting alternate order; the server uses its normal 50 ms tick and
100 ms client poll interval. This is wall-clock measurement, unlike the earlier
synthetic interpolation timeline.

| Input-to-stage latency | Direct snapshots median / max | Interpolation median / max |
| --- | ---: | ---: |
| First matching movement request sent | 127.9 / 156.2 ms | 167.4 / 217.9 ms |
| Command acknowledgement received | 192.7 / 216.5 ms | 235.6 / 272.0 ms |
| First observed authoritative displacement | 257.7 / 292.0 ms | 303.4 / 333.8 ms |
| First rendered displacement | 278.3 / 306.5 ms | 323.7 / 362.9 ms |

The start time is the fixture's internal key-state update. Snapshot/render onset
requires more than 0.01 world units in the requested direction. Acknowledgement
means the server accepted the intent; it is not proof that physics moved the bot.
The snapshot and rendered measurements confirm movement separately.

This measures first visible motion in an open-area fixture, not sustained tracking
lag, GPU FPS, OS keyboard latency or human perception. Interpolation can start
showing part of a newly confirmed segment before the entire segment has played;
its configured 200 ms buffer is not a fixed extra 200 ms on this onset metric.
Poll/tick phase differs between samples, so subtracting the two group medians is
not a causal estimate of the buffer cost. Small host-specific samples do not
establish an internet/network performance target.

A substantial part of the measured onset delay occurs before a matching request
is sent or a state is returned. The original worker serialized movement POST,
state GET and a poll wait. The revised transport combines movement with a post-tick
snapshot, wakes on input changes, disables server-side Nagle buffering, and publishes
input before restoring snapshots. The default 200 ms interpolation buffer remains. This keeps
prediction complexity tied to a measured need. The buffer remains configurable.

Current fixture command, with no separately running server required (it does not
reproduce the old shared-process implementation):

```powershell
.\.venv-win\Scripts\python.exe scripts/check_client_responsiveness.py --samples 50 --transport responsive
```

Linux uses `.venv/bin/python` with Panda3D and a working graphics backend. The
fixture starts a loopback server on an ephemeral port, uses a separate server process and a temporary save slot and writes `artifacts/server-client/responsiveness.json`; it does not
read or write campaign saves. Missing stages or server errors fail the check.

A human playtest remains outstanding: use normal server/client windows, take over
a bot, walk/stop/reverse near a wall, then release and reacquire it. Compare a
config override with `network.interpolation.enabled=false` against the default;
record responsiveness, snapping and collision corrections. This manual check is
separate from the verified internal-input rendering fixture.


## Portfolio measurement revision

The final fixture uses a separate authoritative server process, matching the normal
server/client architecture. Earlier measurements shared a Python process with the
renderer, so GIL contention confounded their timing. Those diagnostics are retained
and must not be presented as the final deployment comparison. The fixture defers
monster waves, waits for stationary authoritative/display positions, alternates
interpolation order, and retains partial samples on error. It injects internal key
state and explicitly renders frames; it does not measure OS input latency.

The production changes are independently covered by protocol, possession-release
and input-before-poll regressions. Neither transport predicts local movement.

The 2026-10-22 separate-process check collected 50 samples per mode per transport.
With default interpolation, legacy onset was 395.660/752.009 ms median/p95 and
responsive onset was 238.693/452.459 ms (maximum 653.546 ms). Direct rendering
was 96.071/281.647 ms with responsive transport. The interpolated p95 misses the
predeclared 400 ms target. See the [release evidence](PORTFOLIO_READINESS.md)
for raw samples, source commit, teardown error and remaining acceptance gates.
