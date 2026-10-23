"""Linux/X11 integration check using targeted X11 window keyboard events (needs libX11).

Run: .venv/bin/python scripts/check_window.py [--live]
This opens/focuses the game window, sends test keys, saves evidence, and closes it.

File: scripts/check_window.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import ctypes
import ctypes.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class XKeyEvent(ctypes.Structure):
    """ctypes layout of an X11 keyboard event used by the Linux integration fixture."""

    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("keycode", ctypes.c_uint),
        ("same_screen", ctypes.c_int),
    ]


class XEvent(ctypes.Union):
    """ctypes union large enough to hold a targeted X11 input event."""

    _fields_ = [("key", XKeyEvent), ("pad", ctypes.c_long * 24)]


class WindowKeys:
    """Targeted Linux/X11 test input with explicit press/release and display cleanup."""

    def __init__(self, window, task_mgr):
        """Initialize WindowKeys and its owned state.

        Args:
            window: Native game window handle for targeted X11 events.
            task_mgr: Panda3D task manager scheduling key release.

        Returns:
            None.

        Raises:
            RuntimeError: If the input violates the validation contract described above.
        """
        self.task_mgr = task_mgr
        self.x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError(
                "Cannot open X11 display; run in a WSLg/desktop session."
            )
        self.x11.XSetInputFocus.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        self.x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x11.XStringToKeysym.restype = ctypes.c_ulong
        self.x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XKeysymToKeycode.restype = ctypes.c_uint
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XWarpPointer.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.x11.XSendEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.POINTER(XEvent),
        ]
        self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self.window = window
        self.held = set()
        # Focus once before the first frame; repeatedly refocusing each key
        # races with WSLg's native window activation and can drop events.
        self.x11.XWarpPointer(self.display, 0, self.window, 0, 0, 0, 0, 720, 450)
        self.x11.XSetInputFocus(self.display, self.window, 1, 0)
        self.x11.XSync(self.display, 0)

    def send(self, key, down):
        """Send a targeted X11 press or release and track held keys for cleanup.

        Args:
            key: Configured key name or mapping key being considered.
            down: Whether to send a key press rather than release.

        Returns:
            None; raises RuntimeError when a keycode or send operation is unavailable.

        Raises:
            RuntimeError: If the input violates the validation contract described above.
        """
        sym = self.x11.XStringToKeysym(key.encode())
        code = self.x11.XKeysymToKeycode(self.display, sym)
        if not code:
            raise RuntimeError(f"No keycode for {key}")
        event = XEvent()
        event.key.type = 2 if down else 3
        event.key.display = self.display
        event.key.window = self.window
        event.key.root = self.x11.XDefaultRootWindow(self.display)
        event.key.time = int(time.monotonic() * 1000) & 0xFFFFFFFF
        event.key.x, event.key.y = 720, 450
        event.key.same_screen = 1
        event.key.keycode = code
        if not self.x11.XSendEvent(
            self.display, self.window, False, 1 if down else 2, ctypes.byref(event)
        ):
            raise RuntimeError("X11 targeted key injection failed")
        self.x11.XFlush(self.display)
        if down:
            self.held.add(key)
        else:
            self.held.discard(key)

    def tap(self, key):
        """Press a test key and schedule its release through the engine task manager.

        Args:
            key: Configured key name or mapping key being considered.

        Returns:
            None; the release callback completes after the configured fixture delay.
        """
        self.send(key, True)

        def release(task):
            """Release the previously pressed test key.

            Args:
                task: Panda3D task context providing continuation/completion status.

            Returns:
                Panda3D task completion status.
            """
            self.send(key, False)
            return task.done

        self.task_mgr.doMethodLater(0.12, release, f"release-test-key-{key}")

    def close(self):
        """Release held keys and close this fixture's X11 display connection.

        Returns:
            None.
        """
        for key in list(self.held):
            self.send(key, False)
        self.x11.XCloseDisplay(self.display)


def main():
    """Run the check window diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    from village.cli import attach_profile, prepare

    prepare(parser)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--save-path", help="Test a separate save slot; existing slot is archived"
    )
    args = parser.parse_args()
    attach_profile(parser, args)
    from village.game import VillageGame
    from village.simulation import LOCATIONS, Monster, distance

    app = VillageGame(
        SimpleNamespace(
            demo=not args.live,
            smoke_test=False,
            no_save=not bool(args.save_path),
            save_path=args.save_path,
            new_game=bool(args.save_path),
            pace=1,
            url=args.url,
            model=args.model,
            model_profile=args.model_profile,
        )
    )
    assert app.win.getProperties().getOpen(), "Window did not open"
    inputs = WindowKeys(app.win.getWindowHandle().getIntHandle(), app.taskMgr)
    checks = []
    # Count actual accepted model responses, never routine actions shown while
    # the backend happens to be connected.
    accepted_model_decisions = app.brains.model_history
    state = {"stage": 0, "after": time.monotonic() + 0.5}
    started = time.monotonic()
    out = Path("artifacts")
    out.mkdir(exist_ok=True)

    def check(condition, label):
        """Assert a named integration condition and record it once on success.

        Args:
            condition: Named baseline/scripted/model/adverse condition.
            label: Name of the integration assertion recorded on success.

        Returns:
            None; raises AssertionError when the condition fails.
        """
        if not condition:
            raise AssertionError(label)
        if label not in checks:
            checks.append(label)

    def step(task):
        """Drive the staged real-window control fixture and collect action/save evidence.

        Args:
            task: Panda3D task context providing continuation/completion status.

        Returns:
            Panda3D continuation or completion status.
        """
        now = time.monotonic()
        if now < state["after"]:
            return task.cont
        stage = state["stage"]
        if stage == 0:
            check(app.win.getProperties().getOpen(), "onscreen window open")
            inputs.tap("1")
        elif stage == 1:
            check(app.world.controlled == 0, "key 1 possesses Mira")
            state["position"] = app.world.villagers[0].position
            inputs.send("w", True)
        elif stage == 2:
            inputs.send("w", False)
            check(
                distance(state["position"], app.world.villagers[0].position) > 0.1,
                "W moves the player",
            )
            inputs.tap("Return")
        elif stage == 3:
            if "text_index" not in state:
                check(app.typing and app.entry["focus"], "Enter opens focused dialogue")
                state["text_index"] = 0
            if state["text_index"] < len("hello123"):
                key = "hello123"[state["text_index"]]
                if state.get("text_key_down"):
                    inputs.send(key, False)
                    state["text_key_down"] = False
                    state["text_index"] += 1
                else:
                    inputs.send(key, True)
                    state["text_key_down"] = True
                state["after"] = now + 0.15
                return task.cont
        elif stage == 4:
            check(
                app.entry.get() == "hello123",
                f"real typed text reaches dialogue field (got {app.entry.get()!r})",
            )
            check(app.world.controlled == 0, "typing digits does not change possession")
            inputs.tap("Return")
        elif stage == 5:
            check(
                not app.typing and app.entry.isHidden(),
                "Enter submits and closes dialogue",
            )
            check(
                "Mira: hello123" in app.world.villagers[0].memory,
                "submitted dialogue enters memory",
            )
            inputs.tap("Tab")
        elif stage == 6:
            check(app.world.controlled == 1, "Tab switches to Bram")
            inputs.tap("6")
        elif stage == 7:
            check(app.world.controlled == 5, "key 6 switches to Edda")
            app.world.villagers[5].position = LOCATIONS["farm"]
            state["supplies"] = app.world.villagers[5].supplies
            inputs.tap("h")
        elif stage == 8:
            check(
                app.world.villagers[5].supplies > state["supplies"],
                "H harvests ripe crops",
            )
            if app.world.time < app.world.villagers[5].work_at:
                return task.cont
            if not state.get("planted"):
                inputs.tap("f")
                state["planted"] = True
                state["after"] = now + 0.5
                return task.cont
            check(
                app.world.villagers[5].contributions["planted"] > 0,
                "F plants an empty plot",
            )
            app.world.villagers[5].position = LOCATIONS["orchard"]
            state["wood"] = app.world.villagers[5].wood
            inputs.tap("e")
        elif stage == 9:
            check(app.world.villagers[5].wood > state["wood"], "E gathers orchard wood")
            app.world.villagers[5].position = LOCATIONS["storehouse"]
            state["food_stock"] = app.world.store["food"]
            # Work actions have a one-second simulation cooldown.
            state["wait_work"] = app.world.villagers[5].work_at
        elif stage == 10:
            if app.world.time < state["wait_work"]:
                return task.cont
            inputs.tap("t")
        elif stage == 11:
            check(
                app.world.villagers[5].supplies == 0
                and app.world.villagers[5].wood == 0,
                "T deposits carried food and wood",
            )
            check(
                app.world.store["food"] > state["food_stock"],
                "deposit adds shared food",
            )
            app.world.villagers[5].hunger = 60
            state["wait_work"] = app.world.villagers[5].work_at
        elif stage == 12:
            if app.world.time < state["wait_work"]:
                return task.cont
            inputs.tap("c")
        elif stage == 13:
            check(app.world.villagers[5].hunger < 40, "C eats from the storehouse")
            app.world.villagers[5].position = LOCATIONS["north_gate"]
            app.world.gates["north_gate"] = 100
            app.world.store["wood"] = 10
            state["wait_work"] = app.world.villagers[5].work_at
        elif stage == 14:
            if app.world.time < state["wait_work"]:
                return task.cont
            inputs.tap("j")
        elif stage == 15:
            check(app.world.gates["north_gate"] > 100, "J repairs a damaged gate")
            app.world.monsters.append(
                Monster("window_test_monster", "north_gate", (0, 26))
            )
            inputs.tap("k")
        elif stage == 16:
            monster = next(
                (m for m in app.world.monsters if m.id == "window_test_monster"), None
            )
            check(monster is None or monster.health < 40, "K attacks a nearby monster")
            inputs.tap("g")
        elif stage == 17:
            check(
                app.world.villagers[5].action.startswith("guarding "),
                "G assigns sustained gate defense",
            )
            app.world.villagers[5].energy = 30
            inputs.tap("r")
        elif stage == 18:
            if not state.get("rallied"):
                check(app.world.villagers[5].energy > 30, "R recovers player energy")
                app.world.villagers[5].position = (0, 0)
                app.world.villagers[1].position = (0, 1)
                app.world.villagers[1].energy = 20
                app.world.store["food"] = max(1, app.world.store["food"])
                inputs.tap("l")
                state["rallied"] = True
                state["after"] = now + 0.5
                return task.cont
            check(
                app.world.villagers[5].contributions["rallies"] > 0,
                "L activates elder rally",
            )
            state["orbit"] = app.orbit
            inputs.send("Left", True)
        elif stage == 19:
            inputs.send("Left", False)
            check(app.orbit > state["orbit"], "left arrow orbits camera")
            inputs.tap("Return")
        elif stage == 20:
            check(app.typing, "dialogue can be opened again")
            inputs.tap("Escape")
        elif stage == 21:
            check(not app.typing, "Escape cancels dialogue without quitting")
            inputs.tap("0")
        elif stage == 22:
            check(app.world.controlled is None, "key 0 releases control")
            inputs.tap("p")
        elif stage == 23:
            check(app.paused, "P pauses the simulation")
            state["paused_time"] = app.world.time
            inputs.tap("F5")
        elif stage == 24:
            check(
                app.world.time == state["paused_time"], "paused world does not advance"
            )
            inputs.tap("p")
        elif stage == 25:
            check(not app.paused, "P resumes simulation")
            if args.save_path and not state.get("save_checked"):
                from village.persistence import SaveStore

                restored = SaveStore(args.save_path).load()
                check(restored is not None, "F5 writes a readable save slot")
                check(
                    restored.time == state["paused_time"],
                    "F5 snapshot retains paused simulation time",
                )
                check(
                    restored.villagers[5].contributions["rallies"] > 0,
                    "saved role actions survive reload",
                )
                state["save_checked"] = True
            if args.live and not accepted_model_decisions:
                if now - started > 100:
                    raise AssertionError(f"No live model decision: {app.brains.status}")
                return task.cont
            if args.live:
                check(
                    app.brains.status.startswith("OLLAMA:"), "live model backend active"
                )
                check(bool(accepted_model_decisions), "live model decision applied")
            suffix = "live" if args.live else "demo"
            app.win.saveScreenshot(str(out / f"window-check-{suffix}.png"))
            report = {
                "passed": checks,
                "backend": app.brains.status,
                "model_decisions": accepted_model_decisions,
                "seconds": round(now - started, 2),
                "input_method": "targeted X11 keyboard events",
            }
            (out / f"window-check-{suffix}.json").write_text(
                json.dumps(report, indent=2)
            )
            print(json.dumps(report, indent=2), flush=True)
            app.taskMgr.stop()
            return task.done
        state["stage"] += 1
        state["after"] = now + 0.5
        return task.cont

    app.taskMgr.add(step, "window-input-integration")
    try:
        app.run()
    finally:
        app.save_world()
        inputs.close()
        app.destroy()


if __name__ == "__main__":
    main()
