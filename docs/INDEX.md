# Documentation index

Reviewed 22 October 2026 against production source `e1cc748` and release evidence
`28d766a`. Documentation changes are recorded in [the audit](DOCUMENTATION_AUDIT.md).
Start with [the handover runbook](HANDOVER.md). A historical result is evidence for
its recorded source/configuration, not a new validation of the current checkout.

| Document | Purpose and status |
| --- | --- |
| [README](../README.md) | Current Windows/Linux setup, gameplay, controls, persistence and troubleshooting |
| [Handover](HANDOVER.md) | Receiving developer's setup, operations, recovery, checks and sign-off |
| [Contributing](../CONTRIBUTING.md) | Change workflow, focused validation and extension boundaries |
| [Architecture](ARCHITECTURE.md) | Current ownership, data flow, simulation/inference/transport boundaries |
| [Configuration](CONFIGURATION.md) | Startup overrides, paths, fingerprint compatibility and settings map |
| [Extending](EXTENDING.md) | Assets, roles, actions, systems, saved plugin state and backend contracts |
| [Server/client](SERVER_CLIENT.md) | Current protocol 2, launch, possession, reconnect and loopback limits |
| [Client smoothing](CLIENT_SMOOTHING.md) | Current interpolation and latest latency; older diagnostic explicitly labeled |
| [Evaluation](EVALUATION.md) | Current headless modes, timing, budgets, logs and metric interpretation |
| [Cooperation scenario](COOPERATION_SCENARIO.md) | Current optional siege preset and comparison commands |
| [Coordination](COORDINATION.md) | Current task requests, offers, ownership, strategy and saved state |
| [Coordination results](COORDINATION_RESULTS.md) | Historical ten-seed scripted development comparison |
| [Held-out validation](HELD_OUT_VALIDATION.md) | Frozen v1: 96 scripted runs; resource/travel failure boundaries |
| [Strategy experiment](STRATEGY_EXPERIMENT.md) | Frozen v2: assignment allocator and combined policy; includes regressions |
| [Evaluation gaps](EVALUATION_GAPS.md) | Frozen v3: components and timing; measured-delay confound is disclosed |
| [Repair priority plans](REPAIR_PRIORITY_PLANS.md) | Current opt-in planner interface plus frozen v4 and timing-grid correction |
| [Contention benchmark](CONTENTION_BENCHMARK.md) | Latest narrow causal benchmark: 80 runs; model matches scripted planner; warm 40-call probe |
| [Validation](../VALIDATION.md) | Latest release checks first, followed by dated historical records |
| [Portfolio readiness](PORTFOLIO_READINESS.md) | Acceptance status, raw release evidence and claims permitted |
| [Portfolio demo](PORTFOLIO_DEMO.md) | Three-minute recording plan and pending human acceptance record |
| [Documentation audit](DOCUMENTATION_AUDIT.md) | Audit scope, corrections, checks and remaining handover limits |

The experiment sequence is development → v1 → v2 → v3 → v4 → contention. Do not
pool their seeds, metrics or timings into one AI-benefit score. Rerunning a plan
with current code creates a new run with new hashes. Reused seeds are regression
coverage, not fresh holdout evidence. Historical raw trace folders under ignored
`artifacts/` are not automatically transferred by Git; see the handover runbook.
