# Village Minds — Willowbrook survival prototype

A Python/Panda3D village with six villagers using fast local role routines and background plans from a Docker-hosted model. Take over any villager, grow and share food, supply repairs, and defend the village from respawning monster waves. The village and its memories resume when you restart.

## Start on Windows — PowerShell

Use **native Windows Python**, separate from a Linux/WSL virtual environment. From PowerShell:

```powershell
cd D:\projects\3d_game

# First-time setup; rerun pip install after dependency changes.
py -3 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e .

# Practice without AI or changes to your saved campaign.
.\.venv-win\Scripts\python.exe -m village --demo --no-save
```

For AI villagers, start Docker Desktop and run:

```powershell
cd D:\projects\3d_game
docker compose up -d

# First-time model download; safe to rerun if already downloaded.
docker compose exec ollama ollama pull qwen2.5:1.5b

# Start or resume the saved village.
.\.venv-win\Scripts\python.exe -m village
```

For subsequent launches, start Docker Desktop, run `docker compose up -d`, and launch with the last command. Environment activation is unnecessary because the executable path is explicit. Use **`-m village`**, without `.py`. Do not use `.venv/bin/python` or source the Linux activation script in PowerShell.

If `py` is unavailable, install Python 3.11+ for Windows and reopen PowerShell. Native Windows Python passed the logic/persistence tests, rendering smoke check, normal exit/restart check, and local-model API probe. The full keyboard-event integration check ran on Linux/WSLg; no human manual playtest is claimed.

## Start on Linux / WSL — Bash

A graphical desktop/OpenGL backend is required; WSL needs working WSLg. In this checkout:

```bash
cd /mnt/d/projects/3d_game

# First-time setup. On native Linux, use your actual checkout path above.
python3 -m venv .venv
.venv/bin/python -m pip install -e .

# Practice without AI or changes to your saved campaign.
.venv/bin/python -m village --demo --no-save
```

With Docker running:

```bash
cd /mnt/d/projects/3d_game
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:1.5b
.venv/bin/python -m village
```

Python 3.11+ is required. Panda3D 1.10.16 is pinned. The game window runs on the host; only the model runs in Docker. The Linux `.venv` and Windows `.venv-win` are different environments and must not be shared.

## Fast-forward and AI evaluation

Press **V** during play to cycle 0.5x, 1x, 2x, 5x and 10x; the HUD shows speed.
Use `--pace 10` to start fast. Survival rules advance in small substeps.

To test fifteen simulated minutes without waiting for a game window:

```powershell
.\.venv-win\Scripts\python.exe -m village.evaluation --seeds 7 --duration 900
```

```bash
.venv/bin/python -m village.evaluation --seeds 7 --duration 900
```

This runs scripted villagers without Docker and generates a report under
`artifacts/evaluations/`. Add `--modes all` for scripted / AI / AI-with-memory
comparisons. Model calls now wait for active monster threats, spread across the
scenario horizon and rotate among roles. Reports show actual role/threat coverage.
Individual requests and whole suites have time/call limits.
AI inference still takes real time; evaluation pauses at bounded decision checkpoints.

See the [evaluation guide](docs/EVALUATION.md) for short AI commands, metrics, limits
and `--decision-log artifacts/decisions.jsonl` during normal play.

## Roles and cooperation

| Villager | Role | Responsibility / bonus |
| --- | --- | --- |
| Mira | Farmer | Plant crops, harvest, deliver food; 6 food per harvest |
| Iris | Farmer | Keep food production running; 6 food per harvest |
| Bram | Worker | Haul supplies, gather wood, repair gates; 3 wood per gather and 18 gate HP per repair |
| Otto | Soldier | Guard threatened gates; 20 damage per strike |
| Nell | Soldier | Cover other threatened gates; 20 damage per strike |
| Edda | Elder | Coordinate, help with food, rally nearby villagers using shared food |

