"""Resource allocation, partial loads and strategic ownership safety."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from village.config import get_settings
from village.world import World
from village.allocation import repair_features, repair_candidates, strategy_observation
from village.entities import Monster
from village.models import request_decision, InferenceDecision
from village.telemetry import DecisionLog
from village.strategy_experiment import paired_results, validate_plan


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.saved = deepcopy(self.settings)
        self.settings["ai"]["repair_strategy"]["enabled"] = True
        self.settings["coordination"]["resource_aware"]["enabled"] = True
        self.settings["logistics"]["enabled"] = True
        self.w = World(seed=301)
        self.w.task_board.mode = "requests"
        self.worker = next(v for v in self.w.villagers if v.role == "worker")
        self.elder = next(v for v in self.w.villagers if v.role == "elder")
        self.farmer = next(v for v in self.w.villagers if v.role == "farmer")
        self.w.gates["north_gate"] = 20
        self.w.store["wood"] = 2

    def tearDown(self):
        self.settings.clear()
        self.settings.update(self.saved)

    def test_worker_efficiency_accounts_for_travel_and_clipped_repairs(self):
        task = dict(kind="repair", target="north_gate")
        self.worker.position = self.farmer.position = (0, 15)
        a = repair_features(self.w, task, self.worker)
        b = repair_features(self.w, task, self.farmer)
        self.assertGreater(a["hp_per_wood"], b["hp_per_wood"])
        self.assertLess(a["cost"], b["cost"])
        self.w.gates["north_gate"] = self.settings["rules"]["gate_health"] - 1
        a = repair_features(self.w, task, self.worker)
        self.assertEqual(
            a["hp_per_wood"], 1 / self.settings["rules"]["repair_wood_cost"]
        )
        self.assertGreater(a["travel_seconds"], 0)

    def test_partial_wood_delivery_during_shortage(self):
        self.worker.wood = 1
        self.worker.position = tuple(self.settings["world"]["locations"]["storehouse"])
        self.w.store["wood"] = 0
        decision = self.w.fallback(self.worker)
        self.assertEqual(decision, {"action": "deposit"})
        self.assertTrue(self.w.apply(self.worker, decision))
        self.assertEqual(self.w.store["wood"], 1)
        self.assertEqual(self.worker.wood, 0)

    def test_partial_food_delivery_for_hungry_neighbor(self):
        self.worker.supplies = 1
        self.w.store["food"] = 0
        self.farmer.hunger = 90
        self.worker.position = tuple(self.settings["world"]["locations"]["storehouse"])
        self.assertEqual(self.w.fallback(self.worker), {"action": "deposit"})

    def test_busy_supplier_handoff_preserves_supply_task(self):
        b = self.w.task_board
        self.w.store["wood"] = 0
        self.assertTrue(
            self.w.apply(
                self.elder, dict(action="request_help", target="wood:storehouse")
            )
        )
        supply = b.tasks[-1]
        self.assertTrue(
            self.w.apply(self.worker, dict(action="claim_task", target=supply["id"]))
        )
        self.w.store["wood"] = 2
        b.next_request.clear()
        self.assertTrue(b.offer_repair(self.elder, "north_gate", self.worker.name))
        self.assertEqual(supply["status"], "open")
        self.assertIsNone(supply["assigned_to"])
        repair = b.tasks[-1]
        self.assertEqual(repair["assigned_to"], self.worker.name)
        self.assertEqual(repair["status"], "offered")

    def test_rejected_offer_is_atomic(self):
        b = self.w.task_board
        b.next_request[self.elder.name] = 100
        before = b.snapshot()
        self.assertFalse(b.offer_repair(self.elder, "north_gate", self.worker.name))
        self.assertEqual(b.snapshot(), before)

    def test_active_guard_cannot_be_reassigned(self):
        soldier = next(v for v in self.w.villagers if v.role == "soldier")
        soldier.action = "guarding north_gate"
        self.w.monsters.append(Monster("probe", "north_gate", (0, 23)))
        self.assertNotIn(
            soldier.name, [c["actor"] for c in repair_candidates(self.w.task_board)]
        )
        self.assertFalse(
            self.w.task_board.offer_repair(self.elder, "north_gate", soldier.name)
        )

    def test_model_lease_restores_and_stale_target_is_rejected(self):
        obs = strategy_observation(self.w, self.elder)
        target = obs["choices"][0]["target"]
        self.assertTrue(
            self.w.apply(self.elder, dict(action="dispatch_repair", target=target))
        )
        board = self.w.task_board
        saved = board.snapshot()
        board.restore(saved)
        self.assertTrue(board.strategy_leases)
        owner = board.tasks[-1]["assigned_to"]
        board.rebalance_repairs()
        self.assertEqual(board.tasks[-1]["assigned_to"], owner)
        self.assertFalse(
            self.w.apply(self.elder, dict(action="dispatch_repair", target=target))
        )
        legacy = deepcopy(saved)
        legacy.pop("strategy_leases")
        board.restore(legacy)
        self.assertEqual(board.strategy_leases, {})

    def test_compact_model_choice_validation_and_metrics(self):
        obs = strategy_observation(self.w, self.elder)
        profile = {
            "backend": "fixture",
            "url": "unused",
            "model": "fixture",
            "timeout": 1,
        }
        from village.models import BACKENDS

        class Backend:
            def decide(self, *args):
                return InferenceDecision({"choice": "r0"}, {"prompt_tokens": 200})

        with patch.dict(BACKENDS, fixture=Backend):
            decision = request_decision("unused", "fixture", obs, profile=profile)
        self.assertEqual(decision["action"], "dispatch_repair")
        self.assertEqual(decision.metrics["prompt_tokens"], 200)

        class Invalid:
            def decide(self, *args):
                return {"choice": "injected-action"}

        with patch.dict(BACKENDS, fixture=Invalid):
            with self.assertRaises(ValueError):
                request_decision("unused", "fixture", obs, profile=profile)

    def test_logger_handles_invalid_input_and_counts_partial_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            log = DecisionLog(Path(d) / "events.jsonl", max_bytes=100000)
            self.w.decision_log = log
            self.assertFalse(self.w.apply(self.worker, None))
            self.worker.wood = 1
            self.w.store["wood"] = 0
            self.worker.position = tuple(
                self.settings["world"]["locations"]["storehouse"]
            )
            self.assertTrue(
                self.w.apply(self.worker, {"action": "deposit"}, source="local")
            )
            self.assertEqual(log.count("urgent_delivery", "local", "accepted"), 1)
            log.close()

    def test_pairs_exclude_deadline_censoring(self):
        base = dict(
            case="siege",
            seed=401,
            condition="scripted",
            stop_reason="duration_reached",
            completed_horizon=True,
            failed=False,
            village_health=100,
        )
        model = dict(base, condition="model", village_health=120)
        self.assertEqual(paired_results([base, model])[0]["health_delta"], 20)
        model["stop_reason"] = "run_wall_time_limit"
        self.assertFalse(paired_results([base, model])[0]["eligible"])

    def test_strategy_does_not_pause_proposers_local_routine(self):
        from village.brains import BrainScheduler

        brains = BrainScheduler(self.w, "", "", demo=True)
        obs = strategy_observation(self.w, self.elder)
        index = self.w.villagers.index(self.elder)
        result = brains.consume_decision(
            index,
            self.elder.revision,
            self.w.time,
            dict(action="dispatch_repair", target=obs["choices"][0]["target"]),
        )
        self.assertEqual(result, "accepted")
        self.assertFalse(brains._keep_model_task(index, self.elder))

    def test_metrics_measure_travel_and_store_routes(self):
        from village.evaluation import Metrics

        self.worker.path = [(0, 0)]
        self.worker.action = "walking to storehouse"
        metrics = Metrics(self.w)
        metrics.step(self.w, 0.1)
        self.assertEqual(metrics.travel_villager_seconds, 0.1)
        self.assertEqual(metrics.store_travel_villager_seconds, 0.1)

    def test_experiment_rejects_reused_seeds(self):
        plan = dict(
            seeds=[401],
            excluded_seeds=[401],
            duration_seconds=1,
            request_seconds=1,
            run_wall_seconds=1,
            suite_seconds=1,
            model_calls=1,
        )
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_experiment_cli_runs_three_matched_conditions(self):
        import json, subprocess, sys

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config = root / "config.json"
            config.write_text("{}")
            plan = dict(
                name="tiny-paired-check",
                seeds=[401],
                excluded_seeds=[301],
                duration_seconds=1,
                request_seconds=0.2,
                run_wall_seconds=5,
                suite_seconds=20,
                model_calls=1,
                cases=[dict(name="tiny", config=str(config))],
            )
            path = root / "plan.json"
            path.write_text(json.dumps(plan))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "village.strategy_experiment",
                    "--plan",
                    str(path),
                    "--output",
                    str(root / "out"),
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(next((root / "out").glob("*/summary.json")).read_text())
            self.assertEqual(len(report["runs"]), 3)
            self.assertEqual(
                {r["condition"] for r in report["runs"]},
                {"legacy", "scripted", "model"},
            )
            self.assertTrue(report["paired_model_vs_scripted"][0]["eligible"])
            self.assertEqual(report["failures"], [])
            self.assertTrue(report["protocol"]["config_hashes"])

    def test_suite_deadline_persists_missing_runs(self):
        import json, subprocess, sys

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            config = root / "config.json"
            config.write_text("{}")
            plan = dict(
                name="expired-suite",
                seeds=[401],
                excluded_seeds=[301],
                duration_seconds=1,
                request_seconds=0.2,
                run_wall_seconds=5,
                suite_seconds=0.000001,
                model_calls=1,
                cases=[dict(name="tiny", config=str(config))],
            )
            path = root / "plan.json"
            path.write_text(json.dumps(plan))
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "village.strategy_experiment",
                    "--plan",
                    str(path),
                    "--output",
                    str(root / "out"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(next((root / "out").glob("*/summary.json")).read_text())
            self.assertEqual(report["runs"], [])
            self.assertEqual(len(report["failures"]), 3)
            self.assertTrue(
                all(r["error"] == "suite_deadline" for r in report["failures"])
            )
