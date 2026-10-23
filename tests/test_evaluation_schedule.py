"""Coverage is deterministic and explicit even with small model-call budgets.

File: tests/test_evaluation_schedule.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import unittest
from copy import deepcopy
from types import SimpleNamespace

from village.config import get_settings
from village.evaluation_schedule import CheckpointSchedule


def fixture_world():
    """Construct a world with active gate threats for schedule coverage tests.

    Returns:
        Controlled World instance.
    """
    cast = get_settings()["world"]["cast"]
    world = SimpleNamespace(
        time=0.0,
        next_wave=180.0,
        wave=0,
        failed=False,
        controlled=None,
        villagers=[
            SimpleNamespace(name=v["name"], role=v["role"], alive=True) for v in cast
        ],
        threats={},
    )
    world.gate_threats = lambda: world.threats
    return world


class CheckpointScheduleTests(unittest.TestCase):
    """Regression cases for evaluation schedule."""

    def options(self, calls):
        """Build bounded checkpoint options for the requested call count.

        Args:
            calls: Maximum checkpoint call count in this schedule fixture.

        Returns:
            Checkpoint options dictionary.
        """
        options = deepcopy(get_settings()["evaluation"])
        options.update(
            max_model_calls=calls, duration_seconds=900.0, checkpoint_strategy="threats"
        )
        return options

    def test_two_calls_are_spread_across_horizon_and_require_real_threats(self):
        """Verify two calls are spread across horizon and require real threats.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        schedule = CheckpointSchedule(world, 7, self.options(2))
        self.assertEqual(schedule.planned_times, [180.0, 540.0])
        self.assertIsNone(schedule.take(world))
        world.time = 180.0
        self.assertIsNone(schedule.take(world))
        world.threats = {"west_gate": 1}
        world.wave = 1
        index, context = schedule.take(world)
        self.assertEqual(context["role"], "worker")
        self.assertEqual(context["active_threats"], world.threats)
        world.time = 539.9
        self.assertFalse(schedule.ready(world))
        world.time = 540.0
        world.wave = 5
        self.assertIsNotNone(schedule.take(world))
        self.assertFalse(schedule.ready(world))
        self.assertEqual(schedule.coverage()["active_threat_requests"], 2)

    def test_four_calls_cover_all_roles(self):
        """Verify four calls cover all roles.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        schedule = CheckpointSchedule(world, 7, self.options(4))
        world.threats = {"north_gate": 1}
        for due in schedule.planned_times:
            world.time = due
            world.wave += 1
            self.assertIsNotNone(schedule.take(world))
        self.assertEqual(
            set(schedule.coverage()["roles_requested"]),
            {"soldier", "worker", "farmer", "elder"},
        )
        self.assertEqual(schedule.planned_times, [180.0, 360.0, 540.0, 720.0])

    def test_small_budgets_rotate_roles_across_seeds(self):
        """Verify small budgets rotate roles across seeds.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        roles = set()
        for seed in (7, 19, 31):
            world = fixture_world()
            world.threats = {"east_gate": 1}
            schedule = CheckpointSchedule(world, seed, self.options(2))
            twin = CheckpointSchedule(world, seed, self.options(2))
            self.assertEqual(schedule.roles, twin.roles)
            for due in schedule.planned_times:
                world.time = due
                schedule.take(world)
            roles.update(schedule.coverage()["roles_requested"])
        self.assertEqual(roles, {"soldier", "worker", "farmer", "elder"})

    def test_same_role_actors_are_rotated_before_reusing_actor(self):
        """Verify same role actors are rotated before reusing actor.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        world.threats = {"south_gate": 1}
        schedule = CheckpointSchedule(world, 7, self.options(8))
        for due in schedule.planned_times:
            world.time = due
            schedule.take(world)
        farmers = [r["actor"] for r in schedule.history if r["role"] == "farmer"]
        soldiers = [r["actor"] for r in schedule.history if r["role"] == "soldier"]
        self.assertEqual(farmers, ["Mira", "Iris"])
        self.assertEqual(soldiers, ["Otto", "Nell"])

    def test_missing_role_does_not_consume_a_request_or_select_dead_actor(self):
        """Verify missing role does not consume a request or select dead actor.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        for bot in world.villagers:
            if bot.role == "worker":
                bot.alive = False
        world.time = 180.0
        world.threats = {"north_gate": 1}
        schedule = CheckpointSchedule(world, 7, self.options(2))
        index, context = schedule.take(world)
        self.assertTrue(world.villagers[index].alive)
        self.assertEqual(context["role"], "farmer")
        self.assertNotIn("worker", schedule.coverage()["roles_expected"])
        self.assertEqual(len(schedule.history), 1)

    def test_quiet_scenario_records_no_fabricated_threat_calls(self):
        """Verify quiet scenario records no fabricated threat calls.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        schedule = CheckpointSchedule(world, 7, self.options(2))
        world.time = 890
        self.assertIsNone(schedule.take(world))
        self.assertEqual(schedule.coverage()["active_threat_requests"], 0)
        self.assertEqual(schedule.coverage()["roles_requested"], [])

    def test_interval_mode_keeps_fixed_times_and_reports_quiet_context(self):
        """Verify interval mode keeps fixed times and reports quiet context.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        options = self.options(2)
        options["checkpoint_strategy"] = "interval"
        schedule = CheckpointSchedule(world, 7, options)
        self.assertEqual(schedule.planned_times, [0.0, 30.0])
        schedule.take(world)
        world.time = 30.0
        schedule.take(world)
        self.assertEqual(schedule.coverage()["quiet_requests"], 2)

    def test_zero_budget_is_safe(self):
        """Verify zero budget is safe.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = fixture_world()
        schedule = CheckpointSchedule(world, 7, self.options(0))
        self.assertEqual(schedule.planned_times, [])
        self.assertFalse(schedule.ready(world))


if __name__ == "__main__":
    unittest.main()
