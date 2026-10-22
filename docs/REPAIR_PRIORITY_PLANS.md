# Temporary repair priorities

> Scope: v4 priority study and current planner interface. Results describe the frozen source identified below,
> not a new test of the latest checkout. For current evidence and study order, use
> the [documentation index](INDEX.md) and [handover runbook](HANDOVER.md).

The opt-in `priority_plan` mode gives inference a gate-level decision that can
remain useful while villagers move, eat or finish another job. It replaces a
specific helper reservation with a temporary preference among repair requests.
Existing assignment mode and the default controller remain available.

## Execution and safety

The simulation supplies damaged gates, current threats, estimated breach time,
useful repair HP per wood and route cost. The model returns one choice ID or
`defer`; Python maps it to a gate and rechecks current conditions. A valid plan
lasts 60 simulated seconds by default and a newer plan replaces it.

Local coordination still creates requests, chooses available helpers and validates
resources. The plan only ranks tasks within the repair category. It cannot preempt
an existing owner, override defence/task-category priority, create wood, or force
an exhausted/possessed villager to work. With no wood, a plan can be accepted but
receives no repair-task preference until wood is available. Full gates and expired
plans receive no preference. Planning does not itself collect or reserve wood.

Changing the proposer's local action revision does not invalidate a gate plan.
Dead/possessed proposers, failed worlds and responses exceeding the existing
`ai.max_decision_age_seconds` still fail arbitration. This exception applies only
to `plan_repairs` responses originating from a `repair_priority` observation;
actor-specific assignments retain their original revision check.

The plan, proposer and simulation expiry persist in JSON saves. Older snapshots
without a plan migrate to no active plan. Disabled strategy ignores a saved plan.
This is bounded planning, not model training or learned cooperation.

## Configuration and play

All gameplay choices live in the existing JSON configuration:

| `ai.repair_strategy` key | Default | Meaning |
| --- | --- | --- |
| `enabled` | false | Opt in to repair strategy |
| `mode` | assignment | `assignment` or `priority_plan` |
| `controller` | model | `model` or deterministic `scripted` priority comparator |
| `plan_seconds` | 60 | Lifetime measured in simulation time |
| `priority_prompt` | packaged text | Prompt for gate-level planning |
| `max_choices` | 4 | Bounded gate/assignment choices |

`controller=scripted` is used only in `priority_plan` mode. It chooses the first
candidate, ordered by current estimated breach time, gate health and repair cost,
without calling a provider. Candidate features are heuristics, not a guarantee
that any currently busy helper will be available on arrival.

Windows PowerShell, with the local Docker model already running:

```powershell
.\.venv-win\Scripts\python.exe -m village --config configs/repair-priority.json
```

Linux:

```bash
.venv/bin/python -m village --config configs/repair-priority.json
```

For server/client play, pass the same configuration to both modules. Server mode
runs model inference unless `--demo` is supplied. Start from the siege config and
add the strategy settings above to play that harder scenario with this planner.

## Matched validation protocol

The initial [fixed-delay](../configs/strategy-v4/fixed.json) and
[measured-delay](../configs/strategy-v4/measured.json) protocols each contain 12
runs: two fresh seeds (461, 463), siege and scarce-wood scenarios, three conditions.
Both timing experiments intentionally reuse these seeds for a matched comparison;
the second timing policy is not another independent holdout. The corrected
[grid-aligned measured-delay retest](../configs/strategy-v4/measured-grid.json)
also reuses them and is explicitly a regression retest, not new fresh evidence.

| Condition | Volunteer policy | Planner |
| --- | --- | --- |
| scripted | Same scoring, handoffs and partial delivery settings | None |
| scripted-priority | Same | Deterministic gate priority |
| model | Same | Local Qwen gate priority |

Each planner has at most four role/threat checkpoints, 15 seconds per request,
a 60-second plan horizon and 900 seconds of simulated gameplay. Run/suite budgets
are 100/600 wall seconds. Fixed delay replays five seconds of simulation for both
planners. Measured delay replays actual request wall time, including worker startup, rounded up to the next normal
simulation tick (at most `evaluation.step_seconds` additional delay);
the scripted planner has no provider latency. Baseline routines continue throughout
all replay intervals. This headless timing replay does not simulate concurrent
player input or measure the live network server under inference load.

