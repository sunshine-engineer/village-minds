"""Evaluation tests use fake model responses; only timeout tests spawn processes."""

from copy import deepcopy
import json
import multiprocessing
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
from village.config import get_settings, DEFAULT_PATH
from village.evaluation import (
    bounded_decision,
    run_scenario,
    generate_lessons,
    aggregate,
    Metrics,
    write_report,
)
from village.models import resolve_profile
from village.telemetry import DecisionLog
from village.timing import SimulationClock
from village.world import World
from village.brains import BrainScheduler


def hanging_worker(connection, config, profile, observation, timeout):
    time.sleep(10)


def successful_worker(connection, config, profile, observation, timeout):
    connection.send({"status": "ok", "decision": {"action": "move", "target": "farm"}})
    connection.close()


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.options = deepcopy(get_settings()["evaluation"])
        self.options.update(
            duration_seconds=40.0, run_wall_seconds=10.0, max_model_calls=1
        )
        self.profile = resolve_profile()

    def tearDown(self):
        self.temporary.cleanup()

    def run_mode(self, mode, *, request=None, fixture=None, name=None, options=None):
        output = self.root / (name or mode)
        output.mkdir()
        kwargs = {"request": request} if request else {}
        return run_scenario(
            7,
            mode,
            options or self.options,
            self.profile,
            output,
            DEFAULT_PATH,
            fixture,
            **kwargs,
        )

    def test_metrics_count_starvation_and_repeated_gate_breaches(self):
        world = World()
        metrics = Metrics(world)
        world.store["food"] = 0
        world.villagers[0].hunger = 90
        world.villagers[1].hunger = 90
        metrics.step(world, 0.1)
        self.assertAlmostEqual(metrics.food_shortage_seconds, 0.1)
        self.assertAlmostEqual(metrics.starvation_villager_seconds, 0.2)
        world.gates["north_gate"] = 0
        metrics.after_step(world)
        metrics.after_step(world)
        self.assertEqual(metrics.gate_breaches, 1)
        world.gates["north_gate"] = 10
        metrics.after_step(world)
        world.gates["north_gate"] = 0
        metrics.after_step(world)
        self.assertEqual(metrics.gate_breaches, 2)

    def test_zero_time_budget_does_not_spawn_model_worker(self):
        result = bounded_decision(
            self.profile, {}, DEFAULT_PATH, 0, worker=hanging_worker
        )
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["latency_ms"], 0)

    def test_cli_writes_report_and_never_reads_campaign_save(self):
        campaign = self.root / "campaign.json"
        campaign.write_text('{"sentinel":"untouched"}')
        config = self.root / "override.json"
        config.write_text(json.dumps({"runtime": {"save_path": str(campaign)}}))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "village.evaluation",
                "--config",
                str(config),
                "--seeds",
                "9",
                "--duration",
                "1",
                "--output",
                str(self.root / "reports"),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = next((self.root / "reports").glob("run-*/summary.json"))
        report = json.loads(summary.read_text())
        self.assertEqual(report["manifest"]["seeds"], [9])
        self.assertEqual(report["runs"][0]["model_requests"], 0)
        self.assertEqual(campaign.read_text(), '{"sentinel":"untouched"}')

    def test_scripted_run_never_calls_model_and_repeats_identically(self):
        def forbidden(*args):
            raise AssertionError("Scripted mode contacted model")

        a = self.run_mode("scripted", request=forbidden)
        b = self.run_mode("scripted", request=forbidden, name="repeat")
        for key in (
            "simulated_seconds",
            "village_health",
            "contributions",
            "final_store",
            "local_actions",
            "model_requests",
            "food_shortage_seconds",
        ):
            self.assertEqual(a[key], b[key])
        self.assertTrue(a["completed_horizon"])
        self.assertEqual(a["model_requests"], 0)

    def test_hybrid_uses_budget_and_logs_actual_model_provenance(self):
        seen = []

        def decide(profile, observation, *args):
            seen.append(observation)
            return {
                "status": "ok",
                "decision": {"action": "move", "target": "orchard"},
                "latency_ms": 4.0,
            }

        result = self.run_mode("hybrid", request=decide)
        self.assertEqual(len(seen), 1)
        self.assertEqual(result["accepted_model_actions"], 1)
        rows = [
            json.loads(line)
            for line in (self.root / "hybrid/decisions.jsonl").read_text().splitlines()
        ]
        request = next(r for r in rows if r["event"] == "model_request")
        response = next(r for r in rows if r["event"] == "model_response")
        self.assertEqual(request["request_id"], response["request_id"])
        self.assertEqual(response["latency_ms"], 4.0)
        self.assertTrue(
            any(r["event"] == "decision" and r["source"] == "local" for r in rows)
        )
        self.assertTrue(
            any(
                r["event"] == "decision" and r["source"] == "model" and r["observation"]
                for r in rows
            )
        )

    def test_memory_changes_only_explicit_model_lesson_field(self):
        seen = []

        def decide(profile, observation, *args):
            seen.append(deepcopy(observation))
            return {
                "status": "ok",
                "decision": {"action": "move", "target": "farm"},
                "latency_ms": 1.0,
            }

        fixture = {"lessons": {"Mira": ["A real earlier attempt failed."]}}
        self.run_mode("hybrid", request=decide, fixture=fixture)
        self.run_mode("hybrid-memory", request=decide, fixture=fixture)
        self.assertEqual(seen[0]["lessons_from_previous_failures"], [])
        self.assertEqual(
            seen[1]["lessons_from_previous_failures"], fixture["lessons"]["Mira"]
        )
        seen[1]["lessons_from_previous_failures"] = []
        self.assertEqual(seen[0], seen[1])

    def test_rejected_model_action_is_not_counted_as_accepted(self):
        result = self.run_mode(
            "hybrid",
            request=lambda *a: {
                "status": "ok",
                "decision": {"action": "shell", "target": ""},
                "latency_ms": 1.0,
            },
        )
        self.assertEqual(result["accepted_model_actions"], 0)
        self.assertEqual(result["model_outcomes"], {"rejected": 1})

    def test_timeout_opens_circuit_but_local_simulation_finishes(self):
        self.options["max_model_calls"] = 6
        result = self.run_mode(
            "hybrid",
            request=lambda *a: {
                "status": "timeout",
                "error": "timeout fixture",
                "latency_ms": 5.0,
            },
        )
        self.assertEqual(result["model_requests"], 1)
        self.assertTrue(result["model_circuit_open"])
        self.assertTrue(result["completed_horizon"])
        self.assertGreater(result["local_actions"], 0)

    def test_run_wall_budget_censors_instead_of_claiming_survival(self):
        self.options.update(run_wall_seconds=0.01, duration_seconds=1000.0)
        result = self.run_mode("scripted")
        self.assertFalse(result["completed_horizon"])
        self.assertFalse(result["failed"])
        self.assertTrue(result["censored"])
        self.assertEqual(result["stop_reason"], "run_wall_time_limit")

    def test_idle_failure_fixture_contains_factual_contributions(self):
        fixture = generate_lessons(7, 900, 0.1, time.monotonic() + 10)
        self.assertTrue(fixture["failed"])
        self.assertIn("Mira", fixture["lessons"])
        self.assertIn("contributed", fixture["lessons"]["Mira"][0])
        unfinished = generate_lessons(7, 1, 0.1, time.monotonic() + 1)
        self.assertFalse(unfinished["failed"])
        self.assertEqual(unfinished["lessons"], {})

    def test_process_timeout_cleans_up_child(self):
        before = {p.pid for p in multiprocessing.active_children()}
        start = time.monotonic()
        result = bounded_decision(
            self.profile, {}, DEFAULT_PATH, 0.2, worker=hanging_worker
        )
        self.assertEqual(result["status"], "timeout")
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_process_returns_decision(self):
        result = bounded_decision(
            self.profile, {}, DEFAULT_PATH, 5, worker=successful_worker
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["decision"]["action"], "move")

    def test_reports_keep_censored_and_failed_outcomes_separate(self):
        result = self.run_mode("scripted")
        limited = {
            **result,
            "seed": 8,
            "completed_horizon": False,
            "stop_reason": "run_wall_time_limit",
        }
        failed = {
            **result,
            "seed": 9,
            "completed_horizon": False,
            "failed": True,
            "censored": False,
            "stop_reason": "village_destroyed",
        }
        comparison = aggregate([result, limited, failed])[0]
        self.assertEqual(comparison["horizons_completed"], 1)
        self.assertEqual(comparison["wall_limited_runs"], 1)
        self.assertEqual(comparison["village_losses"], 1)
        write_report(
            self.root,
            [result, limited, failed],
            {"skipped_scenarios": 0, "interrupted": False},
        )
        self.assertTrue((self.root / "report.md").is_file())
        self.assertTrue((self.root / "results.csv").is_file())

    def test_jsonl_cap_retains_counters_even_when_rows_drop(self):
        log = DecisionLog(self.root / "limited.jsonl", max_bytes=300)
        try:
            for _ in range(10):
                log.record(
                    "decision", 1, source="local", outcome="accepted", text="x" * 100
                )
            self.assertEqual(log.count("decision", "local", "accepted"), 10)
            self.assertGreater(log.dropped, 0)
        finally:
            log.close()
        self.assertLessEqual((self.root / "limited.jsonl").stat().st_size, 300)

    def test_log_tracks_player_and_stale_model_decisions(self):
        log = DecisionLog(self.root / "player.jsonl", max_bytes=100000)
        world = World(decision_log=log)
        brains = BrainScheduler(world, "", "", demo=True)
        bot = world.villagers[0]
        revision = bot.revision
        world.possess(0)
        world.apply(bot, {"action": "rest"}, source="player")
        outcome = brains.consume_decision(
            0, revision, 0, {"action": "move", "target": "farm"}
        )
        self.assertEqual(outcome, "stale")
        self.assertEqual(log.count("model_response", "model", "stale"), 1)
        self.assertEqual(log.count("decision", "player", "accepted"), 1)
        log.close()

    def test_fast_forward_substeps_preserve_elapsed_time_and_wave_timing(self):
        world = World()
        world.next_wave = 0.5
        brains = BrainScheduler(world, "", "", demo=True)
        clock = SimulationClock(0.1, 100)
        self.assertEqual(clock.advance(world, brains, 1.0), 10)
        self.assertAlmostEqual(world.time, 1.0)
        self.assertEqual(world.wave, 1)
        self.assertAlmostEqual(clock.pending, 0)

    def test_frame_work_cap_keeps_time_pending(self):
        world = World()
        brains = BrainScheduler(world, "", "", demo=True)
        clock = SimulationClock(0.1, 2)
        clock.advance(world, brains, 1.0)
        self.assertAlmostEqual(world.time, 0.2)
        self.assertAlmostEqual(clock.pending, 0.8)
        for _ in range(4):
            clock.advance(world, brains, 0)
        self.assertAlmostEqual(world.time, 1.0)
        self.assertAlmostEqual(clock.pending, 0)


if __name__ == "__main__":
    unittest.main()
