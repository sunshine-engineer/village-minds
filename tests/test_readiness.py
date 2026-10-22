"""Ownership/physics boundaries for responsive transport and causal fixtures."""

import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from village.config import get_settings
from village.server import VillageServer, Envelope
from village.world import World
from village.brains import BrainScheduler
from village.priority_benchmark import run_case, validate_plan


class ReadinessTests(unittest.TestCase):
    def test_exchange_returns_applied_movement_without_duplicate_action(self):
        w = World(seed=301)
        server = VillageServer(w, BrainScheduler(w, "", "", demo=True))
        token = server.handle("/session", None, {})[1]["token"]
        server.handle(
            "/command", token, dict(sequence=1, command=dict(kind="takeover", index=0))
        )
        before = w.villagers[0].position
        move = Envelope(
            "/exchange",
            token,
            dict(sequence=2, command=dict(kind="move", dx=1.0, dy=0.0)),
        )
        server.inbox.put(move)
        server.step(0.05)
        status, reply = move.reply.get_nowait()
        self.assertEqual(status, 200)
        self.assertEqual(reply["state"]["frame"], 1)
        self.assertNotEqual(w.villagers[0].position, before)
        self.assertEqual(
            tuple(reply["state"]["world"]["world"]["villagers"][0]["position"]),
            w.villagers[0].position,
        )
        self.assertEqual(server.sequence, 2)

    def test_exchange_cannot_publish_after_disconnect_or_replacement_session(self):
        w = World(seed=301)
        server = VillageServer(w, BrainScheduler(w, "", "", demo=True))
        token = server.handle("/session", None, {})[1]["token"]
        exchange = Envelope(
            "/exchange", token, dict(sequence=1, command=dict(kind="takeover", index=0))
        )
        server.inbox.put(exchange)
        server.inbox.put(Envelope("/disconnect", token, {}))
        server.inbox.put(Envelope("/session", None, {}))
        server.step(0.05)
        status, reply = exchange.reply.get_nowait()
        self.assertEqual(status, 401)
        self.assertNotIn("state", reply)
        self.assertNotEqual(server.token, token)

    def test_invalid_exchange_does_not_move_or_publish_state(self):
        w = World(seed=301)
        server = VillageServer(w, BrainScheduler(w, "", "", demo=True))
        token = server.handle("/session", None, {})[1]["token"]
        exchange = Envelope(
            "/exchange",
            token,
            dict(sequence=1, command=dict(kind="move", dx=float("nan"), dy=0)),
        )
        server.inbox.put(exchange)
        server.step(0.05)
        status, reply = exchange.reply.get_nowait()
        self.assertIn(status, (400, 409))
        self.assertNotIn("state", reply)

    def test_fixture_protocol_rejects_duplicate_seeds_and_invalid_step(self):
        plan = json.loads(
            Path("configs/portfolio/priority-development.json").read_text()
        )
        validate_plan(plan)
        plan["seeds"] = [301, 301]
        with self.assertRaises(ValueError):
            validate_plan(plan)
        plan["seeds"] = [301]
        plan["step_seconds"] = 1
        with self.assertRaises(ValueError):
            validate_plan(plan)


class ContentionTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.saved = deepcopy(self.settings)
        from tests.test_strategy import StrategyTests

        self.restore_settings = lambda: StrategyTests.tearDown(self)
        self.saved = deepcopy(self.settings)
        self.settings["ai"]["repair_strategy"].update(
            enabled=True, mode="priority_plan", plan_seconds=30.0
        )
        self.settings["coordination"].update(
            mode="requests",
            priority=["repair", "defend", "wood", "food"],
            repair_handoffs=False,
        )
        self.settings["coordination"]["resource_aware"]["enabled"] = True
        self.settings["logistics"]["enabled"] = False
        self.plan = json.loads(
            Path("configs/portfolio/priority-development.json").read_text()
        )

    def tearDown(self):
        self.restore_settings()

    def test_adverse_choice_changes_owner_and_causes_breach_in_both_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            for case in self.plan["cases"]:
                rows = {
                    condition: run_case(
                        self.plan,
                        case,
                        301,
                        condition,
                        "elder",
                        Path(temp) / case["name"] / condition,
                    )
                    for condition in ("baseline", "scripted", "adverse")
                }
                self.assertFalse(rows["scripted"]["primary_gate_breached"])
                self.assertTrue(rows["adverse"]["primary_gate_breached"])
                self.assertNotEqual(
                    rows["scripted"]["first_repair_owner"]["gate"],
                    rows["adverse"]["first_repair_owner"]["gate"],
                )
                self.assertEqual(
                    rows["scripted"]["initial"], rows["adverse"]["initial"]
                )
                if case["name"] == "far-urgent":
                    self.assertTrue(rows["baseline"]["primary_gate_breached"])

    def test_tick_boundary_response_is_not_credited_before_existing_claim(self):
        case = self.plan["cases"][1]
        with tempfile.TemporaryDirectory() as temp:
            result = run_case(
                self.plan,
                case,
                301,
                "model",
                "elder",
                Path(temp),
                request=lambda *args: dict(
                    status="ok",
                    latency_ms=7250.0,
                    decision=dict(action="plan_repairs", target="north_gate"),
                ),
            )
        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual(result["first_repair_owner"]["gate"], "east_gate")
        self.assertAlmostEqual(result["applied_at"], result["first_repair_owner"]["at"])
        self.assertFalse(result["applied_before_first_claim"])

    def test_model_timeout_keeps_baseline_local_behavior(self):
        case = self.plan["cases"][1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = run_case(
                self.plan, case, 301, "baseline", "elder", root / "baseline"
            )
            model = run_case(
                self.plan,
                case,
                301,
                "model",
                "elder",
                root / "model",
                request=lambda *args: dict(
                    status="timeout", latency_ms=3500.0, error="fixture timeout"
                ),
            )
            self.assertEqual(model["outcome"], "timeout")
            self.assertEqual(model["first_repair_owner"], base["first_repair_owner"])
            self.assertEqual(model["final_gates"], base["final_gates"])
            self.assertEqual(model["initial"], base["initial"])
