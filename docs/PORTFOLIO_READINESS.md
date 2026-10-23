<!--
File: docs/PORTFOLIO_READINESS.md
Purpose: Portfolio readiness checklist.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Portfolio readiness checklist

This is a working acceptance plan. Passing automated checks does not establish
human playability, independent setup, production readiness or AI superiority.

| Phase | Deliverable | Acceptance evidence | Status |
| --- | --- | --- | --- |
| Consequential planning | Two controlled gate-allocation cases; baseline, scripted, model and adverse choices | Chosen priority changes task ownership and gate breach outcome; frozen held-out seeds, delay controls and all failures retained | Passed for two controlled fixtures; model matches scripted planner |
| Inference reliability | At least 40 real requests distributed across four roles | >=95% valid within configured deadline; latency distribution and every failure; invalid/late responses preserve local simulation | Passed 40/40 within deadline (10 per role); warm sequential diagnostic |
| Responsiveness | Reduce serialized input/state/poll waits | >=50 internal-input samples, median <=250 ms and p95 <=400 ms on documented host; no possession/reconnect regressions | Improved; default interpolation misses p95 target: 239 ms median / 452 ms p95 |
| Release reproducibility | Clean Linux and Windows wheel installs; contributor examples | Packaged config/assets/prompts work; action/backend extension examples execute; CI covers advertised versions | Passed automated Linux/Windows installs and four CI lanes; Windows installed render smoke |
| Stability | Extended automated simulation and session lifecycle checks | Save/reload invariants, 10 possession changes, three reconnects, bounded failures | Passed 1,800 simulated seconds, 10 possessions, three reconnects and six restores; no campaign failure occurred |
| Human review | 30-minute playtest, clean setup by another developer, three-minute demo | Named reviewer, dated result and recorded issues; never infer these from automation | Requires human review |

Targets above are project acceptance targets. A negative model result can support
an honest engineering portfolio. Claims of improved cooperation require causal
improvement over the scripted comparator on held-out conditions.

The original game, saved worlds and server/client prototype remain supported.
New experiments are opt-in and do not modify a player's campaign save.

Evidence: [causal allocation benchmark](CONTENTION_BENCHMARK.md). The current
claim is bounded gate allocation; no LLM advantage over the scripted planner
was observed. [Human review and recording checklist](PORTFOLIO_DEMO.md).


## Reproduce automated release gates

Run from the repository root using the platform's virtual-environment Python.
The commands below use `python` as shorthand; Windows uses
`.\.venv-win\Scripts\python.exe`, Linux `.venv/bin/python`.

```bash
python -m unittest discover -s tests -q
python scripts/check_contributor_contracts.py
python -m pip wheel --no-deps . --wheel-dir artifacts/release/dist
python scripts/check_wheel_install.py --wheel-directory artifacts/release/dist
python scripts/check_release_soak.py --simulated-seconds 1800
python scripts/check_client_responsiveness.py --samples 50 --transport responsive --output artifacts/portfolio/responsiveness-responsive.json
python scripts/check_client_responsiveness.py --samples 50 --transport legacy --output artifacts/portfolio/responsiveness-legacy.json
```

Keep the wheel directory limited to one project wheel. The clean-install helper
creates a new temporary virtual environment, installs the wheel and its pinned
Panda3D dependency, copies only the contributor example/script to a directory
outside the source tree, checks the imported package path, then starts the installed
headless server and validates its save. It needs pip index access unless
`--wheelhouse PATH` supplies the dependency wheels. Native Windows additionally
supports `--render-smoke` with a working graphics backend. Screenshot evidence is
written beside that helper's JSON report.

The soak uses direct authority calls and fixed steps across 1,800 **simulated**
seconds. It checks possession, disconnect/reconnect, save restoration and new
attempts after village failure. It is not a 30-minute wall-time server test,
HTTP transport stress test or human playtest. Real HTTP lifecycle tests run in
the unit suite; real rendered latency is measured separately.

Run responsiveness checks with inference and test suites idle. Both transports
use the same server tick, poll setting, configured presentation buffer and internal
input fixture. Report every stage and maximum alongside median/p95. Measurements
are host-specific and exclude OS keyboard latency and human perception.

