"""Strategic plans survive helper churn but remain bounded by local safety.

File: tests/test_priority_plans.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import unittest
from copy import deepcopy
from unittest.mock import patch

from tests import test_strategy as fixtures
from village.allocation import repair_candidates, strategy_observation
from village.brains import BrainScheduler
from village.models import request_decision


class PriorityPlanTests(unittest.TestCase):
    """Regression cases for priority plans."""

    tearDown = fixtures.StrategyTests.tearDown

    # Reuse fixtures without inheriting the assignment-mode regression tests.
    def setUp(self):
        """Create isolated state for each regression case.

        Returns:
            None.
        """
        fixtures.StrategyTests.setUp(self)
        self.settings["ai"]["repair_strategy"]["mode"] = "priority_plan"

    def test_zero_wood_and_busy_helpers_do_not_invalidate_strategy(self):
        """Verify zero wood and busy helpers do not invalidate strategy.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.w.store["wood"] = 0
        for bot in self.w.villagers:
            bot.energy = 0
        choices = repair_candidates(self.w.task_board, self.elder)
        self.assertTrue(choices)
        self.assertTrue(
            self.w.apply(
                self.elder, dict(action="plan_repairs", target=choices[0]["target"])
            )
        )
        self.assertFalse(any(t["assigned_to"] for t in self.w.task_board.tasks))

    def test_plan_ranks_only_useful_repairs_without_overriding_task_kinds(self):
        """Verify plan ranks only useful repairs without overriding task kinds.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        b = self.w.task_board
        self.w.gates["south_gate"] = 30
        self.assertTrue(
            self.w.apply(self.elder, dict(action="plan_repairs", target="south_gate"))
        )
        selected = dict(kind="repair", target="south_gate")
        other = dict(kind="repair", target="north_gate")
        self.assertLess(b.plan_priority(selected), b.plan_priority(other))
        self.assertEqual(b.plan_priority(dict(kind="defend", target="south_gate")), 1)
        self.w.store["wood"] = 0
        self.assertEqual(b.plan_priority(selected), 1)
        self.w.store["wood"] = 2
        self.w.time = b.repair_plan["expires_at"]
        self.assertEqual(b.plan_priority(selected), 1)

    def test_current_gate_state_revalidated_and_full_gate_not_prioritized(self):
        """Verify current gate state revalidated and full gate not prioritized.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.assertFalse(
            self.w.apply(self.elder, dict(action="plan_repairs", target="unknown"))
        )
        self.assertTrue(
            self.w.apply(self.elder, dict(action="plan_repairs", target="north_gate"))
        )
        self.w.gates["north_gate"] = self.settings["rules"]["gate_health"]
        self.assertEqual(
            self.w.task_board.plan_priority(dict(kind="repair", target="north_gate")), 1
        )
        self.assertFalse(
            self.w.apply(self.elder, dict(action="plan_repairs", target="north_gate"))
        )

    def test_plan_survives_actor_revision_but_not_possession_or_age(self):
        """Verify plan survives actor revision but not possession or age.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        brains = BrainScheduler(self.w, "", "", demo=True)
        index = self.w.villagers.index(self.elder)
        obs = strategy_observation(self.w, self.elder)
        decision = dict(action="plan_repairs", target="north_gate")
        self.elder.revision += 1
        self.assertEqual(
            brains.consume_decision(
                index, self.elder.revision - 1, self.w.time, decision, observation=obs
            ),
            "accepted",
        )
        self.w.possess(index)
        self.assertEqual(
            brains.consume_decision(
                index, self.elder.revision, self.w.time, decision, observation=obs
            ),
            "stale",
        )
        self.w.possess(None)
        self.w.time += self.settings["ai"]["max_decision_age_seconds"]
        self.assertEqual(
            brains.consume_decision(
                index, self.elder.revision, 0, decision, observation=obs
            ),
            "stale",
        )

    def test_free_worker_claims_priority_gate_without_reassigning_busy_owner(self):
        """Verify free worker claims priority gate without reassigning busy owner.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        b = self.w.task_board
        self.w.gates["south_gate"] = 30
        for gate in ("north_gate", "south_gate"):
            b.next_request.clear()
            self.assertTrue(
                self.w.apply(
                    self.elder, dict(action="request_help", target=f"repair:{gate}")
                )
            )
        for v in self.w.villagers:
            if v is not self.worker:
                v.energy = 0
        self.w.apply(self.worker, dict(action="plan_repairs", target="south_gate"))
        intent = b.policy(self.worker)
        self.assertEqual(intent["action"], "claim_task")
        selected = next(t for t in b.tasks if t["id"] == intent["target"])
        self.assertEqual(selected["target"], "south_gate")
        self.w.apply(self.worker, intent)
        self.w.apply(self.worker, dict(action="plan_repairs", target="north_gate"))
        self.assertEqual(selected["assigned_to"], self.worker.name)
        self.assertEqual(selected["status"], "accepted")

    def test_persistence_migration_and_strict_validation(self):
        """Verify persistence migration and strict validation.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        b = self.w.task_board
        self.w.apply(self.elder, dict(action="plan_repairs", target="north_gate"))
        saved = b.snapshot()
        b.restore(saved)
        self.assertEqual(b.repair_plan, saved["repair_plan"])
        broken = deepcopy(saved)
        broken["repair_plan"]["expires_at"] = -1
        with self.assertRaises(ValueError):
            b.restore(broken)
        del saved["repair_plan"]
        b.restore(saved)
        self.assertIsNone(b.repair_plan)

    def test_invalid_config_and_disabled_saved_plan(self):
        """Verify invalid config and disabled saved plan.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        from village.config import validate

        strategy = self.settings["ai"]["repair_strategy"]
        reference = deepcopy(self.settings)
        for key, value in (
            ("mode", "unknown"),
            ("controller", "unknown"),
            ("plan_seconds", 0),
        ):
            old = strategy[key]
            strategy[key] = value
            with self.assertRaises(ValueError):
                validate(self.settings, reference)
            strategy[key] = old
        self.w.apply(self.elder, dict(action="plan_repairs", target="north_gate"))
        strategy["enabled"] = False
        self.assertEqual(
            self.w.task_board.plan_priority(dict(kind="repair", target="north_gate")), 1
        )

    def test_scripted_and_model_decisions_use_same_gate_intent(self):
        """Verify scripted and model decisions use same gate intent.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        obs = strategy_observation(self.w, self.elder)
        self.settings["ai"]["repair_strategy"]["controller"] = "scripted"
        with patch(
            "village.models.OllamaBackend.decide",
            side_effect=AssertionError("provider called"),
        ):
            scripted = request_decision("", "", obs)
        self.assertFalse(scripted.metrics["provider_called"])
        self.settings["ai"]["repair_strategy"]["controller"] = "model"
        with patch(
            "village.models.OllamaBackend.decide", return_value={"choice": "r0"}
        ):
            model = request_decision("", "", obs)
        self.assertEqual(model, scripted)
