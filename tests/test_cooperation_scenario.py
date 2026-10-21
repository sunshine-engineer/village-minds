"""Causal controls use real survival rules, not fabricated AI outcomes."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from village.config import get_settings
from village.evaluation import run_scenario, aggregate
from village.evaluation_controls import EvaluationWorld


class CooperationTests(unittest.TestCase):
    def test_intervention_blocks_sharing_before_state_changes(self):
        world = EvaluationWorld(disabled_actions=["deposit"])
        bot = world.villagers[0]
        bot.position = tuple(get_settings()["world"]["locations"]["storehouse"])
        bot.supplies = 6
        before = world.store.copy()
        self.assertFalse(world.apply(bot, {"action": "deposit"}))
        self.assertEqual(world.store, before)
        self.assertEqual(bot.supplies, 6)
        self.assertEqual(world.blocked_actions["deposit"], 1)
        normal = EvaluationWorld()
        bot = normal.villagers[0]
        bot.position = tuple(get_settings()["world"]["locations"]["storehouse"])
        bot.supplies = 6
        self.assertTrue(normal.apply(bot, {"action": "deposit"}))

    def test_interventions_cannot_be_mislabeled_as_ai_comparisons(self):
        options = dict(get_settings()["evaluation"], control="no-defense")
        with self.assertRaisesRegex(ValueError, "scripted mode"):
            run_scenario(7, "hybrid", options, {}, Path("/unused"), Path("/unused"))

    def test_siege_survival_depends_on_sharing_defense_and_repairs(self):
        # Startup-only settings: exercise the packaged config through fresh CLI processes.
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            outcomes = {}
            for control in ("cooperative", "no-sharing", "no-defense", "no-repairs"):
                output = Path(folder) / control
                process = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "village.evaluation",
                        "--config",
                        str(root / "configs/cooperation-siege.json"),
                        "--modes",
                        "scripted",
                        "--seeds",
                        "7",
                        "--control",
                        control,
                        "--output",
                        str(output),
                        "--wall-seconds",
                        "30",
                        "--suite-seconds",
                        "35",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=40,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                summary = json.loads(
                    next(output.glob("run-*/summary.json")).read_text()
                )
                result = summary["runs"][0]
                self.assertEqual(result["control"], control)
                self.assertEqual(result["scenario_name"], "cooperation-siege")
                self.assertEqual(result["model_requests"], 0)
                self.assertNotIn("wall_time_limit", result["stop_reason"])
                outcomes[control] = result
            grouped = aggregate(list(outcomes.values()))
            self.assertEqual(len(grouped), 4)
            self.assertTrue(all(row["runs"] == 1 for row in grouped))
            self.assertTrue(outcomes["cooperative"]["completed_horizon"])
            for control in ("no-sharing", "no-defense", "no-repairs"):
                self.assertTrue(outcomes[control]["failed"], control)
                self.assertTrue(outcomes[control]["blocked_actions"], control)
            self.assertEqual(
                sum(
                    v["deposited_food"]
                    for v in outcomes["no-sharing"]["contributions"].values()
                ),
                0,
            )
            self.assertEqual(
                sum(
                    v["kills"] for v in outcomes["no-defense"]["contributions"].values()
                ),
                0,
            )
            self.assertEqual(
                sum(
                    v["repairs"]
                    for v in outcomes["no-repairs"]["contributions"].values()
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