Everyone can contribute: other roles harvest 4 food, gather 2 wood, repair 10 HP, and strike for 8 damage. These are game mechanics, not just personality prompts. Everyone needs food and energy.

The village starts with 200 health, four gates with 150 HP each, 18 shared food, 12 shared wood, and four ripe crop plots. The first monster wave appears after 180 **simulation seconds**, then another every 90 seconds, with more monsters in later waves and at most ten active enemies. Monsters spawn outside the walls, attack their gate, and advance toward the village center after a breach. They can kill nearby villagers. Guarding is a sustained task: villagers travel to the gate and automatically strike enemies within eight units until given another task.

The village is lost if its health reaches zero or all villagers die. Hoarding food, neglecting planting, running out of repair wood, or failing to defend gates can cause a loss. A healthy farmer cannot replace every soldier, and guards cannot feed the village without shared supplies.

The default simulation pace is `0.5`, so the first-wave grace period is about six real minutes at normal frame rates. This leaves time for slow CPU inference. Use `--pace 1` for normal speed or `--pace 0.25` for more thinking time. There is no offline progression: closing the game does not consume food or advance monsters.

## Farming and the storehouse

```text
Farm: harvest ripe plot → carried food → storehouse: deposit → others can eat
Farm: plant empty plot → grow for 45 simulation seconds → harvest again
Orchard: gather wood → carried wood → storehouse: deposit → repair damaged gates
```

Crops visibly change between empty soil, growing green crops, and ripe yellow crops. Harvesting empties a plot; someone must replant it. Walking past the farm does not harvest or plant it.

Food and wood in a villager's inventory remain private until deposited. Eating consumes one carried food, or one shared food when at the storehouse, and reduces hunger by 35. Repairing consumes one shared wood and energy, and requires proximity to a damaged gate. Work actions have a one-second simulation cooldown, so holding/spamming an action cannot create unlimited supplies.

## Controls

Select the game window before pressing keys.

| Key | Action |
| --- | --- |
| 1–6 / Tab | Take over a living villager / cycle villagers |
| 0 | Release control to AI; observer mode |
| WASD | Walk relative to camera |
| Left / right arrows; mouse wheel | Orbit; zoom |
| Enter | Open dialogue; Enter again submits |
| F | Plant an empty nearby farm plot |
| H | Harvest a ripe nearby farm plot |
| E | Gather wood near the orchard |
| T | Deposit carried food and wood near the storehouse |
| C | Eat carried food, or shared food at the storehouse |
| R | Rest to recover energy |
| G | Travel to and guard the nearest gate |
| J | Repair a nearby damaged gate using shared wood |
| K | Attack a nearby monster |
| L | Elder rally; uses one shared food to support nearby villagers |
| Q / U / Y / X | Request help / elder offers task / accept task / release task |
| P | Pause / resume simulation |
| F5 | Save immediately |
| Escape | Cancel dialogue, or quit and save |

People within eight units hear player and bot dialogue. Role routines include occasional contextual remarks about food, repairs, threats, and sharing; these remarks are scripted and do not interrupt walking. Model-generated dialogue is an additional slower layer. Replies are asynchronous and not guaranteed. Role instructions, warnings, and previous failures guide model decisions, but the model can still choose poorly. `--demo` runs local routines without model calls; normal mode runs those same routines alongside background AI.

## Saving, continuing, and learning from failure

**Normal launches automatically resume** `saves/village.json` in the project folder. The default is based on the installed module location (this checkout when installed with `-e .`), not the terminal's working directory. Windows and WSL can share this JSON file when they use the same checkout. Run only one game instance per save path at a time.

The snapshot includes:

- Positions, paths, roles, health, hunger, energy, carried food/wood, contributions, and recent conversation memories.
- Crop stages/growth, shared stock, gate/village health, monster positions/health, wave timers, and random-generator state.
- Previous failure records and each villager's bounded lessons from them.

