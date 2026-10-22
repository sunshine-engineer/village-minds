"""Real loopback HTTP and offscreen Panda3D input-to-motion measurement.

No simulated clock, inference, save files or prediction. A controlled fixture
isolates movement in an open part of the map; this is not a human playtest.
"""

import argparse
import os
import json
import math
from pathlib import Path
import statistics
import sys
import threading
import subprocess
import tempfile
import queue
from copy import deepcopy
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument(
        "--output", default="artifacts/server-client/responsiveness.json"
    )
    parser.add_argument(
        "--transport",
        choices=("legacy", "exchange", "responsive"),
        default="responsive",
    )
    parser.add_argument("--suite-seconds", type=float, default=600.0)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("At least two samples required")
    from village.config import get_settings
    from village.world import World
    from village.persistence import SaveStore
    from village.network import RemoteSession
    from village.client import game_class
    from village.game import C

    settings = get_settings()
    settings["network"]["exchange_motion"] = args.transport != "legacy"
    settings["network"]["wake_on_input"] = args.transport == "responsive"
    settings["network"]["tcp_no_delay"] = args.transport != "legacy"
    temporary = tempfile.TemporaryDirectory()
    work = Path(temporary.name)
    config = deepcopy(settings)
    save = work / "world.json"
    config["network"]["save_path"] = str(save)
    config["telemetry"]["decision_log"] = ""
    config_path = work / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    world = World(seed=301)
    world.villagers[0].position = (0, 0)
    world.next_wave = (
        (2 * args.samples + 1) * settings["network"]["request_seconds"] * 10
    )
    SaveStore(save).save(world)
    stderr = (work / "server-errors.log").open("w")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "village.server",
            "--demo",
            "--config",
            str(config_path),
            "--save-path",
            str(save),
            "--port",
            "0",
            "--run-seconds",
            str(args.suite_seconds),
        ],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
    )
    ready = queue.Queue(maxsize=1)

    def read_ready():
        ready.put(process.stdout.readline())

    reader = threading.Thread(target=read_ready, daemon=True)
    reader.start()
    failures = []
    port = None
    overall_deadline = time.monotonic() + args.suite_seconds

    class TracedSession(RemoteSession):
        trial = None

        def command(self, command):
            trial = self.trial
            matching = (
                trial is not None
                and command.get("kind") == "move"
                and command.get("dx", 0) * trial["direction"] > 0.9
            )
            if matching and "request_sent_at" not in trial:
                trial["request_sent_at"] = time.monotonic()
                reply = super().command(command)
                trial["ack_received_at"] = time.monotonic()
                return reply
            return super().command(command)

        def poll(self):
            state = super().poll()
            trial = self.trial
            if (
                state
                and trial
                and "snapshot_at" not in trial
                and state["controlled"] == 0
            ):
                x = state["world"]["world"]["villagers"][0]["position"][0]
                if (x - trial["baseline_x"]) * trial["direction"] > 0.01:
                    trial["snapshot_at"] = time.monotonic()
            return state

    session = game = None
    rows = []
    try:
        line = ready.get(timeout=6 * settings["network"]["request_seconds"])
        metadata = json.loads(line)
        if not metadata.get("ready"):
            raise RuntimeError("Temporary server did not become ready")
        port = metadata["port"]
        session = TracedSession(f"http://127.0.0.1:{port}")
        game = game_class()(
            argparse.Namespace(
                smoke_test=True, no_save=True, demo=True, pace=1.0, url="", model=""
            ),
            session,
        )
        game.smoke_frames = None
        game.orbit = 0
        game.clock_dt = lambda: 1 / 60

        def frame():
            if time.monotonic() >= overall_deadline:
                raise RuntimeError("Responsiveness suite wall budget exceeded")
            if process.poll() is not None:
                raise RuntimeError(
                    "Temporary server exited before measurement completed"
                )
            game.update(argparse.Namespace(cont="cont"))
            game.graphicsEngine.renderFrame()
            time.sleep(1 / 120)

        def settle(seconds):
            started = changed_at = time.monotonic()
            previous = None
            while (
                time.monotonic() - started < 3 * settings["network"]["request_seconds"]
            ):
                frame()
                now = time.monotonic()
                position = (
                    game.world.villagers[0].position[0],
                    game.actors[0][0].getX(),
                )
                if previous is None or any(
                    abs(a - b) > 1e-5 for a, b in zip(previous, position)
                ):
                    changed_at = now
                previous = position
                if game.world.failed:
                    raise RuntimeError("Responsiveness fixture village failed")
                if (
                    now - started >= seconds
                    and now - changed_at >= 2 * settings["network"]["poll_seconds"]
                    and game.world.controlled == 0
                ):
                    return
            raise RuntimeError("Motion did not settle before measurement")

        game.takeover(0)
        settle(1.0)
        if game.world.controlled != 0:
            raise RuntimeError("Failed to take control")
        for i in range(args.samples):
            for enabled in ((False, True) if i % 2 == 0 else (True, False)):
                # Alternate order to reduce constant warm-up and scheduling bias.
                game.presentation.settings["enabled"] = enabled
                game.keys.clear()
                session.trial = None
                settle(0.8)
                direction = 1 if i % 2 == 0 else -1
                trial = dict(
                    direction=direction,
                    baseline_x=game.world.villagers[0].position[0],
                    display_baseline_x=game.actors[0][0].getX(),
                    input_at=time.monotonic(),
                )
                session.trial = trial
                game.keys.add(C["right"] if direction == 1 else C["left"])
                deadline = time.monotonic() + 3 * settings["network"]["request_seconds"]
                while time.monotonic() < deadline:
                    frame()
                    if (
                        "render_at" not in trial
                        and "snapshot_at" in trial
                        and (game.actors[0][0].getX() - trial["display_baseline_x"])
                        * direction
                        > 0.01
                    ):
                        trial["render_at"] = time.monotonic()
                    if all(
                        k in trial
                        for k in ("ack_received_at", "snapshot_at", "render_at")
                    ):
                        break
                else:
                    raise RuntimeError(f"Incomplete responsiveness sample: {trial}")
                rows.append(
                    dict(
                        interpolation=enabled,
                        sample=i,
                        **{
                            k.removesuffix("_at")
                            + "_ms": round(1000 * (trial[k] - trial["input_at"]), 3)
                            for k in (
                                "request_sent_at",
                                "ack_received_at",
                                "snapshot_at",
                                "render_at",
                            )
                        },
                    )
                )
                session.trial = None
                game.keys.clear()
        report = dict(
            method="separate authoritative server process, real loopback HTTP, offscreen Panda3D renderFrame, monotonic wall time",
            human_playtest=False,
            fixture_revision=3,
            separate_server_process=True,
            waves_deferred=True,
            stationary_before_input=True,
            transport=args.transport,
            network=settings["network"],
            samples=rows,
            summary=[],
        )
        for enabled in (False, True):
            group = [r for r in rows if r["interpolation"] == enabled]
            report["summary"].append(
                dict(
                    interpolation=enabled,
                    samples=len(group),
                    **{
                        key: dict(
                            median=round(statistics.median(r[key] for r in group), 3),
                            p95=sorted(r[key] for r in group)[
                                math.ceil(0.95 * len(group)) - 1
                            ],
                            max=max(r[key] for r in group),
                        )
                        for key in (
                            "request_sent_ms",
                            "ack_received_ms",
                            "snapshot_ms",
                            "render_ms",
                        )
                    },
                )
            )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report["summary"], indent=2))
    except BaseException as exc:
        failure = dict(
            error=f"{type(exc).__name__}: {exc}",
            transport=args.transport,
            completed_samples=rows,
            trial=session.trial if session else None,
            client_status=session.status if session else None,
            last_known_state=(
                dict(
                    frame=session.latest.get("frame"),
                    controlled=session.latest.get("controlled"),
                    world_failed=session.latest["world"]["world"]["failed"],
                    actor_health=session.latest["world"]["world"]["villagers"][0][
                        "health"
                    ],
                )
                if session
                else None
            ),
            simulation_failures=failures,
        )
        output = Path(args.output).with_suffix(".failed.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(failure, indent=2) + "\n")
        raise
    finally:
        if session:
            session.close()
        if game:
            game.destroy()
        if process.poll() is None:
            if os.name == "nt":
                # Windows venv launchers can own a child interpreter. Stop only
                # this fixture's process tree so inherited log handles close.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        reader.join(timeout=1)
        process.stdout.close()
        stderr.close()
        temporary.cleanup()


if __name__ == "__main__":
    main()
