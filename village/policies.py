"""Default role/needs policy. Register alternative policies through extensions."""

from .config import get_settings
from .map_data import LOCATIONS, GATES, GATE_MAX
from .navigation import distance

P = get_settings()["policy"]
R = get_settings()["rules"]


def default_policy(self, bot):
    """Fast needs/role policy, always active and also supplied as model advice."""
    if not bot.alive or self.failed:
        return None

    def go(place, action, **fields):
        if distance(bot.position, LOCATIONS[place]) < (
            R["crop_radius"] if place == "farm" else P["arrival_radius"]
        ):
            return {"action": action, **fields}
        if bot.path and bot.action == f"walking to {place}":
            return None
        return {"action": "move", "target": place}

    if bot.hunger > P["eat_above_hunger"]:
        if bot.supplies >= R["eat_food_cost"] or (
            distance(bot.position, LOCATIONS["storehouse"]) < R["store_radius"]
            and self.store["food"] >= R["eat_food_cost"]
        ):
            return {"action": "eat"}
        if self.store["food"] >= R["eat_food_cost"]:
            return go("storehouse", "eat")
    if bot.energy < P["rest_below_energy"]:
        return {"action": "rest"}
    if bot.action == "resting" and bot.energy < P["rest_until_energy"]:
        return None
    threats = self.gate_threats()
    if bot.role == "soldier":
        if threats:
            # Spread soldiers across simultaneous threats.
            ordered = sorted(threats, key=lambda name: (-threats[name], name))
            target = ordered[self.role_index(bot) % len(ordered)]
        else:
            target = P["soldier_gates"][self.role_index(bot) % len(P["soldier_gates"])]
        if bot.action == f"guarding {target}":
            return None
        return {"action": "guard", "target": target}
    if (
        bot.supplies >= P["deposit_at_inventory"]
        or bot.wood >= P["deposit_at_inventory"]
    ):
        return go("storehouse", "deposit")
    if bot.role == "worker":
        damaged = min(self.gates, key=self.gates.get)
        if (
            self.gates[damaged] < GATE_MAX - P["repair_missing_health"]
            and self.store["wood"] >= R["repair_wood_cost"]
        ):
            return go(damaged, "repair", target=damaged)
        if self.store["wood"] < P["wood_target"]:
            return go("orchard", "gather")
    if get_settings()["roles"][bot.role].get(
        "can_rally", False
    ) and "rally" in self.available_actions(bot):
        return {"action": "rally"}
    if any(c.stage == "ripe" for c in self.crops):
        return go("farm", "harvest")
    if any(c.stage == "empty" for c in self.crops):
        return go("farm", "farm")
    if bot.supplies or bot.wood:
        return go("storehouse", "deposit")
    if bot.energy < P["idle_rest_below_energy"]:
        return {"action": "rest"}
    return None
