# Survival prototype validation — 22 October 2026

## Continuous autonomy update

- All 37 tests pass on Linux and native Windows. The new tests hold a real background worker on an event and verify **all six villagers move while that one model call remains blocked**, with one request and zero accepted model decisions. Other new checks cover takeover isolation, model-error cooldowns, urgent needs overriding a model destination, guard patrols, field inspection while crops grow, distinct work slots, contextual chatter, strategic action schemas, and accurate model/local counters.
- A native Windows five-second game run showed all six moving before the first accepted model response. Each moved more than eight world units from its starting position. This was a temporary session and did not modify the user's save.
- A native Windows offscreen run then confirmed continued local work **plus an accepted real background model plan**: 26 local actions and one accepted model decision over 25.13 seconds. Evidence: `artifacts/autonomy-windows-model.json` and its screenshot. The offscreen run avoided taking keyboard focus.
- An additional full X11 keyboard-check attempt did not complete its exact-text assertion: the field received extra characters instead of `hello123`. No new full keyboard-suite pass is claimed for this controller change; the prior 33-check result below is historical. The new unit tests and native concurrency checks are the current autonomy evidence.
- Local routine actions are never counted as model responses. The window test now reads the scheduler's accepted model history directly, avoiding a false positive when local work happens while Ollama is connected.
- The save schema did not change. Existing world snapshots remain compatible. Model requests remain serial; routine decisions and simulation movement run independently for all villagers.

## Confirmed in this environment

Python 3.14.4, Panda3D 1.10.16, Linux/WSL2 with WSLg, and Docker-hosted Ollama 0.32.15 / `qwen2.5:1.5b` were used. Native Windows Python 3.14.7 was also tested using the existing `.venv-win` environment; commands are in README.md.

- **37 standard-library tests passed on both Linux and native Windows** with their respective Python executables and `-m unittest discover -s tests -v`. Python compilation passed.
- Tests cover perception/hearing, memories, action validation, paths and boundaries, takeover/release and stale results, background inference, role bonuses, crop planting/growth/harvest, shared deposits/eating, repairs, guarding/combat/cooldowns, starvation/death, waves, and failure recording.
- Save tests cover timers/positions/inventory/conversation/RNG round trips, retained failure history, context supplied to the model, corrupt-primary recovery, rejecting invalid state, preserving a save after a failed atomic replacement, and saving immediately after a killing blow before monster cleanup.
- A deterministic **idle village failed at 429.3 simulation seconds**. With the same seed, the **scripted cooperation baseline survived 900 simulation seconds with village health 200/200**, living villagers, shared food/wood, harvests, repairs, and kills. This is a game-rule comparison, not an LLM cooperation benchmark.
- The offscreen smoke test rendered successfully on both Linux and native Windows (`wglGraphicsPipe`). A separate scene fixture rendered two monsters outside the walls, a breached gate, a damaged gate, a damaged village center, and empty/growing/ripe crops. Assertions checked monster nodes, hidden breached-gate geometry, and crop-stage geometry. Screenshot: `artifacts/survival-scene.png`.
- **Previous survival release: 33 assertions passed in an actual onscreen game with live AI and an isolated save slot**. Keyboard events were sent through X11 to the real graphics window. Checks include exact repeated-letter text entry, possession, moving, planting, harvesting, wood gathering, depositing, eating, repairs, attacks, sustained guarding, elder rally, rest, camera orbit, chat cancellation, pause/resume, F5 saving, and reloading role contributions/timers. A real accepted model `farm` action was captured. The complete run took 65.55 seconds. Evidence: `artifacts/window-check-live.json` and its screenshot.
- On both Linux and native Windows, two actual CLI game processes verified **normal exit saving and automatic resume** of changed shared inventory, village health, and dialogue memory. Their scheduled exits used the same `userExit` path as normal quitting; they were not forcibly killed. An isolated temporary save was used. Evidence: `artifacts/restart-check.json`.
- A native Windows `python.exe -m village.probe --timeout 60` call reached the Docker model at localhost and received an accepted `move` action targeting the farm. The repeated native rendering smoke check completed without framebuffer warnings after requesting an offscreen-compatible buffer.
- A real loss → save → new attempt → save → reload → local-model request check passed. The new attempt was number 2; Mira's observation included the earlier loss, breached gates, stock levels, and her zero contributions. The real model chose an accepted `move` action targeting the farm. Evidence: `artifacts/failure-memory-model-check.json`. This confirms memory delivery and execution, not improved reasoning or learned model weights.

The onscreen test uses position, resource, enemy, and energy fixtures to isolate each action; it does not claim the player manually walked the whole route. Targeted X11 events exercise the input/GUI pipeline, not direct calls to the action handlers. The underlying mechanics are checked separately in the logic tests.

## Persistence behavior verified / intended limits

- The default slot is the project-relative `saves/village.json`, resolved from the module location so changing the terminal working directory does not silently choose a different slot when using this editable checkout.
- Normal startup resumes that slot. F5, normal exit, a detected loss, and a ten-real-second autosave interval write snapshots. Temporary sessions and smoke tests do not load or overwrite the normal campaign.
- Atomic replacement protects the current snapshot; `.bak` retains a prior snapshot. Interrupted writes and damaged primaries were tested. Backups are local, not an external backup service.
- A destroyed village remains destroyed on ordinary restart. `--new-game` archives its prior run and retains bounded failure records/lessons while creating a fresh healthy attempt.
- Offline time does not advance simulation. Player possession and pending model requests are session state; villagers resume under AI with fresh decisions.
- Run one game instance per save slot. Cross-process write locking and schema migrations are not implemented.

## Limits that remain

- No human manual playtest is claimed. Native Windows rendering/startup/exit/restart and logic/persistence checks passed; the full targeted keyboard integration evidence is from Linux/WSLg.
- CPU inference is slow. A six-villager model cycle can take much longer than one decision. All local routines continue during requests and error cooldowns; the live checks establish accepted model plans, not uninterrupted successful inference. Default routines and occasional role remarks are explicitly scripted, not evidence of generative reasoning.
- Model cooperation, consistent personalities, causal understanding, and improvement across attempts have not been established. Memories are bounded context, not training. A single move-to-farm response after a failure does not prove learning.
- Failure records summarize observed conditions and contributions. They are not a counterfactual analysis proving which specific choice caused the loss.
- Combat, wall/vision interactions, and monster steering are simplified. This is not a full physics or tactical AI implementation.
- Long-running balance beyond the deterministic 900-simulation-second baseline has not been established. Stronger waves can overwhelm the village.
- Sudden process/power failure can lose progress after the latest successful save. Recovery from abrupt native Windows power loss and multi-session conflicts remain untested.

## Reproduce

```bash
python3 -m unittest discover -s tests -v
.venv/bin/python -m village --smoke-test
.venv/bin/python scripts/check_window.py
.venv/bin/python scripts/check_window.py --live --save-path artifacts/window-test-save.json
.venv/bin/python scripts/check_restart.py
.venv/bin/python scripts/check_autonomy.py --headless --wait-for-model
.venv/bin/python -m village.probe
```

The explicit window-test slot is an isolated fixture; previous runs of that slot are archived. `check_restart.py` uses a temporary slot. None of these commands needs the user's normal campaign. The last three graphics/model checks need their respective desktop or Ollama services.
