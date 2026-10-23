"""An inert inference response must not change the physics integration grid.

File: tests/test_evaluation_timing.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from village.config import get_settings
from village.evaluation import run_scenario
from village.models import resolve_profile


class TimingGridTests(unittest.TestCase):
    """Regression cases for evaluation timing."""

    def test_arbitrary_measured_delays_leave_noop_gameplay_identical(self):
        """Verify arbitrary measured delays leave noop gameplay identical.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        options = deepcopy(get_settings()["evaluation"])
        options.update(
            duration_seconds=180.0,
            run_wall_seconds=15.0,
            max_model_calls=3,
            checkpoint_strategy="interval",
            checkpoint_start_seconds=1.0,
            timing_policy="measured_delay",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline_folder = root / "scripted"
            baseline_folder.mkdir()
            baseline = run_scenario(
                301,
                "scripted",
                options,
                resolve_profile(),
                baseline_folder,
                Path("unused"),
            )

            def events(folder):
                """Read normalized local decision events from a completed fixture trace.

                Args:
                    folder: Per-case artifact directory.

                Returns:
                    Normalized decision-event list.
                """
                return [
                    {
                        k: r.get(k)
                        for k in (
                            "sim_time",
                            "actor",
                            "source",
                            "outcome",
                            "decision",
                            "before",
                            "after",
                        )
                    }
                    for r in (
                        json.loads(line)
                        for line in (folder / "decisions.jsonl")
                        .read_text()
                        .splitlines()
                    )
                    if r["event"] == "decision" and r.get("source") != "model"
                ]

            baseline_events = events(baseline_folder)
            for delay in (0.037, 3.9995206, 5.0260881):
                folder = root / str(delay)
                folder.mkdir()

                def request(*args):
                    """Return the deterministic model-response fixture for this regression.

                    Args:
                        *args: Parsed command-line options for this entry point.

                    Returns:
                        Controlled response envelope used by the test.
                    """
                    return dict(
                        status="ok",
                        latency_ms=delay * 1000,
                        decision=dict(action="defer_strategy", target=""),
                    )

                result = run_scenario(
                    301,
                    "hybrid",
                    options,
                    resolve_profile(),
                    folder,
                    Path("unused"),
                    request=request,
                )
                self.assertGreater(result["model_requests"], 0)
                self.assertEqual(events(folder), baseline_events)
                for key in (
                    "contributions",
                    "village_health",
                    "final_store",
                    "gate_breaches",
                    "simulated_seconds",
                ):
                    self.assertEqual(result[key], baseline[key], key)
                for record in result["inference_records"]:
                    self.assertGreaterEqual(
                        record["simulated_delay_seconds"] + 1e-9, delay
                    )
                    self.assertLess(
                        record["delay_quantization_seconds"],
                        options["step_seconds"] + 1e-9,
                    )
                    tick = record["response_at"] / options["step_seconds"]
                    self.assertAlmostEqual(tick, round(tick), places=6)
