# Portfolio readiness checklist

This is a working acceptance plan. Passing automated checks does not establish
human playability, independent setup, production readiness or AI superiority.

| Phase | Deliverable | Acceptance evidence | Status |
| --- | --- | --- | --- |
| Consequential planning | Two controlled gate-allocation cases; baseline, scripted, model and adverse choices | Chosen priority changes task ownership and gate breach outcome; frozen held-out seeds, delay controls and all failures retained | Passed for two controlled fixtures; model matches scripted planner |
| Inference reliability | At least 40 real requests distributed across four roles | >=95% valid within configured deadline; latency distribution and every failure; invalid/late responses preserve local simulation | Passed 40/40 within deadline (10 per role); warm sequential diagnostic |
| Responsiveness | Reduce serialized input/state/poll waits | >=50 internal-input samples, median <=250 ms and p95 <=400 ms on documented host; no possession/reconnect regressions | Pending |
| Release reproducibility | Clean Linux and Windows wheel installs; contributor examples | Packaged config/assets/prompts work; action/backend extension examples execute; CI covers advertised versions | Pending |
| Stability | Extended automated simulation and session lifecycle checks | Save/reload invariants, 10 possession changes, three reconnects, bounded failures | Pending |
| Human review | 30-minute playtest, clean setup by another developer, three-minute demo | Named reviewer, dated result and recorded issues; never infer these from automation | Requires human review |

Targets above are project acceptance targets. A negative model result can support
an honest engineering portfolio. Claims of improved cooperation require causal
improvement over the scripted comparator on held-out conditions.

The original game, saved worlds and server/client prototype remain supported.
New experiments are opt-in and do not modify a player's campaign save.

Evidence: [causal allocation benchmark](CONTENTION_BENCHMARK.md). The current
claim is bounded gate allocation; no LLM advantage over the scripted planner
was observed. [Human review and recording checklist](PORTFOLIO_DEMO.md).
