"""Crop, resource, combat, wave and failure rules.

File: village/survival.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from .config import get_settings
from .entities import Crop as Crop
from .entities import Monster
from .map_data import CROP_GROW_SECONDS, GATE_MAX, GATES, HEARING, LOCATIONS, SIGHT
from .navigation import distance, pathfind

S = get_settings()
R, P, W = S["rules"], S["policy"], S["world"]


class SurvivalRules:
    """Simulation-only farming, resources, combat, monster waves and failure mechanics."""

    def local_crop(self, bot, stage):
        """Find the nearest plot in a required stage within the actor's work radius.

        Args:
            bot: Villager whose current state or work is being considered.
            stage: Required crop stage.

        Returns:
            Matching Crop, or None when no local plot is usable.
        """
        return next(
            (
                c
                for c in sorted(
                    self.crops, key=lambda c: distance(bot.position, c.position)
                )
                if c.stage == stage
                and distance(bot.position, c.position) < R["crop_radius"]
            ),
            None,
        )

    def can_gather(self, bot):
        """Check orchard distance, remaining wood, energy and work cooldown.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Whether wood gathering is legal now.
        """
        return (
            distance(bot.position, LOCATIONS["orchard"]) < R["gather_radius"]
            and self.resources["orchard"] > 0
            and bot.energy >= R["gather_energy"]
        )

    def available_actions(self, bot):
        """List currently legal survival actions and their valid targets.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Action/target mapping; empty for dead actors or a failed world.
        """
        if self.failed or not bot.alive:
            return {}
        actions = {
            "move": list(LOCATIONS)
            + [
                v.name
                for v in self.villagers
                if v is not bot
                and v.alive
                and distance(v.position, bot.position) <= SIGHT
            ],
            "guard": list(GATES),
        }
        partners = [
            v.name
            for v in self.villagers
            if v is not bot
            and v.alive
            and distance(v.position, bot.position) <= HEARING
        ]
        if partners:
            actions["talk"] = partners
        if bot.energy < R["rest_available_below"]:
            actions["rest"] = [""]
        if self.time >= bot.work_at:
            if bot.energy >= R["plant_energy"] and self.local_crop(bot, "empty"):
                actions["farm"] = [""]
            if bot.energy >= R["harvest_energy"] and self.local_crop(bot, "ripe"):
                actions["harvest"] = [""]
            if self.can_gather(bot):
                actions["gather"] = [""]
            at_store = (
                distance(bot.position, LOCATIONS["storehouse"]) < R["store_radius"]
            )
            if at_store and (bot.supplies or bot.wood):
                actions["deposit"] = [""]
            if (
                bot.supplies >= R["eat_food_cost"]
                or (at_store and self.store["food"] >= R["eat_food_cost"])
            ) and (
                bot.hunger >= R["eat_min_hunger"]
                or bot.energy < R["eat_energy_threshold"]
                or bot.health < R["eat_health_threshold"]
            ):
                actions["eat"] = [""]
            repairs = [
                name
                for name, pos in GATES.items()
                if distance(bot.position, pos) < R["repair_radius"]
                and self.gates[name] < GATE_MAX
                and self.store["wood"] >= R["repair_wood_cost"]
                and bot.energy >= R["repair_energy"]
            ]
            if repairs:
                actions["repair"] = repairs
        attacks = [
            m.id
            for m in self.monsters
            if m.health > 0
            and distance(bot.position, m.position) <= R["attack_range"]
            and bot.energy >= R["attack_energy"]
            and self.time >= bot.attack_at
        ]
        if attacks:
            actions["attack"] = attacks
        if (
            S["roles"][bot.role].get("can_rally", False)
            and self.time >= bot.rally_at
            and bot.energy >= R["rally_energy"]
            and self.store["food"] >= R["rally_food_cost"]
            and any(
                v is not bot
                and v.alive
                and distance(v.position, bot.position) <= R["rally_radius"]
                and (
                    v.energy < R["rally_energy_threshold"]
                    or v.health < R["rally_health_threshold"]
                )
                for v in self.villagers
            )
        ):
            actions["rally"] = [""]
        actions.update(self.task_board.actions(bot))
        for name, hook in self.extensions.actions.items():
            targets = hook.available(self, bot)
            if targets:
                actions[name] = targets
        return actions

    def survival_action(self, bot, decision):
        """Apply resource, farm, repair, guard, rally or attack mechanics after validation.

        Args:
            bot: Villager whose current state or work is being considered.
            decision: Proposed structured action with optional target/dialogue fields.

        Returns:
            Whether the action succeeded.
        """
        action, target = decision.get("action"), decision.get("target", "")
        allowed = self.available_actions(bot)
        if action not in allowed or target not in allowed[action]:
            return False
        if action == "guard":
            bot.path = pathfind(bot.position, self.destination(bot, target))
            bot.action = f"guarding {target}"
            return True
        if action == "attack":
            monster = next(m for m in self.monsters if m.id == target)
            return self.strike(bot, monster)
        bot.path.clear()
        if action == "farm":
            crop = self.local_crop(bot, "empty")
            crop.stage, crop.age = "growing", 0
            bot.energy -= R["plant_energy"]
            bot.contributions["planted"] += 1
            bot.action = "planting crops"
        elif action == "harvest":
            crop = self.local_crop(bot, "ripe")
            crop.stage, crop.age = "empty", 0
            food = S["roles"][bot.role].get("harvest_yield", R["base_harvest_yield"])
            bot.supplies += food
            bot.energy -= R["harvest_energy"]
            bot.contributions["harvested"] += food
            bot.action = "harvesting"
            self.log(f"{bot.name} harvested {food} food; deliver it to the storehouse.")
        elif action == "deposit":
            for resource, amount in (("food", bot.supplies), ("wood", bot.wood)):
                self.store[resource] += amount
                bot.contributions["deposited_" + resource] += amount
            self.log(f"{bot.name} shared {bot.supplies} food and {bot.wood} wood.")
            bot.supplies = bot.wood = 0
            bot.action = "depositing supplies"
        elif action == "eat":
            if bot.supplies >= R["eat_food_cost"]:
                bot.supplies -= R["eat_food_cost"]
            else:
                self.store["food"] -= R["eat_food_cost"]
            bot.hunger = max(0, bot.hunger - R["eat_hunger_restore"])
            bot.energy = min(R["villager_max"], bot.energy + R["eat_energy_restore"])
            bot.health = min(R["villager_max"], bot.health + R["eat_health_restore"])
            bot.action = "eating"
        elif action == "repair":
            self.store["wood"] -= R["repair_wood_cost"]
            self.gates[target] = min(
                GATE_MAX,
                self.gates[target]
                + S["roles"][bot.role].get("repair_amount", R["base_repair_amount"]),
            )
            bot.energy -= R["repair_energy"]
            bot.contributions["repairs"] += 1
            bot.action = f"repairing {target}"
        elif action == "rally":
            self.store["food"] -= R["rally_food_cost"]
            bot.energy -= R["rally_energy"]
            for other in self.villagers:
                if (
                    other is not bot
                    and other.alive
                    and distance(bot.position, other.position) <= R["rally_radius"]
                ):
                    other.energy = min(
                        R["villager_max"], other.energy + R["rally_energy_restore"]
                    )
                    other.health = min(
                        R["villager_max"], other.health + R["rally_health_restore"]
                    )
                    other.memory.append(
                        f"{bot.name} rallied us: share food, repair gates, and defend together."
                    )
            bot.rally_at = self.time + R["rally_cooldown"]
            bot.contributions["rallies"] += 1
            bot.action = "rallying villagers"
        bot.work_at = self.time + R["work_cooldown"]
        bot.memory.append(
            f"I chose {action}. Village health {int(self.village_health)}, shared food {self.store['food']}."
        )
        return True

    def gate_threats(self):
        """Count living monsters assigned to each currently threatened gate.

        Returns:
            Gate-name to living-monster-count mapping.
        """
        return {
            name: sum(m.health > 0 and m.gate == name for m in self.monsters)
            for name in GATES
            if any(m.health > 0 and m.gate == name for m in self.monsters)
        }

    def strike(self, bot, monster):
        """Apply a legal in-range attack, role damage, cooldown and kill attribution.

        Args:
            bot: Villager whose current state or work is being considered.
            monster: Target living monster.

        Returns:
            Whether an attack was performed.
        """
        if (
            self.time < bot.attack_at
            or bot.energy < R["attack_energy"]
            or monster.health <= 0
        ):
            return False
        monster.health = max(
            0,
            monster.health
            - S["roles"][bot.role].get("attack_damage", R["base_attack_damage"]),
        )
        bot.energy -= R["attack_energy"]
        bot.attack_at = self.time + R["attack_cooldown"]
        self.task_board.note_progress(
            bot, {"action": "attack"}, target_gate=monster.gate
        )
        if monster.health <= 0:
            bot.contributions["kills"] += 1
            bot.memory.append(
                f"I defeated {monster.id}. Guarding protects the village."
            )
            self.log(f"{bot.name} defeated {monster.id}.")
        return True

    def spawn_wave(self):
        """Spawn the next configured monster wave outside the village walls.

        Returns:
            None; respects active-monster limits and advances wave bookkeeping.
        """
        self.wave += 1
        for _ in range(
            min(R["wave_max_spawn"], 1 + self.wave // R["wave_growth_every"])
        ):
            if sum(m.health > 0 for m in self.monsters) >= R["max_monsters"]:
                break
            gate = self.rng.choice(list(GATES))
            x, y = GATES[gate]
            scale = R["monster_spawn_coordinate"] / max(abs(x), abs(y))
            self.monsters.append(
                Monster(f"monster_{self.next_monster_id}", gate, (x * scale, y * scale))
            )
            self.next_monster_id += 1
        self.next_wave = self.time + R["wave_interval_seconds"]
        self.log(
            f"Alarm! Monster wave {self.wave} is approaching. Defend and repair the gates."
        )
        for bot in self.villagers:
            bot.memory.append(
                f"Wave {self.wave}: {self.gate_threats()}. Cooperation is required to survive."
            )
            bot.next_think = min(bot.next_think, self.time)

    def survival_tick(self, dt):
        """Advance crops, hunger, cooldown work, monsters, damage and failure checks.

        Args:
            dt: Elapsed simulation seconds; rendering overrides receive real frame seconds.

        Returns:
            None; changes authoritative simulation state.
        """
        for crop in self.crops:
            if crop.stage == "growing":
                crop.age = min(CROP_GROW_SECONDS, crop.age + dt)
                if crop.age >= CROP_GROW_SECONDS:
                    crop.stage = "ripe"
        if self.time >= self.next_wave:
            self.spawn_wave()
        for bot in self.villagers:
            if not bot.alive:
                continue
            bot.hunger = min(
                R["villager_max"], bot.hunger + dt * R["hunger_per_second"]
            )
            if bot.hunger > R["starvation_threshold"]:
                bot.health = max(0, bot.health - dt * R["starvation_damage_per_second"])
            if bot.action.startswith("guarding "):
                threats = [
                    m
                    for m in self.monsters
                    if m.health > 0
                    and distance(bot.position, m.position) <= R["attack_range"]
                ]
                if threats:
                    self.strike(
                        bot,
                        min(threats, key=lambda m: distance(bot.position, m.position)),
                    )
        for monster in self.monsters:
            if monster.health <= 0:
                continue
            gx, gy = GATES[monster.gate]
            outside = tuple(
                v * R["monster_gate_coordinate"] / max(abs(gx), abs(gy))
                for v in (gx, gy)
            )
            if self.gates[monster.gate] > 0:
                target = outside
                if distance(monster.position, target) < R["monster_gate_radius"]:
                    self.gates[monster.gate] = max(
                        0, self.gates[monster.gate] - dt * R["monster_gate_damage"]
                    )
                    continue
            else:
                live = [v for v in self.villagers if v.alive]
                victim = (
                    min(live, key=lambda v: distance(v.position, monster.position))
                    if live
                    else None
                )
                if (
                    victim
                    and distance(victim.position, monster.position)
                    < R["monster_victim_radius"]
                ):
                    victim.health = max(
                        0, victim.health - dt * R["monster_villager_damage"]
                    )
                    continue
                target = LOCATIONS["square"]
                if distance(monster.position, target) < R["monster_core_radius"]:
                    self.village_health = max(
                        0, self.village_health - dt * R["monster_core_damage"]
                    )
                    continue
            d = distance(monster.position, target)
            if d:
                step = min(d, dt * R["monster_speed"])
                monster.position = tuple(
                    a + (b - a) / d * step for a, b in zip(monster.position, target)
                )
        self.monsters = [m for m in self.monsters if m.health > 0]
        for i, bot in enumerate(self.villagers):
            if not bot.alive and bot.action != "fallen":
                bot.action = "fallen"
                bot.path.clear()
                bot.revision += 1
                self.log(f"{bot.name} has fallen. The village needs help.")
                if self.controlled == i:
                    self.possess(None)
        if self.village_health <= 0:
            self.fail(
                "Monsters destroyed the village center after the defenses failed."
            )
        elif not any(v.alive for v in self.villagers):
            self.fail("All villagers fell: food and defense cooperation failed.")

    def fail(self, reason):
        """Record village destruction once and retain factual campaign lessons.

        Args:
            reason: Recorded explanation for the lifecycle transition.

        Returns:
            None; marks the current attempt failed without resetting it.
        """
        if self.failed:
            return
        self.failed, self.failure_reason = True, reason
        breached = [name for name, hp in self.gates.items() if hp <= 0]
        episode = {
            "attempt": self.campaign["attempt"],
            "seconds": round(self.time, 1),
            "reason": reason,
            "breached_gates": breached,
            "store": self.store.copy(),
            "contributions": {v.name: v.contributions.copy() for v in self.villagers},
        }
        self.campaign["failures"] = (self.campaign["failures"] + [episode])[
            -S["memory"]["failure_capacity"] :
        ]
        for bot in self.villagers:
            lesson = (
                f"Attempt {self.campaign['attempt']} failed: {reason} "
                f"Breached gates: {', '.join(breached) or 'none'}. Shared food {self.store['food']}, wood {self.store['wood']}. "
                f"As {bot.role}, I contributed {bot.contributions}. Next attempt: deposit harvests, eat, supply repairs, and guard threatened gates together."
            )
            bot.lessons.append(lesson)
            self.campaign["lessons"][bot.name] = list(bot.lessons)
            bot.revision += 1
        self.log(
            "VILLAGE DESTROYED. Lessons recorded. Start with --new-game to try again."
        )
