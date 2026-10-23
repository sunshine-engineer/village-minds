"""Bounded per-role repair-allocation diagnostics on explicit controlled fixtures.

File: village/inference_probe.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import json
import math
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .cli import attach_profile, prepare
from .config import get_settings
from .inference import bounded_decision


def fixture(role):
    """Create a controlled damaged-gate world for one requested proposer role.

    Args:
        role: Configured villager role name.

    Returns:
        World, proposer and compact observation tuple.
    """
    from .allocation import strategy_observation
    from .entities import Monster
    from .world import World

    settings = get_settings()["inference_probe"]
    w = World(seed=settings["seed"])
    for gate in list(w.gates)[:2]:
        w.gates[gate] = settings["gate_health"]
        pos = get_settings()["world"]["locations"][gate]
        scale = get_settings()["rules"]["monster_gate_coordinate"] / max(
            abs(v) for v in pos
        )
        w.monsters.append(Monster("probe-" + gate, gate, tuple(v * scale for v in pos)))
    w.store["wood"] = get_settings()["rules"]["repair_wood_cost"] * 2
    bot = next(v for v in w.villagers if v.role == role)
    return w, bot, strategy_observation(w, bot)


def main():
    """Measure per-role schema-valid responses within strict request and suite deadlines.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    settings = prepare(parser)
    parser.add_argument("--output", default="artifacts/inference")
    args = parser.parse_args()
    attach_profile(parser, args)
    if not settings["ai"]["repair_strategy"]["enabled"]:
        parser.error("Enable ai.repair_strategy in the config")
    root = Path(args.output) / (
        "probe-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    root.mkdir(parents=True)
    (root / "config.json").write_text(json.dumps(settings, indent=2))
    options = settings["inference_probe"]
    deadline = time.monotonic() + options["suite_seconds"]
    import os
    import platform
    import sys

    from .validation import source_hashes

    frozen_sources = source_hashes()
    rows = []
    for repeat in range(options["rounds"]):
        for role in options["roles"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            world, bot, observation = fixture(role)
            request_limit = min(options["request_seconds"], remaining)
            response = bounded_decision(
                args.model_profile,
                observation,
                root / "config.json",
                request_limit,
            )
            row = dict(
                role=role,
                round=repeat,
                request_seconds=request_limit,
                within_deadline=response["latency_ms"] <= request_limit * 1000,
                **response,
            )
            row["observation"] = observation
            row["applied"] = response["status"] == "ok" and world.apply(
                bot, response["decision"], source="model"
            )
            row["allocation"] = bool(
                row["applied"] and response["decision"]["action"] == "dispatch_repair"
            )
            row["plan"] = bool(
                row["applied"] and response["decision"]["action"] == "plan_repairs"
            )
            rows.append(row)
            print(
                f"{role} round={repeat}: {response['status']} {response['latency_ms']:.0f}ms; applied={row['applied']}",
                flush=True,
            )
            (root / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    summary = []
    for role in options["roles"]:
        group = [r for r in rows if r["role"] == role]
        latencies = sorted(r["latency_ms"] for r in group)
        summary.append(
            dict(
                role=role,
                attempted=len(group),
                expected=options["rounds"],
                valid_applied=sum(r["applied"] for r in group),
                allocations=sum(r["allocation"] for r in group),
                priority_plans=sum(r["plan"] for r in group),
                valid_in_deadline=sum(
                    r["status"] == "ok" and r["within_deadline"] for r in group
                ),
                timeouts=sum(r["status"] == "timeout" for r in group),
                mean_ms=statistics.mean(latencies) if latencies else None,
                max_ms=max(latencies) if latencies else None,
                p50_ms=statistics.median(latencies) if latencies else None,
                p95_ms=(
                    latencies[math.ceil(0.95 * len(latencies)) - 1]
                    if latencies
                    else None
                ),
            )
        )
    expected = options["rounds"] * len(options["roles"])
    valid = sum(r["status"] == "ok" and r["within_deadline"] for r in rows)
    passed = len(rows) == expected and valid / expected >= options["minimum_valid_rate"]
    if source_hashes() != frozen_sources:
        raise RuntimeError("Frozen probe source changed")
    (root / "summary.json").write_text(
        json.dumps(
            {
                "fixture": "controlled damaged gates, limited wood, no survival benchmark",
                "expected_requests": expected,
                "attempted_requests": len(rows),
                "valid_in_deadline": valid,
                "minimum_valid_rate": options["minimum_valid_rate"],
                "passed": passed,
                "sources": frozen_sources,
                "profile": args.model_profile,
                "host": dict(
                    platform=platform.platform(),
                    processor=platform.processor(),
                    logical_cpus=os.cpu_count(),
                    python=sys.version,
                ),
                "by_role": summary,
                "results": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Report: {root / 'summary.json'}", flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