The four-role schedule can leave unused calls or missing roles if gates do not
need repairs or the village dies first. Report these gaps rather than inferring
four-role reliability from a smaller sample. Existing v1–v3 evidence is unchanged.

`model_requests` counts planner checkpoints, including the scripted comparator.
Inspect `inference_records[].controller` and `inference.controller/provider_called`
to distinguish real model calls from scripted choices. `repair_priority_plans`
records accepted plans and repair actions on the selected gate during their active
interval. `productive_priority_plans` counts plans with such actions. These are
associations: a repair might have happened without the plan. Compare paired survival,
health, repair HP/wood, travel and uncovered threats to assess added benefit.
`model_deferrals` excludes accepted plans and assignments.

Reproduce on Windows (Linux substitutes `.venv/bin/python`):

```powershell
.\.venv-win\Scripts\python.exe -m village.strategy_experiment --plan configs/strategy-v4/fixed.json --output artifacts/strategy-v4
.\.venv-win\Scripts\python.exe -m village.strategy_experiment --plan configs/strategy-v4/measured.json --output artifacts/strategy-v4
```

Resolved configurations, source hashes, all rows, request outcomes and paired
comparisons are saved by the runner. The original measured batch is retained but excluded from benefit comparisons
for the timing confound below.


## Timing confound and correction

The initial measured-delay implementation split the final replay tick by an
arbitrary HTTP latency remainder. That moved all subsequent simulation ticks off
the baseline grid. Different physics/cooldown/event boundaries could then change
survival even when the planner did nothing.

The initial measured batch appeared to produce a model survivor at siege seed
461: 900 seconds, 78.2 health, versus baseline destruction at 636.3 seconds.
A post-hoc control replayed its four recorded latencies but deferred **every** plan.
It reproduced the same checkpoint times, survival and health exactly. This is a
confirmed evaluation confound, not evidence of AI benefit.

- [Initial measured batch, excluded from benefit](results/repair-priority-measured-v4-confounded.json)
- [Original rows](results/repair-priority-measured-v4-confounded.csv)
- [No-plan timing control](results/repair-priority-timing-control-v4.json)

The fix keeps every replay step on the same grid as the no-inference baseline.
Responses apply at the next normal tick; records retain requested delay, actual
simulated delay and quantization overhead. A regression compares full local action
traces and gameplay outcomes against an inert response under 0.037, 3.9995206 and
5.0260881-second delays. It fails with fractional-tick replay and passes with the
fix. The ordinary fixed 5-second batch also has identical local action traces and
accepted ownership in every baseline/planner pair.

The original 24 runs match source commit `b82c5ad`; the corrected timing retest
matches `ecbab11`. No policy or model prompt changed after inspecting results.
The correction changes evaluator integration only. Earlier v3 measured-delay
records remain available as historical evidence, but their causal comparisons
also have this timing confound.

The diagnostic tool `scripts/replay_priority_control.py` requires the original
batch folder and its matching frozen source checkout; it rejects a different
source tree. It issues no provider calls. The current checkout intentionally
cannot reproduce the old fractional-step behavior. Each diagnostic invocation
handles one case/seed in a fresh process, preserving startup-only configuration.


## Results and decision

All 12 fixed-delay runs and all 12 corrected measured-delay runs completed with
no missing/wall-limited cases and zero dropped decision records. Each planner used
12 of its 16 possible checkpoints per timing policy; individual runs missed the
fourth call before destruction. Across each policy, calls covered all four roles:
soldier 4, worker 2, farmer 4, elder 2. This is batch coverage, not four-role
coverage in every run.

| Timing policy | Real model responses valid / requested | Accepted model plans | Plans followed by repairs, model / scripted |
| --- | ---: | ---: | ---: |
| Fixed 5 seconds | 12 / 12 | 11 | 8 / 9 |
| Measured, corrected grid | 12 / 12 | 12 | 9 / 10 |

