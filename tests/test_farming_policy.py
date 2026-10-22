"""Policy regressions: choose executable work or navigate to a specific plot."""

import unittest
from village.world import World
from village.brains import BrainScheduler
from village.entities import Crop
from village.navigation import distance, walkable, work_point, pathfind
from village.config import get_settings


class FarmingPolicyTests(unittest.TestCase):
    def isolated_elder(self):
        world = World()
        bot = world.villagers[5]
        for other in world.villagers:
            if other is not bot:
                other.health = 0
        bot.position = (-11.0, 7.5)
        return world, bot

    def advance(self, world, brains, seconds):
        for _ in range(round(seconds * 10)):
            world.tick(0.1)
            brains.tick()

    def test_small_work_radius_can_finish_movement_within_same_grid_cell(self):
        point = work_point((0.4, 0), (0, 0), 0.2)
        self.assertEqual(point, (0, 0))
        self.assertEqual(pathfind((0.4, 0), point), [(0, 0)])
        self.assertEqual(pathfind(point, point), [])

    def test_out_of_range_harvest_does_not_block_nearby_planting(self):
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
        world, bot = self.isolated_elder()
        for index, crop in enumerate(world.crops):
            crop.stage = "ripe" if index == 0 else "growing"
        self.assertEqual(world.fallback(bot), {"action": "move", "target": "farm"})
        start = bot.position
        self.advance(world, BrainScheduler(world, "", "", demo=True), 10)
        self.assertNotEqual(bot.position, start)
        self.assertGreater(bot.contributions["harvested"], 0)

    def test_custom_distant_plot_is_reached_instead_of_returning_to_farm_center(self):
        world, bot = self.isolated_elder()
        bot.position = (-14, 9)
        world.crops = [Crop((-21, 15), "ripe")]
        self.advance(world, BrainScheduler(world, "", "", demo=True), 15)
        self.assertGreater(bot.contributions["harvested"], 0)

    def test_work_cooldown_preserves_current_order_without_retrying_harvest(self):
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
