"""Frozen, bounded multi-scenario validation of scripted coordination strategies.

Each scenario runs in a fresh interpreter because village configuration is startup-only.
No models or campaign saves are used. Run python -m village.validation --help.
"""

import argparse
import csv
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from .config import load_config, read_json

STRATEGIES = ("independent", "requests", "assigned")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    """Freeze simulation/evaluator inputs; the batch reporting module is separate."""
    package = Path(__file__).parent
    files = [p for p in package.rglob("*.py") if p.name != "validation.py"]
    files += list((package / "data").rglob("*.json"))
    files += list((package / "data" / "prompts").rglob("*.txt"))
    return {str(p.relative_to(package)): digest(p) for p in sorted(files)}


def read_plan(path):
    path = Path(path).resolve()
    plan = read_json(path)
    required = {
        "name",
        "seeds",
        "excluded_development_seeds",
        "duration_seconds",
        "step_seconds",
        "run_wall_seconds",
        "scenario_wall_seconds",
        "suite_wall_seconds",
        "output_dir",
        "scenarios",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise ValueError("Invalid validation plan fields")
    if not isinstance(plan["name"], str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]*", plan["name"]
    ):
        raise ValueError("Invalid validation name")
    for key in ("seeds", "excluded_development_seeds"):
        seeds = plan[key]
        if (
            not isinstance(seeds, list)
            or not seeds
            or any(type(v) is not int or v < 0 for v in seeds)
            or len(set(seeds)) != len(seeds)
        ):
            raise ValueError("Seeds must be unique nonnegative integers")
    if set(plan["seeds"]) & set(plan["excluded_development_seeds"]):
        raise ValueError("Validation seeds overlap the recorded development seeds")
    import math

    for key in (
        "duration_seconds",
        "step_seconds",
        "run_wall_seconds",
        "scenario_wall_seconds",
        "suite_wall_seconds",
    ):
        value = plan[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{key} must be finite and positive")
    if plan["step_seconds"] > 0.1:
        raise ValueError("Validation substeps must not exceed 0.1 seconds")
    if not isinstance(plan["output_dir"], str) or not plan["output_dir"]:
        raise ValueError("Invalid output directory")
    if not isinstance(plan["scenarios"], list) or not plan["scenarios"]:
        raise ValueError("At least one scenario is required")
    names = set()
    scenarios = []
    for scenario in plan["scenarios"]:
        if not isinstance(scenario, dict) or set(scenario) != {"name", "config"}:
            raise ValueError("Invalid scenario fields")
        name = scenario["name"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name)
            or name in names
        ):
            raise ValueError("Scenario names must be unique safe directory names")
        names.add(name)
        if not isinstance(scenario["config"], str):
            raise ValueError("Scenario config must be a path")
        config_path = (path.parent / scenario["config"]).resolve()
        config = load_config(config_path)
        control = config["evaluation"]["controls"]["cooperative"]
        if (
            not config["coordination"]["enabled"]
            or not control["routines"]
            or control["disabled_actions"]
        ):
            raise ValueError(
                "Validation requires task coordination and every survival action enabled"
            )
        if config["evaluation"]["scenario_name"] != name:
            raise ValueError("Scenario label does not match its configuration")
        if plan["step_seconds"] > config["runtime"]["max_step_seconds"]:
            raise ValueError("Validation step exceeds configured simulation limit")
        # Freeze full effective settings; changing the original preset during a
        # run cannot silently alter a later child process.
        config = deepcopy(config)
        config["evaluation"].update(
            step_seconds=plan["step_seconds"],
            modes=["scripted"],
            control="cooperative",
            duration_seconds=plan["duration_seconds"],
            run_wall_seconds=plan["run_wall_seconds"],
            suite_wall_seconds=plan["scenario_wall_seconds"],
            max_model_calls=0,
            seeds=plan["seeds"],
        )
        scenarios.append((name, config_path, config))
    return plan, scenarios


def collect_runs(root, expected_seeds):
    """Only complete, verified seed/strategy results enter the primary comparison."""
    rows = []
    problems = []
    for seed in expected_seeds:
        for strategy in STRATEGIES:
            file = root / f"{seed}-scripted-{strategy}" / "result.json"
            if not file.exists():
                problems.append(f"missing seed={seed} strategy={strategy}")
                continue
            row = read_json(file)
            if (
                row.get("seed"),
                row.get("mode"),
                row.get("control"),
                row.get("coordination_mode"),
            ) != (seed, "scripted", "cooperative", strategy):
                raise ValueError(f"Unexpected result identity in {file}")
            if row.get("model_requests") != 0 or row.get("blocked_actions"):
                raise ValueError(f"Capabilities/inference mismatch in {file}")
            if not (row.get("completed_horizon") or row.get("failed")):
                problems.append(
                    f'incomplete seed={seed} strategy={strategy}: {row.get("stop_reason")}'
                )
            rows.append(row)
    return rows, problems


