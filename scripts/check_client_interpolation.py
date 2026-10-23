"""Offscreen render check: run from the repository root with Panda3D installed.

File: scripts/check_client_interpolation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import json
import math
import pathlib
import sys
from copy import deepcopy
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main():
    """Run the check client interpolation diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    from village.client import game_class
    from village.config import get_settings
    from village.entities import Monster
    from village.persistence import snapshot
    from village.world import World

    world = World(seed=301)
    world.monsters = [Monster("m1", "north_gate", (0, 10))]
    base = snapshot(world)
    current = [0.0]

    def packet(t, frame):
        """Build a controlled confirmed snapshot at a known simulation/receive time.

        Args:
            t: Controlled simulation/receive timestamp in seconds.
            frame: Monotonically increasing fixture snapshot number.

        Returns:
            Snapshot dictionary with deterministic poses and connection metadata.
        """
        state = deepcopy(base)
        state["world"]["time"] = t
        state["world"]["villagers"][0]["position"] = [t * 5, 0]
        state["world"]["monsters"][0]["position"] = [t * 5, 10]
        return dict(
            server_id="render-fixture",
            frame=frame,
            controlled=0,
            _client_epoch=1,
            _client_received_at=t,
            world=state,
            brains=dict(local_decisions=0, model_decisions=0),
        )

    class Session:
        """Render-fixture session supplying controlled snapshots without HTTP."""

        def __init__(self):
            """Initialize Session and its owned state.

            Returns:
                None.
            """
            self.latest = packet(0, 0)
            self.pending = None
            self.connected = True
            self.status = "CONNECTED"
            self.settings = get_settings()["network"]
            self.motion = (0, 0)

        def poll(self):
            """Deliver the fixture's next confirmed snapshot without an HTTP connection.

            Returns:
                Next pending snapshot, or None when the fixture has no update.
            """
            result = self.pending
            self.pending = None
            return result

        def submit(self, command):
            """Accept a fixture command without mutating authoritative simulation state.

            Args:
                command: Sequenced player input command dictionary.

            Returns:
                None; this render-only session stub does not execute server actions.
            """
            return True

    session = Session()
    args = argparse.Namespace(
        smoke_test=True, no_save=True, demo=True, pace=1.0, url="", model=""
    )
    with patch("village.client.time.monotonic", side_effect=lambda: current[0]):
        game = game_class()(args, session)
        game.smoke_frames = None
        game.clock_dt = lambda: 1 / 60
        try:
            next_packet = 1
            frames = []
            for i in range(121):
                current[0] = i / 60
                while next_packet * 0.2 <= current[0] + 1e-9:
                    session.pending = packet(next_packet * 0.2, next_packet)
                    next_packet += 1
                game.update(argparse.Namespace(cont="cont"))
                game.graphicsEngine.renderFrame()
                actor = game.actors[0][0].getX()
                monster = game.monster_nodes["m1"].getX()
                target = game.camera.getX() - math.sin(game.orbit) * game.zoom
                assert abs(target - actor) < 1e-5, (target, actor)
                assert abs(actor - monster) < 1e-5, (actor, monster)
                latest = (next_packet - 1) * 0.2
                assert abs(game.world.villagers[0].position[0] - latest * 5) < 1e-5
                assert abs(game.world.time - latest) < 1e-5
                frames.append(
                    dict(
                        t=current[0],
                        display_x=actor,
                        authoritative_x=game.world.villagers[0].position[0],
                        leg_pitch=game.actors[0][2][0].getP(),
                    )
                )
            steps = [
                abs(b["display_x"] - a["display_x"])
                for a, b in zip(frames[24:], frames[25:])
            ]
            raw = [
                abs(b["authoritative_x"] - a["authoritative_x"])
                for a, b in zip(frames[24:], frames[25:])
            ]
            assert max(steps) < 0.12 and max(raw) > 0.9, (max(steps), max(raw))
            moving = [
                f for f in frames[30:] if abs(f["t"] / 0.2 - round(f["t"] / 0.2)) > 0.05
            ]
            assert len({round(f["leg_pitch"], 3) for f in moving}) > 20
            game.graphicsEngine.renderFrame()
            game.graphicsEngine.renderFrame()
            game.win.saveScreenshot("artifacts/client-interpolation.png")
            report = dict(
                frames=len(frames),
                timeline_fps=60,
                measured_frame_rate=False,
                snapshot_hz=5,
                max_rendered_step=max(steps),
                max_snapshot_step=max(raw),
                camera_matches_actor=True,
                monsters_interpolated=True,
                authoritative_world_unchanged=True,
                animation_between_packets=True,
                samples=frames,
            )
            pathlib.Path(
                "artifacts/server-client/interpolation-render.json"
            ).write_text(json.dumps(report, indent=2) + "\n")
            print(
                json.dumps(
                    {k: v for k, v in report.items() if k != "samples"}, indent=2
                )
            )
        finally:
            game.destroy()


if __name__ == "__main__":
    main()