The game saves every **10 real seconds**, on **F5**, on normal exit, and immediately when a village is lost. Writes use a temporary file plus atomic replacement; `.bak` retains the previous snapshot. A corrupt primary falls back to a valid backup. If neither is valid, startup stops with an error and does not overwrite them. An abrupt process/power failure can lose progress since the most recent successful save. Read the HUD for save failures.

Player possession is not restored; the saved villager resumes under AI until you take control again. Time does not advance while the game is closed.

A destroyed village stays destroyed on a normal restart. To begin a fresh attempt **while retaining lessons and failure history**:

```powershell
# Windows
.\.venv-win\Scripts\python.exe -m village --new-game
```

```bash
# Linux / WSL
.venv/bin/python -m village --new-game
```

`--new-game` archives the prior run with a timestamp, restores a healthy village, increments the attempt number, and carries its failure lessons forward. It also works for deliberately abandoning a living village; only actual losses produce failure lessons.

At a loss, each villager receives a factual record of why the attempt ended, breached gates, remaining shared resources, and their own contributions. Those records persist and are included in future model observations. This is **external memory in the prompt**, not model-weight training, reinforcement learning, or a guarantee of better cooperation. Failure summaries describe the recorded conditions; they are not proven causal explanations.

Use another save slot or a temporary session:

```powershell
.\.venv-win\Scripts\python.exe -m village --save-path saves\experiment.json
.\.venv-win\Scripts\python.exe -m village --demo --no-save
```

```bash
.venv/bin/python -m village --save-path saves/experiment.json
.venv/bin/python -m village --demo --no-save
```

`--no-save` neither loads nor writes a campaign. The smoke test is always temporary. Keep backups of the whole `saves` folder; it contains local game history and dialogue. Save files are JSON, not Python pickle.

## Local model and decision boundaries

