"""Input must be published before potentially expensive snapshot restoration."""

import unittest
from types import SimpleNamespace
from village.client import game_class


class ClientInputTests(unittest.TestCase):
    def test_input_precedes_poll_and_remains_normalized(self):
        from village.game import C

        order = []

        class Session:
            connected = True
            status = "CONNECTED"

            def __init__(self):
                self.motion = (0.0, 0.0)

            def poll(self):
                order.append("poll")
                self.observed = self.motion
                return None

        session = Session()
        presentation = SimpleNamespace(sample=lambda now: ({}, 0.0))
        game = SimpleNamespace(
            session=session,
            presentation=presentation,
            world=SimpleNamespace(controlled=0),
            brains=SimpleNamespace(status=""),
            keys={C["right"], C["forward"]},
            orbit=0.0,
            typing=False,
        )
        game_class().advance_world(game, 0.016)
        self.assertAlmostEqual(sum(x * x for x in session.observed), 1.0)
        self.assertGreater(session.observed[0], 0)
        self.assertGreater(session.observed[1], 0)
        game.typing = True
        game_class().advance_world(game, 0.016)
        self.assertEqual(session.observed, (0.0, 0.0))
        session.connected = False
        game_class().advance_world(game, 0.016)
        self.assertIsNone(game.world.controlled)
        self.assertEqual(session.motion, (0.0, 0.0))
