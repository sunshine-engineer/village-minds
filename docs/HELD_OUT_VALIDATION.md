# Held-out coordination validation

This suite tests whether the scripted coordination results generalize beyond the ten development seeds and the original siege. It does not call language models or measure learned cooperation.

## Frozen protocol

[The versioned plan](../configs/validation/holdout-v1.json) fixes eight new seeds: **211, 223, 227, 229, 233, 239, 241 and 251**. They do not overlap the recorded development set (7, 19, 31, 43, 59, 71, 83, 97, 109 and 127).

Every seed is run with independent routines, volunteer requests and elder assignments in each of four scenarios: **96 runs** in total. The horizon is 900 simulated seconds with 0.1-second steps. All survival actions remain enabled. No policy weights, task priorities, ownership rules or model prompts change between runs.

| Scenario | What changes from the siege | What it tests |
| --- | --- | --- |
| [Siege](../configs/cooperation-siege.json) | No gameplay changes | Generalization to new monster-wave seeds |
| [Food pressure](../configs/validation/food-pressure.json) | Crop growth 45→150 seconds; hunger 0.3→0.4/second; farmer yield 6→4; other yield 4→3 | Organizing food work when production and consumption are less forgiving |
| [Wood pressure](../configs/validation/wood-pressure.json) | Initial wood 2→0; orchard capacity 24→6; regeneration 3 every 20 seconds→1 every 30 seconds | Gathering, delivering and allocating scarce repair resources |
| [Long haul](../configs/validation/long-haul.json) | Storehouse moves from (-8,-7) to (-18,-19); orchard from (14,10) to (18,18) | Travel costs and task expiry with longer supply routes |

The policies were developed with the earlier seeds and siege. The new scenario choices intentionally stress known mechanics; this is not a representative sample of all possible villages. All results, including ceiling/floor effects, must be retained. Do not adjust a losing scenario and call its rerun the same holdout experiment.

## Run

From the repository root, Linux:

```bash
.venv/bin/python -m village.validation
```