Ollama serves Qwen2.5 1.5B by default, shared across villagers with separate personalities and observations. The model is Apache-2.0 and its download is about 986 MB; the Docker image needs additional disk space. CPU speed and memory use depend on hardware. The included configuration is CPU-first. See [Ollama Docker instructions](https://docs.ollama.com/docker) for supported GPU setup.

```text
Authoritative Python world
 → surroundings + role + survival warnings + recent memory + past failure lessons
 → background Ollama /api/chat request
 → structured action → current-state validation → simulation update
 → atomic JSON snapshot
```

The per-request JSON schema exposes currently available actions and valid targets. Python checks distance, role, cooldown, energy, resource availability, and living/dead state again before execution. Model text cannot execute code. The model receives a global village-status board and known map, plus nearby villagers/enemies; vision and hearing use radius checks without wall occlusion.

### Continuous autonomy

Every living, unpossessed villager evaluates needs and role duties independently about every **0.8–0.95 simulation seconds**. This runs before a model response arrives, during inference, and during model-error cooldowns:

- Farmers plant, harvest, deposit food, and inspect growing fields while waiting.
- Workers gather/deposit wood and repair damaged gates.
- Soldiers travel to threatened gates, patrol when clear, and attack automatically in range.
- The elder supports villagers, helps with food, and checks the village.
- Hunger, energy, stock shortages, and threats change priorities. Personal work slots reduce crowding.

Model calls are still serial to bound local inference load; **villager movement and work are concurrent**. The background model chooses longer-lived destinations, gate assignments, or dialogue rather than delayed one-off harvesting commands. Accepted movement orders can finish before routines resume, with a 20-simulation-second upper limit; urgent needs take precedence. A model-assigned guard can keep defending while that gate remains threatened.

Successful model decisions have a 15-simulation-second minimum interval per villager, unless newly heard speech or alarms bring a decision forward. Requests time out after 25 real seconds; errors delay model retries by 20 simulation seconds while **local behavior keeps running**. Invalid/outdated model choices are skipped without stopping the villagers. Takeover/release still invalidates pending decisions, and pausing stops the simulation and decision application.

The HUD separately counts **local actions** and **accepted AI decisions**. An active village is not proof that a model is responding; local routines are explicit game AI. Nearby routine chatter is globally limited to one line every 12 simulation seconds and each speaker has a longer cooldown.

Restart with the usual command to resume your campaign under the default rules. Version 1 saves are upgraded to format 2 when saved; customized world/rules settings require a separate save slot.


Configuration:

- `--model TAG` or `VILLAGE_MODEL`: use a different installed Ollama model.
- `--url URL` or `OLLAMA_URL`: default `http://localhost:11434`.
- `--pace NUMBER`: between 0.1 and the configured maximum (10 by default); default 0.5.
- The Compose API binds to host loopback only. Observations and dialogue go to the configured endpoint.
- The inspected Ollama 0.32.15 image digest is pinned in `compose.yaml`.

To stop Ollama while preserving downloaded models:

```bash
docker compose down
```

## Validation

See [VALIDATION.md](VALIDATION.md) for what was actually tested and the remaining limits. The survival loop has a scripted baseline; that is not evidence of reliable LLM cooperation.

Logic and save/reload tests use the Python standard library:

```powershell
.\.venv-win\Scripts\python.exe -m unittest discover -s tests -v
```

```bash
python3 -m unittest discover -s tests -v
.venv/bin/python -m village --smoke-test
.venv/bin/python scripts/check_window.py
.venv/bin/python scripts/check_window.py --live
.venv/bin/python scripts/check_restart.py
.venv/bin/python scripts/check_autonomy.py
.venv/bin/python -m village.probe
```

The window checker is Linux/X11-specific and requires system `libX11`. It opens a temporary game, sends keyboard events to the actual window, checks controls, saves a screenshot/report under `artifacts/`, and closes it. It does not touch the normal campaign. It uses position/resource fixtures for action checks and does not claim manual playtesting.

The smoke test renders offscreen and saves `artifacts/village-smoke.png`; a graphics backend is still required. Model probes require a running Ollama instance.

## Troubleshooting and prototype limits

- **PowerShell starts nothing with `.venv/bin/python`:** that is the Linux environment. Use `.venv-win\Scripts\python.exe` as shown above, and use `-m village` without `.py`.
- **`/dev/input` messages under WSL:** raw Linux gamepad discovery is optional here. When that directory is absent, startup replaces device-category diagnostics with a keyboard/mouse notice. Graphics errors remain visible.
- **`Known pipe types: glxGraphicsPipe`:** normal renderer information. `Village Minds ready` confirms initialization finished.
- **No window:** use native Windows Python or a functioning desktop/WSLg OpenGL setup.
- **`MODEL FALLBACK`:** check `docker compose ps`, `docker compose logs --tail 40 ollama`, and `docker compose exec ollama ollama list`. Ensure the requested model tag is installed.
- **Port 11434 already in use:** use the existing Ollama service or resolve the conflict before starting this container.
- **Slow AI dialogue/plans:** local role routines continue while the model thinks. Use the separate HUD counters to distinguish activity from model responses. A smaller model, supported GPU, or slower `--pace` can help; shared memory does not make inference faster.
- **Action rejected:** verify proximity, energy, role, cooldown, plot maturity, and shared inventory. Guards attack automatically while guarding; moving or resting cancels that duty.
- **Save not resumed:** check the printed absolute save path and omit `--no-save` / `--new-game`. Use the same save slot on each launch.
- **Save error:** preserve the original and `.bak`. Do not delete your campaign merely to clear an error. Unsupported schema versions fail explicitly; automatic format migrations are not implemented.

This remains a flat-grid prototype with radius combat, simplified monster steering, and procedural art. Monsters target gates and then the center; they do not use full physics/interior navigation. Villagers can overlap. There is no multiplayer, model training, sophisticated relationship system, crafting tree, or final victory objective. Failure lessons and personalities are prompts, not proof of reliable reasoning.

## Source layout and references

The code separates simulation, local policies, model transports, rendering, assets,
controls and persistence. Existing `village.simulation` imports remain supported.
See [architecture](docs/ARCHITECTURE.md) for the module ownership map.

### Customizing and contributing

Use a startup JSON override to change settings without editing Python:

```powershell
.\.venv-win\Scripts\python.exe -m village --config examples/custom.json --demo --no-save
```

```bash
.venv/bin/python -m village --config examples/custom.json --demo --no-save
```

- [Configuration reference](docs/CONFIGURATION.md): defaults, overrides, paths and save compatibility.
- [Extension recipes](docs/EXTENDING.md): visual prefabs, custom actions, roles, systems and model backends.
- [Default settings](village/data/default.json), [asset catalog](village/data/assets/catalog.json), and [model profiles example](examples/models.json).

New saves use format 2. Existing format 1 campaigns load with default gameplay rules.
Changing gameplay/map settings requires a separate save slot; it never silently resets
a campaign. Camera, visuals, controls and model settings can change without resetting.

References: [Panda3D tasks](https://docs.panda3d.org/1.10/python/programming/tasks-and-events/tasks), [Panda3D configuration](https://docs.panda3d.org/1.10/python/programming/configuration/list-of-all-config-variables), [Ollama chat API](https://docs.ollama.com/api/chat), [Ollama Docker](https://docs.ollama.com/docker), [Qwen2.5 1.5B model/license](https://ollama.com/library/qwen2.5:1.5b).

## Project documentation and license

- [Architecture](docs/ARCHITECTURE.md): simulation, local routines, model decisions and saves.
- [Contributing](CONTRIBUTING.md): development checks and bug reports.
- [Validation evidence](VALIDATION.md): completed checks and remaining limits.

Project code and documentation are available under the [MIT License](LICENSE).
Panda3D, Ollama and downloaded models retain their own licenses.

For a harder benchmark, try the [cooperation siege scenario](docs/COOPERATION_SCENARIO.md). It combines earlier, stronger waves with scarce reserves. Compare independent routines, volunteers responding to requests, and elder-assigned tasks while keeping all survival actions enabled. See [task coordination](docs/COORDINATION.md) for player/model actions and save behavior.

To test generalization beyond the development seeds, run `python -m village.validation` using your platform’s virtual-environment Python. The [held-out validation guide](docs/HELD_OUT_VALIDATION.md) describes the frozen 96-run matrix, new scenarios, time limits and evidence.

### Repair allocation experiment

The opt-in [repair strategy and logistics prototype](docs/STRATEGY_EXPERIMENT.md)
adds resource-aware repair offers, urgent partial deliveries and supply-task handoffs.
It includes a bounded per-role inference probe and matched scripted/model evaluation
on fresh seeds. Enable it with `--config configs/strategy-v2/development.json`.
The existing controller remains the default until evidence supports changing it.

### Run a persistent server and connect the 3D client

The [server/client guide](docs/SERVER_CLIENT.md) covers the single-client loopback
prototype, reconnect, exclusive possession and saved worlds. From two terminals:

```powershell
.\.venv-win\Scripts\python.exe -m village.server --demo
.\.venv-win\Scripts\python.exe -m village.client
```

Linux uses `.venv/bin/python` with the same module arguments. Keep the server running
when closing the client; it owns the world and autosaves. Optional compact Docker
inference uses `--config configs/server-local.json` on both processes. The original
single-process launch remains available.

[Evaluation correctness and component results](docs/EVALUATION_GAPS.md) explain why
experimental policies remain opt-in, and why paused AI gains need a timing check.

Network clients now use [configurable movement smoothing](docs/CLIENT_SMOOTHING.md)
for villagers, monsters and the follow camera, with continuous walking animation.
The default 200 ms presentation buffer trades some display latency for smoother
motion; server movement and collisions stay authoritative.
