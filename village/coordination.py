"""Shared, structured help requests and exclusive, voluntary task ownership.

The village board is a public communication channel, not a simulated hearing event.
Model text never becomes instructions: only validated action tokens can change it.
"""

from collections import Counter
from copy import deepcopy
import math
from .config import get_settings
from .map_data import GATES, GATE_MAX, LOCATIONS
from .navigation import distance

MODES = ("independent", "requests", "assigned")
ACTIVE = ("open", "offered", "accepted")


class TaskBoard:
    def __init__(self, world):
        self.world = world
        self.settings = get_settings()["coordination"]
        self.mode = self.settings["mode"]
        self.tasks = []
        self.next_id = 1
        self.next_update = 0.0
        self.counts = Counter()
        self.response_seconds = []
        self.completion_seconds = []
        self.work_response_seconds = []
        self.next_request = {}
        self.next_maintenance = 0.0
        self.strategy_leases = {}
        self.repair_plan = None

    def emit(self, event, task, actor=None, source="task_board"):
        self.counts[event] += 1
        if self.world.decision_log:
            self.world.decision_log.record(
                "task_" + event,
                self.world.time,
                actor=actor,
                source=source,
                task=deepcopy(task),
            )

    def living(self):
        return [
            v
            for i, v in enumerate(self.world.villagers)
            if v.alive and i != self.world.controlled
        ]

    def needs(self):
        w, s = self.world, self.settings
        needs = [("defend", gate) for gate in w.gate_threats()]
        needs += [
            ("repair", gate)
            for gate, hp in w.gates.items()
            if hp < GATE_MAX - get_settings()["policy"]["repair_missing_health"]
        ]
        if w.store["wood"] < s["wood_target"]:
            needs.append(("wood", "storehouse"))
        if w.store["food"] < s["food_target"]:
            needs.append(("food", "storehouse"))
        return sorted(needs, key=lambda item: (s["priority"].index(item[0]), item[1]))

    def done(self, task):
        w = self.world
        kind, target = task["kind"], task["target"]
        if kind == "defend":
            return not w.gate_threats().get(target)
        if kind == "repair":
            return (
                w.gates[target]
                >= GATE_MAX - get_settings()["policy"]["repair_missing_health"]
            )
        return (
            w.store["food" if kind == "food" else "wood"]
            >= self.settings[kind + "_target"]
        )

    def maintain(self):
        if self.world.time < self.next_maintenance:
            return
        self.next_maintenance = self.world.time + self.settings["maintenance_seconds"]
        names = {v.name for v in self.world.villagers if v.alive}
        for task in self.tasks:
            if task["status"] not in ACTIVE:
                continue
            if self.done(task):
                task["status"] = (
                    "completed"
                    if task["accepted_by"] and task["progress_at"] is not None
                    else "resolved"
                )
                task["ended_at"] = self.world.time
                if task["status"] == "completed":
                    self.completion_seconds.append(self.world.time - task["created_at"])
                    self.completion_seconds = self.completion_seconds[
                        -self.settings["history_capacity"] :
                    ]
                self.emit(task["status"], task)
            elif self.world.time >= task["expires_at"]:
                task["status"], task["ended_at"] = "expired", self.world.time
                self.emit("expired", task)
            elif task["assigned_to"] and task["assigned_to"] not in names:
                owner = task["assigned_to"]
                task.update(
                    status="open", assigned_to=None, accepted_by=None, accepted_at=None
                )
                self.strategy_leases.pop(task["id"], None)
                self.emit("released", task, owner)
        # Bound retained history; counters are independent of retained rows.
        active = [t for t in self.tasks if t["status"] in ACTIVE]
        history = [t for t in self.tasks if t["status"] not in ACTIVE]
        self.tasks = history[-self.settings["history_capacity"] :] + active
        active_ids = {t["id"] for t in active}
        self.strategy_leases = {
            k: v
            for k, v in self.strategy_leases.items()
            if k in active_ids and v > self.world.time
        }

    def busy(self, name):
        return any(
            t["status"] in ("offered", "accepted") and t["assigned_to"] == name
            for t in self.tasks
        )

    def ready(self, bot):
        p = get_settings()["policy"]
        return (
            bot in self.living()
            and bot.hunger < p["eat_above_hunger"]
            and bot.energy >= p["rest_below_energy"]
            and not (bot.action == "resting" and bot.energy < p["rest_until_energy"])
        )

    def actions(self, bot):
        if not self.settings["enabled"] or not bot.alive or self.world.failed:
            return {}
        result = {}
        if self.world.time >= self.next_request.get(bot.name, 0):
            targets = [
                f"{kind}:{target}"
                for kind, target in self.needs()
                if not any(
                    t["status"] in ACTIVE and (t["kind"], t["target"]) == (kind, target)
                    for t in self.tasks
                )
            ]
            if (
                targets
                and sum(t["status"] in ACTIVE for t in self.tasks)
                < self.settings["max_active_tasks"]
            ):
                result["request_help"] = targets
        claims = [
            t["id"]
            for t in self.tasks
            if t["status"] == "open"
            or (t["status"] == "offered" and t["assigned_to"] == bot.name)
        ]
        if claims and not self.busy(bot.name):
            result["claim_task"] = claims
        else:
            # An offer reserves a slot, but its recipient can still accept it.
            offers = [
                t["id"]
                for t in self.tasks
                if t["status"] == "offered" and t["assigned_to"] == bot.name
            ]
            if offers:
                result["claim_task"] = offers
        if bot.role in self.settings["assigner_roles"]:
            offers = [
                f"{t['id']}:{v.name}"
                for t in self.tasks
                if t["status"] == "open"
                for v in self.living()
                if not self.busy(v.name)
            ]
            if offers:
                tasks_by_id = {t["id"]: t for t in self.tasks}
                people_by_name = {v.name: v for v in self.living()}

                def offer_score(token):
                    identity, _, name = token.partition(":")
                    task = tasks_by_id[identity]
                    return (
                        self.settings["priority"].index(task["kind"]),
                        self.score(task, people_by_name[name]),
                        token,
                    )

                result["assign_task"] = sorted(offers, key=offer_score)
        releases = [
            t["id"]
            for t in self.tasks
            if t["status"] in ("offered", "accepted") and t["assigned_to"] == bot.name
        ]
        if releases:
            result["release_task"] = releases
        return result

    def execute(self, bot, decision):
        action, target = decision.get("action"), decision.get("target", "")
        if not isinstance(target, str) or target not in self.actions(bot).get(
            action, []
        ):
            return False
        w = self.world
        if action == "request_help":
            kind, place = target.split(":", 1)
            task = dict(
                id=f"task-{self.next_id}",
                kind=kind,
                target=place,
                requested_by=bot.name,
                assigned_to=None,
                accepted_by=None,
                status="open",
                created_at=w.time,
                expires_at=w.time + self.settings["task_ttl_seconds"],
                accepted_at=None,
                ended_at=None,
                progress_at=None,
                work_baseline=0,
            )
            self.next_id += 1
            self.tasks.append(task)
            self.next_request[bot.name] = (
                w.time + self.settings["request_cooldown_seconds"]
            )
            self.emit("requested", task, bot.name)
            w.say(
                bot,
                f"Help needed: {kind} at {place}. See {task['id']} on the village board.",
                source="coordination",
            )
            return True
        identity, _, recipient = target.partition(":")
        task = next(t for t in self.tasks if t["id"] == identity)
        if action == "assign_task":
            task.update(status="offered", assigned_to=recipient)
            self.emit("offered", task, bot.name)
            w.say(
                bot,
                f"{recipient}, please handle {task['kind']} at {task['target']} ({identity}).",
                source="coordination",
            )
        elif action == "claim_task":
            counter = {
                "defend": "kills",
                "repair": "repairs",
                "food": "deposited_food",
                "wood": "deposited_wood",
            }[task["kind"]]
            task.update(
                status="accepted",
                assigned_to=bot.name,
                accepted_by=bot.name,
                accepted_at=w.time,
                work_baseline=bot.contributions[counter],
                progress_at=None,
            )
            self.response_seconds.append(w.time - task["created_at"])
            self.response_seconds = self.response_seconds[
                -self.settings["history_capacity"] :
            ]
            self.emit("accepted", task, bot.name)
            w.say(
                bot,
                f"I'll handle {task['kind']} at {task['target']} ({identity}).",
                source="coordination",
            )
        elif action == "release_task":
            self.strategy_leases.pop(task["id"], None)
            task.update(
                status="open", assigned_to=None, accepted_by=None, accepted_at=None
            )
            self.emit("released", task, bot.name)
        return True

    def plan_priority(self, task):
        plan = self.repair_plan
        strategy = get_settings()["ai"]["repair_strategy"]
        return (
            0
            if (
                strategy["enabled"]
                and strategy["mode"] == "priority_plan"
                and plan
                and self.world.time < plan["expires_at"]
                and task["kind"] == "repair"
                and task["target"] == plan["gate"]
                and not self.done(task)
                and self.world.store["wood"]
                >= get_settings()["rules"]["repair_wood_cost"]
            )
            else 1
        )

    def install_repair_plan(self, bot, gate):
        from .allocation import priority_candidates

        strategy = get_settings()["ai"]["repair_strategy"]
        if strategy["mode"] != "priority_plan" or gate not in [
            c["target"] for c in priority_candidates(self)
        ]:
            return False
        self.repair_plan = dict(
            gate=gate,
            proposed_by=bot.name,
            created_at=self.world.time,
            expires_at=self.world.time + strategy["plan_seconds"],
        )
        self.counts["repair_plans"] += 1
        return True

    def score(self, task, bot):
        if self.settings["resource_aware"]["enabled"] and task["kind"] == "repair":
            from .allocation import repair_features

            features = repair_features(self.world, task, bot)
            return features["cost"] if features else math.inf
        preferences = self.settings["role_preferences"][task["kind"]]
        rank = (
            preferences.index(bot.role) if bot.role in preferences else len(preferences)
        )
        point = GATES.get(
            task["target"], LOCATIONS["orchard" if task["kind"] == "wood" else "farm"]
        )
        return rank * self.settings["role_distance_weight"] + distance(
            bot.position, point
        )

    def coordinate(self):
        self.maintain()
        w = self.world
        if (
            not self.settings["enabled"]
            or self.mode == "independent"
            or w.time < self.next_update
        ):
            return
        self.next_update = w.time + self.settings["update_seconds"]
        people = self.living()
        if not people:
            return
        for kind, target in self.needs():
            candidates = sorted(
                people,
                key=lambda v: (self.score({"kind": kind, "target": target}, v), v.name),
            )
            for requester in candidates:
                token = f"{kind}:{target}"
                if token in self.actions(requester).get("request_help", []):
                    w.apply(
                        requester,
                        {"action": "request_help", "target": token},
                        source="coordination",
                    )
                    break
        if self.settings["repair_handoffs"]:
            self.rebalance_repairs()
        elders = [
            v
            for v in people
            if v.role in self.settings["assigner_roles"] and self.ready(v)
        ]
        if self.mode == "assigned" and elders:
            elder = elders[0]
            for task in sorted(
                self.tasks,
                key=lambda t: (
                    self.settings["priority"].index(t["kind"]),
                    self.plan_priority(t),
                    t["created_at"],
                ),
            ):
                if task["status"] != "open":
                    continue
                candidates = [
                    v for v in people if self.ready(v) and not self.busy(v.name)
                ]
                if candidates:
                    recipient = min(
                        candidates, key=lambda v: (self.score(task, v), v.name)
                    )
                    w.apply(
                        elder,
                        {
                            "action": "assign_task",
                            "target": f"{task['id']}:{recipient.name}",
                        },
                        source="coordination",
                    )

    def release_owner(self, bot, reason):
        for task in self.tasks:
            if (
                task["status"] in ("offered", "accepted")
                and task["assigned_to"] == bot.name
            ):
                task.update(
                    status="open",
                    assigned_to=None,
                    accepted_by=None,
                    accepted_at=None,
                    progress_at=None,
                )
                self.strategy_leases.pop(task["id"], None)
                self.emit("released", task, bot.name)
                if self.world.decision_log:
                    self.world.decision_log.record(
                        "task_handoff",
                        self.world.time,
                        actor=bot.name,
                        reason=reason,
                        task_id=task["id"],
                    )

    def offer_repair(self, proposer, gate, recipient):
        from .allocation import can_handoff

        bot = next((v for v in self.living() if v.name == recipient), None)
        if bot is None or not can_handoff(self, bot, gate):
            return False
        task = next(
            (
                t
                for t in self.tasks
                if t["kind"] == "repair"
                and t["target"] == gate
                and t["status"] in ACTIVE
            ),
            None,
        )
        if task and task["assigned_to"] == recipient:
            return False
        if task is None and f"repair:{gate}" not in self.actions(proposer).get(
            "request_help", []
        ):
            return False
        if task and task["assigned_to"]:
            previous = next(
                v for v in self.world.villagers if v.name == task["assigned_to"]
            )
            self.release_owner(previous, "repair_reallocation")
        self.release_owner(bot, "urgent_repair")
        if task is None:
            # Reuse validated request construction without bypassing board capacity.
            token = f"repair:{gate}"
            if token not in self.actions(proposer).get("request_help", []):
                return False
            self.execute(proposer, {"action": "request_help", "target": token})
            task = next(
                t
                for t in self.tasks
                if t["kind"] == "repair"
                and t["target"] == gate
                and t["status"] in ACTIVE
            )
        task.update(status="offered", assigned_to=recipient)
        self.emit("offered", task, proposer.name)
        return True

    def rebalance_repairs(self):
        from .allocation import can_handoff

        w = self.world
        if w.store["wood"] < get_settings()["rules"]["repair_wood_cost"]:
            return
        for task in sorted(
            self.tasks, key=lambda t: w.gates.get(t["target"], math.inf)
        ):
            if (
                task["kind"] != "repair"
                or task["status"] not in ACTIVE
                or self.strategy_leases.get(task["id"], 0) > w.time
            ):
                continue
            candidates = [
                v for v in self.living() if can_handoff(self, v, task["target"])
            ]
            if not candidates:
                continue
            best = min(candidates, key=lambda v: (self.score(task, v), v.name))
            owner = next(
                (v for v in self.world.villagers if v.name == task["assigned_to"]), None
            )
            if (
                owner
                and self.ready(owner)
                and self.score(task, owner) <= self.score(task, best)
            ):
                continue
            proposer = next(
                (v for v in self.living() if v.role in self.settings["assigner_roles"]),
                best,
            )
            self.offer_repair(proposer, task["target"], best.name)

    def policy(self, bot):
        """Return a task intent; urgent personal needs still belong to normal policy."""
        if not self.settings["enabled"] or not self.ready(bot):
            return None
        w = self.world
        offers = [
            t
            for t in self.tasks
            if t["status"] == "offered" and t["assigned_to"] == bot.name
        ]
        if offers:
            return {"action": "claim_task", "target": offers[0]["id"]}
        task = next(
            (
                t
                for t in self.tasks
                if t["status"] == "accepted" and t["assigned_to"] == bot.name
            ),
            None,
        )
        if task is None and self.mode == "requests" and not self.busy(bot.name):
            choices = [
                t
                for t in self.tasks
                if t["status"] == "open"
                and min(
                    (
                        v
                        for v in self.living()
                        if self.ready(v) and not self.busy(v.name)
                    ),
                    key=lambda v: (self.score(t, v), v.name),
                    default=None,
                )
                is bot
            ]
            if choices:
                choice = min(
                    choices,
                    key=lambda t: (
                        self.settings["priority"].index(t["kind"]),
                        self.plan_priority(t),
                        self.score(t, bot),
                    ),
                )
                return {"action": "claim_task", "target": choice["id"]}
        if task is None:
            return None
        actions = w.available_actions(bot)
        kind, target = task["kind"], task["target"]

        def go(place, action, target=""):
            if target in actions.get(action, []):
                return {"action": action, **({"target": target} if target else {})}
            if bot.path and bot.action == f"walking to {place}":
                return False
            return {"action": "move", "target": place}

        if kind == "defend":
            return (
                {"action": "guard", "target": target}
                if bot.action != f"guarding {target}"
                else False
            )
        if (
            bot.supplies >= get_settings()["policy"]["deposit_at_inventory"]
            or bot.wood >= get_settings()["policy"]["deposit_at_inventory"]
        ):
            return go("storehouse", "deposit")
        if w.time < bot.work_at:
            return False
        if kind == "repair":
            if w.store["wood"] < get_settings()["rules"]["repair_wood_cost"]:
                return None
            return go(target, "repair", target)
        if kind == "wood":
            return go("orchard", "gather")
        if "harvest" in actions:
            return {"action": "harvest"}
        if "farm" in actions:
            return {"action": "farm"}
        return go("farm", "farm") if w.crop_destination(bot) is not None else False

    def note_progress(self, bot, decision, *, target_gate=None):
        for task in self.tasks:
            if (
                task["status"] != "accepted"
                or task["assigned_to"] != bot.name
                or task["progress_at"] is not None
            ):
                continue
            counter = {
                "defend": "kills",
                "repair": "repairs",
                "food": "deposited_food",
                "wood": "deposited_wood",
            }[task["kind"]]
            progress = bot.contributions[counter] > task["work_baseline"]
            if task["kind"] == "defend":
                progress = target_gate == task["target"]
            if task["kind"] == "repair":
                progress = progress and decision.get("target") == task["target"]
            if progress:
                task["progress_at"] = self.world.time
                self.work_response_seconds.append(self.world.time - task["created_at"])
                self.work_response_seconds = self.work_response_seconds[
                    -self.settings["history_capacity"] :
                ]
                self.emit("progress", task, bot.name)

    def summary(self):
        return dict(
            mode=self.mode,
            counts=dict(self.counts),
            active=sum(t["status"] in ACTIVE for t in self.tasks),
            mean_response_seconds=(
                sum(self.response_seconds) / len(self.response_seconds)
                if self.response_seconds
                else None
            ),
            mean_productive_response_seconds=(
                sum(self.work_response_seconds) / len(self.work_response_seconds)
                if self.work_response_seconds
                else None
            ),
            latency_sample_limit=self.settings["history_capacity"],
            mean_completion_seconds=(
                sum(self.completion_seconds) / len(self.completion_seconds)
                if self.completion_seconds
                else None
            ),
        )

    def observe(self):
        return deepcopy([t for t in self.tasks if t["status"] in ACTIVE])

    def snapshot(self):
        return deepcopy(
            dict(
                tasks=self.tasks,
                strategy_leases=self.strategy_leases,
                repair_plan=self.repair_plan,
                next_id=self.next_id,
                counts=dict(self.counts),
                response_seconds=self.response_seconds,
                work_response_seconds=self.work_response_seconds,
                completion_seconds=self.completion_seconds,
                next_request=self.next_request,
            )
        )

    def restore(self, saved):
        # Strictly validate data before installing state; never execute saved text.
        saved = deepcopy(saved)
        if isinstance(saved, dict):
            saved.setdefault("strategy_leases", {})
            saved.setdefault("repair_plan", None)
        if not isinstance(saved, dict) or set(saved) != set(self.snapshot()):
            raise ValueError("Invalid task board state")
        names = {v.name for v in self.world.villagers}
        if (
            not isinstance(saved["tasks"], list)
            or len(saved["tasks"])
            > self.settings["history_capacity"] + self.settings["max_active_tasks"]
        ):
            raise ValueError("Invalid task history")
        ids = set()
        template = dict(
            id="",
            kind="",
            target="",
            requested_by="",
            assigned_to=None,
            accepted_by=None,
            status="",
            created_at=0,
            expires_at=0,
            accepted_at=None,
            ended_at=None,
            progress_at=None,
            work_baseline=0,
        )

        def number(value):
            return (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value)
                and 0 <= value <= 1e12
            )

        for task in saved["tasks"]:
            if not isinstance(task, dict) or set(task) != set(template):
                raise ValueError("Invalid saved task fields")
            identity = task["id"]
            if (
                not isinstance(identity, str)
                or not identity.startswith("task-")
                or not identity[5:].isdigit()
                or identity in ids
            ):
                raise ValueError("Invalid task identity")
            if len(identity) > 50:
                raise ValueError("Invalid task identity length")
            ids.add(identity)
            if task["kind"] not in self.settings["priority"] or task["status"] not in (
                *ACTIVE,
                "completed",
                "resolved",
                "expired",
            ):
                raise ValueError("Invalid task type/status")
            if task["target"] not in (
                GATES if task["kind"] in ("defend", "repair") else {"storehouse": None}
            ):
                raise ValueError("Invalid task destination")
            if task["requested_by"] not in names or any(
                task[k] is not None and task[k] not in names
                for k in ("assigned_to", "accepted_by")
            ):
                raise ValueError("Invalid task participant")
            if type(task["work_baseline"]) is not int or task["work_baseline"] < 0:
                raise ValueError("Invalid task baseline")
            if any(not number(task[k]) for k in ("created_at", "expires_at")) or any(
                task[k] is not None and not number(task[k])
                for k in ("accepted_at", "ended_at", "progress_at")
            ):
                raise ValueError("Invalid task timestamp")
        if (
            type(saved["next_id"]) is not int
            or saved["next_id"] < 1
            or any(int(i[5:]) >= saved["next_id"] for i in ids)
        ):
            raise ValueError("Invalid next task id")
        if not isinstance(saved["counts"], dict) or any(
            k
            not in (
                "repair_plans",
                "requested",
                "offered",
                "accepted",
                "completed",
                "resolved",
                "expired",
                "released",
                "progress",
            )
            or type(v) is not int
            or v < 0
            for k, v in saved["counts"].items()
        ):
            raise ValueError("Invalid task counters")
        for key in ("response_seconds", "work_response_seconds", "completion_seconds"):
            if (
                not isinstance(saved[key], list)
                or len(saved[key]) > self.settings["history_capacity"]
                or any(not number(v) for v in saved[key])
            ):
                raise ValueError("Invalid task latencies")
        if not isinstance(saved["next_request"], dict) or any(
            k not in names or not number(v) for k, v in saved["next_request"].items()
        ):
            raise ValueError("Invalid request cooldowns")
        owners = [
            t["assigned_to"]
            for t in saved["tasks"]
            if t["status"] in ("offered", "accepted")
        ]
        pairs = [
            (t["kind"], t["target"]) for t in saved["tasks"] if t["status"] in ACTIVE
        ]
        if (
            None in owners
            or len(set(owners)) != len(owners)
            or len(set(pairs)) != len(pairs)
        ):
            raise ValueError("Conflicting task ownership")
        if (
            sum(t["status"] in ACTIVE for t in saved["tasks"])
            > self.settings["max_active_tasks"]
        ):
            raise ValueError("Too many active tasks")
        for task in saved["tasks"]:
            if task["expires_at"] < task["created_at"] or (
                task["status"] == "accepted"
                and (
                    task["accepted_by"] != task["assigned_to"]
                    or task["accepted_at"] is None
                )
            ):
                raise ValueError("Invalid task lifecycle")
        for task in saved["tasks"]:
            if task["created_at"] > self.world.time:
                raise ValueError("Future task creation")
            for field in ("accepted_at", "ended_at", "progress_at"):
                if (
                    task[field] is not None
                    and not task["created_at"] <= task[field] <= self.world.time
                ):
                    raise ValueError("Invalid task timestamp order")
            if task["status"] == "open" and any(
                task[k] is not None
                for k in ("assigned_to", "accepted_by", "accepted_at")
            ):
                raise ValueError("An open task cannot have an owner")
            if task["status"] == "offered" and (
                task["accepted_by"] is not None or task["accepted_at"] is not None
            ):
                raise ValueError("An offer cannot be accepted already")
            if task["status"] in ACTIVE and task["ended_at"] is not None:
                raise ValueError("Active task has an end timestamp")
        leases = saved["strategy_leases"]
        if (
            not isinstance(leases, dict)
            or len(leases) > self.settings["max_active_tasks"]
            or any(k not in ids or not number(v) for k, v in leases.items())
        ):
            raise ValueError("Invalid strategic leases")
        plan = saved["repair_plan"]
        if plan is not None and (
            not isinstance(plan, dict)
            or set(plan) != {"gate", "proposed_by", "created_at", "expires_at"}
            or not isinstance(plan["gate"], str)
            or plan["gate"] not in self.world.gates
            or not isinstance(plan["proposed_by"], str)
            or plan["proposed_by"] not in names
            or not number(plan["created_at"])
            or not number(plan["expires_at"])
            or plan["expires_at"] <= plan["created_at"]
        ):
            raise ValueError("Invalid repair priority plan")
        self.repair_plan = deepcopy(plan)
        self.strategy_leases = leases.copy()
        self.tasks = deepcopy(saved["tasks"])
        self.next_id = saved["next_id"]
        self.counts = Counter(saved["counts"])
        self.response_seconds = saved["response_seconds"][:]
        self.completion_seconds = saved["completion_seconds"][:]
        self.work_response_seconds = saved["work_response_seconds"][:]
        self.next_request = saved["next_request"].copy()
        self.maintain()
