"""Causal gate-contention fixtures using ordinary world physics and local routines.

One recovering repairer, two open jobs and scarce wood. This isolates allocation;
it does not establish full-village survival or production model reliability.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import uuid

from .config import configure, get_settings, read_json
from .inference import bounded_decision
from .validation import source_hashes

CONDITIONS = ("baseline", "scripted", "model", "adverse")


def validate_plan(plan):
    required = {
        "name",
        "config",
        "seeds",
        "excluded_seeds",
        "conditions",
        "duration_seconds",
        "step_seconds",
        "decision_delay_seconds",
        "request_seconds",
        "run_wall_seconds",
        "suite_seconds",
        "wood",
        "food",
        "worker_release_seconds",
        "resting_energy",
        "position_jitter",
        "cases",
        "rotate_gates",
        "position_search_radius",
    }
    if set(plan) != required:
        raise ValueError("Invalid contention protocol fields")
    if (
        not plan["seeds"]
        or any(type(s) is not int or s < 0 for s in plan["seeds"])
        or len(set(plan["seeds"])) != len(plan["seeds"])
        or set(plan["seeds"]) & set(plan["excluded_seeds"])
    ):
        raise ValueError("Invalid, duplicate or excluded seeds")
    if (
        not plan["conditions"]
        or len(set(plan["conditions"])) != len(plan["conditions"])
        or any(c not in CONDITIONS for c in plan["conditions"])
    ):
        raise ValueError("Invalid conditions")
    for key in (
        "duration_seconds",
        "step_seconds",
        "request_seconds",
        "run_wall_seconds",
        "suite_seconds",
        "worker_release_seconds",
    ):
        if (
            type(plan[key]) not in (float, int)
            or not math.isfinite(plan[key])
            or plan[key] <= 0
        ):
            raise ValueError(f"Invalid {key}")
    for key in (
        "decision_delay_seconds",
        "resting_energy",
        "position_jitter",
        "position_search_radius",
    ):
        if (
            type(plan[key]) not in (float, int)
            or not math.isfinite(plan[key])
            or plan[key] < 0
        ):
            raise ValueError(f"Invalid {key}")
    if any(type(plan[k]) is not int or plan[k] < 0 for k in ("wood", "food")):
        raise ValueError("Invalid fixture inventory")
    if plan["worker_release_seconds"] >= plan["duration_seconds"] or not plan["cases"]:
        raise ValueError("Fixture must allow work after recovery")
    settings = get_settings()
    if plan["step_seconds"] > settings["runtime"]["max_step_seconds"]:
        raise ValueError("Fixture step exceeds world maximum")
    initial = (
        settings["policy"]["rest_until_energy"]
        - plan["worker_release_seconds"] * settings["rules"]["rest_energy_per_second"]
    )
    if (
        not 0 <= initial <= settings["rules"]["villager_max"]
        or not 0 <= plan["resting_energy"] < settings["policy"]["rest_until_energy"]
    ):
        raise ValueError("Invalid recovery window")
    if type(plan["rotate_gates"]) is not bool:
        raise ValueError("rotate_gates must be boolean")
    names = []
    for case in plan["cases"]:
        if (
            set(case) != {"name", "worker_position", "gates", "threats", "primary_gate"}
            or case["name"] in names
        ):
            raise ValueError("Invalid or duplicate case")
        names.append(case["name"])
        if (
            case["primary_gate"] not in case["gates"]
            or len(case["gates"]) < 2
            or set(case["threats"]) != set(case["gates"])
        ):
            raise ValueError("A contention case needs competing gates and threats")
        from .map_data import GATES

        if any(g not in GATES for g in case["gates"]):
            raise ValueError("Unknown gate")
        if any(
            type(hp) not in (float, int)
            or not math.isfinite(hp)
            or not 0 < hp < settings["rules"]["gate_health"]
            for hp in case["gates"].values()
        ):
            raise ValueError("Invalid gate health")
        if any(type(n) is not int or n < 1 for n in case["threats"].values()):
            raise ValueError("Invalid threat count")
        if len(case["worker_position"]) != 2 or any(
            type(v) not in (float, int) or not math.isfinite(v)
            for v in case["worker_position"]
        ):
            raise ValueError("Invalid worker position")


def oriented_case(case, seed, enabled=True):
    """Rotate both gate identities and positions so a fixed gate name cannot win."""
    from .map_data import GATES

    turns = seed % 4 if enabled else 0

    def rotate(point):
        x, y = point
        for _ in range(turns):
            x, y = -y, x
        return [x, y]

    by_point = {tuple(point): name for name, point in GATES.items()}
    mapping = {gate: by_point[tuple(rotate(point))] for gate, point in GATES.items()}
    result = deepcopy(case)
    result["worker_position"] = rotate(case["worker_position"])
    result["gates"] = {mapping[g]: value for g, value in case["gates"].items()}
    result["threats"] = {mapping[g]: value for g, value in case["threats"].items()}
    result["primary_gate"] = mapping[case["primary_gate"]]
    return result


def fixture(plan, case, seed):
    from .world import World
    from .entities import Monster
    from .navigation import walkable, work_point
    from .map_data import GATES

    w = World(seed=seed)
    settings = get_settings()
    worker = next(v for v in w.villagers if v.role == "worker")
    for bot in w.villagers:
        bot.energy = plan["resting_energy"]
        bot.action = "resting"
        bot.position = tuple(settings["world"]["locations"]["rest"])
    worker.position = tuple(
        v + w.rng.uniform(-plan["position_jitter"], plan["position_jitter"])
        for v in case["worker_position"]
    )
    if not walkable(*worker.position):
        point = work_point(
            tuple(settings["world"]["locations"]["rest"]),
            worker.position,
            plan["position_search_radius"],
        )
        if point is None:
            raise ValueError(
                "No reachable fixture position within configured search radius"
            )
        worker.position = point
    worker.energy = (
        settings["policy"]["rest_until_energy"]
        - plan["worker_release_seconds"] * settings["rules"]["rest_energy_per_second"]
    )
    w.store.update(wood=plan["wood"], food=plan["food"])
    w.gates.update(case["gates"])
    for gate, n in case["threats"].items():
        x, y = GATES[gate]
        scale = settings["rules"]["monster_gate_coordinate"] / max(abs(x), abs(y))
        for _ in range(n):
            w.monsters.append(
                Monster(f"fixture-{w.next_monster_id}", gate, (x * scale, y * scale))
            )
            w.next_monster_id += 1
    return w, worker


def run_case(
    plan,
    case,
    seed,
    condition,
    role,
    folder,
    *,
    request=bounded_decision,
    deadline=math.inf,
):
    from .allocation import strategy_observation
    from .brains import BrainScheduler
    from .models import resolve_profile
    from .telemetry import DecisionLog
    from .persistence import snapshot

    w, worker = fixture(plan, case, seed)
    folder.mkdir(parents=True, exist_ok=True)
    logger = DecisionLog(
        folder / "decisions.jsonl",
        max_bytes=get_settings()["telemetry"]["max_bytes"],
        full_observations=True,
    )
    try:
        w.decision_log = logger
        brains = BrainScheduler(w, "", "", demo=True)
        profile = resolve_profile()
        bot = next(v for v in w.villagers if v.role == role)
        initial = snapshot(w)
        observation = strategy_observation(w, bot)
        sent_at, revision = w.time, bot.revision
        response = None
        started = time.monotonic()
        deadline = min(deadline, started + plan["run_wall_seconds"])
        if condition == "model":
            response = request(
                profile,
                observation,
                get_settings(),
                min(plan["request_seconds"], max(0, deadline - time.monotonic())),
            )
            delay = response["latency_ms"] / 1000
        else:
            delay = plan["decision_delay_seconds"]
            if condition in ("scripted", "adverse"):
                candidate = observation["choices"][0 if condition == "scripted" else -1]
                response = dict(
                    status="ok",
                    latency_ms=0.0,
                    decision=dict(action="plan_repairs", target=candidate["target"]),
                )
        selection = None
        first_owner = None
        breaches = set()
        before_gates = w.gates.copy()
        applied = False
        outcome = "no_plan"
        stop_reason = "duration_reached"

        def step():
            nonlocal first_owner, before_gates
            dt = min(plan["step_seconds"], plan["duration_seconds"] - w.time)
            w.tick(dt)
            brains.tick()
            breaches.update(
                g for g, hp in w.gates.items() if hp <= 0 and before_gates[g] > 0
            )
            before_gates = w.gates.copy()
            if first_owner is None:
                first_owner = next(
                    (
                        dict(gate=t["target"], actor=t["assigned_to"], at=w.time)
                        for t in w.task_board.tasks
                        if t["kind"] == "repair"
                        and t["assigned_to"] == worker.name
                        and t["status"] in ("offered", "accepted")
                    ),
                    None,
                )

        logger.record(
            "contention_start",
            0,
            seed=seed,
            case=case,
            condition=condition,
            role=role,
            observation=observation,
        )
        while w.time < plan["duration_seconds"] - 1e-9 and not w.failed:
            if time.monotonic() >= deadline:
                stop_reason = "wall_time_limit"
                break
            if not applied and w.time + 1e-9 >= delay:
                applied = True
                if response is not None:
                    if response["status"] == "ok":
                        selection = response["decision"].get("target")
                        outcome = brains.consume_decision(
                            w.villagers.index(bot),
                            revision,
                            sent_at,
                            response["decision"],
                            observation=observation,
                            latency_ms=response["latency_ms"],
                            profile=profile,
                        )
                    else:
                        outcome = response["status"]
            step()
        if w.failed:
            stop_reason = "village_destroyed"
        row = dict(
            case=case["name"],
            seed=seed,
            condition=condition,
            role=role,
            selected_gate=selection,
            first_repair_owner=first_owner,
            primary_gate=case["primary_gate"],
            primary_gate_breached=case["primary_gate"] in breaches,
            breached_gates=sorted(breaches),
            final_gates=w.gates,
            wood=w.store["wood"],
            repairs=sum(v.contributions["repairs"] for v in w.villagers),
            simulated_seconds=w.time,
            stop_reason=stop_reason,
            wall_seconds=time.monotonic() - started,
            response=response,
            outcome=outcome,
            applied_before_first_claim=bool(
                response is not None
                and outcome == "accepted"
                and first_owner
                and delay <= first_owner["at"]
            ),
            initial=initial,
            log_dropped_records=logger.dropped,
        )
        (folder / "result.json").write_text(json.dumps(row, indent=2) + "\n")
        return row
    finally:
        logger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--output", default="artifacts/contention", type=Path)
    args = parser.parse_args()
    plan = read_json(args.plan)
    configure(args.plan.resolve().parent / plan["config"])
    validate_plan(plan)
    root = args.output / (
        plan["name"]
        + "-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    root.mkdir(parents=True)
    sources = source_hashes()
    protocol = dict(
        plan=plan,
        sources=sources,
        settings=deepcopy(get_settings()),
        expected_runs=len(plan["cases"]) * len(plan["seeds"]) * len(plan["conditions"]),
    )
    (root / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    deadline = time.monotonic() + plan["suite_seconds"]
    rows = []
    failures = []
    roles = get_settings()["evaluation"]["role_order"]
    for case_index, case in enumerate(plan["cases"]):
        for i, seed in enumerate(plan["seeds"]):
            for condition in (
                plan["conditions"] if i % 2 == 0 else list(reversed(plan["conditions"]))
            ):
                if source_hashes() != sources:
                    raise RuntimeError("Frozen source changed")
                if time.monotonic() >= deadline:
                    failures.append(
                        dict(
                            case=case["name"],
                            seed=seed,
                            condition=condition,
                            error="suite_deadline",
                        )
                    )
                else:
                    try:
                        row = run_case(
                            plan,
                            oriented_case(case, seed, plan["rotate_gates"]),
                            seed,
                            condition,
                            roles[(i + case_index) % len(roles)],
                            root / f"{case['name']}-{seed}-{condition}",
                            deadline=deadline,
                        )
                        rows.append(row)
                        print(
                            f"{case['name']} {seed} {condition}: chosen={row['selected_gate']} owner={row['first_repair_owner']} breached={row['primary_gate_breached']} outcome={row['outcome']}",
                            flush=True,
                        )
                    except Exception as exc:
                        failures.append(
                            dict(
                                case=case["name"],
                                seed=seed,
                                condition=condition,
                                error=f"{type(exc).__name__}: {exc}",
                            )
                        )
                (root / "summary.json").write_text(
                    json.dumps(
                        dict(protocol=protocol, runs=rows, failures=failures), indent=2
                    )
                    + "\n"
                )
    print(f'Report: {root / "summary.json"}', flush=True)
    if (
        failures
        or len(rows) != protocol["expected_runs"]
        or any(
            r["stop_reason"] == "wall_time_limit" or r["log_dropped_records"]
            for r in rows
        )
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
