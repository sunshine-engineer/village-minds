<!--
File: docs/EVALUATION.md
Purpose: AI evaluation and fast-forward.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# AI evaluation and fast-forward

Use the headless runner to test survival quickly. It imports no Panda3D, requires no
display and never reads or writes campaign saves. Normal gameplay can also speed up
without skipping survival rules.

## Quick commands

Windows PowerShell, from the project folder:

```powershell
# Fifteen simulated minutes, one seed, no model or Docker required.
.\.venv-win\Scripts\python.exe -m village.evaluation --seeds 7 --duration 900

# Short three-mode AI smoke check, with one request per AI mode.
.\.venv-win\Scripts\python.exe -m village.evaluation --modes all --seeds 7 --duration 900 --max-model-calls 1 --model-timeout 15 --wall-seconds 25 --suite-seconds 60

# Watch the game at 10x speed and record decisions.
.\.venv-win\Scripts\python.exe -m village --demo --no-save --pace 10 --decision-log artifacts/play-decisions.jsonl
```

Linux / WSL uses the same options:

```bash
.venv/bin/python -m village.evaluation --seeds 7 --duration 900
.venv/bin/python -m village.evaluation --modes all --seeds 7 --duration 900 --max-model-calls 1 --model-timeout 15 --wall-seconds 25 --suite-seconds 60
.venv/bin/python -m village --demo --no-save --pace 10 --decision-log artifacts/play-decisions.jsonl
```

Start Docker/Ollama and install your chosen model before AI modes, as described in
README.md. `--config`, `--profile`, `--url` and `--model` work for evaluation too.
The default evaluation runs the scripted mode across five configured seeds.

## What speeds up

In the game, press **V** to cycle 0.5x → 1x → 2x → 5x → 10x. The HUD displays speed.
Configure the key, speed list, maximum pace and work per frame. Simulation uses
small substeps, so hunger, crops, movement and monster attacks advance together.
If the frame work cap is reached, remaining simulation time is carried forward.
Pause stops it; camera and direct player movement use real frame time. Observer
mode is the easiest way to watch accelerated villagers.

Headless evaluation removes rendering and real-time sleeps. It advances fixed
substeps as fast as the CPU permits. **It cannot make model inference faster.**
By default, AI modes pause the simulation at selected checkpoints, wait for a bounded
response, then resume. `evaluation.timing_policy` also supports `fixed_delay` and
`measured_delay`: these replay normal grid-aligned simulation ticks before applying
the response. See [timing semantics and the corrected replay](EVALUATION_GAPS.md). This prevents accelerated time making every response stale.
That timing policy differs from the live game's asynchronous inference. Compare
conditions within this runner; do not interpret its results as a latency benchmark
for normal real-time gameplay. At high speeds in the normal game, model replies
can expire before they arrive; use checkpoint evaluation for meaningful AI comparisons.

## Conditions

| Mode | Local role routines | Model checkpoints | Prior failure lessons supplied to model |
| --- | --- | --- | --- |
| `scripted` | Yes | No | No |
| `hybrid` | Yes | Yes | No |
| `hybrid-memory` | Yes | Yes | Yes, if a prior idle attempt failed |

Every condition starts from the same fresh seed and world state. When memory mode
is requested, a separate idle simulation generates factual failure records and
contribution lessons using that seed. If it does not fail within the preparation
horizon, no lessons are invented and `memory_available` is false. Preparation uses
the suite wall budget.

The lesson field is injected only into the model observation. Local routines and
scripted chatter do not get additional lessons, keeping this comparison focused on
model access to that information. This evaluates supplied memory, not model training
or self-directed long-term learning. The idle fixture is deliberately limited;
future experiments should use representative failures from real play.

## Threat-aware checkpoints and role coverage

The default `evaluation.checkpoint_strategy` is `threats`. Planned model calls start
at the first scheduled monster wave and are spread across the remaining simulated
horizon. With the default first wave at 180 seconds and a 900-second horizon:

| Call budget | Planned simulation times |
| --- | --- |
| 2 | 180, 540 |
| 4 | 180, 360, 540, 720 |

At or after each planned time, the runner waits for **live monsters threatening a
gate**. It does not spawn extra monsters to satisfy a checkpoint. If the previous
wave is already defeated, the checkpoint waits for the next active threat. The
existing `checkpoint_seconds` setting is the minimum gap between actual requests.
A short/quiet scenario may issue no calls; unused budget and absent coverage are
reported, not treated as successful AI evaluation. Threats are village-wide: the
selected actor need not have a monster inside its personal sight radius.

The configured `role_order` rotates by a stable SHA-256 hash of the world seed.
Requests cycle through roles before reusing a role, and choose the least-requested
living actor within each role. Dead, missing and possessed actors are skipped.
Selection uses no model output, so matched conditions share the same planned times
and role order. Actual times can differ when their world states diverge.

Four calls can cover farmer, worker, soldier and elder in one run. A two-call budget
cannot cover four roles in one run; seeds 7, 19 and 31 together exercise all four
roles under the default roster/order. Arbitrary seed subsets are not guaranteed
full coverage. Check `model_coverage` and the report's coverage table.

To cover four roles in one bounded AI run (allow enough time for your hardware):

```powershell
.\.venv-win\Scripts\python.exe -m village.evaluation --modes hybrid --seeds 7 --duration 900 --max-model-calls 4 --model-timeout 20 --wall-seconds 90 --suite-seconds 100
```