All real model responses arrived within the 15-second client deadline: 3.75–10.60
seconds for fixed delay, 2.64–7.75 seconds for corrected measured delay. The maximum
observed rounding overhead in the corrected model runs was 87.3 ms (the configured
simulation step is 100 ms). These small host-specific samples are diagnostic;
valid JSON and accepted plans do not establish strategic quality.

All three conditions lost every village. Time to loss was identical for all
conditions in both valid timing studies:

| Scenario | Seed | Time to destruction |
| --- | ---: | ---: |
| Siege | 461 | 636.3 s |
| Siege | 463 | 672.0 s |
| Scarce wood | 461 | 537.2 s |
| Scarce wood | 463 | 576.3 s |

Repair HP/wood, travel and uncovered-gate metrics also matched. More strongly,
ordered traces of **all non-planner decisions and accepted task ownership** matched
exactly in every paired condition. The audit excludes wall-clock fields and model
plan decisions; it retains simulation times, actors, outcomes and before/after
state. Thus repairs during a plan would also have occurred without it in these
runs. Accepted plans and associated repairs must not be advertised as benefit.

The current scenarios do not provide useful contention between open repair jobs
and free helpers at plan application. An isolated ownership regression proves a
plan can change which repair a free worker claims without preempting an existing
owner; that behavior did not occur in these full scenarios. The subsequent
[contention benchmark](CONTENTION_BENCHMARK.md) supplies competing damaged gates,
a free worker, scarce wood and an explicit adverse counterfactual. More provider
calls on these v4 full-village scenarios would add little evidence.

The planner remains opt-in. No controller or prompt was tuned after these results.
This prototype demonstrates bounded planning, persistent state, deadline handling
and honest evaluation controls; it does not demonstrate a survival advantage,
learned coordination or improved resource efficiency.

Complete retained evidence:

- [Fixed-delay CSV](results/repair-priority-fixed-v4.csv), [full report](results/repair-priority-fixed-v4.json), [behavior audit](results/repair-priority-fixed-v4-audit.json).
- [Corrected measured-delay CSV](results/repair-priority-measured-v4.csv), [full report](results/repair-priority-measured-v4.json), [behavior audit](results/repair-priority-measured-v4-audit.json).
- [Excluded initial measured batch](results/repair-priority-measured-v4-confounded.json) and [no-plan replay](results/repair-priority-timing-control-v4.json).

Run `scripts/audit_priority_results.py --batch <original-batch-directory> --output
<report.json>` to reproduce the ordered trace comparisons. The original raw traces
remain under `artifacts/strategy-v4/` locally; committed JSON includes the complete
run summaries, per-request timing/roles/outcomes, plans and frozen protocol hashes.


## Live asynchronous integration

A separate native Windows headless server check starts with four damaged gates in
an isolated temporary save and the existing Docker Qwen model. The server advanced
and saved 21.85 simulated seconds while three real plan responses completed in
5.06–5.23 seconds and were accepted. A fourth request was pending when the bounded
22-second server run ended. The saved plan includes its gate, proposer and expiry.
This checks asynchronous application/persistence, not strategic benefit or combat
survival. [Response/plan evidence](results/priority-model-server-smoke.json).

An earlier short-wave integration fixture completed without a saved plan and
failed that assertion. Its repair task was complete by the final save; the exact
response outcomes were not retained, so no rejection cause is inferred.
[Failed fixture record](results/priority-live-first-attempt.json). The policy and
prompt were unchanged; the successful fixture starts from explicitly damaged
persisted gates so acceptance can be tested before local repairs finish.

Reproduce, with the configured local Docker model running:

```powershell
.\.venv-win\Scripts\python.exe scripts/check_priority_server.py
```

The script changes only temporary fixture saves/logs, uses the normal asynchronous
server, and retains response data under `artifacts/server-client/`. It neither
starts containers nor changes a real campaign. Linux substitutes `.venv/bin/python`
and needs access to the configured model endpoint.
