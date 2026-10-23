<!--
File: docs/FILE_INVENTORY.md
Purpose: Explain every tracked file and its documentation/preservation convention.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Tracked file inventory

Reviewed 23 October 2026. Maintenance contact defaults to `sunshine-engineer` as
requested; this does not assign authorship. Modified dates are present only in
editable file headers; unchanged artifacts retain their existing provenance.

This inventory covers 188 maintained/tracked files, including this inventory.
Local venvs, downloaded weights, saves, caches and build/evaluation output are
excluded. Existing directories already match their responsibilities, so there are
no file moves or import-path changes in this pass.

| File | Purpose | Documentation / preservation |
| --- | --- | --- |
| [.editorconfig](../.editorconfig) | UTF-8/newline/indentation defaults with evidence/legal exclusions | Comment header |
| [.env.example](../.env.example) | Optional environment-variable examples; no auto dotenv loading | Comment header; no secrets |
| [.github/workflows/tests.yml](../.github/workflows/tests.yml) | Cross-platform lint, docs, regression and wheel-install CI | YAML comment header |
| [.gitignore](../.gitignore) | Exclude local environments, saves, caches, credentials and generated files | Comment header |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Contributing | HTML comment header; preserve historical result claims |
| [LICENSE](../LICENSE) | Existing MIT license and attribution | Preserve legal text unchanged |
| [README.md](../README.md) | Village Minds — Willowbrook survival prototype | HTML comment header; preserve historical result claims |
| [VALIDATION.md](../VALIDATION.md) | Validation evidence | HTML comment header; preserve historical result claims |
| [compose.yaml](../compose.yaml) | Pinned loopback model container and persistent downloaded-weight volume | YAML comment header |
| [configs/cooperation-siege.json](../configs/cooperation-siege.json) | Validated startup override: cooperation siege | Strict JSON; no extra metadata keys |
| [configs/portfolio/priority-development.json](../configs/portfolio/priority-development.json) | Frozen batch protocol: priority-contention-development | Frozen protocol; inventory metadata only |
| [configs/portfolio/priority-holdout.json](../configs/portfolio/priority-holdout.json) | Frozen batch protocol: priority-contention-holdout-v1 | Frozen protocol; inventory metadata only |
| [configs/portfolio/priority.json](../configs/portfolio/priority.json) | Validated startup override: priority | Strict JSON; no extra metadata keys |
| [configs/portfolio/reliability.json](../configs/portfolio/reliability.json) | Validated startup override: reliability | Strict JSON; no extra metadata keys |
| [configs/repair-priority.json](../configs/repair-priority.json) | Validated startup override: repair priority | Strict JSON; no extra metadata keys |
| [configs/server-local.json](../configs/server-local.json) | Validated startup override: server local | Strict JSON; no extra metadata keys |
| [configs/strategy-v2/development-plan.json](../configs/strategy-v2/development-plan.json) | Frozen batch protocol: development-plan | Frozen protocol; inventory metadata only |
| [configs/strategy-v2/development.json](../configs/strategy-v2/development.json) | Validated startup override: development | Strict JSON; no extra metadata keys |
| [configs/strategy-v2/holdout-plan.json](../configs/strategy-v2/holdout-plan.json) | Frozen batch protocol: holdout-plan | Frozen protocol; inventory metadata only |
| [configs/strategy-v3/confirmation.json](../configs/strategy-v3/confirmation.json) | Frozen batch protocol: handoff-confirmation-v3 | Frozen protocol; inventory metadata only |
| [configs/strategy-v3/factorial.json](../configs/strategy-v3/factorial.json) | Frozen batch protocol: repair-factorial-v3 | Frozen protocol; inventory metadata only |
| [configs/strategy-v3/timing-fixed_delay.json](../configs/strategy-v3/timing-fixed_delay.json) | Frozen batch protocol: repair-fixed-delay-v3 | Frozen protocol; inventory metadata only |
| [configs/strategy-v3/timing-measured_delay.json](../configs/strategy-v3/timing-measured_delay.json) | Frozen batch protocol: repair-measured-delay-v3 | Frozen protocol; inventory metadata only |
| [configs/strategy-v3/timing-paused_checkpoints.json](../configs/strategy-v3/timing-paused_checkpoints.json) | Frozen batch protocol: repair-paused-checkpoints-v3 | Frozen protocol; inventory metadata only |
| [configs/strategy-v4/fixed.json](../configs/strategy-v4/fixed.json) | Frozen batch protocol: repair-priority-fixed-v4 | Frozen protocol; inventory metadata only |
| [configs/strategy-v4/measured-grid.json](../configs/strategy-v4/measured-grid.json) | Frozen batch protocol: repair-priority-grid-measured-v4 | Frozen protocol; inventory metadata only |
| [configs/strategy-v4/measured.json](../configs/strategy-v4/measured.json) | Frozen batch protocol: repair-priority-measured-v4 | Frozen protocol; inventory metadata only |
| [configs/validation/food-pressure.json](../configs/validation/food-pressure.json) | Validated startup override: food pressure | Strict JSON; no extra metadata keys |
| [configs/validation/holdout-v1.json](../configs/validation/holdout-v1.json) | Frozen batch protocol: coordination-holdout-v1 | Frozen protocol; inventory metadata only |
| [configs/validation/long-haul.json](../configs/validation/long-haul.json) | Validated startup override: long haul | Strict JSON; no extra metadata keys |
| [configs/validation/wood-pressure.json](../configs/validation/wood-pressure.json) | Validated startup override: wood pressure | Strict JSON; no extra metadata keys |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Architecture | HTML comment header; preserve historical result claims |
| [docs/CLIENT_SMOOTHING.md](CLIENT_SMOOTHING.md) | Network client movement smoothing | HTML comment header; preserve historical result claims |
| [docs/CONFIGURATION.md](CONFIGURATION.md) | Configuration | HTML comment header; preserve historical result claims |
| [docs/CONSISTENCY_REVIEW.md](CONSISTENCY_REVIEW.md) | Project-wide consistency review — 23 October 2026 | HTML comment header; preserve historical result claims |
| [docs/CONTENTION_BENCHMARK.md](CONTENTION_BENCHMARK.md) | Consequential repair-priority benchmark | HTML comment header; preserve historical result claims |
| [docs/COOPERATION_SCENARIO.md](COOPERATION_SCENARIO.md) | Cooperation siege | HTML comment header; preserve historical result claims |
| [docs/COORDINATION.md](COORDINATION.md) | Help requests and task assignments | HTML comment header; preserve historical result claims |
| [docs/COORDINATION_RESULTS.md](COORDINATION_RESULTS.md) | Coordination comparison: 21 October 2026 | HTML comment header; preserve historical result claims |
| [docs/DOCUMENTATION_AUDIT.md](DOCUMENTATION_AUDIT.md) | Documentation handover audit — 22 October 2026 | HTML comment header; preserve historical result claims |
| [docs/EVALUATION.md](EVALUATION.md) | AI evaluation and fast-forward | HTML comment header; preserve historical result claims |
| [docs/EVALUATION_GAPS.md](EVALUATION_GAPS.md) | Evaluation correctness and component experiments | HTML comment header; preserve historical result claims |
| [docs/EXTENDING.md](EXTENDING.md) | Adding assets, gameplay and models | HTML comment header; preserve historical result claims |
| [docs/FILE_INVENTORY.md](FILE_INVENTORY.md) | Tracked-file purpose and preservation inventory | HTML comment header; preserve historical result claims |
| [docs/HANDOVER.md](HANDOVER.md) | Developer handover | HTML comment header; preserve historical result claims |
| [docs/HELD_OUT_VALIDATION.md](HELD_OUT_VALIDATION.md) | Held-out coordination validation | HTML comment header; preserve historical result claims |
| [docs/INDEX.md](INDEX.md) | Documentation index | HTML comment header; preserve historical result claims |
| [docs/PORTFOLIO_DEMO.md](PORTFOLIO_DEMO.md) | Three-minute review walkthrough | HTML comment header; preserve historical result claims |
| [docs/PORTFOLIO_READINESS.md](PORTFOLIO_READINESS.md) | Portfolio readiness checklist | HTML comment header; preserve historical result claims |
| [docs/PROJECT_STANDARDS.md](PROJECT_STANDARDS.md) | Project consistency conventions | HTML comment header; preserve historical result claims |
| [docs/REPAIR_PRIORITY_PLANS.md](REPAIR_PRIORITY_PLANS.md) | Temporary repair priorities | HTML comment header; preserve historical result claims |
| [docs/SERVER_CLIENT.md](SERVER_CLIENT.md) | Single-server, single-client prototype | HTML comment header; preserve historical result claims |
| [docs/STRATEGY_EXPERIMENT.md](STRATEGY_EXPERIMENT.md) | Repair strategy and logistics experiment v2 | HTML comment header; preserve historical result claims |
| [docs/results/client-interpolation-render.json](results/client-interpolation-render.json) | Published experiment, diagnostic or release evidence; client interpolation render | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/client-responsiveness-v1.json](results/client-responsiveness-v1.json) | Published experiment, diagnostic or release evidence; client responsiveness v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/coordination-holdout-v1-protocol.json](results/coordination-holdout-v1-protocol.json) | Published experiment, diagnostic or release evidence; coordination holdout v1 protocol | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/coordination-holdout-v1-repair-audit.json](results/coordination-holdout-v1-repair-audit.json) | Published experiment, diagnostic or release evidence; coordination holdout v1 repair audit | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/coordination-holdout-v1.csv](results/coordination-holdout-v1.csv) | Published per-run outcome/audit table; coordination holdout v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/handoff-confirmation-v3.csv](results/handoff-confirmation-v3.csv) | Published per-run outcome/audit table; handoff confirmation v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/handoff-confirmation-v3.json](results/handoff-confirmation-v3.json) | Published experiment, diagnostic or release evidence; handoff confirmation v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-authority-soak-v1.json](results/portfolio-authority-soak-v1.json) | Published experiment, diagnostic or release evidence; portfolio authority soak v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-contention-v1-audit.csv](results/portfolio-contention-v1-audit.csv) | Published per-run outcome/audit table; portfolio contention v1 audit | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-contention-v1-audit.json](results/portfolio-contention-v1-audit.json) | Published experiment, diagnostic or release evidence; portfolio contention v1 audit | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-contention-v1-traces.zip](results/portfolio-contention-v1-traces.zip) | Frozen raw contention traces and configuration archive; portfolio contention v1 traces | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-contention-v1.json](results/portfolio-contention-v1.json) | Published experiment, diagnostic or release evidence; portfolio contention v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-install-linux-v1.json](results/portfolio-install-linux-v1.json) | Published experiment, diagnostic or release evidence; portfolio install linux v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-install-windows-v1.json](results/portfolio-install-windows-v1.json) | Published experiment, diagnostic or release evidence; portfolio install windows v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-install-windows-v1.png](results/portfolio-install-windows-v1.png) | Recorded native Windows installed-render screenshot; portfolio install windows v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-latency-cleanup-smoke.json](results/portfolio-latency-cleanup-smoke.json) | Published experiment, diagnostic or release evidence; portfolio latency cleanup smoke | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-latency-first-attempt.failed.json](results/portfolio-latency-first-attempt.failed.json) | Published experiment, diagnostic or release evidence; portfolio latency first attempt.failed | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-latency-legacy-v1.json](results/portfolio-latency-legacy-v1.json) | Published experiment, diagnostic or release evidence; portfolio latency legacy v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-latency-responsive-v1.json](results/portfolio-latency-responsive-v1.json) | Published experiment, diagnostic or release evidence; portfolio latency responsive v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-latency-threaded-legacy-diagnostic.json](results/portfolio-latency-threaded-legacy-diagnostic.json) | Published experiment, diagnostic or release evidence; portfolio latency threaded legacy diagnostic | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-latency-threaded-responsive-diagnostic.json](results/portfolio-latency-threaded-responsive-diagnostic.json) | Published experiment, diagnostic or release evidence; portfolio latency threaded responsive diagnostic | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-release-v1.json](results/portfolio-release-v1.json) | Published experiment, diagnostic or release evidence; portfolio release v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-reliability-v1.json](results/portfolio-reliability-v1.json) | Published experiment, diagnostic or release evidence; portfolio reliability v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-runtime-v1.json](results/portfolio-runtime-v1.json) | Published experiment, diagnostic or release evidence; portfolio runtime v1 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/portfolio-soak-first-attempt.failed.json](results/portfolio-soak-first-attempt.failed.json) | Published experiment, diagnostic or release evidence; portfolio soak first attempt.failed | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/priority-live-first-attempt.json](results/priority-live-first-attempt.json) | Published experiment, diagnostic or release evidence; priority live first attempt | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/priority-model-server-smoke.json](results/priority-model-server-smoke.json) | Published experiment, diagnostic or release evidence; priority model server smoke | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-factorial-v3.csv](results/repair-factorial-v3.csv) | Published per-run outcome/audit table; repair factorial v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-factorial-v3.json](results/repair-factorial-v3.json) | Published experiment, diagnostic or release evidence; repair factorial v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-fixed-delay-v3.csv](results/repair-fixed-delay-v3.csv) | Published per-run outcome/audit table; repair fixed delay v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-fixed-delay-v3.json](results/repair-fixed-delay-v3.json) | Published experiment, diagnostic or release evidence; repair fixed delay v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-measured-delay-v3.csv](results/repair-measured-delay-v3.csv) | Published per-run outcome/audit table; repair measured delay v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-measured-delay-v3.json](results/repair-measured-delay-v3.json) | Published experiment, diagnostic or release evidence; repair measured delay v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-paused-checkpoints-v3.csv](results/repair-paused-checkpoints-v3.csv) | Published per-run outcome/audit table; repair paused checkpoints v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-paused-checkpoints-v3.json](results/repair-paused-checkpoints-v3.json) | Published experiment, diagnostic or release evidence; repair paused checkpoints v3 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-fixed-v4-audit.json](results/repair-priority-fixed-v4-audit.json) | Published experiment, diagnostic or release evidence; repair priority fixed v4 audit | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-fixed-v4.csv](results/repair-priority-fixed-v4.csv) | Published per-run outcome/audit table; repair priority fixed v4 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-fixed-v4.json](results/repair-priority-fixed-v4.json) | Published experiment, diagnostic or release evidence; repair priority fixed v4 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-measured-v4-audit.json](results/repair-priority-measured-v4-audit.json) | Published experiment, diagnostic or release evidence; repair priority measured v4 audit | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-measured-v4-confounded.csv](results/repair-priority-measured-v4-confounded.csv) | Published per-run outcome/audit table; repair priority measured v4 confounded | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-measured-v4-confounded.json](results/repair-priority-measured-v4-confounded.json) | Published experiment, diagnostic or release evidence; repair priority measured v4 confounded | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-measured-v4.csv](results/repair-priority-measured-v4.csv) | Published per-run outcome/audit table; repair priority measured v4 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-measured-v4.json](results/repair-priority-measured-v4.json) | Published experiment, diagnostic or release evidence; repair priority measured v4 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-priority-timing-control-v4.json](results/repair-priority-timing-control-v4.json) | Published experiment, diagnostic or release evidence; repair priority timing control v4 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-strategy-v2-probe.json](results/repair-strategy-v2-probe.json) | Published experiment, diagnostic or release evidence; repair strategy v2 probe | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-strategy-v2.csv](results/repair-strategy-v2.csv) | Published per-run outcome/audit table; repair strategy v2 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-strategy-v2.json](results/repair-strategy-v2.json) | Published experiment, diagnostic or release evidence; repair strategy v2 | Immutable; retain exact bytes and embedded historical hashes |
| [docs/results/repair-timing-v3-failed-attempt.json](results/repair-timing-v3-failed-attempt.json) | Published experiment, diagnostic or release evidence; repair timing v3 failed attempt | Immutable; retain exact bytes and embedded historical hashes |
| [examples/contributor.json](../examples/contributor.json) | Runnable startup/plugin/profile example: contributor | Strict validated JSON; inventory metadata only |
| [examples/custom.json](../examples/custom.json) | Runnable startup/plugin/profile example: custom | Strict validated JSON; inventory metadata only |
| [examples/models.json](../examples/models.json) | Runnable startup/plugin/profile example: models | Strict validated JSON; inventory metadata only |
| [pyproject.toml](../pyproject.toml) | Packaging, pinned runtime/dev dependencies and Ruff configuration | TOML comment header |
| [scripts/audit_priority_results.py](../scripts/audit_priority_results.py) | Compare non-planner decisions and task ownership in a frozen strategy batch. | Module header and definition docstrings |
| [scripts/audit_repairs.py](../scripts/audit_repairs.py) | Audit actual gate HP restored per wood from a completed validation batch. | Module header and definition docstrings |
| [scripts/check_autonomy.py](../scripts/check_autonomy.py) | Verify six villagers act concurrently in a temporary native game session. | Module header and definition docstrings |
| [scripts/check_client_interpolation.py](../scripts/check_client_interpolation.py) | Offscreen render check: run from the repository root with Panda3D installed. | Module header and definition docstrings |
| [scripts/check_client_responsiveness.py](../scripts/check_client_responsiveness.py) | Real loopback HTTP and offscreen Panda3D input-to-motion measurement. | Module header and definition docstrings |
| [scripts/check_consistency.py](../scripts/check_consistency.py) | Check maintained-source headers and documentation without importing the game. | Module header and definition docstrings |
| [scripts/check_contributor_contracts.py](../scripts/check_contributor_contracts.py) | Verify packaged action/backend extension contracts without a model or renderer. | Module header and definition docstrings |
| [scripts/check_extensions.py](../scripts/check_extensions.py) | Render a temporary custom model and exercise configured plugin input/save hooks. | Module header and definition docstrings |
| [scripts/check_priority_server.py](../scripts/check_priority_server.py) | Bounded native/server integration fixture; requires the configured local Ollama model. | Module header and definition docstrings |
| [scripts/check_release_soak.py](../scripts/check_release_soak.py) | Fast-forward authority/persistence soak; not a wall-time or human playtest. | Module header and definition docstrings |
| [scripts/check_restart.py](../scripts/check_restart.py) | Verify actual CLI startup/normal exit saving across two temporary game processes. | Module header and definition docstrings |
| [scripts/check_speed.py](../scripts/check_speed.py) | Offscreen integration for speed keys, substeps, pause and player decision logs. | Module header and definition docstrings |
| [scripts/check_wheel_install.py](../scripts/check_wheel_install.py) | Install a wheel in a new venv and exercise it outside the source checkout. | Module header and definition docstrings |
| [scripts/check_window.py](../scripts/check_window.py) | Linux/X11 integration check using targeted X11 window keyboard events (needs libX11). | Module header and definition docstrings |
| [scripts/describe_runtime.py](../scripts/describe_runtime.py) | Record non-secret host/model metadata for local benchmark reproduction. | Module header and definition docstrings |
| [scripts/replay_priority_control.py](../scripts/replay_priority_control.py) | Post-hoc timing control: replay a model run's delays while deferring every plan. | Module header and definition docstrings |
| [scripts/summarize_contention.py](../scripts/summarize_contention.py) | Audit paired fixture identity and actual event order in a frozen contention batch. | Module header and definition docstrings |
| [tests/test_autonomy.py](../tests/test_autonomy.py) | Test autonomy. | Module header and definition docstrings |
| [tests/test_client_input.py](../tests/test_client_input.py) | Input must be published before potentially expensive snapshot restoration. | Module header and definition docstrings |
| [tests/test_configuration.py](../tests/test_configuration.py) | Config and plugin checks use subprocesses: settings are startup-only. | Module header and definition docstrings |
| [tests/test_cooperation_scenario.py](../tests/test_cooperation_scenario.py) | Causal controls use real survival rules, not fabricated AI outcomes. | Module header and definition docstrings |
| [tests/test_coordination.py](../tests/test_coordination.py) | Structured cooperation: ownership, real work, safety and restart continuity. | Module header and definition docstrings |
| [tests/test_evaluation.py](../tests/test_evaluation.py) | Evaluation tests use fake model responses; only timeout tests spawn processes. | Module header and definition docstrings |
| [tests/test_evaluation_schedule.py](../tests/test_evaluation_schedule.py) | Coverage is deterministic and explicit even with small model-call budgets. | Module header and definition docstrings |
| [tests/test_evaluation_timing.py](../tests/test_evaluation_timing.py) | An inert inference response must not change the physics integration grid. | Module header and definition docstrings |
| [tests/test_farming_policy.py](../tests/test_farming_policy.py) | Policy regressions: choose executable work or navigate to a specific plot. | Module header and definition docstrings |
| [tests/test_interpolation.py](../tests/test_interpolation.py) | Deterministic presentation tests use synthetic packets, never physics prediction. | Module header and definition docstrings |
| [tests/test_models.py](../tests/test_models.py) | Test models. | Module header and definition docstrings |
| [tests/test_priority_audit.py](../tests/test_priority_audit.py) | Evidence auditing must detect actual behavior changes, not wall-clock noise. | Module header and definition docstrings |
| [tests/test_priority_plans.py](../tests/test_priority_plans.py) | Strategic plans survive helper churn but remain bounded by local safety. | Module header and definition docstrings |
| [tests/test_readiness.py](../tests/test_readiness.py) | Ownership/physics boundaries for responsive transport and causal fixtures. | Module header and definition docstrings |
| [tests/test_server.py](../tests/test_server.py) | Authoritative simulation, bounded commands, disconnect and real HTTP checks. | Module header and definition docstrings |
| [tests/test_simulation.py](../tests/test_simulation.py) | Test simulation. | Module header and definition docstrings |
| [tests/test_strategy.py](../tests/test_strategy.py) | Resource allocation, partial loads and strategic ownership safety. | Module header and definition docstrings |
| [tests/test_survival.py](../tests/test_survival.py) | Test survival. | Module header and definition docstrings |
| [tests/test_validation.py](../tests/test_validation.py) | Holdout harness checks use tiny runs, never the full research matrix. | Module header and definition docstrings |
| [village/__init__.py](../village/__init__.py) | Village Minds prototype. | Module header and definition docstrings |
| [village/__main__.py](../village/__main__.py) | Command-line entry point for the local village game. | Module header and definition docstrings |
| [village/allocation.py](../village/allocation.py) | Repair candidates priced by useful HP, wood, travel and opportunity cost. | Module header and definition docstrings |
| [village/assets.py](../village/assets.py) | Data-defined visual prefabs and optional Panda3D model files. | Module header and definition docstrings |
| [village/brains.py](../village/brains.py) | Independent local routines and bounded asynchronous model scheduling. | Module header and definition docstrings |
| [village/cli.py](../village/cli.py) | Shared startup-only config and model options for game and API probe. | Module header and definition docstrings |
| [village/client.py](../village/client.py) | Panda3D viewer/controller for a continuously running loopback village server. | Module header and definition docstrings |
| [village/config.py](../village/config.py) | Validated startup configuration. Import this module before simulation/rendering. | Module header and definition docstrings |
| [village/controls.py](../village/controls.py) | Configured keyboard bindings; simulation actions remain engine independent. | Module header and definition docstrings |
| [village/coordination.py](../village/coordination.py) | Shared, structured help requests and exclusive, voluntary task ownership. | Module header and definition docstrings |
| [village/data/assets/catalog.json](../village/data/assets/catalog.json) | Packaged prefab, scene styling and UI widget definitions | Strict JSON asset contract; inventory metadata only |
| [village/data/default.json](../village/data/default.json) | Authoritative startup configuration defaults and schema reference | Strict JSON; inventory metadata only |
| [village/data/prompts/repair_coordinator.txt](../village/data/prompts/repair_coordinator.txt) | Exact repair coordinator model input template | Preserve exact input text; inventory metadata only |
| [village/data/prompts/repair_priority.txt](../village/data/prompts/repair_priority.txt) | Exact repair priority model input template | Preserve exact input text; inventory metadata only |
| [village/data/prompts/villager.txt](../village/data/prompts/villager.txt) | Exact villager model input template | Preserve exact input text; inventory metadata only |
| [village/decisions.py](../village/decisions.py) | JSON action schema shared by model backends; Python revalidates results. | Module header and definition docstrings |
| [village/entities.py](../village/entities.py) | Simulation entities; no graphics or network imports. | Module header and definition docstrings |
| [village/evaluation.py](../village/evaluation.py) | Bounded, headless comparisons with fixed simulation steps and AI checkpoints. | Module header and definition docstrings |
| [village/evaluation_controls.py](../village/evaluation_controls.py) | Evaluation-only interventions; ordinary game worlds keep every action. | Module header and definition docstrings |
| [village/evaluation_schedule.py](../village/evaluation_schedule.py) | Deterministic role-balanced model checkpoints for bounded comparisons. | Module header and definition docstrings |
| [village/extensions.py](../village/extensions.py) | Explicit, trusted Python extension hooks. Model text can never register code. | Module header and definition docstrings |
| [village/game.py](../village/game.py) | Procedural Panda3D scene and controls. All scene mutations stay on this thread. | Module header and definition docstrings |
| [village/inference.py](../village/inference.py) | Hard wall deadlines shared by live play, evaluation and reliability probes. | Module header and definition docstrings |
| [village/inference_probe.py](../village/inference_probe.py) | Bounded per-role repair-allocation diagnostics on explicit controlled fixtures. | Module header and definition docstrings |
| [village/interpolation.py](../village/interpolation.py) | Bounded presentation-only interpolation of confirmed network positions. | Module header and definition docstrings |
| [village/logistics.py](../village/logistics.py) | Urgent partial deliveries and observable movement without changing abilities. | Module header and definition docstrings |
| [village/map_data.py](../village/map_data.py) | Shared map and roster loaded from startup configuration. | Module header and definition docstrings |
| [village/models.py](../village/models.py) | Model transport adapters. Only decision dictionaries cross this boundary. | Module header and definition docstrings |
| [village/navigation.py](../village/navigation.py) | Grid navigation shared by simulation and controllers. | Module header and definition docstrings |
| [village/network.py](../village/network.py) | Bounded HTTP transport and one background client worker; no rendering imports. | Module header and definition docstrings |
| [village/persistence.py](../village/persistence.py) | Versioned, atomic JSON snapshots; never deserialize executable objects. | Module header and definition docstrings |
| [village/plugins/__init__.py](../village/plugins/__init__.py) | Optional example plugins. Enable explicitly through configuration. | Module header and definition docstrings |
| [village/plugins/encourage.py](../village/plugins/encourage.py) | Example configurable action with validated, persistent cooldown state. | Module header and definition docstrings |
| [village/plugins/offline_backend.py](../village/plugins/offline_backend.py) | Contributor example: deterministic adapter contract, not AI inference. | Module header and definition docstrings |
| [village/policies.py](../village/policies.py) | Default role/needs policy. Register alternative policies through extensions. | Module header and definition docstrings |
| [village/priority_benchmark.py](../village/priority_benchmark.py) | Causal gate-contention fixtures using ordinary world physics and local routines. | Module header and definition docstrings |
| [village/probe.py](../village/probe.py) | Verify a real local model response without starting graphics. | Module header and definition docstrings |
| [village/scene.py](../village/scene.py) | Procedural geometry and configured scene construction; no game rules. | Module header and definition docstrings |
| [village/server.py](../village/server.py) | Loopback prototype server. Only the simulation thread may mutate World. | Module header and definition docstrings |
| [village/simulation.py](../village/simulation.py) | Compatibility facade. New code should import the owning modules directly. | Module header and definition docstrings |
| [village/strategy_experiment.py](../village/strategy_experiment.py) | Frozen paired experiment: legacy scripts, improved scripts and model assistance. | Module header and definition docstrings |
| [village/survival.py](../village/survival.py) | Crop, resource, combat, wave and failure rules. | Module header and definition docstrings |
| [village/telemetry.py](../village/telemetry.py) | Optional JSONL decision traces with bounded disk usage and aggregate counters. | Module header and definition docstrings |
| [village/timing.py](../village/timing.py) | Advance fast simulation using bounded substeps instead of dropping elapsed time. | Module header and definition docstrings |
| [village/ui.py](../village/ui.py) | HUD widget construction from the asset catalog. | Module header and definition docstrings |
| [village/validation.py](../village/validation.py) | Frozen, bounded multi-scenario validation of scripted coordination strategies. | Module header and definition docstrings |
| [village/world.py](../village/world.py) | World lifecycle, perception, movement and validated action dispatch. | Module header and definition docstrings |
