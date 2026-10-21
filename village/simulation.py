"""Authoritative simulation. No graphics or model dependencies."""
from collections import deque
from dataclasses import dataclass, field
import heapq
import math
import random

LIMIT = 32
SIGHT = 12.0
HEARING = 8.0
LOCATIONS = {"square": (0, 0), "farm": (-14, 9), "orchard": (14, 10),
             "tavern": (-10, -9), "well": (8, -5), "rest": (0, 17),
             "storehouse": (-8, -7), "north_gate": (0, 21),
             "south_gate": (0, -21), "east_gate": (21, 0), "west_gate": (-21, 0)}
GATES = {name: pos for name, pos in LOCATIONS.items() if name.endswith("_gate")}
GATE_MAX = 150.0
CROP_GROW_SECONDS = 45.0
# Centers and half sizes; shared by navigation and rendering.
BUILDINGS = [(-11, -15, 3, 2.5), (11, -15, 3, 2.5),
             (-18, -5, 2.5, 3), (18, -5, 2.5, 3), (-9, 18, 3, 2),
             (-8, -10, 2, 1.5)]
CAST = [
    ("Mira", "farmer", "Patient and generous; values food and cooperation.", (0.92, .65, .26), (-3, 0)),
    ("Bram", "worker", "Practical and ambitious; hauls food, gathers wood, and repairs threatened gates.", (.37, .66, .95), (3, 0)),
    ("Iris", "farmer", "Curious and warm; grows crops and shares food with hungry neighbors.", (.65, .46, .86), (0, 4)),
    ("Otto", "soldier", "Blunt and brave; guards threatened gates and protects the farmers.", (.88, .4, .3), (-5, 4)),
    ("Nell", "soldier", "Alert and cooperative; coordinates defense with Otto and guards exposed gates.", (.3, .8, .68), (5, 4)),
    ("Edda", "elder", "Calm and thoughtful; coordinates survival, shares food, and remembers earlier failures.", (.88, .76, .52), (0, -4)),
]


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def walkable(x, y):
    at_wall = ((abs(abs(x) - 24) < .6 and abs(y) > 2.5 and abs(y) < 24.6)
               or (abs(abs(y) - 24) < .6 and abs(x) > 2.5 and abs(x) < 24.6))
    return abs(x) <= LIMIT and abs(y) <= LIMIT and not at_wall and not any(
        abs(x - bx) < hx + .6 and abs(y - by) < hy + .6
        for bx, by, hx, hy in BUILDINGS)


def pathfind(start, goal):
    """Four-neighbor A* on a one-unit grid, avoiding houses."""
    start = tuple(round(v) for v in start)
    goal = tuple(round(v) for v in goal)
    if not walkable(*goal):
        return []
    frontier = [(0, start)]
    cost, came = {start: 0}, {}
    while frontier:
        _, cell = heapq.heappop(frontier)
        if cell == goal:
            path = [cell]
            while cell in came:
                cell = came[cell]
                path.append(cell)
            return list(reversed(path))[1:]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = cell[0] + dx, cell[1] + dy
            new = cost[cell] + 1
            if walkable(*nxt) and new < cost.get(nxt, float("inf")):
                cost[nxt], came[nxt] = new, cell
                heapq.heappush(frontier, (new + distance(nxt, goal), nxt))
    return []


@dataclass
class Villager:
    name: str
    role: str
    personality: str
    color: tuple
    position: tuple
    energy: float = 100
    supplies: int = 0
    action: str = "idle"
    path: list = field(default_factory=list)
    memory: deque = field(default_factory=lambda: deque(maxlen=8))
    speech: str = ""
    speech_until: float = 0
    next_think: float = 0
    revision: int = 0
    health: float = 100
    hunger: float = 0
    wood: int = 0
    lessons: deque = field(default_factory=lambda: deque(maxlen=8))
    contributions: dict = field(default_factory=lambda: {
        "planted": 0, "harvested": 0, "deposited_food": 0,
        "deposited_wood": 0, "repairs": 0, "kills": 0, "rallies": 0})
    work_at: float = 0
    attack_at: float = 0
    rally_at: float = 0

    @property
    def alive(self):
        return self.health > 0


