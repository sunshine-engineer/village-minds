<!--
File: docs/STRATEGY_EXPERIMENT.md
Purpose: Repair strategy and logistics experiment v2.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Repair strategy and logistics experiment v2

> Scope: v2 repair study. Results describe the frozen source identified below,
> not a new test of the latest checkout. For current evidence and study order, use
> the [documentation index](INDEX.md) and [handover runbook](HANDOVER.md).

## Scope and comparison

This experiment gives the model a bounded strategic job: choose a recipient and gate
for a repair, or defer. It cannot invent actions, resources or participants. The
simulation computes legal candidates, useful HP per wood, A* route travel time and
estimated time to breach. A compact structured response selects a candidate ID.
Every response is validated again against the current world before an offer is made.
An offer is not a completed repair and is never counted as survival benefit.

Three conditions run on identical scenario definitions and seeds:

| Condition | Resource scoring and urgent deliveries | Repair model |
| --- | --- | --- |
| legacy | Off | Off |
| scripted | On | Off |
| model | On | On |

Compare `model` against `scripted` to estimate the additional effect of inference.
Compare `scripted` against `legacy` to inspect the policy changes separately.
The model has the same four-call budget in each case and the same role/threat
checkpoint schedule. Calls require an available repair choice; unused calls and
missing roles remain visible. All survival actions stay enabled. No campaign save
is read or written.

The [development plan](../configs/strategy-v2/development-plan.json) uses seed 301.
The [fresh plan](../configs/strategy-v2/holdout-plan.json) fixes seeds 401, 409 and
419 and excludes every previously used development and v1 holdout seed. It retains
the original siege, scarce-wood and long-route scenarios, including their failure
floors. Do not tune policies after seeing these results and reuse the same seeds
as fresh evidence. The v1 results remain unchanged as regression evidence.

## Controller behavior

`coordination.resource_aware` controls a cost combining route time, wood per useful
repair HP, a scarcity multiplier, guard opportunity cost and a penalty for arriving
after estimated breach. These are heuristic costs, not an optimal allocation proof.
Time to breach assumes the current threat count and continuous gate damage; actual
combat, fatigue and future waves can change it.

A ready supplier can hand off a wood/food task when an urgent gate repair has wood
available. The supply request reopens for another volunteer. Active guards, current
repair/defence jobs, possessed villagers and villagers with urgent personal needs
cannot be preempted by the new allocator. Recipient eligibility is checked when constructing choices, while board capacity
and requester cooldown are checked again when applying the offer. This can reject
a schema-valid response even during paused evaluation; three elder calls hit that
limit in this experiment. That was a limitation of this frozen v2 experiment. Current code filters
those constraints before inference; see [the v3 correction](EVALUATION_GAPS.md).

A model repair offer receives a configurable
short lease against automatic reallocation; death, expiry and voluntary release still
apply. Leases persist in saves, and older board snapshots load with no leases.

`logistics.enabled` permits partial wood deliveries when shared wood is scarce and
gates need repairs or the orchard is empty. It permits partial food deliveries for
hungry neighbors when the shared food supply is low. Eating, resting and active
combat take priority. This is deliberately a limited delivery policy, not a new
transport network. Long routes are measured before choosing path, carrier or
storehouse changes.

All new behavior is opt-in. Default settings preserve the existing controller.
[Development settings](../configs/strategy-v2/development.json) enable the prototype
for ordinary play. Existing Windows/Linux launch commands also accept
`--config configs/strategy-v2/development.json`.

## Run and inspect

Linux, from the repository root:

```bash
.venv/bin/python -m village.inference_probe --config configs/strategy-v2/development.json
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v2/development-plan.json
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v2/holdout-plan.json
```

