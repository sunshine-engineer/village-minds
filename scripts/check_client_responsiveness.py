"""Real loopback HTTP and offscreen Panda3D input-to-motion measurement.

No simulated clock, inference, save files or prediction. A controlled fixture
isolates movement in an open part of the map; this is not a human playtest.
"""

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import threading
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
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("At least two samples required")
    from village.config import get_settings
    from village.world import World
    from village.brains import BrainScheduler
    from village.server import VillageServer, make_http_server
    from village.network import RemoteSession
    from village.client import game_class
    from village.game import C

    settings = get_settings()
    settings["network"]["exchange_motion"] = args.transport != "legacy"
    settings["network"]["wake_on_input"] = args.transport == "responsive"
    stop = threading.Event()
    world = World(seed=301)
    world.villagers[0].position = (0, 0)
    world.next_wave = (
        (2 * args.samples + 1) * settings["network"]["request_seconds"] * 10
    )
    runtime = VillageServer(world, BrainScheduler(world, "", "", demo=True))
    http = make_http_server(runtime, "127.0.0.1", 0)
    failures = []

    def simulate():
        try:
            while not stop.is_set():
                started = time.monotonic()
                runtime.step(settings["network"]["tick_seconds"])
                stop.wait(
                    max(
                        0,
                        settings["network"]["tick_seconds"]
                        - (time.monotonic() - started),
                    )
                )
        except Exception as exc:
            failures.append(repr(exc))
            stop.set()

    simulation = threading.Thread(target=simulate, daemon=True)
    serving = threading.Thread(target=http.serve_forever, daemon=True)
    simulation.start()
    serving.start()

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
        session = TracedSession(f"http://127.0.0.1:{http.server_port}")
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
            if failures:
                raise RuntimeError(failures)
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
            method="real loopback HTTP, offscreen Panda3D renderFrame, monotonic wall time",
            human_playtest=False,
            fixture_revision=2,
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
            world_failed=runtime.world.failed,
            server_frame=runtime.frame,
            controlled=runtime.world.controlled,
            actor_health=runtime.world.villagers[0].health,
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
        stop.set()
        simulation.join(timeout=3)
        http.shutdown()
        http.server_close()
        serving.join(timeout=3)


if __name__ == "__main__":
    main()
