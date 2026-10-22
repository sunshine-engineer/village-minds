# Architecture

The host runs Panda3D and authoritative simulation rules. Docker runs an independent
model server. Model responses propose actions; they cannot execute code or directly
mutate state. Local routines keep every unpossessed actor active during inference.

## Ownership and modules

| Module | Responsibility |
| --- | --- |
| `config.py`, `data/default.json` | Validated startup configuration and compatibility fingerprints |
| `entities.py` | Villager, crop and monster dataclasses |
| `map_data.py` | Configured map and roster shared by navigation and scene |
| `navigation.py` | Distance, collision and grid A* |
| `world.py` | World lifecycle, perception, validated dispatch and movement |
| `survival.py` | Crops, inventory, combat, waves and failure rules |
| `policies.py` | Default needs/role decisions |
| `extensions.py`, `plugins/` | Action, policy, timed-system, model and state registration |
| `decisions.py` | Observation-specific JSON action schema |
| `models.py` | Transport registry, Ollama and local compatible chat adapters |
| `brains.py` | Routine scheduling, model worker, ownership checks and arbitration |
| `assets.py`, `data/assets/catalog.json` | Validated prefab catalog and model loading |
| `scene.py` | Procedural geometry and world/actor visual synchronization |
| `ui.py`, `controls.py` | Configured HUD widgets and input bindings |
| `game.py` | Panda3D lifecycle, frame orchestration, camera, possession and saving |
| `telemetry.py` | Bounded JSONL traces and aggregate event counters |
| `evaluation_schedule.py` | Seed-deterministic role rotation, horizon-spread threat checkpoints and coverage |
| `evaluation.py` | Headless experiments, factual failure fixtures, bounded model processes and reports |
| `timing.py` | Fast-forward substeps and retained frame backlog |
| `persistence.py` | Validated versioned JSON, atomic writes and backup recovery |
| `cli.py`, `__main__.py`, `probe.py` | Config/profile startup, game entry and API probe |
| `simulation.py` | Compatibility imports for existing scripts/tests |

## Startup and frame flow

1. Parse the config path and merge validated overrides with packaged defaults.
2. Import simulation modules, register explicit trusted plugins, restore/create state.
3. Load prefab data, initialize Panda3D, build scene/UI and bind configured controls.
4. Each frame: accept player movement, advance survival/system/movement rules, run
   local needs policies and consume/dispatch background strategic decisions.
5. Synchronize visuals and HUD; autosave on its wall-clock schedule or after failure.

No simulation module depends on Panda3D or network I/O. The model worker never
mutates the world or scene; it sends decision objects back through a bounded queue.
Every model decision is checked again on the game thread. Possession revisions reject
responses issued before takeover/release. A per-actor model plan can be interrupted
by urgent needs. Model/local counters remain separate.

## Extension boundaries

Use data for content and tuning, registered hooks for new behavior, and explicit
schema changes for new entity fields. Dependencies point toward configuration,
entities and navigation. The compatibility facade lets existing imports continue to
work; new code should import the module that owns the behavior.

The current world uses a survival rules mixin to separate the rules from lifecycle
orchestration. It is not a general entity-component engine. Plugins execute trusted
Python on the simulation thread, so their correctness and performance need review.

## Persistence

Format 2 stores a configuration fingerprint and registered plugin state. Format 1
remains readable under default gameplay settings. Atomic file replacement and a
previous-snapshot backup protect interrupted writes. Use one writer per save slot;
there is no concurrent save locking, offline simulation or arbitrary schema migration.

Restarting resumes the same attempt, including a destroyed village. `--new-game`
retains prompt lessons. These memories do not train the model or prove improvement.

See [configuration](CONFIGURATION.md), [extension recipes](EXTENDING.md), and
[validation evidence](../VALIDATION.md).

Evaluation uses the same rules, local routines and model-result validation as gameplay,
with a different timing policy: the simulation pauses at fixed strategic checkpoints.
Requests run in spawned processes so a hung adapter cannot stall the suite indefinitely.
Compare results within that policy; see [evaluation](EVALUATION.md) for limitations.

