<!--
File: docs/EVALUATION_GAPS.md
Purpose: Evaluation correctness and component experiments.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Evaluation correctness and component experiments

> Scope: v3 component/timing study. Results describe the frozen source identified below,
> not a new test of the latest checkout. For current evidence and study order, use
> the [documentation index](INDEX.md) and [handover runbook](HANDOVER.md).

This follow-up fixes unavailable repair choices, separates policy components, and
compares paused and delayed model decisions before introducing the server/client
boundary. It preserves the published [v1 holdout](HELD_OUT_VALIDATION.md) and
[v2 experiment](STRATEGY_EXPERIMENT.md) as historical regression evidence.

## Correctness changes

Repair choices now include the proposer. A new repair request is offered to the
model only when that proposer is past its request cooldown and the board has room.
An existing open repair request remains assignable during cooldown and is reused
instead of duplicated. Evaluation selects an eligible role/actor before consuming a
checkpoint, so an unavailable proposer does not waste its slot. Live observations
use the same filter. Every returned intent is still validated against current state;
movement, combat, expiry or player possession during inference can invalidate it.

`coordination.resource_aware.enabled` now controls repair scoring only.
`coordination.repair_handoffs` separately controls automatic repair reallocation and
preemption of lower-priority supply work. `logistics.enabled` controls partial
shortage deliveries. All three default to false. The old experimental v2 preset
explicitly enables handoffs to retain its combined behavior. Requester filtering
improves feasibility, not the quality of model strategy.

## Frozen factorial experiment

[The component plan](../configs/strategy-v3/factorial.json) uses seeds **431/433**,
excluding every previously used v1/v2/development seed. Each seed runs eight policy
combinations across siege, scarce wood and long haul: **48 scripted runs**, all
abilities enabled, no model calls, 900-second horizon and 0.1-second substeps.
Policies were frozen before the run. The runner used a separate frozen package
copy so implementing server/client code could not alter an active experiment.
All 48 runs reached the horizon or destruction; none were missing or wall-limited.

| Components | Siege survived / 2 | Mean siege health | Mean scarce-wood loss seconds | Mean long-haul loss seconds |
| --- | ---: | ---: | ---: | ---: |
| Legacy volunteers | 0 | 0 | 594.8 | 624.8 |
| Scoring | 0 | 0 | 581.8 | 597.8 |
| Handoffs | 2 | 123.9 | 540.8 | 648.2 |
| Partial deliveries | 0 | 0 | 530.7 | 575.8 |
| Scoring + handoffs | 2 | 77.8 | 596.0 | 599.6 |
| Scoring + deliveries | 0 | 0 | 583.4 | 646.0 |
| Handoffs + deliveries | 2 | 133.0 | 609.2 | 594.1 |
| All three | 1 | 24.1 | 624.2 | 597.1 |

Every scarce-wood and long-haul village failed. Those loss times are uncensored.
The siege health means include survivors observed at 900 seconds and failed worlds;
mean observed siege duration is not a mean time-to-failure estimate.

These controlled comparisons reveal interactions: adding scoring to handoffs plus
deliveries changed siege survival from 2/2 to 1/2. Partial deliveries alone lost
sooner than the baseline in both resource/travel cases. Handoffs alone helped these
two siege seeds, but harmed scarce-wood loss time. This identifies risky components
in these fixtures; it does not prove a universal cause of the earlier v2 regressions.

## Prospective handoff confirmation

A [separate frozen plan](../configs/strategy-v3/confirmation.json) tested handoffs
against legacy volunteers on fresh seeds **449/457**, chosen after the component
results and excluded from development. All **12 runs** completed normally.

| Scenario | Legacy | Handoffs |
| --- | ---: | ---: |
| Siege survived | 2/2 | 2/2 |
| Siege mean final health | 147.9 | 94.4 |
| Scarce-wood mean loss seconds | 555.7 | 535.8 |
| Long-haul mean loss seconds | 617.8 | 574.8 |

Handoffs did not add surviving villages here and reduced health or loss time in
each scenario. Therefore no experimental policy is promoted to the default.
Useful HP per wood can rise while survival gets worse; the next policy experiment
must protect time spent supplying and defending, not optimize repair efficiency
alone. More seeds are needed before claiming a robust policy advantage.

## Timing policies

The evaluator supports `evaluation.timing_policy`:

| Policy | Application of a returned model decision |
| --- | --- |
| `paused_checkpoints` | Apply at the original simulation instant |
| `fixed_delay` | Advance local routines/physics by `inference_delay_seconds` before application |
| `measured_delay` | Advance by measured client inference wall time before application |

These modes use the same bounded request subprocess. To retain reproducibility,
the evaluator obtains the response, then replays the local simulation steps that
would have elapsed while it was pending. It preserves the original actor revision
and request time. Combat, local work, task progress, expiry and village destruction
all proceed during replay; productive model assignments are tracked during these
steps too. No subsequent request starts before the pending one completes.

This is equivalent to elapsed-time application for this headless, single-pending-
request fixture with no external player input. It is not an actual concurrent
network benchmark. The live game and server use the asynchronous scheduler instead.
A test advances 35 simulated seconds and confirms an otherwise valid intent is
rejected as stale while local routines keep running.

