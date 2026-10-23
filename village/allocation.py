"""Repair candidates priced by useful HP, wood, travel and opportunity cost.

File: village/allocation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from .config import get_settings
from .navigation import distance, pathfind


def travel_seconds(world, bot, place):
    """Estimate a villager's navigation time to a service or gate.

    Args:
        world: Authoritative simulation world used by this operation.
        bot: Villager whose current state or work is being considered.
        place: Configured service or gate name.

    Returns:
        Travel seconds, or None when the destination is unreachable.
    """
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
    """Price a repair using useful HP, wood scarcity, travel and guard opportunity cost.

    Args:
        world: Authoritative simulation world used by this operation.
        task: Task-board job dictionary with kind, target and ownership state.
        bot: Villager whose current state or work is being considered.

    Returns:
        Feature dictionary, or None for an unreachable repair.
    """
    s = get_settings()["coordination"]["resource_aware"]
    r = get_settings()["rules"]
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
    """Only lower-priority supply work may be interrupted for a real repair.

    Args:
        board: Task board providing current jobs, ownership and coordination settings.
        bot: Villager whose current state or work is being considered.
        gate: Configured cardinal gate name.

    Returns:
        Whether the proposed helper can take the repair.
    """
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
    """List feasible recipient/gate choices, respecting ownership and proposer board constraints.

    Args:
        board: Task board providing current jobs, ownership and coordination settings.
        proposer: Optional villager proposing a strategic repair.

    Returns:
        Bounded, deterministically ranked candidate dictionaries.
    """
    w = board.world
    s = get_settings()["ai"]["repair_strategy"]
    if s["enabled"] and s["mode"] == "priority_plan":
        return priority_candidates(board)
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
    """Build the compact repair-planning observation supplied to a model.

    Args:
        world: Authoritative simulation world used by this operation.
        bot: Villager whose current state or work is being considered.
        lessons: Prior factual lesson strings, bounded by configuration.

    Returns:
        Observation dictionary with choices and bounded lessons.
    """
    candidates = repair_candidates(world.task_board, bot)
    choices = [
        dict(id=f"r{i}", **{k: v for k, v in c.items() if k != "cost"})
        for i, c in enumerate(candidates)
    ]
    return dict(
        name=bot.name,
        role=bot.role,
        personality=bot.personality,
        decision_layer=(
            "repair_priority"
            if get_settings()["ai"]["repair_strategy"]["mode"] == "priority_plan"
            else "repair_allocation"
        ),
        wood=world.store["wood"],
        choices=choices,
        lessons=list(lessons)[: get_settings()["ai"]["repair_strategy"]["max_lessons"]],
    )


def priority_candidates(board):
    """Gate-level plans remain useful when helpers are busy or wood is absent.

    Args:
        board: Task board providing current jobs, ownership and coordination settings.

    Returns:
        Bounded gate candidate dictionaries ordered by urgency.
    """
    w = board.world
    settings = get_settings()
    if (
        not settings["ai"]["repair_strategy"]["enabled"]
        or not board.settings["enabled"]
        or board.mode == "independent"
    ):
        return []
    choices = []
    for gate, hp in w.gates.items():
        if (
            hp
            >= settings["rules"]["gate_health"]
            - settings["policy"]["repair_missing_health"]
        ):
            continue
        features = [
            repair_features(w, dict(kind="repair", target=gate), bot)
            for bot in board.living()
        ]
        features = [f for f in features if f is not None]
        if not features:
            continue
        best = min(features, key=lambda f: f["cost"])
        choices.append(
            dict(
                target=gate,
                gate=gate,
                health=hp,
                threats=w.gate_threats().get(gate, 0),
                **best,
            )
        )
    choices.sort(
        key=lambda c: (
            c["breach_in_seconds"] is None,
            c["breach_in_seconds"] or 0,
            c["health"],
            c["cost"],
            c["gate"],
        )
    )
    return choices[: settings["ai"]["repair_strategy"]["max_choices"]]
