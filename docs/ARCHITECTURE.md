# Architecture

Village Minds is a single-player Python/Panda3D survival prototype. Python owns
world state; model responses are proposals checked against the current rules.

## Decision flow

1. Panda3D advances the world and movement each frame.
2. Independent local role routines handle needs, work, patrols and urgent threats.
3. A background worker sends bounded JSON observations to Ollama over HTTP.
4. Slower model decisions provide destinations, guard assignments or dialogue.
5. The simulation validates responses before applying them. Stale or invalid
   decisions are discarded; local activity continues during model delays/errors.

One inference worker limits load on local hardware. It does not serialize villager
movement. Separate local and model counters expose which controller acted.

## Modules

| File | Responsibility |
| --- | --- |
| `village/simulation.py` | Rules, navigation, perception, resources, monsters and failure |
| `village/brains.py` | Role routines, model schema, background requests and arbitration |
| `village/game.py` | Panda3D rendering, input, possession, HUD and save integration |
| `village/persistence.py` | Validated JSON snapshots, backups and retained failure lessons |
| `village/__main__.py` | Command-line options and application lifecycle |
| `village/probe.py` | Model API connectivity and action validation check |

## Persistence and ownership

The default checkout-relative slot is `saves/village.json`. Saves include world
resources, villagers, monsters, crops, timers, memories and campaign lessons.
Atomic replacement and a backup protect against interrupted writes. No offline
simulation occurs. Use one process per save slot; concurrent writers are unsupported.

Player takeover excludes that actor from autonomous control. Ownership revisions
prevent an earlier pending model response from overriding a newly possessed actor.

Restarting resumes the attempt, including a destroyed village. `--new-game` starts
a fresh attempt with retained failure lessons. These are prompt memories, not model
training or evidence that cooperation improves automatically.

## Deployment boundaries

The game runs on the host desktop. Docker runs Ollama; its port binds to localhost.
The game sends observations and dialogue to the configured model URL. Keep that
endpoint trusted. Models and containers retain their own licenses; the repository
MIT license covers this project's original code and docs.

## Validation limits

Logic tests run without a graphics window or model server. Rendering, keyboard
integration and real inference require separate checks. See [validation](../VALIDATION.md)
for recorded evidence and [contributing](../CONTRIBUTING.md) for commands.