CI runs Linux/Windows on Python 3.11 and 3.14, including the pure contributor
contract and clean-wheel helper. Render/model measurements remain explicit local
checks; CI does not download a model or claim GPU/human validation.

## Claims permitted by the present evidence

- Built a Python/Panda3D simulation with local role autonomy, bounded Docker-model
  requests, validated intents, task ownership and persistent campaign state.
- Implemented a loopback authoritative server/client, possession/reconnect and
  presentation-only interpolation.
- Designed a controlled counterfactual benchmark that measures actual gate
  allocation; the model matched the tested scripted planner.
- Identified and corrected a simulation timing confound using a no-plan replay.

Do not claim production deployment, internet multiplayer, independently learned
cooperation, model-weight updates, broad dialogue quality or superior AI survival.
Stored lessons are remembered text; their downstream benefit requires its own
controlled evaluation.


## Retained failures and corrections

- The first larger legacy latency attempt did not complete. It sent a matching
  movement request but did not retain acknowledgement/snapshot or server-status
  diagnostics. Its cause is unconfirmed and it is excluded from the matched
  comparison. The revised fixture defers waves beyond the measurement horizon,
  verifies stationary authority/render state before input, requires an observed
  authoritative displacement before crediting rendered onset, and writes partial
  samples plus client/server status on failure.
- The first CI clean-wheel check failed its Windows isolation assertion despite
  reporting a package under a temporary venv. The check now canonicalizes both
  paths before testing containment; it still rejects source-checkout imports.
- A possession-release regression now checks that the client does not send motion
  from an obsolete snapshot after an acknowledged release or reconnect needlessly.
- The benchmark timing annotation now uses actual application ticks, with a
  boundary regression; published holdout audits use raw event sequence order.

None of these fixes changes the frozen holdout's repair policy or model prompt.
Original failed evidence is retained, and no failed batch is counted as passing.


## Release evidence, 2026-10-22

All 176 regression tests passed locally on Linux and native Windows. The
[CI run](https://github.com/sunshine-engineer/village-minds/actions/runs/39779302815)
passed Ubuntu/Windows on Python 3.11/3.14 at final evidence commit `28d766a`
(production source `e1cc748`).
[Release manifest](results/portfolio-release-v1.json) records the built wheel hash
and evidence boundaries. Both fresh installs loaded the package from their new
virtual environment outside the checkout, exercised the extension examples and
started/saved the installed server. The Windows install additionally rendered a
[scene screenshot](results/portfolio-install-windows-v1.png).

The direct authority soak completed 1,800 simulated seconds in 25.9 wall seconds,
with 10 possessions, three reconnects and six exact persistence checks allowing
only documented AI scheduling/revision/session transforms. No village failure
occurred, so that run does not establish failure-to-new-attempt behavior; unit
coverage handles that path. This does not satisfy the human 30-minute playtest.

With 50 samples in each presentation mode, separate server/client processes gave:

| Transport | Interpolation | Median onset ms | p95 ms | Maximum ms |
| --- | --- | ---: | ---: | ---: |
| Legacy | Disabled | 298.934 | 908.474 | 1271.366 |
| Responsive | Disabled | 96.071 | 281.647 | 396.953 |
| Legacy | Default enabled | 395.660 | 752.009 | 988.068 |
| Responsive | Default enabled | 238.693 | 452.459 | 653.546 |

[Legacy samples](results/portfolio-latency-legacy-v1.json) and
[responsive samples](results/portfolio-latency-responsive-v1.json) retain every
stage. These sequential, host-specific runs establish an observed improvement,
not statistical generalization or the independent effect of each transport change.
The default interpolated client misses the predefined 400 ms p95 target. Do not
call that gate complete or substitute the passing direct-render result. The
responsive measurement saved all samples but its first teardown returned an
error from an inherited Windows server log handle; the fixture now stops its own
process tree; a two-sample-per-mode rerun exited successfully (cleanup check only,
not a replacement latency acceptance run). Earlier threaded results and incomplete attempts remain diagnostic
artifacts, not replacement acceptance results.

Remaining before the portfolio-ready label: improve and remeasure interpolated
tail latency, complete the normal-window human playtest, independent developer
setup, and the recorded demonstration in the demo checklist.
