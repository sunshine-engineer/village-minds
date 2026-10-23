<!--
File: docs/COOPERATION_SCENARIO.md
Purpose: Cooperation siege.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

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

Keep every survival action enabled and compare **how villagers organize**, rather than removing essential mechanics. This scripted comparison needs no model or Docker.

Linux:

```bash
.venv/bin/python -m village.evaluation --config configs/cooperation-siege.json --compare-coordination --modes scripted --seeds 7 19 31 43 59 71 83 97 109 127 --suite-seconds 240
```

Windows PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m village.evaluation --config configs/cooperation-siege.json --compare-coordination --modes scripted --seeds 7 19 31 43 59 71 83 97 109 127 --suite-seconds 240
```

This runs 30 scenarios: ten matched seeds under `independent`, `requests` and `assigned`. All retain farming, sharing, repairs and defense. Map, balance, action validation, starting resources, seed and horizon are identical; only automatic task coordination changes. See [how requests and assignments work](COORDINATION.md).

The report includes survival/losses, final health, starvation, gate breaches, unguarded threat time, task progress and model provenance. `uncovered_threat_gate_seconds` counts each threatened gate while no living guard with attack energy stands within attack range of that gate. `uncovered_threat_fraction` divides that by total threatened-gate seconds; it describes coverage, not actual monster damage.

Paired comparisons show survival gains **and regressions**, mean final-health differences, and mean uncovered-fraction differences against the same seed's independent run. Deadline-limited/missing pairs are excluded explicitly. Task acknowledgement is separate from actual productive response. Latency means use the most recent `history_capacity` samples. More requests alone do not earn a better result.

To run one strategy, use `--coordination requests` (or `independent` / `assigned`) instead of `--compare-coordination`. Each invocation prints its report path. Keep complete seed sets and report individual failures; ten seeds are still a small sample.

See the [recorded ten-seed comparison](COORDINATION_RESULTS.md) for results and regressions. The preset currently selects volunteer requests; use `--coordination assigned` for automatic elder offers.

## Add model decisions

With the configured local model running, use four checkpoints to give all four roles a chance to act. This is a bounded single-seed check:

```powershell
.\.venv-win\Scripts\python.exe -m village.evaluation --config configs/cooperation-siege.json --modes hybrid --coordination requests --seeds 7 --max-model-calls 4 --model-timeout 20 --wall-seconds 90 --suite-seconds 100
```

On Linux, replace the executable with `.venv/bin/python`. For a 900-second horizon, planned slots are 60, 270, 480 and 690 seconds; requests wait for real active threats. Failure or model timeouts can leave calls unused. `hybrid-memory` uses factual failure lessons from an idle attempt under these same siege rules.

The full scripted routines still run underneath model decisions. Surviving with accepted AI actions does not establish that AI caused survival. Compare scripted and AI modes using the same `--coordination` strategy, seeds, checkpoint plan and budgets before claiming improvement. `--compare-coordination` can also be combined with AI modes, but multiplies inference work; choose an explicit suite budget and inspect skipped scenarios.

## Play it

```powershell
.\.venv-win\Scripts\python.exe -m village --config configs/cooperation-siege.json --demo
```

On Linux, use `.venv/bin/python`. Remove `--demo` to enable the configured model. This preset has its own save slot, `saves/cooperation-siege.json`; it does not load the standard village campaign. Later edits to fingerprinted gameplay rules require a separate save path.
`--new-game` retains lessons and still requires compatible configuration; it does not bypass a fingerprint mismatch.

## Legacy mechanics diagnostics

`--control no-sharing`, `no-defense`, `no-repairs` and `idle` remain available for scripted mechanics diagnostics. They deliberately disable actions or routines and **are not the primary cooperation benchmark**. Removing defense against monsters is not evidence that an AI coordinator is useful. These controls cannot be combined with `--compare-coordination`.

The original 2/3 survival result measured independent routines with all actions enabled. Later coordination comparisons must identify the strategy explicitly. Do not mix the old disabled-action results into a claim about model quality.