def summarize(rows, seeds):
    groups = []
    for strategy in STRATEGIES:
        group = [r for r in rows if r["coordination_mode"] == strategy]
        finished = [r for r in group if r["completed_horizon"] or r["failed"]]
        groups.append(
            dict(
                strategy=strategy,
                expected=len(seeds),
                observed=len(group),
                completed_or_failed=len(finished),
                survived=sum(r["completed_horizon"] for r in finished),
                lost=sum(r["failed"] for r in finished),
                incomplete_or_missing=len(seeds) - len(finished),
                mean_final_health=(
                    sum(r["village_health"] for r in finished) / len(finished)
                    if finished
                    else None
                ),
                mean_starvation_villager_seconds=(
                    sum(r["starvation_villager_seconds"] for r in finished)
                    / len(finished)
                    if finished
                    else None
                ),
            )
        )
    # Pairing uses the same scenario and seed; never mix different resource regimes.
    from .evaluation import paired_coordination

    return dict(strategies=groups, paired=paired_coordination(rows))


def write_batch_report(output, manifest, scenarios):
    result = {"manifest": manifest, "scenarios": scenarios}
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    fields = [
        "scenario",
        "seed",
        "coordination_mode",
        "completed_horizon",
        "failed",
        "stop_reason",
        "simulated_seconds",
        "village_health",
        "villagers_lost",
        "gate_breaches",
        "starvation_villager_seconds",
        "uncovered_threat_fraction",
        "model_requests",
    ]
    with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {**row, "scenario": scenario["name"]}
            for scenario in scenarios
            for row in scenario["runs"]
        )
    lines = [
        "# Held-out coordination validation",
        "",
        "Scripted policies; all survival capabilities enabled. Policies were frozen before running.",
        "Each cell is survived / completed-or-failed runs; incomplete and missing runs are separate.",
        "",
        "| Scenario | Independent | Requests | Assigned | Incomplete/missing |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for scenario in scenarios:
        groups = scenario["summary"]["strategies"]
        cells = [f"{g['survived']}/{g['completed_or_failed']}" for g in groups]
        lines.append(
            "| "
            + scenario["name"]
            + " | "
            + " | ".join(cells)
            + " | "
            + str(sum(g["incomplete_or_missing"] for g in groups))
            + " |"
        )
    lines += [
        "",
        "| Scenario | Strategy | Matched seeds | Missing/limited pairs | Survival gains | Regressions | Mean final-health delta | Mean uncovered-fraction delta |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scenario in scenarios:
        for row in scenario["summary"]["paired"]:
            lines.append(
                "| "
                + scenario["name"]
                + " | "
                + " | ".join(
                    str(row[k])
                    for k in (
                        "strategy",
                        "matched_seeds",
                        "excluded_or_missing_pairs",
                        "survival_gains",
                        "survival_regressions",
                        "mean_final_health_delta",
                        "mean_uncovered_fraction_delta",
                    )
                )
                + " |"
            )
    lines += [
        "",
        f"Status: {manifest['status']}. Expected runs: {manifest['expected_runs']}. Observed: {manifest['observed_runs']}.",
        "Survival at a fixed horizon is not indefinite survival. Results from different scenarios are not pooled into a universal winner.",
        "No language-model decisions were requested; these results cannot establish AI reasoning or learning.",
        "See summary.json for per-seed outcomes, full input hashes, protocol and incomplete-run details.",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default="configs/validation/holdout-v1.json")
    parser.add_argument("--output", help="Override parent output directory")
    args = parser.parse_args()
    try:
        plan, scenarios = read_plan(args.plan)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    plan_path = Path(args.plan).resolve()
    parent = (
        Path(args.output).expanduser().resolve()
        if args.output
        else (plan_path.parent / plan["output_dir"]).resolve()
    )
    output = parent / (
        plan["name"]
        + "-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    output.mkdir(parents=True)
    frozen = source_hashes()
    manifest = dict(
        plan=plan,
        plan_sha256=digest(plan_path),
        source_sha256=frozen,
        runner_sha256=digest(__file__),
        started_at=datetime.now(timezone.utc).isoformat(),
        expected_runs=len(scenarios) * len(plan["seeds"]) * len(STRATEGIES),
        observed_runs=0,
        status="running",
        scenarios=[],
    )
    frozen_scenarios = []
    for name, source, config in scenarios:
        config_path = output / (name + "-config.json")
        config_path.write_text(
            json.dumps(config, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        info = dict(
            name=name,
            source_config_sha256=digest(source),
            frozen_config_sha256=digest(config_path),
            frozen_config=config_path.name,
        )
        manifest["scenarios"].append(info)
        frozen_scenarios.append((name, config_path))
    (output / "protocol.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    def verify_inputs():
        if source_hashes() != frozen or digest(__file__) != manifest["runner_sha256"]:
            raise RuntimeError(
                "Simulation/evaluation code changed after the protocol was frozen"
            )
        for info in manifest["scenarios"]:
            if digest(output / info["frozen_config"]) != info["frozen_config_sha256"]:
                raise RuntimeError(
                    "Frozen scenario configuration changed during validation"
                )

    print(f'Frozen protocol: {output / "protocol.json"}', flush=True)
    deadline = time.monotonic() + plan["suite_wall_seconds"]
    results = []
    try:
        for name, config_path in frozen_scenarios:
            verify_inputs()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                manifest["status"] = "suite_wall_time_limit"
                break
            parent_output = output / name
            command = [
                sys.executable,
                "-m",
                "village.evaluation",
                "--config",
                str(config_path),
                "--compare-coordination",
                "--modes",
                "scripted",
                "--control",
                "cooperative",
                "--seeds",
                *[str(v) for v in plan["seeds"]],
                "--duration",
                str(plan["duration_seconds"]),
                "--max-model-calls",
                "0",
                "--wall-seconds",
                str(plan["run_wall_seconds"]),
                "--suite-seconds",
                str(min(plan["scenario_wall_seconds"], remaining)),
                "--output",
                str(parent_output),
            ]
            status = "finished"
            # Save child output directly; it remains inspectable while this process runs.
            with (output / (name + ".log")).open("w", encoding="utf-8") as log:
                try:
                    child = subprocess.run(
                        command, stdout=log, stderr=subprocess.STDOUT, timeout=remaining
                    )
                    if child.returncode:
                        status = f"child_exit_{child.returncode}"
                except subprocess.TimeoutExpired:
                    status = "suite_wall_time_limit"
            children = (
                sorted(parent_output.glob("run-*")) if parent_output.exists() else []
            )
            if len(children) > 1:
                raise ValueError("Unexpected duplicate scenario outputs")
            rows, problems = (
                collect_runs(children[0], plan["seeds"])
                if children
                else ([], ["child produced no output"])
            )
            scenario = dict(
                name=name,
                status=status,
                problems=problems,
                summary=summarize(rows, plan["seeds"]),
                runs=rows,
                evidence=str(children[0].relative_to(output)) if children else None,
            )
            results.append(scenario)
            manifest["observed_runs"] += len(rows)
            print(
                name
                + ": "
                + ", ".join(
                    f"{g['strategy']} {g['survived']}/{g['completed_or_failed']}"
                    for g in scenario["summary"]["strategies"]
                )
                + f'; incomplete/missing={sum(g["incomplete_or_missing"] for g in scenario["summary"]["strategies"])}',
                flush=True,
            )
            write_batch_report(output, manifest, results)
        verify_inputs()
        if manifest["status"] == "running":
            manifest["status"] = (
                "complete"
                if len(results) == len(scenarios)
                and all(
                    not r["problems"] and r["status"] == "finished" for r in results
                )
                else "incomplete"
            )
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
    except (OSError, ValueError, RuntimeError) as exc:
        manifest["status"] = "error"
        manifest["error"] = str(exc)
    finally:
        represented = {r["name"] for r in results}
        for name, _ in frozen_scenarios:
            if name not in represented:
                results.append(
                    dict(
                        name=name,
                        status="not_run",
                        problems=["scenario did not complete collection"],
                        summary=summarize([], plan["seeds"]),
                        runs=[],
                        evidence=None,
                    )
                )
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_batch_report(output, manifest, results)
    print(f'Report: {output / "report.md"}', flush=True)
    if manifest["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
