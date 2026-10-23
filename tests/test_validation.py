"""Holdout harness checks use tiny runs, never the full research matrix.

File: tests/test_validation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from village.config import get_settings
from village.validation import collect_runs, read_plan, summarize

ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    """Regression cases for validation."""

    def setUp(self):
        """Create isolated state for each regression case.

        Returns:
            None.
        """
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = json.loads(
            (ROOT / "configs/validation/holdout-v1.json").read_text()
        )
        for scenario in self.plan["scenarios"]:
            scenario["config"] = str(
                (ROOT / "configs/validation" / scenario["config"]).resolve()
            )
        self.path = self.root / "plan.json"

    def tearDown(self):
        """Restore state and release resources after each regression case.

        Returns:
            None.
        """
        self.temp.cleanup()

    def write_plan(self):
        """Write a tiny bounded validation protocol using the fixture output paths.

        Returns:
            Fixture value consumed by assertions in this regression.
        """
        self.path.write_text(json.dumps(self.plan))
        return self.path

    def test_new_seeds_and_all_four_scenarios_preflight(self):
        """Verify new seeds and all four scenarios preflight.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        plan, scenarios = read_plan(self.write_plan())
        self.assertFalse(set(plan["seeds"]) & set(plan["excluded_development_seeds"]))
        self.assertEqual(len(scenarios), 4)
        self.assertEqual(len(plan["seeds"]) * len(scenarios) * 3, 96)
        for _, _, config in scenarios:
            expected = dict(get_settings()["coordination"])
            actual = dict(config["coordination"])
            expected.pop("mode")
            actual.pop("mode")
            self.assertEqual(actual, expected)
            self.assertEqual(config["policy"], get_settings()["policy"])
            self.assertTrue(config["coordination"]["enabled"])
            self.assertEqual(
                config["evaluation"]["controls"]["cooperative"]["disabled_actions"], []
            )

    def test_overlap_duplicate_seeds_and_invalid_budget_rejected(self):
        """Verify overlap duplicate seeds and invalid budget rejected.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        for patch in ({"seeds": [7]}, {"seeds": [211, 211]}, {"suite_wall_seconds": 0}):
            with self.subTest(patch=patch):
                original = deepcopy(self.plan)
                self.plan.update(patch)
                with self.assertRaises(ValueError):
                    read_plan(self.write_plan())
                self.plan = original

    def test_disabled_survival_actions_rejected_before_running(self):
        """Verify disabled survival actions rejected before running.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        config = json.loads((ROOT / "configs/cooperation-siege.json").read_text())
        config["evaluation"]["controls"] = {
            "cooperative": {"disabled_actions": ["guard"]}
        }
        path = self.root / "disabled.json"
        path.write_text(json.dumps(config))
        self.plan["scenarios"] = [{"name": "cooperation-siege", "config": str(path)}]
        with self.assertRaisesRegex(ValueError, "every survival action"):
            read_plan(self.write_plan())

    def test_collector_keeps_missing_and_censored_runs_explicit(self):
        """Verify collector keeps missing and censored runs explicit.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        path = self.root / "211-scripted-independent"
        path.mkdir()
        result = dict(
            seed=211,
            mode="scripted",
            control="cooperative",
            coordination_mode="independent",
            model_requests=0,
            blocked_actions={},
            completed_horizon=False,
            failed=False,
            stop_reason="run_wall_time_limit",
        )
        (path / "result.json").write_text(json.dumps(result))
        rows, problems = collect_runs(self.root, [211])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(problems), 3)
        summary = summarize(rows, [211])
        self.assertEqual(summary["strategies"][0]["completed_or_failed"], 0)
        self.assertEqual(summary["strategies"][0]["incomplete_or_missing"], 1)

    def test_collector_rejects_inference_or_capability_changes(self):
        """Verify collector rejects inference or capability changes.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        path = self.root / "211-scripted-independent"
        path.mkdir()
        result = dict(
            seed=211,
            mode="scripted",
            control="cooperative",
            coordination_mode="independent",
            model_requests=1,
            blocked_actions={},
            completed_horizon=True,
            failed=False,
        )
        (path / "result.json").write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "inference mismatch"):
            collect_runs(self.root, [211])

    def test_cli_freezes_inputs_runs_three_strategies_and_preserves_save(self):
        """Verify cli freezes inputs runs three strategies and preserves save.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        config = json.loads((ROOT / "configs/cooperation-siege.json").read_text())
        save = self.root / "campaign.json"
        save.write_text('{"sentinel":"untouched"}')
        config["runtime"]["save_path"] = str(save)
        path = self.root / "tiny.json"
        path.write_text(json.dumps(config))
        self.plan.update(
            seeds=[211],
            duration_seconds=1,
            run_wall_seconds=10,
            scenario_wall_seconds=20,
            suite_wall_seconds=30,
            scenarios=[{"name": "cooperation-siege", "config": str(path)}],
        )
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "village.validation",
                "--plan",
                str(self.write_plan()),
                "--output",
                str(self.root / "outputs"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=40,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        output = next((self.root / "outputs").glob("*/summary.json"))
        summary = json.loads(output.read_text())
        self.assertEqual(summary["manifest"]["status"], "complete")
        self.assertEqual(summary["manifest"]["observed_runs"], 3)
        self.assertEqual(summary["manifest"]["expected_runs"], 3)
        self.assertIn("coordination.py", summary["manifest"]["source_sha256"])
        self.assertEqual(summary["scenarios"][0]["problems"], [])
        self.assertEqual(
            {r["coordination_mode"] for r in summary["scenarios"][0]["runs"]},
            {"independent", "requests", "assigned"},
        )
        self.assertEqual(save.read_text(), '{"sentinel":"untouched"}')
        self.assertTrue((output.parent / "protocol.json").exists())
