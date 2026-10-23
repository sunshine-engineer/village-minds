"""Bounded native/server integration fixture; requires the configured local Ollama model.

Starts from damaged gates in an isolated temporary save. It does not modify any
existing campaign or Docker container. Run from the repository root.

File: scripts/check_priority_server.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import pathlib
import subprocess
import sys
import tempfile


def main():
    """Run the check priority server diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        config = json.loads(pathlib.Path("configs/server-local.json").read_text())
        config["ai"]["repair_strategy"].update(mode="priority_plan", plan_seconds=60.0)
        config["rules"] = dict(first_wave_seconds=60.0)
        config["network"]["save_path"] = str(root / "server.json")
        config["telemetry"]["decision_log"] = str(root / "decisions.jsonl")
        path = root / "config.json"
        path.write_text(json.dumps(config))
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
        from village.config import configure

        configure(path)
        from village.persistence import SaveStore
        from village.world import World

        world = World(seed=301)
        for gate in world.gates:
            world.gates[gate] = 20.0
        SaveStore(root / "server.json").save(world)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "village.server",
                "--config",
                str(path),
                "--port",
                "0",
                "--run-seconds",
                "22",
            ],
            capture_output=True,
            text=True,
            timeout=35,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        rows = [
            json.loads(line)
            for line in (root / "decisions.jsonl").read_text().splitlines()
        ]
        requests = [r for r in rows if r["event"] == "model_request"]
        responses = [r for r in rows if r["event"] == "model_response"]
        assert requests and responses, (requests, responses)
        assert any(
            r["inference"] and r["outcome"] in ("accepted", "rejected", "stale")
            for r in responses
        ), responses
        saved = json.loads((root / "server.json").read_text())
        assert saved["world"]["time"] >= 21.0
        pathlib.Path(
            "artifacts/server-client/priority-live-attempt-data.json"
        ).write_text(
            json.dumps(
                dict(responses=responses, board=saved["world"]["task_board"]), indent=2
            )
            + "\n"
        )
        assert saved["world"]["task_board"]["repair_plan"] is not None, saved["world"][
            "task_board"
        ]
        report = dict(
            server_simulated_seconds=saved["world"]["time"],
            requests=len(requests),
            repair_plan=saved["world"]["task_board"]["repair_plan"],
            responses=responses,
            stdout=result.stdout,
        )
        pathlib.Path(
            "artifacts/server-client/priority-model-server-smoke.json"
        ).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
