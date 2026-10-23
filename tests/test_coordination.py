"""Structured cooperation: ownership, real work, safety and restart continuity.

File: tests/test_coordination.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from village.config import DEFAULT_PATH, get_settings
from village.decisions import decision_schema
from village.entities import Monster
from village.evaluation import paired_coordination, run_scenario
from village.models import resolve_profile
from village.persistence import restore, snapshot
from village.world import World


class CoordinationTests(unittest.TestCase):
    """Regression cases for coordination."""

    def setUp(self):
        """Create isolated state for each regression case.

        Returns:
            None.
        """
        self.world = World()
        self.board = self.world.task_board
        self.board.settings = deepcopy(self.board.settings)
        self.elder = self.world.villagers[5]
        self.worker = self.world.villagers[1]
        self.farmer = self.world.villagers[0]
        self.world.store["wood"] = 0

    def request(self):
        """Return the deterministic model-response fixture for this regression.

        Returns:
            Controlled response envelope used by the test.
        """
        self.assertTrue(
            self.world.apply(
                self.worker, {"action": "request_help", "target": "wood:storehouse"}
            )
        )
        return self.board.tasks[-1]

    def test_requests_do_not_duplicate_or_teleport_resources(self):
        """Verify requests do not duplicate or teleport resources.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.assertFalse(
            self.world.apply(
                self.elder, {"action": "request_help", "target": "wood:storehouse"}
            )
        )
        self.assertEqual(self.world.store["wood"], 0)
        self.assertEqual(task["status"], "open")
        self.assertEqual(len(self.board.tasks), 1)

    def test_only_authorized_assigners_offer_and_only_recipient_accepts(self):
        """Verify only authorized assigners offer and only recipient accepts.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        offer = {"action": "assign_task", "target": task["id"] + ":" + self.farmer.name}
        self.assertFalse(self.world.apply(self.worker, offer))
        self.assertTrue(self.world.apply(self.elder, offer))
        self.assertFalse(
            self.world.apply(
                self.worker, {"action": "claim_task", "target": task["id"]}
            )
        )
        self.assertTrue(
            self.world.apply(
                self.farmer, {"action": "claim_task", "target": task["id"]}
            )
        )
        self.assertEqual(task["accepted_by"], self.farmer.name)

    def test_exclusive_ownership_and_release(self):
        """Verify exclusive ownership and release.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.assertTrue(
            self.world.apply(
                self.worker, {"action": "claim_task", "target": task["id"]}
            )
        )
        self.assertFalse(
            self.world.apply(
                self.farmer, {"action": "claim_task", "target": task["id"]}
            )
        )
        self.assertTrue(
            self.world.apply(
                self.worker, {"action": "release_task", "target": task["id"]}
            )
        )
        self.assertTrue(
            self.world.apply(
                self.farmer, {"action": "claim_task", "target": task["id"]}
            )
        )

    def test_real_wood_delivery_marks_productive_work_and_completion(self):
        """Verify real wood delivery marks productive work and completion.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.world.apply(self.worker, {"action": "claim_task", "target": task["id"]})
        self.worker.position = tuple(get_settings()["world"]["locations"]["storehouse"])
        self.worker.wood = self.board.settings["wood_target"]
        self.assertTrue(self.world.apply(self.worker, {"action": "deposit"}))
        self.board.maintain()
        self.assertEqual(task["status"], "completed")
        self.assertIsNotNone(task["progress_at"])
        self.assertEqual(self.board.counts["completed"], 1)

    def test_someone_else_resolving_need_does_not_credit_assignee(self):
        """Verify someone else resolving need does not credit assignee.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.world.apply(self.farmer, {"action": "claim_task", "target": task["id"]})
        self.worker.position = tuple(get_settings()["world"]["locations"]["storehouse"])
        self.worker.wood = self.board.settings["wood_target"]
        self.world.apply(self.worker, {"action": "deposit"})
        self.board.maintain()
        self.assertEqual(task["status"], "resolved")
        self.assertEqual(self.board.counts["completed"], 0)

    def test_guard_automatic_attack_counts_real_task_progress(self):
        """Verify guard automatic attack counts real task progress.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        bot = self.world.villagers[3]
        self.world.monsters = [Monster("test", "north_gate", (0, 25))]
        self.world.apply(
            self.elder, {"action": "request_help", "target": "defend:north_gate"}
        )
        task = self.board.tasks[-1]
        self.world.apply(bot, {"action": "claim_task", "target": task["id"]})
        bot.position = (0, 22)
        self.world.apply(bot, {"action": "guard", "target": "north_gate"})
        self.world.tick(0.1)
        self.assertIsNotNone(task["progress_at"])
        self.assertLess(
            self.world.monsters[0].health, get_settings()["rules"]["monster_health"]
        )

    def test_hunger_overrides_task_without_destroying_ownership(self):
        """Verify hunger overrides task without destroying ownership.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.world.apply(self.farmer, {"action": "claim_task", "target": task["id"]})
        self.farmer.position = tuple(get_settings()["world"]["locations"]["storehouse"])
        self.farmer.hunger = 90
        self.assertEqual(self.world.fallback(self.farmer)["action"], "eat")
        self.assertEqual(task["assigned_to"], self.farmer.name)

    def test_expiry_and_dead_owner_release(self):
        """Verify expiry and dead owner release.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.world.apply(self.worker, {"action": "claim_task", "target": task["id"]})
        self.worker.health = 0
        self.board.maintain()
        self.assertEqual(task["status"], "open")
        self.world.time = task["expires_at"]
        self.board.maintain()
        self.assertEqual(task["status"], "expired")

    def test_automatic_assignments_skip_player(self):
        """Verify automatic assignments skip player.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.board.mode = "assigned"
        self.world.possess(1)
        self.board.coordinate()
        self.assertTrue(self.board.tasks)
        self.assertFalse(
            any(t["assigned_to"] == self.worker.name for t in self.board.tasks)
        )

    def test_board_survives_restart_and_legacy_snapshots_remain_valid(self):
        """Verify board survives restart and legacy snapshots remain valid.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        task = self.request()
        self.world.apply(self.worker, {"action": "claim_task", "target": task["id"]})
        self.world.time = 3
        saved = snapshot(self.world)
        resumed = restore(saved)
        self.assertEqual(resumed.task_board.tasks, self.board.tasks)
        self.assertEqual(resumed.task_board.counts, self.board.counts)
        self.assertIsNotNone(resumed.fallback(resumed.villagers[1]))
        saved["world"].pop("task_board")
        self.assertEqual(restore(saved).task_board.tasks, [])

    def test_corrupt_saved_task_owner_is_rejected(self):
        """Verify corrupt saved task owner is rejected.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.request()
        saved = snapshot(self.world)
        saved["world"]["task_board"]["tasks"][0]["assigned_to"] = "unknown"
        with self.assertRaises(ValueError):
            restore(saved)

    def test_model_schema_exposes_only_valid_structured_tokens(self):
        """Verify model schema exposes only valid structured tokens.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.request()
        observation = self.world.observe(self.elder)
        observation["decision_layer"] = "strategic"
        branches = decision_schema(observation)["oneOf"]
        offer = next(
            b for b in branches if b["properties"]["action"]["enum"] == ["assign_task"]
        )
        self.assertTrue(
            all(v.startswith("task-1:") for v in offer["properties"]["target"]["enum"])
        )
        self.assertTrue(observation["task_board"])
        self.assertEqual(
            len(observation["coordination_roster"]), len(self.world.villagers)
        )

    def test_paired_comparison_keeps_regressions_and_excludes_deadlines(self):
        """Verify paired comparison keeps regressions and excludes deadlines.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        base = dict(
            seed=7,
            mode="scripted",
            control="cooperative",
            coordination_mode="independent",
            completed_horizon=True,
            failed=False,
            village_health=100,
            stop_reason="duration_reached",
            uncovered_threat_fraction=0.5,
        )
        worse = dict(
            base,
            coordination_mode="assigned",
            completed_horizon=False,
            failed=True,
            village_health=0,
            stop_reason="village_destroyed",
            uncovered_threat_fraction=0.8,
        )
        limited = dict(worse, seed=19, stop_reason="run_wall_time_limit")
        row = paired_coordination(
            [base, worse, dict(base, seed=19), limited, dict(base, seed=31)]
        )[0]
        self.assertEqual(row["matched_seeds"], 1)
        self.assertEqual(row["excluded_or_missing_pairs"], 2)
        self.assertEqual(row["survival_regressions"], 1)
        self.assertEqual(row["mean_final_health_delta"], -100)
        self.assertEqual(row["mean_uncovered_fraction_delta"], 0.3)

    def test_board_capacity_does_not_remove_survival_actions(self):
        """Verify board capacity does not remove survival actions.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        before = self.world.available_actions(self.worker)
        self.board.settings["max_active_tasks"] = 1
        self.request()
        self.world.store["food"] = 0
        self.assertNotIn("request_help", self.world.available_actions(self.farmer))
        after = self.world.available_actions(self.worker)
        for action in ("move", "guard"):
            self.assertEqual(before[action], after[action])

    def test_fake_model_can_request_then_assign_a_real_threat_task(self):
        """Verify fake model can request then assign a real threat task.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        options = deepcopy(get_settings()["evaluation"])
        options.update(
            duration_seconds=190,
            checkpoint_strategy="interval",
            checkpoint_start_seconds=180.2,
            checkpoint_seconds=0.1,
            max_model_calls=2,
            role_order=["elder"],
            coordination_mode="independent",
        )
        seen = []

        def request(profile, observation, *args):
            """Return the deterministic model-response fixture for this regression.

            Args:
                profile: Resolved model profile containing backend and generation options.
                observation: Request-time context containing legal choices and relevant world state.
                *args: Parsed command-line options for this entry point.

            Returns:
                Controlled response envelope used by the test.
            """
            seen.append(observation)
            actions = observation["available_actions"]
            if len(seen) == 1:
                decision = {
                    "action": "request_help",
                    "target": actions["request_help"][0],
                }
            else:
                decision = {
                    "action": "assign_task",
                    "target": actions["assign_task"][0],
                }
            return {"status": "ok", "decision": decision, "latency_ms": 1}

        with tempfile.TemporaryDirectory() as folder:
            result = run_scenario(
                7,
                "hybrid",
                options,
                resolve_profile(),
                Path(folder),
                DEFAULT_PATH,
                request=request,
            )
        self.assertEqual(result["accepted_model_actions"], 2)
        self.assertEqual(result["coordination"]["counts"]["requested"], 1)
        self.assertEqual(result["coordination"]["counts"]["offered"], 1)
        self.assertTrue(seen[0]["village"]["gate_threats"])
