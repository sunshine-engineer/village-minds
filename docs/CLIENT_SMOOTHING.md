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

A native Windows Panda3D fixture rendered **121 updates at 60 FPS with five
snapshots/second**. After startup buffering, maximum per-frame actor displacement
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
