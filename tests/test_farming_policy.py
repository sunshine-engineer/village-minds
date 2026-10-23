"""Policy regressions: choose executable work or navigate to a specific plot.

File: tests/test_farming_policy.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import unittest

from village.brains import BrainScheduler
from village.config import get_settings
from village.entities import Crop
from village.navigation import distance, pathfind, walkable, work_point
from village.world import World


class FarmingPolicyTests(unittest.TestCase):
    """Regression cases for farming policy."""

    def isolated_elder(self):
        """Create a world where only the elder can perform the tested crop work.

        Returns:
            World and elder fixture.
        """
        world = World()
        bot = world.villagers[5]
        for other in world.villagers:
            if other is not bot:
                other.health = 0
        bot.position = (-11.0, 7.5)
        return world, bot

    def advance(self, world, brains, seconds):
        """Advance a deterministic fixture using the ordinary world and optional local scheduler.

        Args:
            world: Authoritative simulation world used by this operation.
            brains: Scheduler responsible for local policies and bounded inference.
            seconds: Requested simulated duration in seconds.

        Returns:
            None; performs the side effects described above.
        """
        for _ in range(round(seconds * 10)):
            world.tick(0.1)
            brains.tick()

    def test_small_work_radius_can_finish_movement_within_same_grid_cell(self):
        """Verify small work radius can finish movement within same grid cell.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        point = work_point((0.4, 0), (0, 0), 0.2)
        self.assertEqual(point, (0, 0))
        self.assertEqual(pathfind((0.4, 0), point), [(0, 0)])
        self.assertEqual(pathfind(point, point), [])

    def test_out_of_range_harvest_does_not_block_nearby_planting(self):
        """Verify out of range harvest does not block nearby planting.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world, bot = self.isolated_elder()
        for index, crop in enumerate(world.crops):
            crop.stage = "ripe" if index == 0 else "empty"
        self.assertNotIn("harvest", world.available_actions(bot))
        self.assertIn("farm", world.available_actions(bot))
        decision = world.fallback(bot)
        self.assertEqual(decision, {"action": "farm"})
        self.assertTrue(world.apply(bot, decision))
        self.assertEqual(bot.contributions["planted"], 1)

    def test_walks_to_ripe_crop_when_no_local_work_is_available(self):
        """Verify walks to ripe crop when no local work is available.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world, bot = self.isolated_elder()
        for index, crop in enumerate(world.crops):
            crop.stage = "ripe" if index == 0 else "growing"
        self.assertEqual(world.fallback(bot), {"action": "move", "target": "farm"})
        start = bot.position
        self.advance(world, BrainScheduler(world, "", "", demo=True), 10)
        self.assertNotEqual(bot.position, start)
        self.assertGreater(bot.contributions["harvested"], 0)

    def test_custom_distant_plot_is_reached_instead_of_returning_to_farm_center(self):
        """Verify custom distant plot is reached instead of returning to farm center.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world, bot = self.isolated_elder()
        bot.position = (-14, 9)
        world.crops = [Crop((-21, 15), "ripe")]
        self.advance(world, BrainScheduler(world, "", "", demo=True), 15)
        self.assertGreater(bot.contributions["harvested"], 0)

    def test_work_cooldown_preserves_current_order_without_retrying_harvest(self):
        """Verify work cooldown preserves current order without retrying harvest.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world, bot = self.isolated_elder()
        bot.position = (-14, 9)
        bot.work_at = 5
        self.assertIsNone(world.fallback(bot))
        brains = BrainScheduler(world, "", "", demo=True)
        before = bot.position
        self.advance(world, brains, 1)
        self.assertEqual(bot.position, before)
        self.assertEqual(bot.contributions["harvested"], 0)

    def test_blocked_crop_center_has_a_walkable_in_range_work_point(self):
        """Verify blocked crop center has a walkable in range work point.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world, bot = self.isolated_elder()
        bot.position = (-11, -20)
        world.crops = [Crop((-11, -15), "ripe")]
        point = world.crop_destination(bot)
        self.assertIsNotNone(point)
        self.assertTrue(walkable(*point))
        self.assertLess(
            distance(point, world.crops[0].position),
            get_settings()["rules"]["crop_radius"],
        )
        self.advance(world, BrainScheduler(world, "", "", demo=True), 15)
        self.assertGreater(bot.contributions["harvested"], 0)


if __name__ == "__main__":
    unittest.main()
