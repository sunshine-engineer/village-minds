# Consequential repair-priority benchmark

The v4 full-village runs accepted model plans but did not change local actions.
This benchmark first asks a smaller causal question: does selecting a gate change
which repair a recovering worker claims, and whether an urgent gate breaches?

## Frozen design

Two initial states use ordinary world movement, repairs, monster damage, fatigue,
task ownership and inventory checks. All action types stay enabled. Each state has
one wood, two damaged gates, simultaneous threats and one worker recovering until
roughly seven simulated seconds. Other villagers begin fatigued and cannot recover
within the 20.5-second horizon. Repair tasks have priority over defence tasks in
**every** condition, including the baseline. This is an allocation fixture, not a
normal full-village scenario or proof of broad cooperation.

- **Near urgent:** the urgent gate is close; normal resource scoring should already
  make a reasonable choice.
- **Far urgent:** the cheaper nearby repair is less urgent. Choosing the farther
  gate can prevent a breach that occurs under the cheaper local choice.

Gate identities and worker positions rotate with the seed. Blocked initial
positions are projected to a reachable cell within a configured four-unit radius;
initial snapshots record the actual position. Seeds also perturb position by up
to 0.3 units. These are small variations of two designed fixtures, not ten distinct
world/scenario distributions. Development covers all four orientations; the
predeclared held-out prime seeds cover two orientations.

| Condition | Strategic choice |
| --- | --- |
| baseline | No plan; ordinary volunteer cost scoring |
| scripted | First candidate ordered by estimated breach time, health and cost |
| model | One real structured local-model request selecting a gate or deferring |
| adverse | Last candidate, the deliberately less urgent choice |

Scripted/adverse choices apply at five simulated seconds. Model application
replays actual request wall time on the same fixed 0.1-second grid; worker actions
continue during that replay. A late plan cannot preempt an already accepted job.
No-op/baseline runs retain the same integration grid. This headless replay does
not measure actual concurrent inference, rendering and player input together.

The primary outcome is **whether the designated urgent gate breaches within the
20.5-second horizon**, not eventual village survival. First repair ownership,
selected gate, inference status/latency and final gate health are also retained.
The adverse control must change ownership and worsen the gate outcome before
model success is meaningful. Compare model against the scripted planner to assess
whether inference adds value beyond the same candidate features.

[Development protocol](../configs/portfolio/priority-development.json) uses
301/307/308/310. Its initial layout attempts are retained locally, including
blocked-cell failures and a far-gate travel-time floor; only development geometry
was adjusted. The final development controls pass in all four orientations.

[Held-out protocol](../configs/portfolio/priority-holdout.json) declares unused
seeds 601/607/613/617/619/631/641/643/647/653, two cases and four conditions:
**80 runs**, including 60 baseline/scripted/model comparisons plus 20 adverse
controls. There is at most one provider call in each model run: 20 total. Role
labels rotate across four roles. No policy/prompt changes are allowed after
inspecting holdout outcomes. The 15-second request, 40-second run and 900-second
suite budgets retain timeouts and missing cases instead of silently excluding them.

```powershell
.\.venv-win\Scripts\python.exe -m village.priority_benchmark --plan configs/portfolio/priority-development.json
.\.venv-win\Scripts\python.exe -m village.priority_benchmark --plan configs/portfolio/priority-holdout.json
.\.venv-win\Scripts\python.exe -m village.inference_probe --config configs/portfolio/reliability.json
```

Linux substitutes `.venv/bin/python`. Use the existing Docker Qwen service; these
commands do not download models or read/write campaign saves. The separate
reliability probe makes 40 requests (ten per role), reports schema-valid responses
within the hard 15-second deadline, and uses a configurable 95% acceptance target.
It does not measure strategic quality or establish a population reliability guarantee.

Each batch retains its exact resolved settings, source hashes, initial worlds,
full per-run traces, outcomes and failures. Model timeouts remain part of the
strategy's outcome denominator. The frozen results below retain every run.


## Held-out results

All **80/80** runs completed, with zero missing cases, wall-time limits or dropped
records. Exact initial snapshots match across all four conditions in every pair.
All 20 adverse controls changed repair ownership and worsened the urgent-gate
outcome relative to the scripted planner.

| Case | Baseline breaches | Scripted breaches | Model breaches | Adverse breaches |
| --- | ---: | ---: | ---: | ---: |
| Near urgent | 0/10 | 0/10 | 0/10 | 10/10 |
| Far urgent | 5/10 | 0/10 | 0/10 | 10/10 |

All 20 model responses were schema-valid within 15 seconds. Median was 4.08 s,
p95 4.46 s, maximum 14.31 s. The first response arrived after the worker's claim;
the baseline already chose the useful gate in that run. There were 19 selected
plans and one deferral; 18 valid plans preceded the worker's first claim. The
standalone probe below tests reliability separately from these outcomes.

Planning changes actual actions and prevents five breaches relative to the base
volunteer policy. **The model matches the scripted planner and adds no measured
advantage over it.** In particular, neither passing schema validation nor accepting
a late plan proves that inference affected the worker. The nearby case also shows
that model calls can be unnecessary when the local cost policy already suffices.
The evidence supports this controlled allocation capability, not general village
survival, emergent cooperation or an independent model-reasoning benchmark.

[Full report](results/portfolio-contention-v1.json),
[paired/event-order audit](results/portfolio-contention-v1-audit.json),
[compact CSV](results/portfolio-contention-v1-audit.csv), and
[all raw traces/configuration](results/portfolio-contention-v1-traces.zip).

The frozen package hashes exactly match commit `8468cb9`. A later reporting-only
fix (`e47e296`) records the actual application tick and does not label a response
as earlier than a claim occurring in that same tick. Policy, fixtures and prompt
were unchanged. The published audit uses **raw event sequence order** instead of
the original convenience timing flag, so it is not subject to that boundary issue.

Reproduce the audit from the published evidence without provider calls:

```bash
python -m zipfile -e docs/results/portfolio-contention-v1-traces.zip artifacts/contention-replay
python scripts/summarize_contention.py --batch artifacts/contention-replay --output artifacts/contention-reproduced.json
```

Rerunning inference is a new measurement with its own source hashes and host
latencies; it need not reproduce the same model text or latency. Retain all results
and do not relabel the reused seeds as fresh evidence.


## Four-role reliability diagnostic

The separate sequential probe completed **40/40** requests within the hard
15-second deadline: ten each for farmer, worker, soldier and elder. All 40 decoded
choices validated and applied as gate plans. Per-role median latency was 2.90–2.95
seconds; maximum across roles was 4.17 seconds. No requests were missing or timed
out. This meets the configured 95% sample acceptance target.

These repeated fixtures ran after the holdout batch with the model already in
service; they are primarily a warm/repeated-request diagnostic. Forty successes
do not establish population-level 95% reliability, cold-start behavior or another
host's latency. The holdout's first request took 14.31 seconds and illustrates why
the hard deadline/fallback path remains necessary.

[Full per-request reliability evidence](results/portfolio-reliability-v1.json)
(source hashes match `e47e296`). [Runtime metadata](results/portfolio-runtime-v1.json)
records native Windows 11, Python 3.14.7, Panda3D 1.10.16, 12 logical CPUs and
Intel64 Family 6 Model 186 Stepping 2. The already-loaded Ollama model reported
Qwen2.5 1.5B Q4_K_M, a 2,048-token context and zero VRAM allocated. This describes
the observed runtime; it does not establish performance on other hardware.