Windows PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m village.inference_probe --config configs/strategy-v2/development.json
.\.venv-win\Scripts\python.exe -m village.strategy_experiment --plan configs/strategy-v2/development-plan.json
.\.venv-win\Scripts\python.exe -m village.strategy_experiment --plan configs/strategy-v2/holdout-plan.json
```

Start the existing local Docker model service first. The sample uses the configured
`local_qwen` profile with 2,048 context tokens, 24 output tokens and temperature zero.
The probe creates a controlled damaged-gate fixture for each role twice. It measures
valid/applied choices, timeouts and per-role latency, including cold/warm effects;
these eight calls are diagnostics rather than a statistical reliability guarantee.
Ollama prompt/generation/load timings and token counts are recorded separately from
client wall time. Other backends may not expose provider timings.

Live play and evaluation share a spawned request worker with a hard wall deadline,
including process startup. A hung custom adapter is terminated; local gameplay
continues in the background. Evaluation deliberately pauses simulated time during
requests for repeatability. Its results do not measure the consequences of inference
lag during live combat.

The fresh batch has 27 runs, at most 36 model calls, 15 seconds per request, 90 seconds
per run and a 600-second suite budget. Process startup/cleanup can add a small wall
overhead. Missing or wall-limited runs exit nonzero and are excluded from paired
benefit calculations. The runner freezes source hashes, resolved configs and the
plan before execution. Outputs are under `artifacts/strategy/` and contain the
protocol, configs, per-run JSONL traces, summary, CSV and subprocess logs.

Inspect survival and health first, then gate exposure and resources. Also inspect:

- Useful repair HP divided by wood actually consumed, reconstructed from accepted
  repair before/after state. Repairs near full health are clipped to useful HP.
- Model allocations that led to an assignee repair, separately from accepted offers
  and deferrals. These repairs are associated with a model task, not proof of causal
  benefit: a scripted worker might have repaired the same gate.
- Total villager travel seconds and store-bound travel seconds, plus uncovered
  threatened-gate seconds and fraction. Failed worlds have shorter observation time.
- Per-role request outcomes and latency, unused calls, task handoffs, partial
  deliveries and dropped trace records. A partial or dropped trace invalidates a
  complete repair-efficiency audit.

See the recorded results below for the tested limits. Small seed samples and a
single CPU model cannot establish general model superiority.

## Recorded inference diagnostics — 22 October 2026

Native Windows Python reached the existing Docker Ollama service (`qwen2.5:1.5b`,
CPU, Q4_K_M). With the final compact prompt all eight responses were schema-valid,
applied repair offers; none timed out under a 15-second request budget.

| Role | Valid / attempted | Mean client seconds | Maximum client seconds |
| --- | ---: | ---: | ---: |
| farmer | 2 / 2 | 4.80 | 6.81 |
| worker | 2 / 2 | 4.11 | 5.51 |
| soldier | 2 / 2 | 4.21 | 5.67 |
| elder | 2 / 2 | 4.27 | 5.77 |

The second round took 2.71–2.78 seconds. The server was already running; this was
not a forced model-unload/cold-start test. With only two samples per role, reported
p95 is the observed maximum, not a useful tail-latency estimate. A separate earlier
minimal-request diagnostic took 9.15 seconds with a 4.75-second model load. These are
measurements from this machine, not a hardware-independent service guarantee.

The previous generic prompts contained about 1,750 tokens. The compact final probe
used about 375 tokens and seven generated tokens. Provider timing separates prefill,
generation and load from client/process/transport overhead. The probe proves that
this bounded allocation interface works in its fixture, not that the selected
assignments are strategically good.

## Fresh-seed gameplay results — 22 October 2026

All **27 runs** on seeds 401, 409 and 419 ended normally at the horizon or in
village destruction. No runs were missing or wall-limited, and no traces dropped
records. Full [CSV](results/repair-strategy-v2.csv) and [JSON evidence](results/repair-strategy-v2.json)
include every adverse result, source/config hashes and per-request provider timings.

| Scenario | Condition | Survived / 3 | Mean observed seconds | Useful repair HP / wood | Mean uncovered threat fraction |
| --- | --- | ---: | ---: | ---: | ---: |
| siege | legacy | 3 | 900.0 | 11.49 | 0.616 |
| siege | scripted | 1 | 779.5 | 12.52 | 0.601 |
| siege | model | 0 | 686.9 | 11.76 | 0.625 |
| wood-pressure | legacy | 0 | 549.2 | 10.53 | 0.617 |
| wood-pressure | scripted | 0 | 633.0 | 11.97 | 0.612 |
| wood-pressure | model | 0 | 615.9 | 11.53 | 0.621 |
| long-haul | legacy | 0 | 623.7 | 11.49 | 0.689 |
| long-haul | scripted | 0 | 566.0 | 11.14 | 0.696 |
| long-haul | model | 0 | 596.3 | 11.20 | 0.641 |

Repair efficiency pools useful HP and consumed wood within each condition; it is
not the unweighted mean of per-run ratios. Siege observed duration includes
survivors censored at 900 seconds and is not a mean time-to-failure estimate. All
wood-pressure and long-haul runs failed, so their observed loss times are uncensored.

The new scripts improved repair HP per wood in siege and scarce wood, but regressed
on **two of three siege survival pairs** against legacy scripts. Model assistance
had **zero survival gains and one survival regression** against the improved scripts.
All three conditions lost every scarce-wood and long-haul seed. The model condition
lost sooner on two of three scarce-wood pairs; longer mean long-haul survival did not
produce a surviving village. These results do not support enabling the new policy
or model allocator by default.

### Deliveries, routes and inference

| Scenario | Condition | Mean total travel villager-seconds | Mean store-bound villager-seconds | Mean uncovered threat gate-seconds | Partial deliveries |
| --- | --- | ---: | ---: | ---: | ---: |
| siege | legacy | 3566.6 | 922.6 | 463.9 | 0 |
| siege | scripted | 3114.6 | 834.1 | 425.9 | 29 |
| siege | model | 2768.9 | 717.5 | 401.7 | 23 |
| wood-pressure | legacy | 1889.7 | 500.1 | 255.5 | 0 |
| wood-pressure | scripted | 2479.9 | 688.3 | 317.5 | 45 |
| wood-pressure | model | 2453.1 | 655.4 | 323.1 | 45 |
| long-haul | legacy | 2765.7 | 925.2 | 400.2 | 0 |
| long-haul | scripted | 2545.1 | 846.7 | 348.8 | 15 |
| long-haul | model | 2619.9 | 882.2 | 353.0 | 20 |

Travel and uncovered seconds depend on how long each village survived. For long
haul, mean store-bound walking villagers over each run were 1.484 / 1.501 / 1.479
for legacy / scripted / model. The corresponding uncovered fractions were
0.689 / 0.696 / 0.641. Longer routes remain a measured constraint; no new transport
or map changes were added. Do not infer a causal delivery benefit from these
combined-policy comparisons.

There were **27 model requests**, all schema-valid and within 15 seconds. Of these,
**24 were applied and three were rejected** by the board constraints, with
client latencies 3.84–6.46 seconds. **19 of 24 applied offers** led to an assignee repair;
the others did not. These are associated repairs, not proven additional repairs.
The model never chose defer, even though replacement-cost context and that option
were available. Valid JSON and accepted offers did not establish strategic quality.

Each gameplay run used three of its four available call slots before useful repair
choices or the village ended. Requested roles were farmer (9), elder (9), soldier (6)
and worker (3). Six elder responses were applied; the other three were rejected.
All other role responses were applied. Nine unused calls remain reported rather
than being silently redistributed.

The source was frozen before this batch; no policy was tuned after seeing these
fresh results. The earlier seed-301 development run also showed model regressions
and prompted adding current-owner replacement-cost context before this freeze.
Next investigation should isolate resource scoring, handoffs and urgent deliveries
in separate ablations, then use another fresh seed set. This experiment does not
establish which individual change caused the survival regression.

Raw evidence: `artifacts/strategy/holdout-plan-20261022T071500-08d59860`. Controlled final probe evidence:
`artifacts/inference/probe-20261022T071414-ab6a8763/summary.json`, also published
as [probe JSON](results/repair-strategy-v2-probe.json).
