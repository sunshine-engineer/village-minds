# Three-minute review walkthrough

This is a recording script, not a claim that a video or human playtest exists.
Use a disposable save. Keep the scope visible: loopback, one client, one possessed
villager, local scripted autonomy and an optional model planner.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Start the headless server and connect the 3D client | The server owns physics, villagers, model requests and persistence |
| 0:30–1:00 | Observe role routines, then take over a villager and move/work | Fast local policies continue while background inference is pending |
| 1:00–1:30 | Deliver supplies or repair; release control; reconnect | The world continues when the client leaves; input/session expiry returns control safely |
| 1:30–2:00 | Restart the server using the same save | Show preserved resources/time/memory. Stored lessons are persistence, not trained model weights |
| 2:00–2:30 | Open the contention benchmark report | Compare actual task ownership and gate breaches against scripted and adverse controls; name the tested model/hardware |
| 2:30–3:00 | Show a rejected/late response, readiness checklist and limits | Explain validation, timing-grid regression, latency and the evidence still missing |

Windows, from the repository root, in separate terminals:

```powershell
.\.venv-win\Scripts\python.exe -m village.server --config configs/repair-priority.json --save-path saves/portfolio-demo.json
.\.venv-win\Scripts\python.exe -m village.client --config configs/repair-priority.json
```

Start the documented local Docker model first, or add `--demo` to the server
command for a model-free walkthrough. Linux uses `.venv/bin/python` with the same
arguments and needs a working graphical backend. The client need not have model
weights; model inference runs on the server side through Docker.

Preserve the server output and show the actual configuration used. Do not splice
benchmark outcomes into live footage as if they happened in that village. The
controlled benchmark uses a deliberately short repair-decision scenario with
fatigued helpers and repair-first task priority. It does not prove full-village
survival, emergent conversation or an LLM advantage over a scripted planner.

## Human acceptance record

Leave each item pending until someone performs it. Record date, reviewer, commit,
OS/Python/model, commands and any issue; attach a recording or notes if available.

- [ ] Another developer installs from a clean clone using only the README.
- [ ] A 30-minute wall-time playtest completes without a crash.
- [ ] Exercise all roles, ten possession switches and three reconnects.
- [ ] Walk, stop and reverse near walls; inspect camera/animation and collisions.
- [ ] Restart and verify resources, villager state and stored lessons.
- [ ] Test with the model stopped and confirm local gameplay continues.
- [ ] Record the three-minute walkthrough and check that its narration matches the evidence.

Automated clean-venv installation, simulated-time soak and internal input rendering
checks support this review; they do not fill in these human checkboxes.
