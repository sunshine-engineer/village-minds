"""Independent local routines and bounded asynchronous model scheduling.

File: village/brains.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import queue
import threading
import time

from .config import get_settings
from .decisions import decision_schema as decision_schema
from .inference import bounded_decision
from .map_data import GATES, HEARING
from .models import BACKENDS, InferenceDecision, resolve_profile
from .models import request_decision as request_decision
from .navigation import distance, pathfind

S = get_settings()
A, P, R = S["ai"], S["policy"], S["rules"]


class BrainScheduler:
    """Fast local autonomy for everyone; one slow model request for extra decisions."""

    def __init__(self, world, url, model, demo=False, profile=None):
        """Initialize BrainScheduler and its owned state.

        Args:
            world: Authoritative simulation world used by this operation.
            url: Configured model endpoint, or loopback server URL for network sessions.
            model: Installed model tag selected for inference.
            demo: Whether to use local scripted routines without model requests.
            profile: Resolved model profile containing backend and generation options.

        Returns:
            None.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
        self.world, self.url, self.model = world, url, model
        self.demo = demo
        self.profile = profile or resolve_profile(url=url, model=model)
        self.active_profile = self.profile
        if not demo:
            for name in set(A["villager_profiles"].values()):
                if resolve_profile(name)["backend"] not in BACKENDS:
                    raise ValueError(f"Unknown backend in profile: {name}")
            if self.profile["backend"] not in BACKENDS:
                raise ValueError(f"Unknown backend: {self.profile['backend']}")
        self.status = (
            "LOCAL ROUTINES | demo"
            if demo
            else "MODEL: pending | local routines active"
        )
        self.jobs, self.results = queue.Queue(maxsize=1), queue.Queue(maxsize=1)
        self.busy = False
        self.cursor = 0
        self.retry_at = 0
        count = len(world.villagers)
        self.routine_due = [
            world.time + i * A["routine_stagger_seconds"] for i in range(count)
        ]
        self.override_until = [0.0] * count
        self.model_tasks = [None] * count
        self.patrol_due = [world.time] * count
        self.patrol_side = [(-1 if i % 2 else 1) for i in range(count)]
        self.activity_due = [world.time] * count
        self.activity_step = list(range(count))
        self.next_social = world.time + A["initial_social_seconds"]
        self.social_due = [
            world.time + i * A["social_stagger_seconds"] for i in range(count)
        ]
        self.local_decisions = 0
        self.model_decisions = 0
        self.model_history = []
        self.request_count = 0
        self.request_context = None
        if not demo:
            threading.Thread(
                target=self._worker, daemon=True, name="village-model"
            ).start()

    def _worker(self):
        """Process queued inference requests and publish results without mutating the world.

        Returns:
            None; runs as a daemon and communicates through bounded queues.
        """
        while True:
            index, revision, sent_at, observation = self.jobs.get()
            try:
                profile = self.profile_for(observation["name"])
                response = bounded_decision(profile, observation, S, profile["timeout"])
                if response["status"] != "ok":
                    raise TimeoutError(response.get("error", response["status"]))
                self.results.put(
                    (
                        index,
                        revision,
                        sent_at,
                        InferenceDecision(
                            response["decision"], response.get("inference", {})
                        ),
                        None,
                    )
                )
            except Exception as exc:
                self.results.put(
                    (
                        index,
                        revision,
                        sent_at,
                        None,
                        f"{type(exc).__name__}: {str(exc)[:110]}",
                    )
                )

    def _urgent(self, bot):
        """Detect needs or role emergencies that should interrupt a model order.

        Args:
            bot: Villager whose current state or work is being considered.

        Returns:
            Whether urgent local work should take precedence.
        """
        if bot.hunger >= P["urgent_hunger"] or bot.energy < P["urgent_energy"]:
            return True
        threats = self.world.gate_threats()
        if bot.role == "soldier" and threats:
            return not any(bot.action == f"guarding {name}" for name in threats)
        if bot.role == "worker" and self.world.store["wood"]:
            return any(hp < P["urgent_gate_health"] for hp in self.world.gates.values())
        return False

    def _keep_model_task(self, index, bot):
        """Check whether a still-useful model order may continue.

        Args:
            index: Villager roster index selected by the caller.
            bot: Villager whose current state or work is being considered.

        Returns:
            Whether the current model order remains eligible.
        """
        if self._urgent(bot):
            return False
        task = self.model_tasks[index]
        if task == "guard" and bot.action.startswith("guarding "):
            gate = bot.action.removeprefix("guarding ")
            if self.world.gate_threats().get(gate):
                return True
        if self.world.time >= self.override_until[index]:
            return False
        if task == "move":
            return bool(bot.path)
        if task == "guard":
            return bot.action.startswith("guarding ")
        if task == "rest":
            return bot.action == "resting" and bot.energy < P["rest_until_energy"]
        # Short actions/dialogue get a brief turn before routines resume.
        return True

    def _patrol(self, index, bot):
        """Issue a configured patrol destination to an idle villager.

        Args:
            index: Villager roster index selected by the caller.
            bot: Villager whose current state or work is being considered.

        Returns:
            None; may update the villager's movement order.
        """
        world = self.world
        if (
            bot.path
            or not bot.action.startswith("guarding ")
            or world.time < self.patrol_due[index]
            or bot.energy < P["patrol_min_energy"]
        ):
            return
        if any(
            m.health > 0 and distance(bot.position, m.position) <= R["attack_range"]
            for m in world.monsters
        ):
            return
        gate = bot.action.removeprefix("guarding ")
        if gate not in GATES:
            return
        x, y = GATES[gate]
        side = self.patrol_side[index]
        point = (
            (side * A["patrol_distance"], y * A["patrol_coordinate"] / abs(y))
            if x == 0
            else (x * A["patrol_coordinate"] / abs(x), side * A["patrol_distance"])
        )
        bot.path = pathfind(bot.position, point)
        if world.decision_log and bot.path:
            world.decision_log.record(
                "patrol",
                world.time,
                source="local",
                actor=bot.name,
                outcome="accepted",
                target=list(point),
            )
        self.patrol_side[index] = -side
        self.patrol_due[index] = (
            world.time + A["patrol_seconds"] + index * A["patrol_index_seconds"]
        )

    def _idle_activity(self, index, bot):
        """Schedule role-appropriate activity when no urgent job is available.

        Args:
            index: Villager roster index selected by the caller.
            bot: Villager whose current state or work is being considered.

        Returns:
            None; may dispatch a local intent.
        """
        world = self.world
        if (
            bot.path
            or bot.action.startswith("guarding ")
            or bot.energy < P["idle_min_energy"]
            or (bot.action == "resting" and bot.energy < P["rest_until_energy"])
            or world.time < self.activity_due[index]
        ):
            return
        place = (
            "farm"
            if bot.role == "farmer"
            else "storehouse"
            if bot.role == "worker"
            else "square"
        )
        x, y = world.destination(bot, place)
        offsets = A["activity_offsets"]
        dx, dy = offsets[self.activity_step[index] % len(offsets)]
        self.activity_step[index] += 1
        bot.path = pathfind(bot.position, (x + dx, y + dy))
        if bot.path:
            bot.action = (
                "checking crops"
                if bot.role == "farmer"
                else "checking stores"
                if bot.role == "worker"
                else "checking village"
            )
            self.local_decisions += 1
            if world.decision_log:
                world.decision_log.record(
                    "activity",
                    world.time,
                    source="local",
                    actor=bot.name,
                    outcome="accepted",
                    action=bot.action,
                    target=list(bot.path[-1]),
                )
        self.activity_due[index] = (
            world.time + A["activity_seconds"] + index * A["activity_index_seconds"]
        )

    def _routines(self):
        """Run due needs and role policies independently for each eligible villager.

        Returns:
            None; updates local work and scheduling counters.
        """
        world = self.world
        for index, bot in enumerate(world.villagers):
            if (
                not bot.alive
                or index == world.controlled
                or world.time < self.routine_due[index]
            ):
                continue
            self.routine_due[index] = (
                world.time + A["routine_seconds"] + index * A["routine_index_seconds"]
            )
            if self._keep_model_task(index, bot):
                self._patrol(index, bot)
                continue
            decision = world.fallback(bot)
            if decision and world.apply(bot, decision, source="local"):
                self.local_decisions += 1
            if decision is None and world.time >= bot.work_at:
                self._idle_activity(index, bot)
            self._patrol(index, bot)
        self._social()

    def _social(self):
        """Occasional scripted context barks; never stop walking or a work order.

        Returns:
            None; may append dialogue and advance social cooldowns.
        """
        world = self.world
        if world.time < self.next_social:
            return
        self.next_social = world.time + A["social_interval_seconds"]
        candidates = [
            i
            for i, bot in enumerate(world.villagers)
            if bot.alive
            and i != world.controlled
            and world.time >= self.social_due[i]
            and bot.speech_until <= world.time
        ]
        for index in sorted(candidates, key=lambda i: self.social_due[i]):
            bot = world.villagers[index]
            partners = [
                other
                for other in world.villagers
                if other is not bot
                and other.alive
                and distance(bot.position, other.position) <= HEARING
            ]
            if not partners:
                continue
            other = min(partners, key=lambda v: distance(bot.position, v.position))
            threats = world.gate_threats()
            templates = A["social_messages"]
            gate = max(threats, key=threats.get).replace("_", " ") if threats else ""
            if threats:
                template = templates["threat"]
            elif world.store["food"] < A["social_low_food"]:
                template = templates["low_food"]
            elif world.store["wood"] < A["social_low_wood"]:
                template = templates["low_wood"]
            elif bot.supplies:
                template = templates["carrying_food"]
            elif bot.role == "elder" and bot.lessons:
                template = templates["elder_lessons"]
            else:
                template = templates["roles"].get(bot.role, templates["generic"])
            text = template.format(other=other.name, gate=gate, supplies=bot.supplies)
            world.say(bot, text, source="local")
            self.social_due[index] = world.time + A["speaker_cooldown_seconds"]
            break

    def tick(self):
        """Apply completed responses and schedule local work and the next model request.

        Returns:
            None; the caller retains authority over world updates.
        """
        world = self.world
        if world.failed:
            self.status = "VILLAGE LOST | lessons saved with the world"
            return
        try:
            index, revision, sent_at, result, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            context = self.request_context or {}
            self.consume_decision(
                index,
                revision,
                sent_at,
                result,
                error,
                request_id=context.get("id"),
                observation=context.get("observation"),
                latency_ms=(
                    (time.monotonic() - context["started"]) * 1000
                    if "started" in context
                    else None
                ),
            )
            self.request_context = None
        # This runs regardless of model latency, errors, or request cooldowns.
        world.task_board.coordinate()
        self._routines()
        if self.demo or world.time < self.retry_at or self.busy:
            return
        for offset in range(len(world.villagers)):
            index = (self.cursor + offset) % len(world.villagers)
            bot = world.villagers[index]
            if bot.alive and index != world.controlled and world.time >= bot.next_think:
                if A["repair_strategy"]["enabled"]:
                    from .allocation import strategy_observation

                    observation = strategy_observation(world, bot, bot.lessons)
                    if not observation["choices"]:
                        bot.next_think = world.time + A["think_seconds"]
                        continue
                else:
                    observation = world.observe(bot)
                    observation["decision_layer"] = "strategic"
                self.active_profile = self.profile_for(bot.name)
                self.request_count += 1
                self.request_context = {
                    "id": f"model-{self.request_count}",
                    "started": time.monotonic(),
                    "observation": observation,
                }
                if world.decision_log:
                    world.decision_log.record(
                        "model_request",
                        world.time,
                        source="model",
                        actor=bot.name,
                        request_id=self.request_context["id"],
                        observation=observation,
                        model=self.active_profile["model"],
                        backend=self.active_profile["backend"],
                    )
                self.jobs.put_nowait((index, bot.revision, world.time, observation))
                self.busy = True
                self.cursor = (index + 1) % len(world.villagers)
                break

    def profile_for(self, name):
        """Resolve the explicit per-villager profile or scheduler fallback.

        Args:
            name: Registered identity or name selected by the caller.

        Returns:
            Resolved model profile dictionary.
        """
        assigned = A["villager_profiles"].get(name)
        return resolve_profile(assigned) if assigned else self.profile

    def consume_decision(
        self,
        index,
        revision,
        sent_at,
        result,
        error=None,
        *,
        request_id=None,
        observation=None,
        latency_ms=None,
        profile=None,
    ):
        """Common validation/arbitration for live async and evaluation checkpoints.

        Args:
            index: Villager roster index selected by the caller.
            revision: Actor revision captured when inference was requested.
            sent_at: Simulation timestamp captured for the original request.
            result: Returned decision or result envelope being consumed.
            error: Optional failure description from a worker.
            request_id: Optional correlation identifier for decision telemetry.
            observation: Request-time context containing legal choices and relevant world state.
            latency_ms: Optional measured request wall latency in milliseconds.
            profile: Resolved model profile containing backend and generation options.

        Returns:
            Outcome label recording acceptance, rejection, staleness or error.
        """
        world = self.world
        bot = world.villagers[index]
        profile = profile or self.active_profile
        reason = ""
        if error:
            self.status = "MODEL FALLBACK | local routines active | " + error
            self.retry_at = world.time + A["retry_seconds"]
            outcome = "error"
            reason = error
        elif (
            world.failed
            or not bot.alive
            or (
                revision != bot.revision
                and not (
                    isinstance(result, dict)
                    and result.get("action") == "plan_repairs"
                    and (observation or {}).get("decision_layer") == "repair_priority"
                )
            )
            or index == world.controlled
            or world.time - sent_at >= A["max_decision_age_seconds"]
        ):
            outcome = "stale"
            reason = "world_failed_dead_possessed_or_expired"
        else:
            self.status = "MODEL: " + profile["model"] + " | local routines active"
            accepted = world.apply(
                bot,
                result,
                source="model",
                request_id=request_id,
                observation=observation,
            )
            outcome = "accepted" if accepted else "rejected"
            if accepted:
                self.model_decisions += 1
                self.model_history.append(
                    {
                        "name": bot.name,
                        "decision": result,
                        "model": profile["model"],
                        "backend": profile["backend"],
                    }
                )
                del self.model_history[: -A["model_history_limit"]]
                self.model_tasks[index] = result.get("action")
                self.override_until[index] = world.time + (
                    A["plan_seconds"]
                    if result.get("action") in ("move", "guard", "rest")
                    else A["short_plan_seconds"]
                )
            else:
                reason = "unavailable_or_invalid"
                self.status += " | outdated/unavailable choice skipped"
            if accepted and result.get("action") in (
                "dispatch_repair",
                "plan_repairs",
                "defer_strategy",
            ):
                self.model_tasks[index] = None
                self.override_until[index] = world.time
            bot.next_think = world.time + A["think_seconds"]
        if world.decision_log:
            world.decision_log.record(
                "model_response",
                world.time,
                source="model",
                actor=bot.name,
                outcome=outcome,
                reason=reason,
                request_id=request_id,
                decision=result,
                latency_ms=latency_ms,
                inference=getattr(result, "metrics", {}),
                model=profile["model"],
                backend=profile["backend"],
            )
        return outcome
