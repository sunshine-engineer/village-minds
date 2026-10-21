"""World lifecycle, perception, movement and validated action dispatch."""

from collections import deque
import math
import random
from .config import get_settings
from .map_data import (
    CAST,
    LOCATIONS,
    GATES,
    GATE_MAX,
    SIGHT,
    HEARING,
    CROP_GROW_SECONDS,
)
from .entities import Villager, Crop, Monster
from .navigation import distance, pathfind, walkable
from .survival import SurvivalRules
from .policies import default_policy
from .extensions import load_extensions

S = get_settings()
R, P, W = S["rules"], S["policy"], S["world"]


class World(SurvivalRules):
    def __init__(self, seed=None, campaign=None, extensions=None, decision_log=None):
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
        self.events.append(text)

    def possess(self, index):
        # Invalidate all in-flight decisions across both takeover and release.
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
        if self.decision_log is None:
            return self._apply(bot, decision)
        from .telemetry import state_summary

        before = state_summary(self, bot)
        if observation is None and self.decision_log.full_observations:
            observation = self.observe(bot)
        accepted = self._apply(bot, decision)
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
        """Validate model intents against current state, never execute model code."""
        if self.failed or not bot.alive or not isinstance(decision, dict):
            return False
        action = decision.get("action")
        if not isinstance(action, str):
            return False
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
        if self.failed:
            return
        dt = max(0, min(dt, S["runtime"]["max_step_seconds"]))
        self.time += dt
        self.survival_tick(dt)
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
        """Personal work slots reduce crowding at shared destinations."""
        index = next(i for i, v in enumerate(self.villagers) if v is bot)
        offsets = W["work_offsets"]
        dx, dy = offsets[index % len(offsets)]
        x, y = LOCATIONS[place]
        point = (x + dx, y + dy)
        return point if walkable(*point) else (x, y)

    def fallback(self, bot):
        policy = self.extensions.policies.get(bot.role, default_policy)
        return policy(self, bot)

    def role_index(self, bot):
        return next(
            i
            for i, v in enumerate(v for v in self.villagers if v.role == bot.role)
            if v is bot
        )
