"""Default role/needs policy. Register alternative policies through extensions.

File: village/policies.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from .config import get_settings
from .map_data import GATE_MAX
from .map_data import GATES as GATES
from .map_data import LOCATIONS as LOCATIONS
from .navigation import distance as distance

P = get_settings()["policy"]
R = get_settings()["rules"]


def default_policy(self, bot):
    """Fast needs/role policy, always active and also supplied as model advice.

    Args:
        bot: Villager whose current state or work is being considered.

    Returns:
        Local intent dictionary, or None when the current order can continue.
    """
    if not bot.alive or self.failed:
        return None

    available = self.available_actions(bot)

    def go(place, action, **fields):
        """Choose a legal service action or movement toward a reachable work point.

        Args:
            place: Configured service or gate name.
            action: Registered action name.
            **fields: Additional structured intent fields.

        Returns:
            Intent dictionary, or None when the current work order should continue.
        """
        if fields.get("target", "") in available.get(action, []):
            return {"action": action, **fields}
        if self.time < bot.work_at:
            return None
        if bot.path and bot.action == f"walking to {place}":
            return None
        return {"action": "move", "target": place}

    if bot.hunger > P["eat_above_hunger"]:
        if "eat" in available:
            return {"action": "eat"}
        if self.time < bot.work_at:
            return None
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
    if self.time < bot.work_at:
        return None
    if "harvest" in available:
        return {"action": "harvest"}
    if "farm" in available:
        return {"action": "farm"}
    if any(c.stage in ("ripe", "empty") for c in self.crops):
        if bot.path and bot.action == "walking to farm":
            return None
        if self.crop_destination(bot) is not None:
            return {"action": "move", "target": "farm"}
    if bot.supplies or bot.wood:
        return go("storehouse", "deposit")
    if bot.energy < P["idle_rest_below_energy"]:
        return {"action": "rest"}
    return None