Windows PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m village.validation
```

Use `--plan path/to/plan.json` for another explicitly versioned protocol and `--output path` to choose an output parent. Plan paths resolve relative to the plan file. Scenario settings still use the normal configuration loader.

The default plan bounds each run at 30 wall seconds, each scenario at 180 seconds and the whole simulation batch at 600 seconds. Actual runtime depends on hardware. A deadline creates incomplete/missing results, not a survival success; an incomplete batch exits nonzero. Full-size runs are intentionally excluded from the unit-test suite; tests use a one-second, single-seed fixture.

## Evidence and reproducibility

The runner writes `protocol.json` **before starting simulations**, including the plan, full source hashes, runner hash and hashes of each effective config snapshot. Each scenario runs in a fresh interpreter because configuration is startup-only. The same frozen config is used for its three strategies. The runner verifies input hashes before each scenario and after the batch, and stops on changes.

Each invocation gets a unique folder under `artifacts/validation/` containing:

- Frozen effective configs and protocol.
- A child process log and full evaluator evidence per scenario.
- Batch `summary.json`, flat `results.csv` and `report.md`.
- Per-run outcomes, task counters, damage/starvation/coverage metrics, contribution counts and bounded decision logs.

No campaign save is loaded or written. The scenario presets have separate save paths if used for ordinary play, but evaluation ignores them.

## Interpretation

Compare survival **within each scenario**, then inspect paired gains and regressions against the same seed's independent run. Report final health, starvation, coverage and task response to explain differences. More requests, acknowledgements or completed jobs do not by themselves establish better survival.

Uncovered-threat fraction is threatened-gate time lacking an in-range guard with attack energy, divided by total threatened-gate time. It is a coverage diagnostic, not damage prevented. Failed runs are shorter than full-horizon runs. Task latency means retain only the configured recent history samples.

Do not pool repeated seeds across scenarios as independent evidence for a universal winner. Eight seeds per scenario are a small sample. A frozen policy can improve overall and still regress on individual seeds or resource regimes. Model inference requires a separate matched scripted-versus-hybrid experiment; this suite makes zero model requests.

The initial ten-seed development comparison is recorded in [coordination results](COORDINATION_RESULTS.md). The result section below records prospective validation separately.

## Recorded results — 21 October 2026

All 96 runs completed their horizon or ended in village destruction. No runs were missing, skipped, wall limited or censored by a deadline. All model-request counts and disabled-action counts were zero.

| Scenario | Independent | Volunteers | Elder assignments |
| --- | ---: | ---: | ---: |
| cooperation-siege | 3/8 | 7/8 | 5/8 |
| food-pressure | 3/8 | 6/8 | 4/8 |
| wood-pressure | 0/8 | 0/8 | 0/8 |
| long-haul | 0/8 | 0/8 | 0/8 |

The volunteer advantage persisted on the fresh siege and tighter-food samples, but it was not universal: volunteers regressed on one seed in each of those scenarios. Elder assignments also had regressions. Wood scarcity and long supply routes defeated every strategy.

| Scenario | Strategy | Paired survival gains / regressions | Mean final-health change / 200 |
| --- | --- | ---: | ---: |
| cooperation-siege | requests | 5 / 1 | +28.675 |
| cooperation-siege | assigned | 4 / 2 | +35.625 |
| food-pressure | requests | 4 / 1 | +33.200 |
| food-pressure | assigned | 2 / 1 | +23.500 |

### Failure boundaries

Both harder boundary scenarios have a survival floor: 0/8 for every strategy. They expose limitations but cannot rank strategies by survival percentage. Because every run in these two cases failed within the horizon, their observed time to destruction is uncensored:

| Scenario | Independent mean loss time | Volunteers mean loss time | Assignments mean loss time |
| --- | ---: | ---: | ---: |
| wood-pressure | 658.9s | 502.1s | 539.5s |
| long-haul | 489.2s | 543.8s | 564.7s |

Under scarce wood, the coordination strategies lost sooner than independent routines. Under long haul they lasted longer, but still failed every time. These policies are not robust to those resource and travel regimes. No parameters were adjusted after seeing the losses.

The food variant reduced final shared-food reserves to roughly 7–13 on average, versus 210–289 in the fresh siege sample, but no strategy accumulated measured starvation time. It tests tighter food buffers; it is not yet a severe starvation benchmark. All scenarios had zero measured starvation-villager seconds in this matrix.

The long-haul navigation audit verified reachable, legal storehouse and orchard work points for all six initial villagers (12 checks). All strategies actually shared supplies, repaired gates and killed monsters in the failure scenarios. Their failures did not result from deliberately disabled actions or completely inaccessible service markers.

### Scarce-wood trace audit (secondary analysis)

Accepted repair records show a concrete efficiency difference. These are pooled actual gate HP restored divided by actual shared wood consumed, not nominal action counts. None of the audited decision logs dropped records.

| Strategy | Gate HP restored per wood | Worker repairs | Repairs by other roles |
| --- | ---: | ---: | ---: |
| independent | 17.91 | 177 | 0 |
| requests | 10.30 | 5 | 127 |
| assigned | 10.28 | 5 | 138 |

Workers restore up to 18 HP per wood while other roles restore up to 10. The request/assignment policies delegated most repairs to those other roles. This supports a resource-efficiency concern; it does not isolate how much that inefficiency caused the earlier destruction. A new, separately specified experiment should test resource-aware assignments and partial-load delivery without reusing this matrix as unseen validation.

Reproduce the trace audit after running the matrix:

```bash
python scripts/audit_repairs.py artifacts/validation/<run-folder>/summary.json --scenario wood-pressure
```

### Evidence and limits

- [Per-run CSV: all 96 outcomes](results/coordination-holdout-v1.csv).
- [Protocol and source hashes](results/coordination-holdout-v1-protocol.json): frozen inputs plus post-run completion/runtime metadata. The original pre-run protocol remains in the local evidence folder.
- [Repair trace audit](results/coordination-holdout-v1-repair-audit.json).
- Full local evidence: `artifacts/validation/coordination-holdout-v1-20261021T234106-f40823d3/`.
- Policies and evaluator matched published commit `1ff6c75` before the run; the runner verified code/config hashes throughout.
- Matrix runtime: Linux/WSL2 Python 3.14.4. Native Windows ran the harness smoke fixture and full regression suite; the 96-run matrix was not repeated on Windows.
- Effective config hashes include resolved machine-local paths; source config/code hashes support cross-checking the published inputs. They are not a promise of identical file hashes after relocating a checkout.
- Eight seeds per scenario and four deliberately chosen regimes provide limited evidence. Repeated seeds across scenarios are not independent samples for a pooled win rate.
- These are scripted-controller results. No inference, personality quality, model learning or general AI-cooperation benefit is established.
