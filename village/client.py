"""Panda3D viewer/controller for a continuously running loopback village server.

File: village/client.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import math
import time

from .config import get_settings


def game_class():
    # Import rendering only after startup settings and the initial server handshake.
    """Construct the remote-rendering subclass after startup configuration is available.

    Returns:
        RemoteGame class; no local physics or inference is enabled.
    """
    from .game import C, D, VillageGame
    from .interpolation import SnapshotInterpolator
    from .persistence import restore

    class RemoteGame(VillageGame):
        """Panda3D presentation of authoritative snapshots with queued player input."""

        def __init__(self, args, session):
            """Initialize RemoteGame and its owned state.

            Args:
                args: Parsed command-line options for this entry point.
                session: RemoteSession supplying confirmed snapshots and accepting queued input.

            Returns:
                None.
            """
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
            """Publish input before restoring the newest authoritative snapshot and sampling presentation.

            Args:
                dt: Elapsed simulation seconds; rendering overrides receive real frame seconds.

            Returns:
                None; updates the local render/HUD mirror without advancing physics.
            """
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
            """Choose a buffered presentation pose while preserving authoritative fallback.

            Args:
                kind: Entity or request category used by the owning operation.
                identity: Stable entity identifier used to match presentation history.
                authoritative: Newest confirmed position used when a buffered pose is unavailable.

            Returns:
                Displayed position, or the supplied authoritative position.
            """
            return self.display_poses.get((kind, identity), authoritative)

        def display_time(self):
            """Expose interpolated simulation time for animation.

            Returns:
                Presentation time in simulation seconds.
            """
            return self.animation_time

        def takeover(self, index):
            """Queue a possession change for acknowledgement by the server.

            Args:
                index: Villager roster index selected by the caller.

            Returns:
                None; possession changes only after server validation.
            """
            if not self.typing:
                self.keys.clear()
                self.session.motion = (0.0, 0.0)
                self.session.submit(dict(kind="takeover", index=index))

        def apply_player_decision(self, bot, decision):
            """Queue a player work action instead of mutating the client world.

            Args:
                bot: Villager whose current state or work is being considered.
                decision: Proposed structured action with optional target/dialogue fields.

            Returns:
                Whether the bounded client queue accepted the action.
            """
            return self.session.submit(dict(kind="action", **decision))

        def submit_chat(self, text):
            """Queue player dialogue for server-side validation and hearing.

            Args:
                text: Dialogue or event text to validate and publish.

            Returns:
                None; closes the local dialogue editor.
            """
            if self.typing:
                self.session.submit(dict(kind="say", text=text))
                self.close_chat()

        def toggle_pause(self):
            """Explain that pausing is unavailable in the remote client.

            Returns:
                None; the authoritative server keeps running.
            """
            self.brains.status = (
                "Server simulation continues while connected or disconnected"
            )

        def cycle_speed(self):
            """Explain that the remote client cannot alter server simulation pace.

            Returns:
                None; server timing remains unchanged.
            """
            self.brains.status = "Simulation speed is managed by the server"

        def save_world(self):
            """Keep the rendering client from writing authoritative campaign files.

            Returns:
                True; saving belongs to the server.
            """
            return True

        def update(self, task):
            # Suppress the single-player smoke harness: it mutates World directly.
            """Run a render frame and optional bounded client smoke-test interactions.

            Args:
                task: Panda3D task context providing continuation/completion status.

            Returns:
                Panda3D task continuation status.

            Raises:
                RuntimeError: If the input violates the validation contract described above.
            """
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
    """Connect a render-only client to the authoritative loopback server.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    from .cli import attach_profile, prepare

    parser = argparse.ArgumentParser(description=__doc__)
    settings = prepare(parser)
    parser.add_argument(
        "--server",
        default=f"http://{settings['network']['host']}:{settings['network']['port']}",
    )
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    attach_profile(parser, args)
    from .network import RemoteError, RemoteSession

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