@dataclass
class Crop:
    position: tuple
    stage: str = "ripe"
    age: float = CROP_GROW_SECONDS


@dataclass
class Monster:
    id: str
    gate: str
    position: tuple
    health: float = 40


class World:
    def __init__(self, seed=7, campaign=None):
        self.rng = random.Random(seed)
        self.villagers = [Villager(*entry) for entry in CAST]
        self.time = 0.0
        self.controlled = None
        self.events = deque(maxlen=7)
        self.resources = {"orchard": 24}
        self.regen_at = 20
        self.store = {"food": 18, "wood": 12}
        self.gates = {name: GATE_MAX for name in GATES}
        self.village_health = 200.0
        self.crops = [Crop(pos) for pos in [(-16, 8), (-12, 8), (-16, 12), (-12, 12)]]
        self.monsters = []
        self.wave = 0
        self.next_wave = 180.0
        self.next_monster_id = 1
        self.failed = False
        self.failure_reason = ""
        self.campaign = campaign or {"attempt": 1, "failures": [], "lessons": {}}
        for bot in self.villagers:
            bot.lessons.extend(self.campaign["lessons"].get(bot.name, []))
        self.log(f"Attempt {self.campaign['attempt']}: cooperate to feed and defend Willowbrook.")

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
            "name": bot.name, "role": bot.role, "personality": bot.personality,
            "position": [round(v, 1) for v in bot.position],
            "energy": round(bot.energy), "supplies": bot.supplies,
            "health": round(bot.health), "hunger": round(bot.hunger), "wood": bot.wood,
            "available_actions": self.available_actions(bot),
            "village": {"health": round(self.village_health), "gates": self.gates.copy(),
                "storehouse": self.store.copy(), "wave": self.wave,
                "seconds_until_wave": round(max(0, self.next_wave - self.time)),
                "gate_threats": self.gate_threats(), "attempt": self.campaign["attempt"]},
            "crops": [{"stage": c.stage, "seconds_to_ripe": round(max(0, CROP_GROW_SECONDS-c.age))}
                      for c in self.crops],
            "nearby_monsters": [{"id": m.id, "position": m.position, "health": round(m.health)}
                for m in self.monsters if m.health > 0 and distance(bot.position,m.position) <= SIGHT],
            "lessons_from_previous_failures": list(bot.lessons),
            "recommended_task": self.fallback(bot),
            "current_action": bot.action,
            "conversation_partners": [other.name for other in self.villagers
                if other is not bot and other.alive and distance(bot.position, other.position) <= HEARING],
            "gather_here": (["orchard"] if self.can_gather(bot) else []),
            "nearby_villagers": [{"name": other.name,
                "position": [round(v, 1) for v in other.position], "action": other.action,
                "distance": round(distance(bot.position, other.position), 1), "supplies": other.supplies}
                for other in self.villagers if other is not bot and other.alive
                and distance(bot.position, other.position) <= SIGHT],
            "nearby_places": {name: {"position": pos, "supplies": self.resources.get(name)}
                for name, pos in LOCATIONS.items() if distance(bot.position, pos) <= SIGHT},
            "village_map": LOCATIONS, "recent_memories": list(bot.memory),
            "objective": "Cooperate to keep the village alive: grow and deposit food, eat, gather and deposit wood, repair gates, and guard against monsters. Ignoring these jobs can destroy the village. Use past failure lessons.",
        }

    def say(self, bot, text, target=None):
        text = " ".join(str(text).split())[:180]
        if not text or not bot.alive:
            return
        bot.speech, bot.speech_until = text, self.time + 8
        line = f"{bot.name}: {text}"
        bot.memory.append(line)
        self.log(line)
        for other in self.villagers:
            if other is not bot and other.alive and distance(bot.position, other.position) <= HEARING:
                other.memory.append(line)
                other.next_think = min(other.next_think, self.time + 1)

    def apply(self, bot, decision):
        """Validate model intents against current state, never execute model code."""
        if self.failed or not bot.alive or not isinstance(decision, dict):
            return False
        action = decision.get("action")
        if action in ("farm", "harvest", "gather", "deposit", "eat", "repair") and self.time < bot.work_at:
            return False
        if action in ("farm", "harvest", "deposit", "eat", "repair", "guard", "attack", "rally"):
            return self.survival_action(bot, decision)
        if action == "move":
            target = decision.get("target")
            if not isinstance(target, str):
                return False
            point = LOCATIONS.get(target)
            if point is None:
                other = next((v for v in self.villagers if v.name == target and v.alive
                    and v is not bot and distance(v.position, bot.position) <= SIGHT), None)
                if other is None:
                    return False
                point = other.position
            if target in LOCATIONS:
                point = self.destination(bot,target)
            bot.path = pathfind(bot.position, point)
            bot.action = f"walking to {target}" if bot.path else "idle"
        elif action == "talk":
            target = decision.get("target")
            other = next((v for v in self.villagers if v.name == target and v is not bot and v.alive), None)
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
            amount = min(self.resources["orchard"], 3 if bot.role == "worker" else 2)
            self.resources["orchard"] -= amount
            bot.wood += amount
            bot.energy -= 4
            bot.work_at = self.time + 1
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

    def fallback(self, bot):
        """Fast needs/role policy, always active and also supplied as model advice."""
        if not bot.alive or self.failed:
            return None
        def go(place, action, **fields):
            if distance(bot.position, LOCATIONS[place]) < (5 if place == "farm" else 2.8):
                return {"action": action, **fields}
            if bot.path and bot.action == f"walking to {place}":
                return None
            return {"action": "move", "target": place}
        if bot.hunger > 40:
            if bot.supplies or (distance(bot.position, LOCATIONS["storehouse"]) < 3 and self.store["food"]):
                return {"action": "eat"}
            if self.store["food"]:
                return go("storehouse", "eat")
        if bot.energy < 25:
            return {"action": "rest"}
        if bot.action == "resting" and bot.energy < 85:
            return None
        threats = self.gate_threats()
        if bot.role == "soldier":
            if threats:
                # Spread soldiers across simultaneous threats.
                ordered = sorted(threats, key=lambda name: (-threats[name], name))
                target = ordered[(0 if bot.name == "Otto" else 1) % len(ordered)]
            else:
                target = "north_gate" if bot.name == "Otto" else "south_gate"
            if bot.action == f"guarding {target}":
                return None
            return {"action": "guard", "target": target}
        if bot.supplies >= 6 or bot.wood >= 6:
            return go("storehouse", "deposit")
        if bot.role == "worker":
            damaged = min(self.gates, key=self.gates.get)
            if self.gates[damaged] < GATE_MAX - 10 and self.store["wood"]:
                return go(damaged, "repair", target=damaged)
            if self.store["wood"] < 20:
                return go("orchard", "gather")
        if bot.role == "elder" and "rally" in self.available_actions(bot):
            return {"action": "rally"}
        if any(c.stage == "ripe" for c in self.crops):
            return go("farm", "harvest")
        if any(c.stage == "empty" for c in self.crops):
            return go("farm", "farm")
        if bot.supplies or bot.wood:
            return go("storehouse", "deposit")
        if bot.energy < 70:
            return {"action": "rest"}
        return None

    def move_player(self, dx, dy, dt):
        if self.controlled is None or self.failed:
            return
        bot = self.villagers[self.controlled]
        length = math.hypot(dx, dy)
        if not length:
            return
        step = 4.5 * min(dt, .1) / length
        bot.action = "player"
        bot.path.clear()
        x, y = bot.position
        if walkable(x + dx * step, y):
            x += dx * step
        if walkable(x, y + dy * step):
            y += dy * step
        bot.position = (x, y)

    def tick(self, dt):
        if self.failed:
            return
        dt = max(0, min(dt, .1))
        self.time += dt
        self.survival_tick(dt)
        if self.time >= self.regen_at:
            self.resources = {name: min(24, n + 3) for name, n in self.resources.items()}
            self.regen_at = self.time + 20
        for i, bot in enumerate(self.villagers):
            if not bot.alive:
                continue
            if i == self.controlled:
                if bot.action == "resting":
                    bot.energy = min(100, bot.energy + dt * 4)
                if not bot.action.startswith("guarding "):
                    continue
            if bot.path:
                target = bot.path[0]
                d = distance(bot.position, target)
                step = 2.5 * dt
                if d <= step:
                    bot.position = target
                    bot.path.pop(0)
                    if not bot.path and not bot.action.startswith("guarding "):
                        bot.action = "idle"
                else:
                    bot.position = tuple(a + (b - a) / d * step for a, b in zip(bot.position, target))
                bot.energy = max(0, bot.energy - dt * .2)
            elif bot.action == "resting":
                bot.energy = min(100, bot.energy + dt * 4)

    def destination(self, bot, place):
        """Personal work slots reduce crowding at shared destinations."""
        index = next(i for i,v in enumerate(self.villagers) if v is bot)
        offsets = [(-1,0),(1,0),(0,-1),(0,1),(-1,1),(1,1)]
        dx,dy = offsets[index]
        x,y = LOCATIONS[place]
        point = (x+dx,y+dy)
        return point if walkable(*point) else (x,y)

    def can_gather(self, bot):
        return (distance(bot.position, LOCATIONS["orchard"]) < 2.5
                and self.resources["orchard"] > 0 and bot.energy >= 4)

    def local_crop(self, bot, stage):
        return next((c for c in sorted(self.crops, key=lambda c: distance(bot.position,c.position))
                     if c.stage == stage and distance(bot.position,c.position) < 5), None)

    def available_actions(self, bot):
        if self.failed or not bot.alive:
            return {}
        actions = {"move": list(LOCATIONS) + [v.name for v in self.villagers
            if v is not bot and v.alive and distance(v.position,bot.position) <= SIGHT],
            "guard": list(GATES)}
        partners = [v.name for v in self.villagers if v is not bot and v.alive
                    and distance(v.position,bot.position) <= HEARING]
        if partners:
            actions["talk"] = partners
        if bot.energy < 75:
            actions["rest"] = [""]
        if self.time >= bot.work_at:
            if bot.energy >= 3 and self.local_crop(bot, "empty"):
                actions["farm"] = [""]
            if bot.energy >= 6 and self.local_crop(bot, "ripe"):
                actions["harvest"] = [""]
            if self.can_gather(bot):
                actions["gather"] = [""]
            at_store = distance(bot.position, LOCATIONS["storehouse"]) < 3
            if at_store and (bot.supplies or bot.wood):
                actions["deposit"] = [""]
            if (bot.supplies or (at_store and self.store["food"])) and (bot.hunger >= 5 or bot.energy < 90 or bot.health < 95):
                actions["eat"] = [""]
            repairs = [name for name,pos in GATES.items() if distance(bot.position,pos) < 3.5
                       and self.gates[name] < GATE_MAX and self.store["wood"] > 0 and bot.energy >= 6]
            if repairs:
                actions["repair"] = repairs
        attacks = [m.id for m in self.monsters if m.health > 0 and
                   distance(bot.position,m.position) <= 8 and bot.energy >= 2 and self.time >= bot.attack_at]
        if attacks:
            actions["attack"] = attacks
        if (bot.role == "elder" and self.time >= bot.rally_at and bot.energy >= 4 and self.store["food"] > 0
            and any(v is not bot and v.alive and distance(v.position,bot.position) <= 12
                    and (v.energy < 85 or v.health < 90) for v in self.villagers)):
            actions["rally"] = [""]
        return actions

    def survival_action(self, bot, decision):
        action, target = decision.get("action"), decision.get("target", "")
        allowed = self.available_actions(bot)
        if action not in allowed or target not in allowed[action]:
            return False
        if action == "guard":
            bot.path = pathfind(bot.position, self.destination(bot,target))
            bot.action = f"guarding {target}"
            return True
        if action == "attack":
            monster = next(m for m in self.monsters if m.id == target)
            return self.strike(bot, monster)
        bot.path.clear()
        if action == "farm":
            crop = self.local_crop(bot, "empty")
            crop.stage, crop.age = "growing", 0
            bot.energy -= 3
            bot.contributions["planted"] += 1
            bot.action = "planting crops"
        elif action == "harvest":
            crop = self.local_crop(bot, "ripe")
            crop.stage, crop.age = "empty", 0
            food = 6 if bot.role == "farmer" else 4
            bot.supplies += food
            bot.energy -= 6
            bot.contributions["harvested"] += food
            bot.action = "harvesting"
            self.log(f"{bot.name} harvested {food} food; deliver it to the storehouse.")
        elif action == "deposit":
            for resource, amount in (("food",bot.supplies),("wood",bot.wood)):
                self.store[resource] += amount
                bot.contributions["deposited_"+resource] += amount
            self.log(f"{bot.name} shared {bot.supplies} food and {bot.wood} wood.")
            bot.supplies = bot.wood = 0
            bot.action = "depositing supplies"
        elif action == "eat":
            if bot.supplies:
                bot.supplies -= 1
            else:
                self.store["food"] -= 1
            bot.hunger = max(0,bot.hunger-35)
            bot.energy = min(100,bot.energy+10)
            bot.health = min(100,bot.health+3)
            bot.action = "eating"
        elif action == "repair":
            self.store["wood"] -= 1
            self.gates[target] = min(GATE_MAX, self.gates[target] + (18 if bot.role == "worker" else 10))
            bot.energy -= 6
            bot.contributions["repairs"] += 1
            bot.action = f"repairing {target}"
        elif action == "rally":
            self.store["food"] -= 1
            bot.energy -= 4
            for other in self.villagers:
                if other is not bot and other.alive and distance(bot.position,other.position) <= 12:
                    other.energy = min(100,other.energy+8)
                    other.health = min(100,other.health+4)
                    other.memory.append(f"Edda rallied us: share food, repair gates, and defend together.")
            bot.rally_at = self.time + 25
            bot.contributions["rallies"] += 1
            bot.action = "rallying villagers"
        bot.work_at = self.time + 1
        bot.memory.append(f"I chose {action}. Village health {int(self.village_health)}, shared food {self.store['food']}.")
        return True

    def gate_threats(self):
        return {name: sum(m.health > 0 and m.gate == name for m in self.monsters)
                for name in GATES if any(m.health > 0 and m.gate == name for m in self.monsters)}

    def strike(self, bot, monster):
        if self.time < bot.attack_at or bot.energy < 2 or monster.health <= 0:
            return False
        monster.health = max(0,monster.health-(20 if bot.role == "soldier" else 8))
        bot.energy -= 2
        bot.attack_at = self.time + 1.2
        if monster.health <= 0:
            bot.contributions["kills"] += 1
            bot.memory.append(f"I defeated {monster.id}. Guarding protects the village.")
            self.log(f"{bot.name} defeated {monster.id}.")
        return True

    def spawn_wave(self):
        self.wave += 1
        for _ in range(min(4, 1 + self.wave // 3)):
            if sum(m.health > 0 for m in self.monsters) >= 10:
                break
            gate = self.rng.choice(list(GATES))
            x,y = GATES[gate]
            scale = 31 / 21
            self.monsters.append(Monster(f"monster_{self.next_monster_id}",gate,(x*scale,y*scale)))
            self.next_monster_id += 1
        self.next_wave = self.time + 90
        self.log(f"Alarm! Monster wave {self.wave} is approaching. Defend and repair the gates.")
        for bot in self.villagers:
            bot.memory.append(f"Wave {self.wave}: {self.gate_threats()}. Cooperation is required to survive.")
            bot.next_think = min(bot.next_think,self.time)

    def survival_tick(self, dt):
        for crop in self.crops:
            if crop.stage == "growing":
                crop.age = min(CROP_GROW_SECONDS,crop.age+dt)
                if crop.age >= CROP_GROW_SECONDS:
                    crop.stage = "ripe"
        if self.time >= self.next_wave:
            self.spawn_wave()
        for bot in self.villagers:
            if not bot.alive:
                continue
            bot.hunger = min(100,bot.hunger+dt*.12)
            if bot.hunger > 80:
                bot.health = max(0,bot.health-dt*.4)
            if bot.action.startswith("guarding "):
                threats = [m for m in self.monsters if m.health > 0 and distance(bot.position,m.position) <= 8]
                if threats:
                    self.strike(bot,min(threats,key=lambda m:distance(bot.position,m.position)))
        for monster in self.monsters:
            if monster.health <= 0:
                continue
            gx,gy = GATES[monster.gate]
            outside = (gx * 25/21, gy * 25/21)
            if self.gates[monster.gate] > 0:
                target = outside
                if distance(monster.position,target) < .5:
                    self.gates[monster.gate] = max(0,self.gates[monster.gate]-dt*1.5)
                    continue
            else:
                live = [v for v in self.villagers if v.alive]
                victim = min(live,key=lambda v:distance(v.position,monster.position)) if live else None
                if victim and distance(victim.position,monster.position) < 1.5:
                    victim.health = max(0,victim.health-dt*3)
                    continue
                target = LOCATIONS["square"]
                if distance(monster.position,target) < 2:
                    self.village_health = max(0,self.village_health-dt*2)
                    continue
            d = distance(monster.position,target)
            if d:
                step = min(d,dt*1.4)
                monster.position = tuple(a+(b-a)/d*step for a,b in zip(monster.position,target))
        self.monsters = [m for m in self.monsters if m.health > 0]
        for i,bot in enumerate(self.villagers):
            if not bot.alive and bot.action != "fallen":
                bot.action = "fallen"
                bot.path.clear()
                bot.revision += 1
                self.log(f"{bot.name} has fallen. The village needs help.")
                if self.controlled == i:
                    self.possess(None)
        if self.village_health <= 0:
            self.fail("Monsters destroyed the village center after the defenses failed.")
        elif not any(v.alive for v in self.villagers):
            self.fail("All villagers fell: food and defense cooperation failed.")

    def fail(self, reason):
        if self.failed:
            return
        self.failed, self.failure_reason = True, reason
        breached = [name for name,hp in self.gates.items() if hp <= 0]
        episode = {"attempt":self.campaign["attempt"], "seconds":round(self.time,1),
            "reason":reason, "breached_gates":breached, "store":self.store.copy(),
            "contributions":{v.name:v.contributions.copy() for v in self.villagers}}
        self.campaign["failures"] = (self.campaign["failures"]+[episode])[-20:]
        for bot in self.villagers:
            lesson = (f"Attempt {self.campaign['attempt']} failed: {reason} "
                f"Breached gates: {', '.join(breached) or 'none'}. Shared food {self.store['food']}, wood {self.store['wood']}. "
                f"As {bot.role}, I contributed {bot.contributions}. Next attempt: deposit harvests, eat, supply repairs, and guard threatened gates together.")
            bot.lessons.append(lesson)
            self.campaign["lessons"][bot.name] = list(bot.lessons)
            bot.revision += 1
        self.log("VILLAGE DESTROYED. Lessons recorded. Start with --new-game to try again.")
