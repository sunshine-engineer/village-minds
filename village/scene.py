"""Procedural geometry and configured scene construction; no game rules."""

from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    TextNode,
    TransparencyAttrib,
)
from .config import get_settings
from .map_data import BUILDINGS, LOCATIONS, GATES, GATE_MAX, CROP_GROW_SECONDS

D = get_settings()["display"]
R = get_settings()["rules"]
W = get_settings()["world"]


def cube_node():
    data = GeomVertexData("cube", GeomVertexFormat.getV3n3(), Geom.UHStatic)
    vertex, normal = GeomVertexWriter(data, "vertex"), GeomVertexWriter(data, "normal")
    faces = [
        ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]),
        ((0, 0, -1), [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)]),
        ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)]),
        ((0, 1, 0), [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)]),
        ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)]),
        ((-1, 0, 0), [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)]),
    ]
    triangles = GeomTriangles(Geom.UHStatic)
    for face, (n, points) in enumerate(faces):
        for p in points:
            vertex.addData3(*p)
            normal.addData3(*n)
        i = face * 4
        triangles.addVertices(i, i + 1, i + 2)
        triangles.addVertices(i, i + 2, i + 3)
    geom = Geom(data)
    geom.addPrimitive(triangles)
    node = GeomNode("cube")
    node.addGeom(geom)
    return node


