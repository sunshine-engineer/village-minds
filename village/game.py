"""Procedural Panda3D scene and controls. All scene mutations stay on this thread."""

import math
import sys
import time
from pathlib import Path
from panda3d.core import NodePath, loadPrcFileData
from direct.showbase.ShowBase import ShowBase
from .world import World
from .map_data import GATES, HEARING, LOCATIONS
from .navigation import distance
from .persistence import SaveStore, DEFAULT_SAVE_PATH
from .brains import BrainScheduler
from .scene import SceneBuilder, cube_node
from .assets import AssetCatalog
from .config import get_settings

D = get_settings()["display"]
C = get_settings()["controls"]
RT = get_settings()["runtime"]
R = get_settings()["rules"]


class VillageGame(SceneBuilder, ShowBase):
    def __init__(self, args):
        # WSLg supplies keyboard/mouse through the window, but may not expose
        # Linux's raw gamepad device directory. Avoid alarming evdev diagnostics
        # only in that known case; leave graphics and other errors visible.
        if sys.platform.startswith("linux"):
            # Request explicit repeat detection for X11 keyboard/text input.
            loadPrcFileData("x11-keyboard", "x-detectable-auto-repeat true")
        if sys.platform.startswith("linux") and not Path("/dev/input").is_dir():
            loadPrcFileData("missing-raw-input", "notify-level-device fatal")
            print(
                "Input: raw gamepad devices unavailable; using window keyboard/mouse.",
                flush=True,
            )
        loadPrcFileData(
            "display",
            f"window-title {D['title']}\nwin-size {D['window_size'][0]} {D['window_size'][1]}\nsync-video {str(D['sync_video']).lower()}\naudio-library-name {D['audio_library']}",
        )
        self.assets = AssetCatalog(get_settings()["assets"]["manifest"])
        if args.smoke_test:
            loadPrcFileData("", "window-type offscreen\nback-buffers 0")
        self.save_store = (
            None
            if args.smoke_test or getattr(args, "no_save", False)
            else SaveStore(getattr(args, "save_path", DEFAULT_SAVE_PATH))
        )
        self.world = (
            (
                self.save_store.new_attempt()
                if getattr(args, "new_game", False)
                else self.save_store.load()
            )
            if self.save_store
            else None
        ) or World()
        from .telemetry import DecisionLog
        from .timing import SimulationClock

        trace = getattr(
            args, "decision_log", get_settings()["telemetry"]["decision_log"]
        )
        if (
            trace
            and self.save_store
            and Path(trace).expanduser().resolve() == self.save_store.path
        ):
            raise ValueError("Decision log must differ from the campaign save path")
        self.world.decision_log = (
            DecisionLog(
                trace,
                max_bytes=get_settings()["telemetry"]["max_bytes"],
                full_observations=get_settings()["telemetry"]["full_observations"],
            )
            if trace
            else None
        )
        self.simulation_clock = SimulationClock(
            RT["max_step_seconds"], RT["max_steps_per_frame"]
        )
        self.save_status = (
            "Temporary session (no save)"
            if not self.save_store
            else f"Autosave every {RT['autosave_seconds']} seconds | {C['save']} save"
        )
        self.next_save_wall = time.monotonic() + RT["autosave_seconds"]
        self.failure_saved = self.world.failed
        self.paused = False
        self.pace = getattr(args, "pace", RT["pace"])
        if self.save_store:
            self.save_store.save(self.world)
            print(
                f"Save: {self.save_store.path} | attempt {self.world.campaign['attempt']}",
                flush=True,
            )
        super().__init__()
        self.disableMouse()
        self.camLens.setFov(D["fov"])
        self.camLens.setNearFar(D["near"], D["far"])
        self.setBackgroundColor(*D["background"])
        self.brains = BrainScheduler(
            self.world,
            args.url,
            args.model,
            args.demo or args.smoke_test,
            profile=getattr(args, "model_profile", None),
        )
        self.keys = set()
        self.typing = False
        self.orbit = 0
        self.zoom = D["zoom"]
        self.cube = NodePath(cube_node())
        self.setup_lights()
        self.build_village()
        self.actors = [self.build_actor(bot) for bot in self.world.villagers]
        self.monster_nodes = {}
        self.build_ui()
        from .controls import bind_controls

        bind_controls(self)
        self.taskMgr.add(self.update, "village-update")
        self.smoke_frames = 0 if args.smoke_test else None

    def build_ui(self):
        from .ui import build_ui

        build_ui(self)

    def takeover(self, index):
        if self.typing:
            return
        self.keys.clear()
        self.world.possess(index)

    def cycle(self):
        index = self.world.controlled
        self.takeover(0 if index is None else (index + 1) % len(self.world.villagers))

    def change_zoom(self, amount):
        self.zoom = max(D["zoom_min"], min(D["zoom_max"], self.zoom + amount))

    def player_action(self, action):
        if self.typing or self.paused or self.world.controlled is None:
            return
        bot = self.world.villagers[self.world.controlled]
        choices = self.world.available_actions(bot).get(action, [])
        target = choices[0] if choices else ""
        if action == "guard":
            target = min(GATES, key=lambda name: distance(bot.position, GATES[name]))
        elif action == "repair" and choices:
            target = min(choices, key=self.world.gates.get)
        elif action == "attack" and choices:
            target = min(
                (m for m in self.world.monsters if m.id in choices),
                key=lambda m: distance(bot.position, m.position),
            ).id
        if not self.world.apply(
            bot, {"action": action, "target": target}, source="player"
        ):
            self.world.log(
                f"Cannot {action} here: check distance, energy, cooldown, and shared supplies."
            )

    def open_chat(self):
        if self.typing or self.world.controlled is None:
            return
        self.typing = True
        self.keys.clear()
        self.entry.enterText("")
        self.entry.show()
        # DirectGUI may still be processing the Enter that opened the field.
        # Focus it after that event batch so it cannot submit itself immediately.
        self.entry["focus"] = 0
        self.taskMgr.doMethodLater(
            D["focus_delay_seconds"], self.focus_chat, "focus-chat"
        )

    def focus_chat(self, task):
        if self.typing and not self.entry.isHidden():
            self.entry["focus"] = 1
        return task.done

    def submit_chat(self, text):
        if not self.typing:
            return
        if self.world.controlled is not None:
            bot = self.world.villagers[self.world.controlled]
            self.world.say(bot, text, source="player")
        self.close_chat()

    def close_chat(self):
        self.taskMgr.remove("focus-chat")
        self.entry["focus"] = 0
        self.entry.hide()
        self.keys.clear()
        # Defer so the Enter event that submitted cannot reopen the field.
        self.taskMgr.doMethodLater(
            D["chat_close_delay_seconds"], self.finish_chat, "finish-chat"
        )

    def finish_chat(self, task):
        self.typing = False
        return task.done

    def escape(self):
        if self.typing:
            self.close_chat()
        else:
            self.userExit()

    def update(self, task):
        dt = min(self.clock_dt(), RT["max_step_seconds"])
        if not self.typing and not self.paused:
            self.orbit += (
                (int(C["orbit_left"] in self.keys) - int(C["orbit_right"] in self.keys))
                * dt
                * D["orbit_speed"]
            )
            # Camera-relative movement on the ground plane.
            right = int(C["right"] in self.keys) - int(C["left"] in self.keys)
            forward = int(C["forward"] in self.keys) - int(C["backward"] in self.keys)
            dx = right * math.cos(self.orbit) - forward * math.sin(self.orbit)
            dy = right * math.sin(self.orbit) + forward * math.cos(self.orbit)
            self.world.move_player(dx, dy, dt)
        if not self.paused:
            self.simulation_clock.advance(self.world, self.brains, dt * self.pace)
        if time.monotonic() >= self.next_save_wall or (
            self.world.failed and not self.failure_saved
        ):
            self.save_world()
            self.next_save_wall = time.monotonic() + RT["autosave_seconds"]
            self.failure_saved = self.world.failed
        self.update_survival_visuals()
        speaker = max(
            range(len(self.world.villagers)),
            key=lambda i: (self.world.villagers[i].speech_until, i),
        )
        if self.world.controlled is not None:
            controlled = self.world.villagers[self.world.controlled]
            if controlled.speech_until > self.world.time:
                speaker = self.world.controlled
        for index, (bot, (root, body, legs, speech_path, speech)) in enumerate(
            zip(self.world.villagers, self.actors)
        ):
            if not bot.alive:
                root.hide()
                continue
            root.show()
            previous = root.getPos()
            x, y = bot.position
            root.setPos(x, y, 0)
            walking = math.hypot(x - previous.x, y - previous.y) > 0.001
            if walking:
                root.setH(math.degrees(math.atan2(-(x - previous.x), y - previous.y)))
            for i, leg in enumerate(legs):
                leg.setP(
                    math.sin(self.world.time * D["animation_speed"] + i * math.pi)
                    * D["leg_swing_degrees"]
                    if walking
                    else 0
                )
            body_height = body.getPythonTag("rest_height")
            body.setZ(
                body_height
                + (
                    abs(math.sin(self.world.time * D["animation_speed"]))
                    * D["body_bob"]
                    if walking
                    else 0
                )
            )
            speech.setText(bot.speech if self.world.time < bot.speech_until else "")
            if index == speaker and self.world.time < bot.speech_until:
                speech_path.show()
            else:
                speech_path.hide()
        target = (
            LOCATIONS["square"]
            if self.world.controlled is None
            else self.world.villagers[self.world.controlled].position
        )
        self.camera.setPos(
            target[0] + math.sin(self.orbit) * self.zoom,
            target[1] - math.cos(self.orbit) * self.zoom,
            self.zoom * D["camera_height_ratio"],
        )
        self.camera.lookAt(target[0], target[1], 0)
        rows = []
        for i, bot in enumerate(self.world.villagers):
            marker = ">" if i == self.world.controlled else " "
            rows.append(
                f"{marker} {C['takeover_keys'][i]} {bot.name} / {bot.role}\n     HP {int(bot.health)}  Energy {int(bot.energy)}  Hunger {int(bot.hunger)}\n     Food {bot.supplies} Wood {bot.wood} | {bot.action[:D['roster_action_chars']]}\n"
            )
        self.roster.setText("\n".join(rows))
        self.feed.setText("\n".join(list(self.world.events)[-D["feed_lines"] :]))
        self.status.setText(
            self.brains.status
            + f"\nSpeed {self.pace:g}x | Local actions {self.brains.local_decisions} | AI decisions {self.brains.model_decisions}"
            + f"\nVillage {int(self.world.village_health)}/{R['village_health']:g} | Attempt {self.world.campaign['attempt']} | Wave {self.world.wave}"
            + f"\nShared food {self.world.store['food']} | Wood {self.world.store['wood']} | Next wave {max(0,int(self.world.next_wave-self.world.time))}s"
            + "\n"
            + self.save_status
        )
        if self.world.failed:
            self.hint.setText(
                "VILLAGE DESTROYED | --new-game starts a new attempt with lessons retained"
            )
        elif self.paused:
            self.hint.setText(f"PAUSED | {C['pause']} resumes | {C['save']} saves")
        elif self.world.controlled is None:
            self.hint.setText(
                f"OBSERVER MODE | Pick a villager: {'/'.join(C['takeover_keys'][:len(self.world.villagers)])}"
            )
        else:
            bot = self.world.villagers[self.world.controlled]
            nearby = [
                v.name
                for v in self.world.villagers
                if v is not bot
                and v.alive
                and distance(v.position, bot.position) <= HEARING
            ]
            self.hint.setText(
                f"PLAYING AS {bot.name.upper()}  |  Within earshot: {', '.join(nearby) or 'nobody'}"
            )
        if self.smoke_frames is not None:
            self.smoke_frames += 1
            if self.smoke_frames == 3:
                self.takeover(min(1, len(self.world.villagers) - 1))
                self.world.move_player(1, 0, 0.1)
                self.world.say(
                    self.world.villagers[min(1, len(self.world.villagers) - 1)],
                    "Hello, Willowbrook!",
                )
            if self.smoke_frames == 8:
                self.takeover(None)
            if self.smoke_frames >= 15:
                Path("artifacts").mkdir(exist_ok=True)
                self.win.saveScreenshot("artifacts/village-smoke.png")
                self.userExit()
        return task.cont

    def cycle_speed(self):
        if self.typing:
            return
        speeds = RT["speed_steps"]
        index = next((i for i, v in enumerate(speeds) if abs(v - self.pace) < 1e-9), -1)
        self.pace = speeds[(index + 1) % len(speeds)]

    def close_decision_log(self):
        if self.world.decision_log and not self.world.decision_log.handle.closed:
            self.world.decision_log.record(
                "session_end",
                self.world.time,
                pending_model_request=self.brains.busy,
                dropped_records=self.world.decision_log.dropped,
            )
            self.world.decision_log.close()

    def toggle_pause(self):
        if not self.typing:
            self.paused = not self.paused
            self.keys.clear()

    def save_world(self):
        if not self.save_store:
            return True
        try:
            self.save_store.save(self.world)
            self.next_save_wall = time.monotonic() + RT["autosave_seconds"]
            self.save_status = (
                "Saved | " + self.save_store.path.name + f" | {C['save']} save"
            )
            return True
        except (OSError, ValueError) as exc:
            self.save_status = "SAVE FAILED: " + str(exc)[:85]
            print(self.save_status, flush=True)
            return False

    @staticmethod
    def clock_dt():
        from panda3d.core import ClockObject

        return ClockObject.getGlobalClock().getDt()
