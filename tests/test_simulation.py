"""Test simulation.

File: tests/test_simulation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import threading
import unittest
from unittest.mock import patch

from village.brains import BrainScheduler, decision_schema, request_decision
from village.simulation import LIMIT, LOCATIONS, World, pathfind, walkable


class SimulationTests(unittest.TestCase):
    """Regression cases for simulation."""

    def test_perception_is_local(self):
        """Verify perception is local.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        bot, near, far = world.villagers[:3]
        bot.position, near.position, far.position = (0, 0), (3, 0), (23, 23)
        names = [v["name"] for v in world.observe(bot)["nearby_villagers"]]
        self.assertIn(near.name, names)
        self.assertNotIn(far.name, names)
        self.assertIn(near.name, world.observe(bot)["conversation_partners"])
        self.assertNotIn(far.name, world.observe(bot)["conversation_partners"])
        self.assertNotIn("orchard", world.observe(bot)["nearby_places"])

    def test_hearing_is_local_and_memory_bounded(self):
        """Verify hearing is local and memory bounded.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        speaker, near, far = world.villagers[:3]
        speaker.position, near.position, far.position = (0, 0), (3, 0), (23, 23)
        for i in range(12):
            world.say(speaker, f"hello {i}")
        self.assertEqual(len(near.memory), 8)
        self.assertEqual(len(far.memory), 0)
        self.assertIn("hello 11", near.memory[-1])

    def test_rejects_unavailable_and_malformed_actions(self):
        """Verify rejects unavailable and malformed actions.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        bot = world.villagers[0]
        for decision in [
            None,
            [],
            {"action": "shell"},
            {"action": "gather"},
            {"action": "move", "target": []},
            {"action": "move", "target": "moon"},
            {"action": "talk", "target": "Mira", "dialogue": "hello"},
            {"action": "talk", "target": "Bram", "dialogue": 23},
        ]:
            self.assertFalse(world.apply(bot, decision), decision)
        self.assertEqual(bot.supplies, 0)

    def test_harvest_competition_and_recovery(self):
        """Verify harvest competition and recovery.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        a, b = world.villagers[:2]
        a.position = b.position = LOCATIONS["farm"]
        for crop in world.crops[1:]:
            crop.stage = "empty"
        self.assertTrue(world.apply(a, {"action": "harvest"}))
        self.assertFalse(world.apply(b, {"action": "harvest"}))
        self.assertEqual(a.supplies, 6)
        self.assertEqual(a.energy, 94)
        world.apply(a, {"action": "rest"})
        for _ in range(20):
            world.tick(0.1)
        self.assertEqual(a.energy, 100)

    def test_player_can_rest_and_release_returns_to_ai(self):
        """Verify player can rest and release returns to ai.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        world.possess(0)
        bot = world.villagers[0]
        bot.energy = 30
        world.apply(bot, {"action": "rest"})
        world.tick(0.1)
        self.assertGreater(bot.energy, 30)
        world.move_player(1, 0, 0.1)
        self.assertEqual(bot.action, "player")
        world.possess(None)
        self.assertEqual(bot.action, "idle")
        self.assertEqual(bot.next_think, world.time)

    def test_astar_routes_around_house(self):
        """Verify astar routes around house.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        route = pathfind((-11, -20), (-11, -10))
        self.assertTrue(route)
        self.assertTrue(all(walkable(*cell) for cell in route))
        self.assertGreater(len(route), 10)
        self.assertEqual(route[-1], (-11, -10))
        self.assertEqual(pathfind((0, 0), (-11, -15)), [])

    def test_player_cannot_enter_house_or_leave_map(self):
        """Verify player cannot enter house or leave map.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        world.possess(0)
        bot = world.villagers[0]
        bot.position = (-11, -18.2)
        for _ in range(20):
            world.move_player(0, 1, 0.1)
        self.assertTrue(walkable(*bot.position))
        bot.position = (LIMIT, 0)
        world.move_player(1, 0, 0.1)
        self.assertEqual(bot.position, (LIMIT, 0))

    def test_takeover_clears_path_and_stale_model_result(self):
        """Verify takeover clears path and stale model result.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        bot = world.villagers[0]
        world.apply(bot, {"action": "move", "target": "farm"})
        revision = bot.revision
        scheduler = BrainScheduler(world, "", "", demo=True)
        world.possess(0)
        self.assertEqual(bot.path, [])
        scheduler.results.put((0, revision, world.time, {"action": "rest"}, None))
        scheduler.tick()
        self.assertEqual(bot.action, "player")
        world.possess(None)
        self.assertGreater(bot.revision, revision)

    def test_demo_has_activity_without_model(self):
        """Verify demo has activity without model.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        scheduler = BrainScheduler(world, "", "", demo=True)
        for _ in range(1200):
            world.tick(0.1)
            scheduler.tick()
        self.assertGreater(
            sum(v.contributions["harvested"] for v in world.villagers), 0
        )
        self.assertTrue(any(v.memory for v in world.villagers))
        self.assertTrue(all(walkable(*v.position) for v in world.villagers))

    def test_failure_switches_to_fallback(self):
        """Verify failure switches to fallback.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        scheduler = BrainScheduler(world, "", "", demo=True)
        scheduler.demo = False
        scheduler.results.put((0, 0, 0, None, "connection refused"))
        scheduler.tick()
        self.assertIn("FALLBACK", scheduler.status)
        self.assertEqual(scheduler.retry_at, 20)


class APIContractTests(unittest.TestCase):
    """Regression cases for simulation."""

    def test_scheduler_runs_inference_off_main_thread(self):
        """Verify scheduler runs inference off main thread.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        # Prevent this worker test dispatching another real request after its
        # one mocked result is consumed and the patch context closes.
        for bot in world.villagers[1:]:
            bot.next_think = 100
        main_thread = threading.get_ident()
        calls = []

        def infer(*args, **kwargs):
            """Return the mocked structured response used by this simulation test.

            Args:
                *args: Parsed command-line options for this entry point.
                **kwargs: Keyword options forwarded to the owning implementation.

            Returns:
                Structured response fixture.
            """
            calls.append(threading.get_ident())
            return {"status": "ok", "decision": {"action": "rest"}}

        with patch("village.brains.bounded_decision", side_effect=infer):
            scheduler = BrainScheduler(world, "http://localhost:11434", "test-model")
            scheduler.tick()
            self.assertTrue(scheduler.busy)
            result = scheduler.results.get(timeout=2)
            scheduler.results.put(result)
            scheduler.tick()
        self.assertEqual(world.villagers[0].action, "resting")
        self.assertNotEqual(calls[0], main_thread)

    def test_schema_restricts_talk_and_gather_to_senses(self):
        """Verify schema restricts talk and gather to senses.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        world = World()
        bot = world.villagers[0]
        bot.position = (24, 24)
        schema = decision_schema(world.observe(bot))
        actions = [
            branch["properties"]["action"]["enum"][0] for branch in schema["oneOf"]
        ]
        self.assertNotIn("talk", actions)
        self.assertNotIn("gather", actions)
        bot.position = world.villagers[1].position
        schema = decision_schema(world.observe(bot))
        talk = next(
            b for b in schema["oneOf"] if b["properties"]["action"]["enum"] == ["talk"]
        )
        self.assertEqual(
            talk["properties"]["target"]["enum"],
            world.observe(bot)["conversation_partners"],
        )
        bot.position = LOCATIONS["orchard"]
        schema = decision_schema(world.observe(bot))
        self.assertTrue(
            any(
                b["properties"]["action"]["enum"] == ["gather"] for b in schema["oneOf"]
            )
        )

    def test_ollama_contract(self):
        """Verify ollama contract.

        Returns:
            None; unittest assertions report a regression on failure.
        """

        class Response:
            """Context-managed mock HTTP response with bounded read behavior."""

            def __enter__(self):
                """Return the mock HTTP response when entering the request context.

                Returns:
                    This mock response instance.
                """
                return self

            def __exit__(self, *args):
                """Complete the mock response context without suppressing exceptions.

                Args:
                    *args: Parsed command-line options for this entry point.

                Returns:
                    None; performs the side effects described above.
                """
                pass

            def read(self, limit):
                """Return mock response bytes subject to the requested response-read limit.

                Args:
                    limit: Maximum number of response bytes requested by the transport.

                Returns:
                    Mock response bytes.
                """
                return json.dumps(
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "talk",
                                    "target": "Bram",
                                    "dialogue": "Hello!",
                                }
                            )
                        }
                    }
                ).encode()

        with patch("urllib.request.urlopen", return_value=Response()) as send:
            result = request_decision(
                "http://localhost:11434/",
                "test-model",
                {"name": "Mira", "personality": "patient"},
            )
        self.assertEqual(result["action"], "talk")
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["format"]["type"], "object")
        self.assertEqual(send.call_args.kwargs["timeout"], 25)


if __name__ == "__main__":
    unittest.main()