class SceneBuilder:
    def setup_lights(self):
        ambient = AmbientLight("sky")
        ambient.setColor(tuple(D["ambient"]))
        self.render.setLight(self.render.attachNewNode(ambient))
        sun = DirectionalLight("sun")
        sun.setColor(tuple(D["sun"]))
        node = self.render.attachNewNode(sun)
        node.setHpr(*D["sun_hpr"])
        self.render.setLight(node)

    def box(self, parent, pos, scale, color):
        node = self.cube.copyTo(parent)
        node.setPos(*pos)
        node.setScale(*scale)
        node.setColor(*color, 1)
        return node

    def label(self, parent, text, pos, size=None, color=None):
        size = self.assets.catalog["style"]["label_size"] if size is None else size
        color = self.assets.catalog["style"]["label_color"] if color is None else color
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

    def prefab(self, parent, name, **options):
        return self.assets.instantiate(self, parent, name, **options)

    def build_village(self):
        style = self.assets.catalog["style"]
        for instance in self.assets.catalog["instances"]:
            node = self.render.attachNewNode(instance["prefab"])
            pos = (
                (*LOCATIONS[instance["location"]], 0)
                if "location" in instance
                else instance["position"]
            )
            node.setPos(*pos)
            self.prefab(node, instance["prefab"])
        for index, (x, y, hx, hy) in enumerate(BUILDINGS):
            root = self.render.attachNewNode("building")
            root.setPos(x, y, 0)
            parts = self.prefab(root, "building", bounds=(hx, hy))
            parts["roof"].setR(
                self.assets.catalog["building_roof_roll"] * (1 if index % 2 else -1)
            )
        self.crop_nodes = []
        for crop in self.world.crops:
            root = self.render.attachNewNode("crop")
            root.setPos(*crop.position, 0)
            parts = self.prefab(root, "crop")
            _, label = self.label(
                root, "", (0, 0, style["crop_label_height"]), style["crop_label_size"]
            )
            self.crop_nodes.append(
                ([n for name, n in parts.items() if name.startswith("stalk_")], label)
            )
        for name, (x, y) in LOCATIONS.items():
            self.label(
                self.render,
                name.upper(),
                (x, y, style["location_label_height"]),
                style["location_label_size"],
                style["location_label_color"],
            )
        wall = W["wall_coordinate"]
        for sign in (-1, 1):
            opening = W["gate_half_opening"] + style["wall_gate_margin"]
            center = (wall + opening) / 2
            for center in (-center, center):
                for name, pos in [
                    ("wall_horizontal", (center, sign * wall, 0)),
                    ("wall_vertical", (sign * wall, center, 0)),
                ]:
                    node = self.render.attachNewNode(name)
                    node.setPos(*pos)
                    parts = self.prefab(node, name)
                    if name == "wall_horizontal":
                        parts["wall"].setSx((wall - opening) / 2)
                    else:
                        parts["wall"].setSy((wall - opening) / 2)
        for x in (-wall, wall):
            for y in (-wall, wall):
                node = self.render.attachNewNode("tower")
                node.setPos(x, y, 0)
                self.prefab(node, "tower")
        self.gate_nodes = {}
        self.gate_labels = {}
        for name, (x, y) in GATES.items():
            scale = wall / max(abs(x), abs(y))
            bx, by = x * scale, y * scale
            node = self.render.attachNewNode(name)
            node.setPos(bx, by, 0)
            self.prefab(node, "gate_horizontal" if x == 0 else "gate_vertical")
            self.gate_nodes[name] = node
            _, self.gate_labels[name] = self.label(
                self.render,
                "",
                (bx, by, style["gate_label_height"]),
                style["gate_label_size"],
            )
        root = self.render.attachNewNode("core")
        root.setPos(*LOCATIONS["square"], 0)
        self.core = self.prefab(root, "core")["core"]
        self.label(
            root,
            style["core_label"],
            (0, 0, style["core_label_height"]),
            style["core_label_size"],
        )

    def build_actor(self, bot):
        style = self.assets.catalog["style"]
        root = self.render.attachNewNode(bot.name)
        parts = self.prefab(root, "villager", color=bot.color)
        parts["body"].setPythonTag("rest_height", parts["body"].getZ())
        role = self.assets.catalog["role_prefabs"].get(bot.role)
        if role:
            self.prefab(root, role, color=bot.color)
        legs = [node for name, node in parts.items() if name.startswith("leg_")]
        self.label(
            root, bot.name, (0, 0, style["actor_name_height"]), style["actor_name_size"]
        )
        speech_path, speech = self.label(
            root, "", (0, 0, style["speech_height"]), style["speech_size"]
        )
        speech.setWordwrap(style["speech_wordwrap"])
        speech.setCardColor(*style["speech_card_color"])
        speech.setCardAsMargin(*style["speech_margin"])
        speech_path.setTransparency(TransparencyAttrib.MAlpha)
        return root, parts["body"], legs, speech_path, speech

    def update_survival_visuals(self):
        style = self.assets.catalog["style"]
        for crop, (stalks, label) in zip(self.world.crops, self.crop_nodes):
            for stalk in stalks:
                if crop.stage == "empty":
                    stalk.hide()
                else:
                    stalk.show()
                    height = (
                        style["crop_min_height"]
                        + style["crop_growth_height"] * crop.age / CROP_GROW_SECONDS
                    )
                    stalk.setSz(height)
                    stalk.setZ(height)
                    stalk.setColor(
                        *(
                            style["ripe_color"]
                            if crop.stage == "ripe"
                            else style["growing_color"]
                        )
                    )
            label.setText(crop.stage.upper())
        for name, node in self.gate_nodes.items():
            hp = self.world.gates[name]
            self.gate_labels[name].setText(f"{name.replace('_',' ').upper()} {int(hp)}")
            if hp <= 0:
                node.hide()
            else:
                node.show()
                node.setColor(
                    *self.damage_color(
                        style["gate_broken_color"],
                        style["gate_full_color"],
                        hp / GATE_MAX,
                    )
                )
        self.core.setColor(
            *self.damage_color(
                style["core_broken_color"],
                style["core_full_color"],
                self.world.village_health / R["village_health"],
            )
        )
        living = {m.id for m in self.world.monsters}
        for identity in list(self.monster_nodes):
            if identity not in living:
                self.monster_nodes.pop(identity).removeNode()
        for monster in self.world.monsters:
            if monster.id not in self.monster_nodes:
                node = self.render.attachNewNode(monster.id)
                self.prefab(node, "monster")
                self.label(
                    node,
                    monster.id,
                    (0, 0, style["monster_label_height"]),
                    style["monster_label_size"],
                )
                self.monster_nodes[monster.id] = node
            self.monster_nodes[monster.id].setPos(*monster.position, 0)

    @staticmethod
    def damage_color(broken, healthy, ratio):
        return tuple(a + (b - a) * ratio for a, b in zip(broken, healthy))
