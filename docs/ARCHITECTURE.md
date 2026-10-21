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
