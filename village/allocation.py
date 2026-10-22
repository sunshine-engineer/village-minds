"""Repair candidates priced by useful HP, wood, travel and opportunity cost."""

from .config import get_settings
from .navigation import pathfind, distance


def travel_seconds(world, bot, place):
    goal = world.destination(bot, place)
    path = pathfind(bot.position, goal)
    if not path:
        return 0.0 if distance(bot.position, goal) < 1e-9 else None
    points = [bot.position, *path]
    return (
        sum(distance(a, b) for a, b in zip(points, points[1:]))
        / get_settings()["rules"]["villager_speed"]
    )


def repair_features(world, task, bot):
    s = get_settings()["coordination"]["resource_aware"]
    r = get_settings()["rules"]
    p = get_settings()["policy"]
    travel = travel_seconds(world, bot, task["target"])
    if travel is None:
        return None
    hp = world.gates[task["target"]]
    useful = min(
        r["gate_health"] - hp,
        get_settings()["roles"][bot.role].get("repair_amount", r["base_repair_amount"]),
    )
    efficiency = useful / r["repair_wood_cost"]
    threats = world.gate_threats().get(task["target"], 0)
    breach_in = (
        hp / (threats * r["monster_gate_damage"])
        if threats and r["monster_gate_damage"]
        else None
    )
    opportunity = (
        s["guard_opportunity_cost"] if bot.action.startswith("guarding ") else 0.0
    )
    scarcity = (
        s["scarcity_multiplier"]
        if world.store["wood"] <= s["scarce_wood_below"]
        else 1.0
    )
    cost = (
        travel * s["travel_weight"]
        + r["repair_wood_cost"] / max(useful, 1e-9) * s["resource_weight"] * scarcity
        + opportunity
    )
    if breach_in is not None and travel > breach_in:
        cost += s["late_arrival_penalty"]
    return dict(
        travel_seconds=round(travel, 2),
        hp_per_wood=round(efficiency, 2),
        breach_in_seconds=round(breach_in, 2) if breach_in is not None else None,
        cost=cost,
    )


def can_handoff(board, bot, gate):
    """Only lower-priority supply work may be interrupted for a real repair."""
    if bot.action.startswith("guarding ") and board.world.gate_threats().get(
        bot.action.removeprefix("guarding ")
    ):
        return False
    if not board.ready(bot):
        return False
    current = next(
        (
            t
            for t in board.tasks
            if t["status"] in ("offered", "accepted") and t["assigned_to"] == bot.name
        ),
        None,
    )
    if current is None:
        return True
    if not board.settings["repair_handoffs"] or current["kind"] not in ("wood", "food"):
        return False
    s = board.settings["resource_aware"]
    return (
        board.world.store["wood"] >= get_settings()["rules"]["repair_wood_cost"]
        and board.world.gates[gate] <= s["handoff_gate_health"]
    )


def repair_candidates(board, proposer=None):
    w = board.world
    s = get_settings()["ai"]["repair_strategy"]
    candidates = []
    if (
        not s["enabled"]
        or w.store["wood"] < get_settings()["rules"]["repair_wood_cost"]
    ):
        return candidates
    for gate, hp in w.gates.items():
        if (
            hp
            >= get_settings()["rules"]["gate_health"]
            - get_settings()["policy"]["repair_missing_health"]
        ):
            continue
        task = {"kind": "repair", "target": gate}
        active = next(
            (
                t
                for t in board.tasks
                if t["kind"] == "repair"
                and t["target"] == gate
                and t["status"] in ("open", "offered", "accepted")
            ),
            None,
        )
        if (
            proposer is not None
            and active is None
            and f"repair:{gate}" not in board.actions(proposer).get("request_help", [])
        ):
            continue
        for bot in board.living():
            if active and active["assigned_to"] == bot.name:
                continue
            if bot.action.startswith("guarding ") and w.gate_threats().get(
                bot.action.removeprefix("guarding ")
            ):
                continue
            if not can_handoff(board, bot, gate):
                continue
            features = repair_features(w, task, bot)
            if features is None:
                continue
            current = next(
                (v for v in w.villagers if active and v.name == active["assigned_to"]),
                None,
            )
            current_features = repair_features(w, task, current) if current else None
            candidates.append(
                dict(
                    current_owner=current.name if current else None,
                    replacement_saves_cost=(
                        round(current_features["cost"] - features["cost"], 2)
                        if current_features
                        else None
                    ),
                    target=f"{gate}:{bot.name}",
                    gate=gate,
                    actor=bot.name,
                    role=bot.role,
                    **features,
                )
            )
    candidates.sort(key=lambda c: (w.gates[c["gate"]], c["cost"], c["target"]))
    return candidates[: s["max_choices"]]


def strategy_observation(world, bot, lessons=()):
    candidates = repair_candidates(world.task_board, bot)
    choices = [
        dict(id=f"r{i}", **{k: v for k, v in c.items() if k != "cost"})
        for i, c in enumerate(candidates)
    ]
    return dict(
        name=bot.name,
        role=bot.role,
        personality=bot.personality,
        decision_layer="repair_allocation",
        wood=world.store["wood"],
        choices=choices,
        lessons=list(lessons)[: get_settings()["ai"]["repair_strategy"]["max_lessons"]],
    )
