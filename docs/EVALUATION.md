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
Instead, AI modes pause the simulation at selected checkpoints, wait for a bounded
response, then resume. This prevents accelerated time making every response stale.
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

Checkpoints rotate across surviving villagers. Defaults request at most two model
decisions per AI run, with a 30-simulation-second interval. This is a bounded smoke
experiment, not continuous AI control or a sufficient sample to establish benefit.
Increase the call budget and seeds for a stronger experiment, within your wall budget.

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
