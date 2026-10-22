"""Urgent partial deliveries and observable movement without changing abilities."""

from .config import get_settings


def delivery_reason(world, bot):
    s = get_settings()["logistics"]
    if not s["enabled"]:
        return None
    if bot.wood and world.store["wood"] <= s["urgent_wood_below"]:
        if any(
            hp
            < get_settings()["rules"]["gate_health"]
            - get_settings()["policy"]["repair_missing_health"]
            for hp in world.gates.values()
        ):
            return "repair_wood_shortage"
        if world.resources["orchard"] == 0:
            return "orchard_exhausted"
    if bot.supplies and world.store["food"] <= s["urgent_food_below"]:
        if any(
            v.alive and v.hunger >= get_settings()["policy"]["eat_above_hunger"]
            for v in world.villagers
            if v is not bot
        ):
            return "hungry_neighbors"
    return None


def delivery_intent(world, bot):
    if not delivery_reason(world, bot):
        return None
    p = get_settings()["policy"]
    if (
        bot.hunger >= p["eat_above_hunger"]
        or bot.energy < p["rest_below_energy"]
        or (bot.action == "resting" and bot.energy < p["rest_until_energy"])
    ):
        return None
    # A defender currently attacking a monster must not abandon a gate simply
    # because they carry incidental supplies.
    if bot.action.startswith("guarding ") and world.gate_threats().get(
        bot.action.removeprefix("guarding ")
    ):
        return None
    if world.time < bot.work_at:
        return False
    if "deposit" in world.available_actions(bot):
        return {"action": "deposit"}
    if bot.path and bot.action == "walking to storehouse":
        return False
    return {"action": "move", "target": "storehouse"}
