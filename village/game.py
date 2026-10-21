"""Procedural Panda3D scene and controls. All scene mutations stay on this thread."""
import math
import sys
import time
from pathlib import Path
from panda3d.core import (
    AmbientLight, DirectionalLight, Geom, GeomNode, GeomTriangles,
    GeomVertexData, GeomVertexFormat, GeomVertexWriter, TextNode, NodePath,
    TransparencyAttrib, loadPrcFileData,
)
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.gui.DirectGui import DirectEntry, DirectFrame
from .simulation import World, BUILDINGS, LOCATIONS, HEARING, GATES, GATE_MAX, CROP_GROW_SECONDS, distance
from .persistence import SaveStore, DEFAULT_SAVE_PATH
from .brains import BrainScheduler


def cube_node():
    data = GeomVertexData("cube", GeomVertexFormat.getV3n3(), Geom.UHStatic)
    vertex, normal = GeomVertexWriter(data, "vertex"), GeomVertexWriter(data, "normal")
    faces = [((0, 0, 1), [(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]),
             ((0,0,-1), [(-1,1,-1),(1,1,-1),(1,-1,-1),(-1,-1,-1)]),
             ((0,-1,0), [(-1,-1,-1),(1,-1,-1),(1,-1,1),(-1,-1,1)]),
             ((0,1,0), [(1,1,-1),(-1,1,-1),(-1,1,1),(1,1,1)]),
             ((1,0,0), [(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)]),
             ((-1,0,0), [(-1,1,-1),(-1,-1,-1),(-1,-1,1),(-1,1,1)])]
    triangles = GeomTriangles(Geom.UHStatic)
    for face, (n, points) in enumerate(faces):
        for p in points:
            vertex.addData3(*p)
            normal.addData3(*n)
        i = face * 4
        triangles.addVertices(i, i+1, i+2)
        triangles.addVertices(i, i+2, i+3)
    geom = Geom(data)
    geom.addPrimitive(triangles)
    node = GeomNode("cube")
    node.addGeom(geom)
    return node


class VillageGame(ShowBase):
    def __init__(self, args):
        # WSLg supplies keyboard/mouse through the window, but may not expose
        # Linux's raw gamepad device directory. Avoid alarming evdev diagnostics
        # only in that known case; leave graphics and other errors visible.
        if sys.platform.startswith("linux"):
            # Request explicit repeat detection for X11 keyboard/text input.
            loadPrcFileData("x11-keyboard", "x-detectable-auto-repeat true")
        if sys.platform.startswith("linux") and not Path("/dev/input").is_dir():
            loadPrcFileData("missing-raw-input", "notify-level-device fatal")
            print("Input: raw gamepad devices unavailable; using window keyboard/mouse.", flush=True)
        loadPrcFileData("", "window-title Village Minds | Willowbrook\nwin-size 1440 900\nsync-video true\naudio-library-name null")
        if args.smoke_test:
            loadPrcFileData("", "window-type offscreen\nback-buffers 0")
        self.save_store = None if args.smoke_test or getattr(args, "no_save", False) else SaveStore(getattr(args,"save_path",DEFAULT_SAVE_PATH))
        self.world = ((self.save_store.new_attempt() if getattr(args,"new_game",False) else self.save_store.load())
                      if self.save_store else None) or World()
        self.save_status = "Temporary session (no save)" if not self.save_store else "Autosave every 10 seconds | F5 save"
        self.next_save_wall = time.monotonic()+10
        self.failure_saved = self.world.failed
        self.paused = False
        self.pace = getattr(args,"pace",.5)
        if self.save_store:
            self.save_store.save(self.world)
            print(f"Save: {self.save_store.path} | attempt {self.world.campaign['attempt']}",flush=True)
        super().__init__()
        self.disableMouse()
        self.camLens.setFov(58)
        self.camLens.setNearFar(.1, 250)
        self.setBackgroundColor(.53, .72, .82)
        self.brains = BrainScheduler(self.world, args.url, args.model, args.demo or args.smoke_test)
        self.keys = set()
        self.typing = False
        self.orbit = 0
        self.zoom = 42
        self.cube = NodePath(cube_node())
        self.setup_lights()
        self.build_village()
        self.actors = [self.build_actor(bot) for bot in self.world.villagers]
        self.monster_nodes = {}
        self.build_ui()
        for key in ("w", "a", "s", "d", "arrow_left", "arrow_right"):
            self.accept(key, self.keys.add, [key])
            self.accept(key + "-up", self.keys.discard, [key])
        for i in range(6):
            self.accept(str(i+1), self.takeover, [i])
        self.accept("tab", self.cycle)
        self.accept("0", self.takeover, [None])
        self.accept("enter", self.open_chat)
        self.accept("escape", self.escape)
        self.accept("e", self.player_action, ["gather"])
        self.accept("r", self.player_action, ["rest"])
        for key,action in (("f","farm"),("h","harvest"),("t","deposit"),("c","eat"),
                           ("g","guard"),("j","repair"),("k","attack"),("l","rally")):
            self.accept(key,self.player_action,[action])
        self.accept("f5",self.save_world)
        self.accept("p",self.toggle_pause)
        self.accept("wheel_up", self.change_zoom, [-3])
        self.accept("wheel_down", self.change_zoom, [3])
        self.taskMgr.add(self.update, "village-update")
        self.smoke_frames = 0 if args.smoke_test else None

    def setup_lights(self):
        ambient = AmbientLight("sky")
        ambient.setColor((.56, .6, .64, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        sun = DirectionalLight("sun")
        sun.setColor((1, .91, .74, 1))
        node = self.render.attachNewNode(sun)
        node.setHpr(-35, -55, 0)
        self.render.setLight(node)

    def box(self, parent, pos, scale, color):
        node = self.cube.copyTo(parent)
        node.setPos(*pos)
        node.setScale(*scale)
        node.setColor(*color, 1)
        return node

    def label(self, parent, text, pos, size=.65, color=(1,1,1,1)):
        node = TextNode("label")
        node.setText(text)
        node.setAlign(TextNode.ACenter)
        node.setTextColor(*color)
        path = parent.attachNewNode(node)
        path.setPos(*pos)
        path.setScale(size)
        path.setBillboardPointEye()
        path.setLightOff()
        return path, node

    def build_village(self):
        self.box(self.render, (0,0,-.4), (33,33,.4), (.3,.48,.27))
        self.box(self.render, (0,0,.015), (3,24,.02), (.69,.61,.43))
        self.box(self.render, (0,-4,.02), (24,2,.025), (.69,.61,.43))
        self.box(self.render, (0,0,.03), (6,6,.03), (.73,.67,.51))
        for i, (x,y,hx,hy) in enumerate(BUILDINGS):
            self.box(self.render, (x,y,2), (hx,hy,2), (.79,.68,.49))
            roof = self.box(self.render, (x,y,4.15), (hx+.5,hy+.4,.45), (.46,.23,.19))
            roof.setR(8 if i % 2 else -8)
            self.box(self.render, (x,y-hy-.03,1), (.55,.05,1), (.27,.19,.13))
            for offset in (-1.5, 1.5):
                self.box(self.render, (x+offset,y-hy-.04,2.3), (.4,.06,.45), (.45,.72,.8))
        self.crop_nodes = []
        for crop in self.world.crops:
            x,y = crop.position
            self.box(self.render, (x,y,.08), (1.5,1.5,.08), (.32,.24,.13))
            stalks = [self.box(self.render,(x+dx,y+dy,.4),(.3,.3,.4),(.74,.72,.24))
                      for dx,dy in [(-.6,-.6),(.6,-.6),(0,.6)]]
            _,label = self.label(self.render,"",(x,y,1.8),.32)
            self.crop_nodes.append((stalks,label))
        for x,y in [(12,12),(16,12),(18,9),(14,16),(-21,17),(-20,-19),(21,-19),(-18,21)]:
            self.box(self.render, (x,y,1.3), (.3,.3,1.3), (.37,.24,.14))
            crown = self.box(self.render, (x,y,3), (1.5,1.5,1.3), (.21,.4,.24))
            crown.setH(35)
            if x > 0 and y > 0:
                self.box(self.render, (x-.7,y-.9,3), (.22,.22,.22), (.86,.31,.22))
        self.box(self.render, (8,-5,.6), (1.1,1.1,.6), (.45,.5,.5))
        self.box(self.render, (8,-5,1.22), (.8,.8,.03), (.23,.55,.67))
        self.box(self.render, (0,17,.5), (2,.6,.22), (.43,.29,.16))
        for name,(x,y) in LOCATIONS.items():
            self.label(self.render, name.upper(), (x,y,1.8), .5, (.98,.95,.8,1))
        # Solid wall runs leave openings at the four gate positions.
        for sign in (-1,1):
            for center in (-13.5,13.5):
                self.box(self.render,(center,sign*24,1.1),(10.5,.35,1.1),(.45,.43,.37))
                self.box(self.render,(sign*24,center,1.1),(.35,10.5,1.1),(.45,.43,.37))
        for x in (-24,24):
            for y in (-24,24):
                self.box(self.render,(x,y,1.8),(.9,.9,1.8),(.37,.38,.34))
        self.gate_nodes = {}
        self.gate_labels = {}
        for name,(x,y) in GATES.items():
            bx,by = x*24/21,y*24/21
            scale = (2.5,.3,1.2) if x == 0 else (.3,2.5,1.2)
            self.gate_nodes[name] = self.box(self.render,(bx,by,1.2),scale,(.35,.5,.3))
            _,self.gate_labels[name] = self.label(self.render,"",(bx,by,3),.4)
        self.core = self.box(self.render,(0,0,.35),(1,1,.35),(.7,.65,.4))
        self.label(self.render,"VILLAGE HEART",(0,0,2),.35)


    def build_actor(self, bot):
        root = self.render.attachNewNode(bot.name)
        body = self.box(root, (0,0,1), (.35,.25,.5), bot.color)
        self.box(root, (0,0,1.8), (.28,.27,.3), (.88,.69,.51))
        self.box(root, (0,.28,1.85), (.1,.06,.05), (.18,.16,.14))
        if bot.role == "soldier":
            self.box(root,(0,0,2.1),(.34,.32,.12),(.46,.5,.54))
            self.box(root,(.5,0,1.2),(.055,.055,.6),(.8,.83,.85))
        elif bot.role == "farmer":
            self.box(root,(0,0,2.15),(.43,.4,.08),(.81,.67,.36))
        elif bot.role == "elder":
            self.box(root,(.5,0,1),(.06,.06,.95),(.42,.28,.18))
        elif bot.role == "worker":
            self.box(root,(0,-.35,1.2),(.32,.18,.35),(.4,.26,.16))
        legs = [self.box(root, (x,0,.35), (.12,.17,.35), (.22,.26,.29)) for x in (-.18,.18)]
        self.label(root, bot.name, (0,0,2.65), .5)
        speech_path, speech = self.label(root, "", (0,0,3.7), .35)
        speech.setWordwrap(22)
        speech.setCardColor(.08,.12,.15,.9)
        speech.setCardAsMargin(.5,.5,.3,.3)
        speech_path.setTransparency(TransparencyAttrib.MAlpha)
        return root, body, legs, speech_path, speech

    def build_ui(self):
        DirectFrame(parent=self.a2dTopLeft, frameColor=(.035,.065,.08,.92), frameSize=(0,.84,-1.46,0))
        self.title = OnscreenText(parent=self.a2dTopLeft, text="VILLAGE MINDS", pos=(.04,-.07),
            scale=.054, fg=(.95,.81,.48,1), align=TextNode.ALeft)
        self.subtitle = OnscreenText(parent=self.a2dTopLeft, text="W I L L O W B R O O K", pos=(.04,-.12),
            scale=.026, fg=(.7,.8,.79,1), align=TextNode.ALeft)
        self.roster = OnscreenText(parent=self.a2dTopLeft, text="", pos=(.04,-.2),
            scale=.025, fg=(.9,.94,.91,1), align=TextNode.ALeft, mayChange=True)
        self.controls = OnscreenText(parent=self.a2dTopLeft,
            text="1-6 / Tab  Take over   |   0 Observe\nWASD Walk | Arrows Orbit | Wheel Zoom\nF Plant | H Harvest | E Gather wood\nT Deposit | C Eat | R Rest\nG Guard gate | J Repair | K Attack\nL Elder rally | Enter Speak\nP Pause | F5 Save | Esc Quit/cancel",
            pos=(.04,-1.16), scale=.026, fg=(.64,.75,.75,1), align=TextNode.ALeft)
        self.status = OnscreenText(parent=self.a2dTopRight, text="", pos=(-.04,-.06),
            scale=.029, fg=(1,.9,.65,1), align=TextNode.ARight, mayChange=True)
        DirectFrame(parent=self.a2dBottomLeft, frameColor=(.035,.065,.08,.88), frameSize=(0,1.95,0,.42))
        self.feed = OnscreenText(parent=self.a2dBottomLeft, text="", pos=(.04,.35), scale=.028,
            fg=(.85,.91,.88,1), align=TextNode.ALeft, mayChange=True, wordwrap=100)
        self.entry = DirectEntry(parent=self.a2dBottomLeft, pos=(.04,0,.46), scale=.042,
            width=39, numLines=1, command=self.submit_chat, initialText="", focus=0)
        self.entry.hide()
        self.hint = OnscreenText(text="OBSERVER MODE  |  Pick a villager with 1-6", pos=(0,.88),
            scale=.038, fg=(1,.98,.86,1), mayChange=True)

    def takeover(self, index):
        if self.typing:
            return
        self.keys.clear()
        self.world.possess(index)

    def cycle(self):
        index = self.world.controlled
        self.takeover(0 if index is None else (index+1) % len(self.world.villagers))

    def change_zoom(self, amount):
        self.zoom = max(12, min(65,self.zoom+amount))

    def player_action(self, action):
        if self.typing or self.paused or self.world.controlled is None:
            return
        bot = self.world.villagers[self.world.controlled]
        choices = self.world.available_actions(bot).get(action,[])
        target = ""
        if action == "guard":
            target = min(GATES,key=lambda name:distance(bot.position,GATES[name]))
        elif action == "repair" and choices:
            target = min(choices,key=self.world.gates.get)
        elif action == "attack" and choices:
            target = min((m for m in self.world.monsters if m.id in choices),
                         key=lambda m:distance(bot.position,m.position)).id
        if not self.world.apply(bot, {"action":action,"target":target}):
            self.world.log(f"Cannot {action} here: check distance, energy, cooldown, and shared supplies.")

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
        self.taskMgr.doMethodLater(.08, self.focus_chat, "focus-chat")

    def focus_chat(self, task):
        if self.typing and not self.entry.isHidden():
            self.entry["focus"] = 1
        return task.done

    def submit_chat(self, text):
        if not self.typing:
            return
        if self.world.controlled is not None:
            bot = self.world.villagers[self.world.controlled]
            self.world.say(bot, text)
        self.close_chat()

    def close_chat(self):
        self.taskMgr.remove("focus-chat")
        self.entry["focus"] = 0
        self.entry.hide()
        self.keys.clear()
        # Defer so the Enter event that submitted cannot reopen the field.
        self.taskMgr.doMethodLater(.15, self.finish_chat, "finish-chat")

    def finish_chat(self, task):
        self.typing = False
        return task.done

    def escape(self):
        if self.typing:
            self.close_chat()
        else:
            self.userExit()

    def update(self, task):
        dt = min(self.clock_dt(), .1)
        if not self.typing and not self.paused:
            self.orbit += (int("arrow_left" in self.keys)-int("arrow_right" in self.keys)) * dt
            # Camera-relative movement on the ground plane.
            right = int("d" in self.keys)-int("a" in self.keys)
            forward = int("w" in self.keys)-int("s" in self.keys)
            dx = right * math.cos(self.orbit) - forward * math.sin(self.orbit)
            dy = right * math.sin(self.orbit) + forward * math.cos(self.orbit)
            self.world.move_player(dx, dy, dt)
        if not self.paused:
            self.world.tick(dt*self.pace)
            self.brains.tick()
        if time.monotonic() >= self.next_save_wall or (self.world.failed and not self.failure_saved):
            self.save_world()
            self.next_save_wall = time.monotonic()+10
            self.failure_saved = self.world.failed
        self.update_survival_visuals()
        speaker = max(range(len(self.world.villagers)),
            key=lambda i: (self.world.villagers[i].speech_until, i))
        if self.world.controlled is not None:
            controlled = self.world.villagers[self.world.controlled]
            if controlled.speech_until > self.world.time:
                speaker = self.world.controlled
        for index,(bot,(root,body,legs,speech_path,speech)) in enumerate(zip(self.world.villagers,self.actors)):
            if not bot.alive:
                root.hide()
                continue
            root.show()
            previous = root.getPos()
            x,y = bot.position
            root.setPos(x,y,0)
            walking = math.hypot(x-previous.x,y-previous.y) > .001
            if walking:
                root.setH(math.degrees(math.atan2(-(x-previous.x),y-previous.y)))
            for i,leg in enumerate(legs):
                leg.setP(math.sin(self.world.time*10+i*math.pi)*22 if walking else 0)
            body.setZ(1 + (abs(math.sin(self.world.time*10))*.045 if walking else 0))
            speech.setText(bot.speech if self.world.time < bot.speech_until else "")
            if index == speaker and self.world.time < bot.speech_until:
                speech_path.show()
            else:
                speech_path.hide()
        target = (0,0) if self.world.controlled is None else self.world.villagers[self.world.controlled].position
        self.camera.setPos(target[0]+math.sin(self.orbit)*self.zoom,
            target[1]-math.cos(self.orbit)*self.zoom, self.zoom*.95)
        self.camera.lookAt(target[0],target[1],0)
        rows = []
        for i,bot in enumerate(self.world.villagers):
            marker = ">" if i == self.world.controlled else " "
            rows.append(f"{marker} {i+1} {bot.name} / {bot.role}\n     HP {int(bot.health)}  Energy {int(bot.energy)}  Hunger {int(bot.hunger)}\n     Food {bot.supplies} Wood {bot.wood} | {bot.action[:18]}\n")
        self.roster.setText("\n".join(rows))
        self.feed.setText("\n".join(list(self.world.events)[-6:]))
        self.status.setText(self.brains.status +
            f"\nLocal actions {self.brains.local_decisions} | AI decisions {self.brains.model_decisions}"+
            f"\nVillage {int(self.world.village_health)}/200 | Attempt {self.world.campaign['attempt']} | Wave {self.world.wave}"+
            f"\nShared food {self.world.store['food']} | Wood {self.world.store['wood']} | Next wave {max(0,int(self.world.next_wave-self.world.time))}s"+
            "\n"+self.save_status)
        if self.world.failed:
            self.hint.setText("VILLAGE DESTROYED | --new-game starts a new attempt with lessons retained")
        elif self.paused:
            self.hint.setText("PAUSED | P resumes | F5 saves")
        elif self.world.controlled is None:
            self.hint.setText("OBSERVER MODE  |  Pick a villager with 1-6")
        else:
            bot = self.world.villagers[self.world.controlled]
            nearby = [v.name for v in self.world.villagers if v is not bot and v.alive and distance(v.position,bot.position)<=HEARING]
            self.hint.setText(f"PLAYING AS {bot.name.upper()}  |  Within earshot: {', '.join(nearby) or 'nobody'}")
        if self.smoke_frames is not None:
            self.smoke_frames += 1
            if self.smoke_frames == 3:
                self.takeover(1)
                self.world.move_player(1,0,.1)
                self.world.say(self.world.villagers[1], "Hello, Willowbrook!")
            if self.smoke_frames == 8:
                self.takeover(None)
            if self.smoke_frames >= 15:
                Path("artifacts").mkdir(exist_ok=True)
                self.win.saveScreenshot("artifacts/village-smoke.png")
                self.userExit()
        return task.cont

    def toggle_pause(self):
        if not self.typing:
            self.paused = not self.paused
            self.keys.clear()

    def save_world(self):
        if not self.save_store:
            return True
        try:
            self.save_store.save(self.world)
            self.next_save_wall = time.monotonic()+10
            self.save_status = "Saved | " + self.save_store.path.name + " | F5 save"
            return True
        except (OSError, ValueError) as exc:
            self.save_status = "SAVE FAILED: " + str(exc)[:85]
            print(self.save_status,flush=True)
            return False

    def update_survival_visuals(self):
        for crop,(stalks,label) in zip(self.world.crops,self.crop_nodes):
            for stalk in stalks:
                if crop.stage == "empty":
                    stalk.hide()
                else:
                    stalk.show()
                    height = .2 + .7*crop.age/CROP_GROW_SECONDS
                    stalk.setSz(height)
                    stalk.setZ(height)
                    stalk.setColor(*((.86,.77,.23,1) if crop.stage == "ripe" else (.25,.65,.28,1)))
            label.setText(crop.stage.upper())
        for name,node in self.gate_nodes.items():
            hp = self.world.gates[name]
            self.gate_labels[name].setText(f"{name.replace('_',' ').upper()} {int(hp)}")
            if hp <= 0:
                node.hide()
            else:
                node.show()
                node.setColor(1-hp/GATE_MAX,.25+hp/GATE_MAX*.4,.18,1)
        self.core.setColor(1-self.world.village_health/200,.4,.2,1)
        living = {m.id for m in self.world.monsters}
        for identity in list(self.monster_nodes):
            if identity not in living:
                self.monster_nodes.pop(identity).removeNode()
        for monster in self.world.monsters:
            if monster.id not in self.monster_nodes:
                node = self.render.attachNewNode(monster.id)
                self.box(node,(0,0,.7),(.5,.4,.7),(.5,.16,.18))
                self.box(node,(0,0,1.6),(.4,.35,.4),(.65,.23,.2))
                for x in (-.3,.3):
                    self.box(node,(x,0,2.15),(.1,.1,.25),(.82,.77,.57))
                self.label(node,monster.id,(0,0,2.7),.3)
                self.monster_nodes[monster.id] = node
            self.monster_nodes[monster.id].setPos(*monster.position,0)

    @staticmethod
    def clock_dt():
        from panda3d.core import ClockObject
        return ClockObject.getGlobalClock().getDt()
