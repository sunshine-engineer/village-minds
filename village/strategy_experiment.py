"""Frozen paired experiment: legacy scripts, improved scripts and model assistance."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import csv
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid
from .config import load_config, read_json
from .validation import source_hashes, digest

CONDITIONS = ("legacy", "scripted", "model")
ABLATIONS = (
    "legacy",
    "scoring",
    "handoffs",
    "deliveries",
    "scoring-handoffs",
    "scoring-deliveries",
    "handoffs-deliveries",
    "scripted",
)


def validate_plan(plan):
    strategy_mode = plan.get("strategy_mode", "assignment")
    if strategy_mode not in ("assignment", "priority_plan") or (
        "scripted-priority" in plan.get("conditions", ())
        and strategy_mode != "priority_plan"
    ):
        raise ValueError("Scripted priority comparison requires priority_plan strategy")
    if not plan["seeds"] or any(type(s) is not int or s < 0 for s in plan["seeds"]):
        raise ValueError("Invalid seeds")
    if len(set(plan["seeds"])) != len(plan["seeds"]) or set(plan["seeds"]) & set(
        plan["excluded_seeds"]
    ):
        raise ValueError(
            "Fresh seeds must be unique and excluded from earlier experiments"
        )
    if any(
        isinstance(plan[k], bool)
        or not isinstance(plan[k], (int, float))
        or not math.isfinite(plan[k])
        or plan[k] <= 0
        for k in (
            "duration_seconds",
            "request_seconds",
            "run_wall_seconds",
            "suite_seconds",
        )
    ):
        raise ValueError("Budgets must be positive")
    if type(plan["model_calls"]) is not int or plan["model_calls"] < 1:
        raise ValueError("At least one model call is required")
    for name in [
        plan.get("name", "invalid"),
        *(c["name"] for c in plan.get("cases", [])),
    ]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            raise ValueError("Invalid experiment/case name")


def repair_audit(path):
    wood = hp = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (
            row["event"] != "decision"
            or row.get("outcome") != "accepted"
            or row.get("decision", {}).get("action") != "repair"
        ):
            continue
        before, after = row["before"], row["after"]
        wood += max(0, before["store"]["wood"] - after["store"]["wood"])
        hp += sum(
            max(0, after["gates"][g] - value) for g, value in before["gates"].items()
        )
    return dict(
        repair_hp=hp, repair_wood=wood, repair_hp_per_wood=hp / wood if wood else None
    )


def paired_results(rows, baseline_condition="scripted"):
    pairs = []
    for row in rows:
        if row["condition"] != "model":
            continue
        baseline = next(
            (
                r
                for r in rows
                if r["condition"] == baseline_condition
                and (r["seed"], r["case"]) == (row["seed"], row["case"])
            ),
            None,
        )
        valid = baseline is not None and all(
            r["stop_reason"] in ("duration_reached", "village_destroyed")
            for r in (baseline, row)
        )
        pairs.append(
            dict(
                case=row["case"],
                seed=row["seed"],
                baseline=baseline_condition,
                eligible=valid,
                health_delta=(
                    row["village_health"] - baseline["village_health"]
                    if valid
                    else None
                ),
                survival_gain=bool(
                    valid and row["completed_horizon"] and baseline["failed"]
                ),
                survival_regression=bool(
                    valid and baseline["completed_horizon"] and row["failed"]
                ),
            )
        )
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", default="artifacts/strategy")
    args = parser.parse_args()
    plan_path = Path(args.plan).resolve()
    plan = read_json(plan_path)
    validate_plan(plan)
    conditions = tuple(plan.get("conditions", CONDITIONS))
    if (
        not conditions
        or len(set(conditions)) != len(conditions)
        or any(c not in (*ABLATIONS, "model", "scripted-priority") for c in conditions)
    ):
        parser.error("Invalid experiment conditions")
    root = Path(args.output).resolve() / (
        plan["name"]
        + "-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    root.mkdir(parents=True)
    sources = source_hashes()
    frozen = dict(
        plan=deepcopy(plan),
        sources=sources,
        interpreter=sys.version,
        timing_policy=plan.get("timing_policy", "paused_checkpoints"),
        expected_runs=len(plan["seeds"]) * len(plan["cases"]) * len(conditions),
    )
    (root / "protocol.json").write_text(json.dumps(frozen, indent=2) + "\n")
    deadline = time.monotonic() + plan["suite_seconds"]
    rows, failures = [], []
    configs = {}
    # Freeze resolved inputs before looking at any results.
    for case in plan["cases"]:
        base = load_config(plan_path.parent / case["config"])
        for condition in conditions:
            config = deepcopy(base)
            config["coordination"]["mode"] = "requests"
            config["coordination"]["resource_aware"]["enabled"] = condition in (
                "scoring",
                "scoring-handoffs",
                "scoring-deliveries",
                "scripted",
                "scripted-priority",
                "model",
            )
            config["coordination"]["repair_handoffs"] = condition in (
                "handoffs",
                "scoring-handoffs",
                "handoffs-deliveries",
                "scripted",
                "scripted-priority",
                "model",
            )
            config["logistics"]["enabled"] = condition in (
                "deliveries",
                "scoring-deliveries",
                "handoffs-deliveries",
                "scripted",
                "scripted-priority",
                "model",
            )
            config["ai"]["repair_strategy"]["enabled"] = True
            config["ai"]["repair_strategy"]["mode"] = plan.get(
                "strategy_mode", "assignment"
            )
            config["ai"]["repair_strategy"]["controller"] = (
                "scripted" if condition == "scripted-priority" else "model"
            )
            config["ai"]["profiles"]["local_qwen"].update(
                context_size=2048,
                max_tokens=24,
                temperature=0.0,
                timeout=plan["request_seconds"],
            )
            config["evaluation"].update(
                stop_requests_on_error=False,
                full_observations=False,
                timing_policy=plan.get("timing_policy", "paused_checkpoints"),
                inference_delay_seconds=plan.get("inference_delay_seconds", 5.0),
            )
            path = root / f"{case['name']}-{condition}.json"
            path.write_text(json.dumps(config, indent=2) + "\n")
            configs[case["name"], condition] = path
    frozen["config_hashes"] = {
        str(p.relative_to(root)): digest(p) for p in configs.values()
    }
    (root / "protocol.json").write_text(json.dumps(frozen, indent=2) + "\n")
    for case in plan["cases"]:
        for seed in plan["seeds"]:
            # Deterministic alternating order reduces constant warm-cache ordering bias.
            order = conditions if seed % 2 else tuple(reversed(conditions))
            for condition in order:
                if source_hashes() != sources or any(
                    digest(root / p) != h for p, h in frozen["config_hashes"].items()
                ):
                    raise RuntimeError("Source changed after experiment freeze")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    failures.append(
                        dict(
                            case=case["name"],
                            seed=seed,
                            condition=condition,
                            error="suite_deadline",
                        )
                    )
                    continue
                folder = root / f"{case['name']}-{seed}-{condition}"
                budget = min(plan["run_wall_seconds"], remaining)
                cmd = [
                    sys.executable,
                    "-m",
                    "village.evaluation",
                    "--config",
                    str(configs[case["name"], condition]),
                    "--modes",
                    (
                        "hybrid"
                        if condition in ("model", "scripted-priority")
                        else "scripted"
                    ),
                    "--seeds",
                    str(seed),
                    "--duration",
                    str(plan["duration_seconds"]),
                    "--max-model-calls",
                    str(plan["model_calls"]),
                    "--model-timeout",
                    str(plan["request_seconds"]),
                    "--wall-seconds",
                    str(budget),
                    "--suite-seconds",
                    str(budget),
                    "--output",
                    str(folder),
                ]
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=max(0.1, budget + 5),
                    )
                    with (root / "runner.log").open("a", encoding="utf-8") as log:
                        log.write(
                            f"{case['name']} {seed} {condition}\n{result.stdout}\n{result.stderr}\n"
                        )
                    if result.returncode:
                        raise RuntimeError(
                            f"Evaluator exit {result.returncode}: {result.stderr[-300:]}"
                        )
                    summary_path = next(folder.glob("*/summary.json"))
                    report = read_json(summary_path)
                    row = report["runs"][0]
                    trace = next(summary_path.parent.rglob("decisions.jsonl"))
                    row.update(
                        condition=condition, case=case["name"], **repair_audit(trace)
                    )
                    rows.append(row)
                    print(
                        f"{case['name']} seed={seed} {condition}: {row['stop_reason']}; health={row['village_health']:.1f}; calls={row['model_requests']}; productive allocations={row['productive_model_allocations']}",
                        flush=True,
                    )
                except (subprocess.TimeoutExpired, RuntimeError, StopIteration) as exc:
                    failures.append(
                        dict(
                            case=case["name"],
                            seed=seed,
                            condition=condition,
                            error=str(exc),
                        )
                    )
                (root / "summary.json").write_text(
                    json.dumps(
                        dict(
                            protocol=frozen,
                            runs=rows,
                            failures=failures,
                            paired_model_vs_scripted=paired_results(rows),
                            paired_model_vs_scripted_priority=paired_results(
                                rows, "scripted-priority"
                            ),
                        ),
                        indent=2,
                    )
                    + "\n"
                )
    if source_hashes() != sources or any(
        digest(root / p) != h for p, h in frozen["config_hashes"].items()
    ):
        raise RuntimeError("Frozen inputs changed during experiment")
    # Also persist batches whose suite budget expired before a child could start.
    (root / "summary.json").write_text(
        json.dumps(
            dict(
                protocol=frozen,
                runs=rows,
                failures=failures,
                paired_model_vs_scripted=paired_results(rows),
                paired_model_vs_scripted_priority=paired_results(
                    rows, "scripted-priority"
                ),
            ),
            indent=2,
        )
        + "\n"
    )
    fields = [
        "case",
        "seed",
        "condition",
        "stop_reason",
        "completed_horizon",
        "failed",
        "simulated_seconds",
        "village_health",
        "repair_hp_per_wood",
        "repair_hp",
        "repair_wood",
        "travel_villager_seconds",
        "store_travel_villager_seconds",
        "uncovered_threat_gate_seconds",
        "uncovered_threat_fraction",
        "urgent_partial_deliveries",
        "model_requests",
        "productive_model_allocations",
        "productive_priority_plans",
        "model_deferrals",
        "wall_seconds",
        "log_dropped_records",
    ]
    with (root / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f'Report: {root / "summary.json"}', flush=True)
    if (
        failures
        or len(rows) != frozen["expected_runs"]
        or any(
            r["stop_reason"] not in ("duration_reached", "village_destroyed")
            for r in rows
        )
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