[Three matched timing plans](../configs/strategy-v3/) reserve seeds **439/443** for
all three timing policies. These seeds are intentionally reused across the timing
comparison, not counted as independent samples. Each plan compares improved scripts
with the same scripts plus repair inference on the siege, with four calls per run
and a 15-second per-call budget. The source/config snapshots and unused call slots
are retained. A failed initial Windows attempt had wall-limited child processes,
including scripted mode, and is excluded from benefit comparisons. It remains in
local artifacts rather than being silently overwritten.

## Reproduce

Linux:

```bash
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v3/factorial.json
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v3/confirmation.json
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v3/timing-paused_checkpoints.json
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v3/timing-fixed_delay.json
.venv/bin/python -m village.strategy_experiment --plan configs/strategy-v3/timing-measured_delay.json
```

Windows PowerShell uses `.\.venv-win\Scripts\python.exe` with the same arguments.
Use the development plan before spending a new seed set. A failed or interrupted
batch must retain missing/censored cases and exit nonzero. The next revision of a
policy needs another named protocol and a fresh prospective seed set.

## Recorded timing results

All three completed timing protocols ran four cases each, with no missing or
wall-limited runs and no dropped trace records. Every response was schema-valid
and completed within the configured 15-second budget. All four roles were reached.
The scripted condition was identical across timing policies: both seeds lost,
at 747.6 and 756.6 simulated seconds.

| Timing | Model requests | Applied / rejected | Offers leading to repair | Model survived / 2 | Paired survival gains / regressions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Paused | 7 | 7 / 0 | 6 | 1 | 1 / 0 |
| Fixed 5-second delay | 7 | 2 / 5 | 1 | 0 | 0 / 0 |
| Measured delay | 7 | 3 / 4 | 3 | 0 | 0 / 0 |

Paused client latency was 3.93–10.89 seconds; fixed-delay latency was 2.96–5.69;
measured-delay latency was 2.84–5.67. Measured-delay replay uses these actual times,
so its outcomes depend on host load and are not deterministic across machines.
Rejected delayed intents were unavailable in the changed world; they were not
transport/schema failures or age-expired responses. The separate 35-second test
covers expiry by age. The model chose no deferrals in these runs.

The requester filter eliminated board-constraint rejection in the paused sample.
The apparent paused survival gain disappeared in both delayed comparisons. This
small experiment demonstrates sensitivity to timing, not that the model can never
help. It does not justify enabling AI strategy as the default or claiming learned
cooperation. Offer counts and associated repairs remain separate from survival.

The earlier failed paused attempt produced no eligible paired results. It included
wall-limited scripted work and an exceptionally long client wall interval in one
model checkpoint; the cause of the host/process stall was not established. Its [failed-batch report](results/repair-timing-v3-failed-attempt.json) is retained; the
local folder is `repair-paused-checkpoints-v3-20261022T083314-2ac6af38` under
`artifacts/strategy-v3/`. The unchanged protocols were retried after short and full-
horizon scripted diagnostics completed normally. No policy was tuned between
attempts, and the unsuccessful attempt is not counted as completed evidence.

Complete evidence:

- [48 factorial rows](results/repair-factorial-v3.csv) and [protocol/full JSON](results/repair-factorial-v3.json).
- [12 confirmation rows](results/handoff-confirmation-v3.csv) and [protocol/full JSON](results/handoff-confirmation-v3.json).
- [Paused timing rows](results/repair-paused-checkpoints-v3.csv) and [full JSON](results/repair-paused-checkpoints-v3.json).
- [Fixed-delay rows](results/repair-fixed-delay-v3.csv) and [full JSON](results/repair-fixed-delay-v3.json).
- [Measured-delay rows](results/repair-measured-delay-v3.csv) and [full JSON](results/repair-measured-delay-v3.json).

The recorded source tree exactly matches evaluation-stage commit `37d2d0b`.
These evaluations used the frozen evaluation/controller snapshot before the
transport modules and network defaults were added. Recorded hashes identify that
snapshot; the following server/client implementation adds code that is not used
by the headless scenarios. All 72 completed rows are retained separately from the
failed attempt and historical v1/v2 results.


## Repair priorities and the timing-grid correction (v4)

[Temporary repair plans and full v4 evidence](REPAIR_PRIORITY_PLANS.md) add a
scripted planner comparator and audit local decisions rather than treating
associated repairs as proof of benefit. The initial fixed-delay study had no
behavioral or survival improvement in any matched pair.

A new no-plan replay exposed a confirmed confound in measured-delay evaluation:
fractional replay steps shifted the later simulation grid. An apparent survivor
was reproduced with every repair plan deferred. The evaluator now applies
responses at the next normal simulation tick, with recorded quantization overhead
and a regression that fails against the previous implementation. Historical v3
measured-delay comparisons also carry this limitation; their files are retained.
Only the corrected retest should inform the new measured-delay comparison.


The corrected v4 study completed 12/12 runs and the valid fixed study 12/12.
All 24 real model responses were valid within deadline, but every non-planner
action and accepted task owner matched the baseline exactly. All villages failed.
This separates reliable inference from absent strategic benefit; new benchmark
contention is required before increasing the model-call budget.
