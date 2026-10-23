"""Example configurable action with validated, persistent cooldown state.

File: village/plugins/encourage.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import math

from ..config import get_settings
from ..navigation import distance


def register(registry):
    """Validate example settings and register its action and persistent cooldown state.

    Args:
        registry: Trusted extension registry receiving this plugin's hooks.

    Returns:
        None; adds hooks to the trusted extension registry.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    settings = get_settings()
    options = settings["extension_settings"].get("encourage", {})
    if set(options) != {"energy_cost", "energy_restore", "cooldown_seconds"}:
        raise ValueError(
            "encourage requires energy_cost, energy_restore and cooldown_seconds"
        )
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or v <= 0
        for v in options.values()
    ):
        raise ValueError("encourage settings must be positive finite numbers")

    def restore(saved):
        """Validate per-villager example cooldown timestamps before restoring state.

        Args:
            saved: Saved JSON-compatible state to validate before use.

        Returns:
            Independent cooldown dictionary.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
        names = {bot["name"] for bot in settings["world"]["cast"]}
        if not isinstance(saved, dict) or set(saved) - names:
            raise ValueError("Invalid encourage cooldown identities")
        for time in saved.values():
            if (
                isinstance(time, bool)
                or not isinstance(time, (int, float))
                or not math.isfinite(time)
                or time < 0
            ):
                raise ValueError("Invalid encourage cooldown time")
        return saved.copy()

    def available(world, bot):
        """List nearby living recipients whose energy can benefit from encouragement.

        Args:
            world: Authoritative simulation world used by this operation.
            bot: Villager whose current state or work is being considered.

        Returns:
            Legal recipient names, or an empty list when unavailable.
        """
        if (
            not bot.alive
            or world.failed
            or bot.energy < options["energy_cost"]
            or world.time < world.extension_state["encourage"].get(bot.name, 0)
        ):
            return []
        return [
            other.name
            for other in world.villagers
            if other is not bot
            and other.alive
            and other.energy < settings["rules"]["villager_max"]
            and distance(bot.position, other.position) <= settings["world"]["hearing"]
        ]

    def execute(world, bot, decision):
        """Spend actor energy, restore recipient energy and start the example cooldown.

        Args:
            world: Authoritative simulation world used by this operation.
            bot: Villager whose current state or work is being considered.
            decision: Proposed structured action with optional target/dialogue fields.

        Returns:
            True after applying the validated example effect.
        """
        target = next(v for v in world.villagers if v.name == decision["target"])
        bot.energy -= options["energy_cost"]
        target.energy = min(
            settings["rules"]["villager_max"], target.energy + options["energy_restore"]
        )
        world.extension_state["encourage"][bot.name] = (
            world.time + options["cooldown_seconds"]
        )
        world.say(
            bot, f"{target.name}, keep going. We can protect the village together."
        )
        return True

    registry.register_state("encourage", create=dict, restore=restore)
    registry.register_action("encourage", available=available, execute=execute)
