"""An inert inference response must not change the physics integration grid."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from village.config import get_settings
from village.models import resolve_profile
from village.evaluation import run_scenario


class TimingGridTests(unittest.TestCase):
    def test_arbitrary_measured_delays_leave_noop_gameplay_identical(self):
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
