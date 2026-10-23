"""Verify six villagers act concurrently in a temporary native game session.

File: scripts/check_autonomy.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    """Run the check autonomy diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    from village.cli import attach_profile, prepare

    prepare(parser)
    parser.add_argument(
        "--demo", action="store_true", help="Check without any model connection"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Render offscreen without taking desktop focus",
    )
    parser.add_argument(
        "--wait-for-model",
        action="store_true",
        help="Also require one accepted real model plan within 100 seconds",
    )
    args = parser.parse_args()
    attach_profile(parser, args)
    from village.game import VillageGame
    from village.simulation import distance

    if args.headless:
        from panda3d.core import loadPrcFileData

        loadPrcFileData(
            "autonomy-check",
            "window-type offscreen\nback-buffers 0\nclock-mode limited\nclock-frame-rate 20",
        )
    app = VillageGame(
        SimpleNamespace(
            demo=args.demo,
            no_save=True,
            smoke_test=False,
            url=args.url,
            model=args.model,
            model_profile=args.model_profile,
            pace=1,
        )
    )
    starts = [bot.position for bot in app.world.villagers]
    maximum = [0.0] * len(starts)

    def finish(task):
        """Check concurrent villager displacement and optional accepted model progress.

        Args:
            task: Panda3D task context providing continuation/completion status.

        Returns:
            Panda3D continuation or completion status; failed expectations raise AssertionError.
        """
        for i, bot in enumerate(app.world.villagers):
            maximum[i] = max(maximum[i], distance(starts[i], bot.position))
        if task.time < 5:
            return task.cont
        assert all(moved > 0.5 for moved in maximum), maximum
        if args.wait_for_model and not app.brains.model_decisions:
            if task.time >= 100:
                raise AssertionError("No accepted model plan: " + app.brains.status)
            return task.cont
        report = {
            "passed": "all six villagers moved without waiting for a model turn",
            "backend": app.brains.status,
            "local_decisions": app.brains.local_decisions,
            "accepted_model_decisions": app.brains.model_decisions,
            "seconds": round(task.time, 2),
            "villagers": [
                {
                    "name": b.name,
                    "action": b.action,
                    "max_distance_from_start": round(moved, 2),
                }
                for b, moved in zip(app.world.villagers, maximum)
            ],
        }
        out = Path("artifacts")
        out.mkdir(exist_ok=True)
        suffix = ("windows" if sys.platform == "win32" else "linux") + (
            "-model" if args.wait_for_model else ""
        )
        (out / f"autonomy-{suffix}.json").write_text(json.dumps(report, indent=2))
        app.win.saveScreenshot(str(out / f"autonomy-{suffix}.png"))
        print(json.dumps(report, indent=2), flush=True)
        app.taskMgr.stop()
        return task.done

    app.taskMgr.add(finish, "concurrent-autonomy-check")
    try:
        app.run()
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
