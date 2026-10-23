"""Offscreen integration for speed keys, substeps, pause and player decision logs.

File: scripts/check_speed.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    """Run the check speed diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=artifacts) as directory:
        log_path = Path(directory) / "decisions.jsonl"
        from village.config import get_settings
        from village.game import VillageGame

        game = VillageGame(
            SimpleNamespace(
                smoke_test=True,
                demo=True,
                url="",
                model="",
                no_save=True,
                pace=0.5,
                decision_log=str(log_path),
            )
        )
        game.smoke_frames = None
        controls = get_settings()["controls"]
        try:
            for _ in range(4):
                game.messenger.send(controls["speed"])
            assert game.pace == 10
            game.world.next_wave = 0.5
            game.clock_dt = lambda: 0.1
            task = SimpleNamespace(cont="continue")
            game.update(task)
            assert abs(game.world.time - 1) < 1e-8
            assert game.world.wave == 1
            assert "Speed 10x" in game.status.getText()
            game.messenger.send(controls["pause"])
            before = game.world.time
            game.update(task)
            assert game.world.time == before
            game.messenger.send(controls["pause"])
            game.takeover(0)
            game.world.villagers[0].energy = 50
            game.messenger.send(controls["actions"]["rest"])
            game.world.move_player(1, 0, 0.1)
            game.close_decision_log()
            records = [
                json.loads(row)
                for row in log_path.read_text(encoding="utf-8").splitlines()
            ]
            assert any(
                r["event"] == "decision"
                and r["source"] == "player"
                and r["outcome"] == "accepted"
                for r in records
            )
            assert any(
                r["event"] == "movement" and r["source"] == "player" for r in records
            )
            report = {
                "passed": [
                    "speed key reaches 10x",
                    "one frame advances ten safe simulation substeps",
                    "wave timer advances at accelerated speed",
                    "HUD shows 10x",
                    "pause stops accelerated simulation",
                    "player actions and movement recorded in JSONL",
                ],
                "method": "native renderer with Panda3D messenger dispatch and injected frame dt; temporary session",
            }
            (artifacts / "speed-check.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            print(json.dumps(report, indent=2))
        finally:
            game.close_decision_log()
            game.destroy()


if __name__ == "__main__":
    main()
