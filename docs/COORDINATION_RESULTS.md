# Coordination comparison: 21 October 2026

The primary benchmark compares organization with every survival action enabled. It uses scripted policies, not language-model decisions.

## Protocol

- Cooperation siege preset; 900 simulated seconds; fixed 0.1-second steps.
- Ten matched seeds; three strategies; same map, resources, combat rules, action set and public information.
- Strategies: independent role routines, shared requests with volunteers, and elder assignments.
- All 30 scenarios completed their horizon or reached village destruction; no skipped or wall-limited runs.
- Initial development used seeds 7, 19 and 31. The complete ten-seed sample includes those seeds; it is not a wholly held-out test.

Reproduce from the repository root:

```bash
.venv/bin/python -m village.evaluation --config configs/cooperation-siege.json --compare-coordination --modes scripted --seeds 7 19 31 43 59 71 83 97 109 127 --suite-seconds 240
```

On Windows use `.\.venv-win\Scripts\python.exe`. See [the scenario guide](COOPERATION_SCENARIO.md).

## Results

| Strategy | Survived | Mean final health / 200 | Paired survival gains / regressions | Mean uncovered fraction change |
| --- | ---: | ---: | ---: | ---: |
| independent | 2/10 | 24.88 | baseline | baseline |
| requests | 8/10 | 105.46 | 6 / 0 | -10.47 percentage points |
| assigned | 5/10 | 69.64 | 4 / 1 | -7.97 percentage points |

Gains/regressions compare survival on the same seed against independent routines. Negative uncovered-fraction changes indicate better threat coverage; this is not a direct damage metric. Failed runs end at destruction and their observed duration is shorter.

| Seed | Independent | Requests | Assigned |
| ---: | --- | --- | --- |
| 7 | survived (57.8 HP) | survived (129.2 HP) | lost at 707.1s |
| 19 | lost at 675.5s | survived (127.6 HP) | survived (11.2 HP) |
| 31 | survived (191.0 HP) | survived (200.0 HP) | survived (200.0 HP) |
| 43 | lost at 817.2s | survived (72.4 HP) | lost at 767.6s |
| 59 | lost at 840.3s | lost at 888.1s | lost at 701.5s |
| 71 | lost at 693.1s | lost at 694.0s | survived (200.0 HP) |
| 83 | lost at 858.4s | survived (178.0 HP) | survived (200.0 HP) |
| 97 | lost at 646.1s | survived (200.0 HP) | lost at 828.8s |
| 109 | lost at 805.7s | survived (72.2 HP) | survived (85.2 HP) |
| 127 | lost at 656.2s | survived (75.2 HP) | lost at 673.9s |

## Interpretation

Volunteers are the best of these three tested scripted policies on this small sample. The siege preset now selects `requests`; `--coordination assigned` keeps elder-led assignment available. Assignment gains are mixed, including a regression on seed 7. More centralized assignment does not automatically improve survival.

This supports the shared-request implementation, not a claim about AI reasoning, personality, learned cooperation, real-time inference or general superiority. Task offers and acknowledgements are not scored as successful work. A completed task requires productive work by its owner plus resolution of its need.

Ten seeds from one scenario provide limited evidence. Before claiming model benefit, compare scripted and hybrid runs using the same strategy, seeds, call budget and checkpoint policy, and count timeouts explicitly. Do not tune parameters on these seeds and describe a rerun as independent validation.

Local evidence: `artifacts/evaluations/run-20261021T232432-a5056d67/` contains configuration, manifest, per-run JSONL logs, JSON results, summary, CSV and Markdown report. Large generated artifacts are ignored by Git; this document records the reproducible protocol and per-seed outcomes.

## Model smoke checks

Two live Windows `hybrid` runs used the volunteer strategy, seeds 7 and 19, four planned calls per run, a 15-second model timeout, 75-second run limit and 150-second suite limit. Both reached 900 simulated seconds, but each first request timed out and opened the circuit. There were **zero accepted model actions** and six unused calls across the two runs. These checks validate bounded fallback, not successful model coordination. Local evidence: `artifacts/evaluations/run-20261021T232957-44ef7e5d/`.
