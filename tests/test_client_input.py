"""Input must be published before potentially expensive snapshot restoration.

File: tests/test_client_input.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import unittest
from types import SimpleNamespace

from village.client import game_class


class ClientInputTests(unittest.TestCase):
    """Regression cases for client input."""

    def test_input_precedes_poll_and_remains_normalized(self):
        """Verify input precedes poll and remains normalized.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        from village.game import C

        order = []

        class Session:
            """Session stub that observes movement before returning a pending snapshot."""

            connected = True
            status = "CONNECTED"

            def __init__(self):
                """Initialize Session and its owned state.

                Returns:
                    None.
                """
                self.motion = (0.0, 0.0)

            def poll(self):
                """Observe the submitted movement before returning the stubbed pending state.

                Returns:
                    None.
                """
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
