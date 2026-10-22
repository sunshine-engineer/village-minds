"""Bounded per-role repair-allocation diagnostics on explicit controlled fixtures."""

from copy import deepcopy
from datetime import datetime, timezone
import argparse, json, time, uuid, statistics, math
from pathlib import Path
from .cli import prepare, attach_profile
from .config import get_settings
from .inference import bounded_decision


def fixture(role):
    from .world import World
    from .entities import Monster
    from .allocation import strategy_observation

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
    rows = []
    for repeat in range(options["rounds"]):
        for role in options["roles"]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            world, bot, observation = fixture(role)
            response = bounded_decision(
                args.model_profile,
                observation,
                root / "config.json",
                min(options["request_seconds"], remaining),
            )
            row = dict(role=role, round=repeat, **response)
            row["observation"] = observation
            row["applied"] = response["status"] == "ok" and world.apply(
                bot, response["decision"], source="model"
            )
            row["allocation"] = bool(
                row["applied"] and response["decision"]["action"] == "dispatch_repair"
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
    (root / "summary.json").write_text(
        json.dumps(
            {
                "fixture": "controlled damaged gates, limited wood, no survival benchmark",
                "by_role": summary,
                "results": rows,
            },
            indent=2,
        )
        + "\n"
    )
    print(f'Report: {root / "summary.json"}', flush=True)


if __name__ == "__main__":
    main()
