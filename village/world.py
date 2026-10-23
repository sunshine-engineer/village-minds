"""World lifecycle, perception, movement and validated action dispatch.

File: village/world.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import math
import random
from collections import deque

from .config import get_settings
from .entities import Crop, Villager
from .entities import Monster as Monster
from .extensions import load_extensions
from .map_data import (
    CAST,
    CROP_GROW_SECONDS,
    GATE_MAX,
    GATES,
    HEARING,
    LOCATIONS,
    SIGHT,
)
from .navigation import distance, pathfind, walkable, work_point
from .policies import default_policy
from .survival import SurvivalRules

S = get_settings()
R, P, W = S["rules"], S["policy"], S["world"]


class World(SurvivalRules):
    """Authoritative village state with validated intents, perception and movement."""

    def __init__(self, seed=None, campaign=None, extensions=None, decision_log=None):
        """Initialize World and its owned state.

        Args:
            seed: Nonnegative deterministic world/randomization seed.
            campaign: Optional retained attempt/failure history.
            extensions: Optional trusted extension registry.
            decision_log: Optional bounded telemetry sink.

        Returns:
            None.
        """
        self.decision_log = decision_log
        self._movement_log_at = 0.0
        self.extensions = extensions if extensions is not None else load_extensions()
        self.extension_state = {
            name: create() for name, (create, _) in self.extensions.states.items()
        }
        seed = S["runtime"]["seed"] if seed is None else seed
        self.rng = random.Random(seed)
        self.villagers = [Villager(*entry) for entry in CAST]
        self.time = 0.0
        from .coordination import TaskBoard

        self.task_board = TaskBoard(self)
        self.controlled = None
        self.events = deque(maxlen=S["memory"]["event_capacity"])
        self.resources = {"orchard": R["orchard_capacity"]}
        self.regen_at = R["orchard_regen_seconds"]
        self.store = {"food": R["initial_food"], "wood": R["initial_wood"]}
        self.gates = {name: GATE_MAX for name in GATES}
        self.village_health = R["village_health"]
        self.crops = [Crop(tuple(pos)) for pos in W["crops"]]
        self.monsters = []
        self.wave = 0
        self.next_wave = R["first_wave_seconds"]
        self.next_monster_id = 1
        self.failed = False
        self.failure_reason = ""
        self.campaign = campaign or {"attempt": 1, "failures": [], "lessons": {}}
        for bot in self.villagers:
            bot.lessons.extend(self.campaign["lessons"].get(bot.name, []))
        self.log(
            f"Attempt {self.campaign['attempt']}: cooperate to feed and defend Willowbrook."
        )

    def log(self, text):
        """Append a timestamped event to bounded village history.

        Args:
            text: Dialogue or event text to validate and publish.

        Returns:
            None.
        """
        self.events.append(text)

    def possess(self, index):
        # Invalidate all in-flight decisions across both takeover and release.
        """Change player ownership and invalidate affected pending model orders.

        Args:
            index: Villager roster index selected by the caller.

        Returns:
            None; index=None releases to observer mode. Callers must validate roster bounds.
        """
        for bot in self.villagers:
            bot.revision += 1
        if self.controlled is not None:
            previous = self.villagers[self.controlled]
            previous.action = "idle"
            previous.next_think = self.time
        self.controlled = index
        if self.decision_log:
            self.decision_log.record(
                "possession", self.time, source="player", actor_index=index
            )
        if index is not None and not self.villagers[index].alive:
            self.controlled = None
            self.log("That villager has fallen. Choose a survivor.")
            return
        if index is not None:
            bot = self.villagers[index]
            bot.path.clear()
            bot.action = "player"
            self.log(f"You are now {bot.name}.")
        else:
            self.log("Observer mode: all villagers are autonomous.")

    def observe(self, bot):
        """Build role, surroundings, legal-action, memory and public-task context for a villager.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Observation dictionary; no executable code or mutable world object is exposed.
        """
        return {
            "name": bot.name,
            "role": bot.role,
            "personality": bot.personality,
            "position": [round(v, 1) for v in bot.position],
            "energy": round(bot.energy),
            "supplies": bot.supplies,
            "health": round(bot.health),
            "hunger": round(bot.hunger),
            "wood": bot.wood,
            "available_actions": self.available_actions(bot),
            "task_board": self.task_board.observe(),
            "coordination_mode": self.task_board.mode,
            "coordination_roster": [
                dict(
                    name=v.name,
                    role=v.role,
                    position=v.position,
                    hunger=round(v.hunger),
                    energy=round(v.energy),
                    action=v.action,
                )
                for v in self.villagers
                if v.alive
            ],
            "village": {
                "health": round(self.village_health),
                "gates": self.gates.copy(),
                "storehouse": self.store.copy(),
                "wave": self.wave,
                "seconds_until_wave": round(max(0, self.next_wave - self.time)),
                "gate_threats": self.gate_threats(),
                "attempt": self.campaign["attempt"],
            },
            "crops": [
                {
                    "stage": c.stage,
                    "seconds_to_ripe": round(max(0, CROP_GROW_SECONDS - c.age)),
                }
                for c in self.crops
            ],
            "nearby_monsters": [
                {"id": m.id, "position": m.position, "health": round(m.health)}
                for m in self.monsters
                if m.health > 0 and distance(bot.position, m.position) <= SIGHT
            ],
            "lessons_from_previous_failures": list(bot.lessons),
            "recommended_task": self.fallback(bot),
            "current_action": bot.action,
            "conversation_partners": [
                other.name
                for other in self.villagers
                if other is not bot
                and other.alive
                and distance(bot.position, other.position) <= HEARING
            ],
            "gather_here": (["orchard"] if self.can_gather(bot) else []),
            "nearby_villagers": [
                {
                    "name": other.name,
                    "position": [round(v, 1) for v in other.position],
                    "action": other.action,
                    "distance": round(distance(bot.position, other.position), 1),
                    "supplies": other.supplies,
                }
                for other in self.villagers
                if other is not bot
                and other.alive
                and distance(bot.position, other.position) <= SIGHT
            ],
            "nearby_places": {
                name: {"position": pos, "supplies": self.resources.get(name)}
                for name, pos in LOCATIONS.items()
                if distance(bot.position, pos) <= SIGHT
            },
            "village_map": LOCATIONS,
            "recent_memories": list(bot.memory),
            "objective": S["ai"]["objective"],
        }

    def say(self, bot, text, target=None, *, source="system"):
        """Publish bounded dialogue to nearby listeners and append conversational memory.

        Args:
            bot: Villager whose current state or work is being considered.
            text: Dialogue or event text to validate and publish.
            target: Action target token or destination.
            source: Provenance label identifying the caller or decision layer.

        Returns:
            None; records speech provenance when telemetry is enabled.
        """
        text = " ".join(str(text).split())[: S["memory"]["dialogue_chars"]]
        if not text or not bot.alive:
            return
        bot.speech, bot.speech_until = text, self.time + R["speech_seconds"]
        if self.decision_log:
            self.decision_log.record(
                "dialogue", self.time, source=source, actor=bot.name, text=text
            )
        line = f"{bot.name}: {text}"
        bot.memory.append(line)
        self.log(line)
        for other in self.villagers:
            if (
                other is not bot
                and other.alive
                and distance(bot.position, other.position) <= HEARING
            ):
                other.memory.append(line)
                other.next_think = min(
                    other.next_think, self.time + R["speech_wake_seconds"]
                )

    def apply(
        self, bot, decision, *, source="external", request_id=None, observation=None
    ):
        """Apply a proposed intent and record acceptance with compact before/after state.

        Args:
            bot: Villager whose current state or work is being considered.
            decision: Proposed structured action with optional target/dialogue fields.
            source: Provenance label identifying the caller or decision layer.
            request_id: Optional correlation identifier for decision telemetry.
            observation: Request-time context containing legal choices and relevant world state.

        Returns:
            Whether current-state validation accepted the intent.
        """
        if self.decision_log is None:
            accepted = self._apply(bot, decision)
            if accepted:
                self.task_board.note_progress(bot, decision)
            return accepted
        from .logistics import delivery_reason
        from .telemetry import state_summary

        delivery = (
            delivery_reason(self, bot)
            if isinstance(decision, dict)
            and decision.get("action") == "deposit"
            and max(bot.wood, bot.supplies) < P["deposit_at_inventory"]
            else None
        )
        before = state_summary(self, bot)
        if observation is None and self.decision_log.full_observations:
            observation = self.observe(bot)
        accepted = self._apply(bot, decision)
        if accepted:
            self.task_board.note_progress(bot, decision)
        if accepted and delivery:
            self.decision_log.record(
                "urgent_delivery",
                self.time,
                source=source,
                actor=bot.name,
                outcome="accepted",
                reason=delivery,
                food=before["actor"]["food"],
                wood=before["actor"]["wood"],
            )
        self.decision_log.record(
            "decision",
            self.time,
            source=source,
            actor=bot.name,
            outcome="accepted" if accepted else "rejected",
            decision=decision,
            request_id=request_id,
            observation=observation,
            before=before,
            after=state_summary(self, bot),
            reason="" if accepted else "unavailable_or_invalid",
        )
        return accepted

    def _apply(self, bot, decision):
        """Validate model intents against current state, never execute model code.

        Args:
            bot: Villager whose current state or work is being considered.
            decision: Proposed structured action with optional target/dialogue fields.

        Returns:
            Whether a built-in or registered action succeeded.
        """
        if self.failed or not bot.alive or not isinstance(decision, dict):
            return False
        action = decision.get("action")
        if not isinstance(action, str):
            return False
        if action == "defer_strategy":
            return get_settings()["ai"]["repair_strategy"]["enabled"]
        if action == "plan_repairs":
            return self.task_board.install_repair_plan(bot, decision.get("target"))
        if action == "dispatch_repair":
            from .allocation import repair_candidates

            target = decision.get("target", "")
            if not isinstance(target, str) or target not in [
                c["target"] for c in repair_candidates(self.task_board, bot)
            ]:
                return False
            gate, _, recipient = target.partition(":")
            accepted = self.task_board.offer_repair(bot, gate, recipient)
            if accepted:
                task = next(
                    t
                    for t in self.task_board.tasks
                    if t["kind"] == "repair"
                    and t["target"] == gate
                    and t["assigned_to"] == recipient
                    and t["status"] == "offered"
                )
                self.task_board.strategy_leases[task["id"]] = (
                    self.time + get_settings()["ai"]["repair_strategy"]["lease_seconds"]
                )
            return accepted
        if action in ("request_help", "assign_task", "claim_task", "release_task"):
            return self.task_board.execute(bot, decision)
        if action in self.extensions.actions:
            hook = self.extensions.actions[action]
            target = decision.get("target", "")
            if not isinstance(target, str) or target not in hook.available(self, bot):
                return False
            return bool(hook.execute(self, bot, decision))
        if (
            action in ("farm", "harvest", "gather", "deposit", "eat", "repair")
            and self.time < bot.work_at
        ):
            return False
        if action in (
            "farm",
            "harvest",
            "deposit",
            "eat",
            "repair",
            "guard",
            "attack",
            "rally",
        ):
            return self.survival_action(bot, decision)
        if action == "move":
            target = decision.get("target")
            if not isinstance(target, str):
                return False
            point = LOCATIONS.get(target)
            if point is None:
                other = next(
                    (
                        v
                        for v in self.villagers
                        if v.name == target
                        and v.alive
                        and v is not bot
                        and distance(v.position, bot.position) <= SIGHT
                    ),
                    None,
                )
                if other is None:
                    return False
                point = other.position
            if target in LOCATIONS:
                point = self.destination(bot, target)
            bot.path = pathfind(bot.position, point)
            bot.action = f"walking to {target}" if bot.path else "idle"
        elif action == "talk":
            target = decision.get("target")
            other = next(
                (
                    v
                    for v in self.villagers
                    if v.name == target and v is not bot and v.alive
                ),
                None,
            )
            if other is None or distance(bot.position, other.position) > HEARING:
                return False
            text = decision.get("dialogue")
            if not isinstance(text, str) or not text.strip():
                return False
            bot.path.clear()
            bot.action = f"talking to {target}"
            self.say(bot, text, target)
        elif action == "gather":
            if not self.can_gather(bot):
                return False
            bot.path.clear()
            amount = min(
                self.resources["orchard"],
                S["roles"][bot.role].get("wood_yield", R["base_wood_yield"]),
            )
            self.resources["orchard"] -= amount
            bot.wood += amount
            bot.energy -= R["gather_energy"]
            bot.work_at = self.time + R["work_cooldown"]
            bot.action = "gathering wood"
            self.log(f"{bot.name} gathered {amount} wood for repairs.")
        elif action == "rest":
            bot.path.clear()
            bot.action = "resting"
        elif action == "idle":
            bot.path.clear()
            bot.action = "idle"
        else:
            return False
        return True

    def move_player(self, dx, dy, dt):
        """Move the possessed living villager using bounded direction and collision checks.

        Args:
            dx: Horizontal movement axis; server input is bounded to [-1, 1].
            dy: Vertical movement axis; server input is bounded to [-1, 1].
            dt: Elapsed simulation seconds; rendering overrides receive real frame seconds.

        Returns:
            None; uses caller-supplied elapsed time.
        """
        if self.controlled is None or self.failed:
            return
        bot = self.villagers[self.controlled]
        length = math.hypot(dx, dy)
        if not length:
            return
        step = R["player_speed"] * min(dt, S["runtime"]["max_step_seconds"]) / length
        bot.action = "player"
        bot.path.clear()
        x, y = bot.position
        if walkable(x + dx * step, y):
            x += dx * step
        if walkable(x, y + dy * step):
            y += dy * step
        bot.position = (x, y)
        if self.decision_log and self.time >= self._movement_log_at:
            self.decision_log.record(
                "movement",
                self.time,
                source="player",
                actor=bot.name,
                direction=[dx, dy],
                position=list(bot.position),
            )
            self._movement_log_at = (
                self.time + S["telemetry"]["movement_interval_seconds"]
            )

    def tick(self, dt):
        """Advance survival, registered systems and queued movement for one simulation step.

        Args:
            dt: Elapsed simulation seconds; rendering overrides receive real frame seconds.

        Returns:
            None; a failed world remains frozen.
        """
        if self.failed:
            return
        dt = max(0, min(dt, S["runtime"]["max_step_seconds"]))
        self.time += dt
        self.survival_tick(dt)
        self.task_board.maintain()
        if self.failed:
            return
        for tick in self.extensions.systems.values():
            tick(self, dt)
            if self.failed:
                return
        if self.time >= self.regen_at:
            self.resources = {
                name: min(R["orchard_capacity"], n + R["orchard_regen_amount"])
                for name, n in self.resources.items()
            }
            self.regen_at = self.time + R["orchard_regen_seconds"]
        for i, bot in enumerate(self.villagers):
            if not bot.alive:
                continue
            if i == self.controlled:
                if bot.action == "resting":
                    bot.energy = min(
                        R["villager_max"], bot.energy + dt * R["rest_energy_per_second"]
                    )
                if not bot.action.startswith("guarding "):
                    continue
            if bot.path:
                target = bot.path[0]
                d = distance(bot.position, target)
                step = R["villager_speed"] * dt
                if d <= step:
                    bot.position = target
                    bot.path.pop(0)
                    if not bot.path and not bot.action.startswith("guarding "):
                        bot.action = "idle"
                else:
                    bot.position = tuple(
                        a + (b - a) / d * step for a, b in zip(bot.position, target)
                    )
                bot.energy = max(0, bot.energy - dt * R["walking_energy_per_second"])
            elif bot.action == "resting":
                bot.energy = min(
                    R["villager_max"], bot.energy + dt * R["rest_energy_per_second"]
                )

    def destination(self, bot, place):
        """Personal work slots reduce crowding at shared destinations.

        Args:
            bot: Villager whose current state or work is being considered.
            place: Configured service or gate name.

        Returns:
            Planar destination tuple.
        """
        if place == "farm":
            point = self.crop_destination(bot)
            if point is not None:
                return point
        index = next(i for i, v in enumerate(self.villagers) if v is bot)
        offsets = W["work_offsets"]
        dx, dy = offsets[index % len(offsets)]
        x, y = LOCATIONS[place]
        point = (x + dx, y + dy)
        return point if walkable(*point) else (x, y)

    def fallback(self, bot):
        """Select urgent deliveries, owned task work or the role's default policy.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Intent dictionary, False to keep task work, or None when idle.
        """
        if self.failed or not bot.alive:
            return None
        from .logistics import delivery_intent

        delivery = delivery_intent(self, bot)
        if delivery is False:
            return None
        if delivery is not None:
            return delivery
        task = self.task_board.policy(bot)
        if task is False:
            return None
        if task is not None:
            return task
        policy = self.extensions.policies.get(bot.role, default_policy)
        return policy(self, bot)

    def role_index(self, bot):
        """Find this actor's stable index among villagers sharing its role.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Zero-based role-local index.
        """
        return next(
            i
            for i, v in enumerate(v for v in self.villagers if v.role == bot.role)
            if v is bot
        )

    def crop_destination(self, bot):
        """Choose reachable work beside a ripe/empty plot, not just the farm sign.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Planar position, or None when no useful crop work point exists.
        """
        index = next(i for i, v in enumerate(self.villagers) if v is bot)
        offsets = W["work_offsets"]
        offset = offsets[index % len(offsets)]
        for stage in ("ripe", "empty"):
            crops = [c for c in self.crops if c.stage == stage]
            if crops:
                rotation = index % len(crops)
                crops = crops[rotation:] + crops[:rotation]
            for crop in crops:
                point = work_point(
                    bot.position, crop.position, R["crop_radius"], offset
                )
                if point is not None:
                    return point
        return None
