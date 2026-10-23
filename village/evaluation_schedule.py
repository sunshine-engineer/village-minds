"""Deterministic role-balanced model checkpoints for bounded comparisons.

File: village/evaluation_schedule.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import hashlib
from collections import Counter


class CheckpointSchedule:
    """Seed-deterministic role rotation and horizon-spread threat-aware checkpoints."""

    def __init__(self, world, seed, options):
        """Initialize CheckpointSchedule and its owned state.

        Args:
            world: Authoritative simulation world used by this operation.
            seed: Nonnegative deterministic world/randomization seed.
            options: Validated run settings and budgets.

        Returns:
            None.
        """
        self.strategy = options["checkpoint_strategy"]
        self.gap = options["checkpoint_seconds"]
        self.budget = options["max_model_calls"]
        self.horizon = options["duration_seconds"]
        roles = list(options["role_order"])
        rotation = int(hashlib.sha256(str(seed).encode()).hexdigest(), 16) % len(roles)
        self.roles = roles[rotation:] + roles[:rotation]
        self.expected_roles = sorted(
            {v.role for v in world.villagers if v.alive and v.role in roles}
        )
        start = options["checkpoint_start_seconds"]
        if self.strategy == "threats":
            start = max(start, world.next_wave)
            span = max(0, self.horizon - start)
            self.planned_times = [
                start + span * i / self.budget for i in range(self.budget)
            ]
        else:
            self.planned_times = [start + i * self.gap for i in range(self.budget)]
        self.cursor = 0
        self.actor_counts = Counter()
        self.history = []

    def ready(self, world):
        """Check the next planned slot, spacing and optional active-threat requirement.

        Args:
            world: Authoritative simulation world used by this operation.

        Returns:
            Whether a model checkpoint can be considered now.
        """
        issued = len(self.history)
        if world.failed or issued >= self.budget:
            return False
        due = self.planned_times[issued]
        if self.history:
            due = max(due, self.history[-1]["sim_time"] + self.gap)
        return world.time + 1e-9 >= due and (
            self.strategy != "threats" or bool(world.gate_threats())
        )

    def take(self, world, eligible=None):
        """Issue at most once per slot; missing/dead roles are skipped explicitly.

        Args:
            world: Authoritative simulation world used by this operation.
            eligible: Optional predicate restricting candidate proposers.

        Returns:
            Actor index/context pair, or None when no eligible checkpoint can be issued.
        """
        if not self.ready(world):
            return None
        for offset in range(len(self.roles)):
            role_index = (self.cursor + offset) % len(self.roles)
            role = self.roles[role_index]
            candidates = [
                i
                for i, v in enumerate(world.villagers)
                if v.alive
                and i != world.controlled
                and v.role == role
                and (eligible is None or eligible(v))
            ]
            if not candidates:
                continue
            index = min(candidates, key=lambda i: (self.actor_counts[i], i))
            bot = world.villagers[index]
            context = {
                "checkpoint_strategy": self.strategy,
                "planned_time": self.planned_times[len(self.history)],
                "sim_time": world.time,
                "actor": bot.name,
                "role": role,
                "wave": world.wave,
                "active_threats": world.gate_threats().copy(),
            }
            self.history.append(context)
            self.actor_counts[index] += 1
            self.cursor = (role_index + 1) % len(self.roles)
            return index, context
        return None

    def coverage(self):
        """Report actual role/threat requests separately from unused call budget.

        Returns:
            JSON-compatible coverage dictionary.
        """
        return {
            "roles_expected": self.expected_roles,
            "roles_requested": sorted({r["role"] for r in self.history}),
            "actors_requested": sorted({r["actor"] for r in self.history}),
            "requests_by_role": dict(Counter(r["role"] for r in self.history)),
            "active_threat_requests": sum(
                bool(r["active_threats"]) for r in self.history
            ),
            "quiet_requests": sum(not r["active_threats"] for r in self.history),
            "planned_times": self.planned_times,
            "history": self.history.copy(),
        }
