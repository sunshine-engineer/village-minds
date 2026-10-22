"""Panda3D viewer/controller for a continuously running loopback village server."""

import argparse
import math
import time
from .config import get_settings


def game_class():
    # Import rendering only after startup settings and the initial server handshake.
    from .game import VillageGame, C, D
    from .persistence import restore
    from .interpolation import SnapshotInterpolator

    class RemoteGame(VillageGame):
        def __init__(self, args, session):
            self.session = session
            self.presentation = SnapshotInterpolator(
                get_settings()["network"]["interpolation"]
            )
            initial = session.latest
            self.presentation.push(initial)
            self.display_poses, self.animation_time = self.presentation.sample(
                time.monotonic()
            )
            session.world = restore(initial["world"])
            session.world.controlled = initial["controlled"]
            args.remote_source = session
            super().__init__(args)
            self.controls.setText(
                self.controls.getText()
                .replace(
                    f"{C['speak']} Speak | {C['pause']} Pause | {C['speed']} Speed",
                    f"{C['speak']} Speak | Simulation runs on server",
                )
                .replace(
                    f"{C['save']} Save | {C['escape']} Quit/cancel",
                    f"Server autosaves | {C['escape']} Disconnect",
                )
            )
            self.smoke_started = time.monotonic()
            self.smoke_said = False

        def advance_world(self, dt):
            # Send current input before snapshot validation/scene work can delay it.
            if self.session.connected:
                self.orbit += (
                    (
                        int(C["orbit_left"] in self.keys)
                        - int(C["orbit_right"] in self.keys)
                    )
                    * dt
                    * D["orbit_speed"]
                )
                right = int(C["right"] in self.keys) - int(C["left"] in self.keys)
                forward = int(C["forward"] in self.keys) - int(
                    C["backward"] in self.keys
                )
                # Rotating two pressed axes can exceed one; normalize before sending.
                dx = right * math.cos(self.orbit) - forward * math.sin(self.orbit)
                dy = right * math.sin(self.orbit) + forward * math.cos(self.orbit)
                scale = max(1.0, math.hypot(dx, dy))
                self.session.motion = (
                    (dx / scale, dy / scale) if not self.typing else (0.0, 0.0)
                )
            else:
                self.session.motion = (0.0, 0.0)
            state = self.session.poll()
            if state is not None and self.presentation.push(state):
                self.world = restore(state["world"])
                self.world.controlled = state["controlled"]
                self.brains.local_decisions = state["brains"]["local_decisions"]
                self.brains.model_decisions = state["brains"]["model_decisions"]
            self.display_poses, self.animation_time = self.presentation.sample(
                time.monotonic()
            )
            self.brains.status = self.session.status
            if not self.session.connected:
                self.world.controlled = None

        def display_position(self, kind, identity, authoritative):
            return self.display_poses.get((kind, identity), authoritative)

        def display_time(self):
            return self.animation_time

        def takeover(self, index):
            if not self.typing:
                self.keys.clear()
                self.session.motion = (0.0, 0.0)
                self.session.submit(dict(kind="takeover", index=index))

        def apply_player_decision(self, bot, decision):
            return self.session.submit(dict(kind="action", **decision))

        def submit_chat(self, text):
            if self.typing:
                self.session.submit(dict(kind="say", text=text))
                self.close_chat()

        def toggle_pause(self):
            self.brains.status = (
                "Server simulation continues while connected or disconnected"
            )

        def cycle_speed(self):
            self.brains.status = "Simulation speed is managed by the server"

        def save_world(self):
            return True

        def update(self, task):
            # Suppress the single-player smoke harness: it mutates World directly.
            smoke = self.smoke_frames
            self.smoke_frames = None
            result = super().update(task)
            self.smoke_frames = smoke
            if not self.session.connected:
                self.hint.setText(
                    self.session.status + " | Reconnecting; server simulation continues"
                )
            if smoke is not None:
                self.smoke_frames += 1
                if self.smoke_frames == 3:
                    self.takeover(0)
                elapsed = time.monotonic() - self.smoke_started
                if self.world.controlled == 0:
                    if not self.smoke_said:
                        self.session.submit(
                            dict(kind="say", text="Connected to the shared village.")
                        )
                        self.smoke_said = True
                    if elapsed < 1.0:
                        self.keys.add(C["right"])
                    else:
                        self.keys.clear()
                time.sleep(0.01)
                if (
                    elapsed >= 2.0 and self.smoke_said
                ) or elapsed >= 3 * self.session.settings["request_seconds"]:
                    from pathlib import Path

                    Path("artifacts").mkdir(exist_ok=True)
                    self.win.saveScreenshot("artifacts/client-smoke.png")
                    if not self.smoke_said:
                        raise RuntimeError(
                            "Client smoke test failed to acquire a villager"
                        )
                    self.userExit()
            return result

    return RemoteGame


def main():
    from .cli import prepare, attach_profile

    parser = argparse.ArgumentParser(description=__doc__)
    settings = prepare(parser)
    parser.add_argument(
        "--server",
        default=f"http://{settings['network']['host']}:{settings['network']['port']}",
    )
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    attach_profile(parser, args)
    from .network import RemoteSession, RemoteError

    try:
        session = RemoteSession(args.server)
    except (OSError, ValueError, RuntimeError, RemoteError) as exc:
        parser.exit(1, f"Cannot connect: {exc}\n")
    args.demo = True
    args.no_save = True
    args.pace = 1.0
    game = None
    try:
        game = game_class()(args, session)
        game.run()
    finally:
        session.close()
        if game:
            game.destroy()


if __name__ == "__main__":
    main()