Use `--checkpoint-strategy interval` for the previous fixed-interval behavior.
`evaluation.checkpoint_start_seconds` selects the earliest start (default zero);
interval mode requests every `checkpoint_seconds`, even when no threats exist.
Threat mode also respects that earliest start but waits until the first wave.
Set `evaluation.role_order` to include any custom roles you want to evaluate.

The default two-call budget is still a bounded diagnostic, not continuous AI
control or evidence of improved cooperation. Old early-only reports and new
threat-aware reports use different experiments and should not be pooled blindly.

## Limits that prevent indefinite waits

- `--duration`: maximum simulated seconds per scenario; destruction ends it earlier.
- `--max-model-calls`: maximum requests per AI scenario; zero disables requests.
- `--model-timeout`: checkpoint wall limit, including worker startup, also bounded
  by the selected profile's HTTP timeout and the remaining scenario/suite budget.
- `--wall-seconds`: per-scenario wall budget (default 40 seconds).
- `--suite-seconds`: total simulation, fixture and model budget (default 120 seconds).
- Ctrl+C stops the current run and writes a report for completed scenarios.

A request runs in a spawned process; a stalled client is terminated on timeout.
Process termination, scheduling and report I/O can add a small overhead beyond a
budget. These are application deadlines, not real-time OS guarantees. Stopping a
client does not guarantee that a model server has cancelled its internal work.
By default, a timeout/error opens the model circuit for the rest of that scenario;
local simulation continues and the result records the failure. Configure
`evaluation.stop_requests_on_error` to change that behavior.

Slow models may consume the suite budget before all scenarios run. Skipped scenarios
and wall-limited results are explicit. A low timeout can yield **zero accepted AI
actions**; that is not evidence of AI-assisted survival. Short runs are smoke checks.

## Outputs and interpretation

Each invocation creates a unique folder under `artifacts/evaluations/`:

- `report.md`: readable comparison with completed, destroyed, wall-limited and skipped counts.
- `summary.json`: options, seed/mode results, config fingerprint, prompt hash and selected model.
- `results.csv`: one row per completed scenario invocation, including stop reason and metrics.
- `config.json`: resolved local settings for reproduction, without copying API-key environment values.
- `lessons-SEED.json`: factual idle-failure fixture, when requested.
- `SEED-MODE/result.json` and `decisions.jsonl`: scenario metrics and event trace.

Metrics include observed simulation duration, village health, villagers lost, food
shortage time, starvation villager-seconds, gate breach events, individual contributions,
model request/acceptance counts, errors/timeouts and end-to-end checkpoint latency.
Coverage records planned/actual times, requested roles/actors, active-threat versus
quiet requests and unused call budgets. Coverage counts requests, not successful
decisions or proven benefit.
Food/starvation intervals use state at the beginning of each substep. Breaches count
crossings from positive gate health to zero, including repeat breaches after repairs.

An unfailed run is **censored**: it may have reached the horizon or stopped at a wall
limit. Observed durations are not mean time-to-failure estimates. Look at stop reasons,
accepted model actions, comparable call budgets and seed-paired outcomes before
claiming AI improves cooperation. Model sampling and server behavior remain variable.

## Decision logs during normal play

Use `--decision-log PATH.jsonl` or `telemetry.decision_log` in configuration. Logging
is opt-in for normal play and enabled per scenario in evaluation. Each record includes
a schema version, run ID, sequence number, simulated time and elapsed wall time.

- `decision`: source (`local`, `model`, `player`, or external API caller), actor,
  proposed action, acceptance, compact before/after state and request correlation.
- `model_request` / `model_response`: full request observation, profile model/backend,
  latency, accepted/rejected/stale/error/timeout outcome and reason.
- `activity`, `patrol`, `dialogue`, `possession`, `movement`: supporting intent events.
  Continuous player movement is sampled using the configured movement interval.

Enable `telemetry.full_observations` or evaluation `--full-observations` for complete
local decision observations too. Otherwise local records use compact state, avoiding
large repeated snapshots. Rejection reasons are broad validation categories, not a
full explanation of the model's reasoning. Automatic guard strikes and every animation
frame are not separate policy decisions or full world replay snapshots.

Logs append with a new session/run ID. A configured byte cap stops disk writes while
aggregate counters continue; scenario results report dropped records. Observations
contain dialogue/memories, so inspect local artifacts before sharing. Artifacts and
saves remain ignored by Git.

## Developer checks

```bash
python -m unittest discover -s tests -v
python scripts/check_speed.py
```

The speed integration check uses an actual renderer and Panda3D messenger events,
not OS keyboard automation or a human playtest. Evaluation tests use fake responses
for deterministic metrics and real spawned processes for timeout/cleanup checks.

## Harder cooperation scenario

Use `--config configs/cooperation-siege.json --compare-coordination --modes scripted` to compare independent routines, shared requests and elder assignments on the same seeds with all survival actions enabled. The [siege guide](COOPERATION_SCENARIO.md) explains commands, metrics, paired comparisons and limitations. `--coordination` selects a single strategy. Disabled-action controls remain mechanics diagnostics, not the main cooperation benchmark.

## Validate beyond the development scenario

`python -m village.validation` runs [the frozen multi-scenario protocol](HELD_OUT_VALIDATION.md) with fresh seeds, all three strategies and every survival action enabled. Use `--plan` for the matrix; individual scenario configs still use the evaluator’s `--config`. The batch records hashes, per-scenario paired results and incomplete runs. It makes no model requests.