`evaluation_controls.py` owns evaluation-only action interventions through an `EvaluationWorld` subclass. It logs blocked actions without changing ordinary `World` behavior or campaign persistence. `configs/cooperation-siege.json` supplies the opt-in siege balance; no scenario constants are embedded in survival code.

`coordination.py` owns structured requests, exclusive task ownership, assignment/acceptance, progress, expiry, task policies and validated save state. `World` exposes board actions and public observations; `BrainScheduler` drives automation. Existing role routines remain the independent baseline and handle urgent needs. Evaluation compares the three strategies with a fixed action set and records paired seed differences.

`validation.py` supervises the multi-scenario holdout protocol in fresh evaluator processes. It freezes effective configs and code hashes, enforces batch deadlines, validates result identities/capabilities, and reports missing or censored runs separately. Scenario definitions and seeds live in `configs/validation/`; full-size matrices do not run in ordinary unit tests.

`allocation.py` computes legal repair candidates and resource/travel/urgency features;
`logistics.py` handles urgent partial-load delivery. `coordination.py` owns handoffs
and persisted strategic leases. `models.py` translates compact choice IDs into
validated intents. `inference.py` owns the shared hard-deadline subprocess boundary
for live scheduling, reliability probes and paused evaluations. Backend decisions
remain dictionaries, with optional provider timing metadata on `InferenceDecision`.

`inference_probe.py` measures controlled per-role inference reliability.
`strategy_experiment.py` freezes matched legacy/scripted/model runs using new seeds.
`evaluation.py` records productive model assignments separately from accepted
choices, travel time, coverage and urgent deliveries. See
[repair experiments](STRATEGY_EXPERIMENT.md) for metrics and interpretation limits.

`server.py` owns the authoritative world and persistence on its simulation thread.
HTTP handlers enqueue bounded envelopes; they never mutate game state directly.
The single active session has exclusive possession, sequenced commands and expiry.

`network.py` owns bounded HTTP requests and a background client worker. `client.py`
reuses the Panda3D scene/HUD through the `VillageGame.advance_world` boundary; it
replaces snapshots and sends commands rather than advancing physics or inference.
Both startup configuration and protocol/save fingerprints are checked locally.
See [server/client design and limits](SERVER_CLIENT.md).

Evaluation can replay fixed or measured inference delay with local routines active
and apply an intent using its original actor revision/time. Component switches and
fresh protocols isolate repair scoring, handoffs and deliveries. The completed
[gap experiments](EVALUATION_GAPS.md) remain separate from the earlier datasets.

`interpolation.py` buffers confirmed poses with local receive times and connection
epochs. The network client samples it once per render frame. `display_position`
and `display_time` hooks keep interpolated transforms/animation separate from the
authoritative World; the default hooks preserve single-process behavior. The
controlled actor and camera share a pose, and monster nodes use the same sampler.
See [smoothing design](CLIENT_SMOOTHING.md) for reset/underrun behavior and limits.

Repair strategy supports actor-specific offers and opt-in gate-level priority plans.
`allocation.py` computes candidates, `models.py` maps compact choice IDs to intents,
and `TaskBoard` owns persisted plan expiry and local task ranking. Gate plans do not
reserve helpers. See [repair priority planning](REPAIR_PRIORITY_PLANS.md).


Protocol 2 can acknowledge a movement command with the state after that normal
simulation tick. Queued requests are still handled only on the simulation thread;
HTTP workers do not mutate the world. The client uses command acknowledgements to
track possession while draining its queue, avoiding movement based on an obsolete
snapshot after release. Input changes wake the bounded transport worker. Neither
change introduces client physics or movement prediction.

`priority_benchmark.py` builds short causal allocation fixtures without touching
campaign saves. Its fixed-grid timing replay, paired initial snapshots and adverse
controls are separate from live network responsiveness measurements. The offline
contributor backend demonstrates an adapter contract and supplies no AI evidence.
