# Cooperation siege

The default village can survive the current evaluation horizon at full health. This opt-in scenario puts food sharing, gate repairs and defense under simultaneous pressure. It uses the same map, villagers, legal actions and model interfaces.

## Rules

All scenario balance values live in [configs/cooperation-siege.json](../configs/cooperation-siege.json), merged with the [defaults](../village/data/default.json).

| Setting | Standard | Siege |
| --- | ---: | ---: |
| Starting shared food / wood | 18 / 12 | 2 / 2 |
| First wave | 180 seconds | 60 seconds |
| Later waves | Every 90 seconds | Every 60 seconds |
| Wave growth | Every third wave | Every second wave |
| Monster health | 40 | 60 |
| Gate damage per monster per second | 1.5 | 3 |
| Hunger growth per second | 0.12 | 0.3 |
| Starvation damage per second | 0.4 | 0.8 |

Farmers must grow and deliver food, workers must replenish shared wood and repair gates, and defenders must intercept waves while returning for food and rest. Elders can support others through rallying. The scenario does not force a particular role assignment or require dialogue to unlock actions.

## Run the comparison

From the repository root, run the cooperative baseline first. It does not need Docker or a model.

Linux:

```bash
.venv/bin/python -m village.evaluation --config configs/cooperation-siege.json --modes scripted --seeds 7 19 31
```

Windows PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m village.evaluation --config configs/cooperation-siege.json --modes scripted --seeds 7 19 31
```

Then repeat the same command with each `--control` value:

| Control | Intervention |
| --- | --- |
| `cooperative` (default) | All normal routines and actions remain available |
| `no-sharing` | Block deposits into the shared storehouse |
| `no-defense` | Block guard and attack orders |
| `no-repairs` | Block gate repairs |
| `idle` | Disable local routines; simulation still advances |

For example, append `--control no-sharing` to the baseline command. Controls are evaluation-only and require `--modes scripted`. They intentionally block actions without rewriting the fallback policy; blocked retries are logged as interventions and rejected decisions. These are system ablations, not optimized selfish agents.

Each invocation prints its own report path. Reports identify the scenario and control, include per-villager contributions, and show shared food/wood, repairs, kills, rallies, starvation, breaches and model provenance. Compare equal seeds, settings and horizons. A wall-limited run is inconclusive, not a survival success.

## Add model decisions

With the configured local model running, use four checkpoints to give all four roles a chance to act. This is a bounded single-seed check:

```powershell
.\.venv-win\Scripts\python.exe -m village.evaluation --config configs/cooperation-siege.json --modes hybrid --seeds 7 --max-model-calls 4 --model-timeout 20 --wall-seconds 90 --suite-seconds 100
```

On Linux, replace the executable with `.venv/bin/python`. For a 900-second horizon, planned slots are 60, 270, 480 and 690 seconds; requests wait for real active threats. Failure or model timeouts can leave calls unused. `hybrid-memory` uses factual failure lessons from an idle attempt under these same siege rules.

The full scripted routines still run underneath model decisions. Surviving with accepted AI actions does not establish that AI caused survival. Compare scripted and AI modes over more seeds before claiming improvement.

## Play it

```powershell
.\.venv-win\Scripts\python.exe -m village --config configs/cooperation-siege.json --demo
```

On Linux, use `.venv/bin/python`. Remove `--demo` to enable the configured model. This preset has its own save slot, `saves/cooperation-siege.json`; it does not load the standard village campaign. Later edits to gameplay rules require a compatible save or an explicit `--new-game`.

## What the controls establish

On the initial three-seed scripted check, cooperative routines survived two of three 900-second runs. Removing sharing, defense, or repairs caused village destruction in all three runs for each control. This demonstrates dependencies of the tested policy under this preset. It does not prove that every possible strategy requires those actions, that every role is indispensable, or that models learned to cooperate. The seed that still defeats the baseline is useful headroom for improving strategy.
