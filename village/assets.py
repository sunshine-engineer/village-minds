"""Data-defined visual prefabs and optional Panda3D model files.

File: village/assets.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from pathlib import Path

from .config import DATA, _validate_types, _vector, get_settings, read_json


class AssetCatalog:
    """Validated visual prefab catalog with manifest-relative model paths."""

    def __init__(self, path):
        """Initialize AssetCatalog and its owned state.

        Args:
            path: Input/output filesystem path for the described resource.

        Returns:
            None.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
        self.path = Path(path)
        self.catalog = read_json(self.path)
        if not isinstance(self.catalog, dict) or not isinstance(
            self.catalog.get("prefabs"), dict
        ):
            raise ValueError("Asset manifest requires a prefabs object")
        required = {
            "ground",
            "building",
            "crop",
            "wall_horizontal",
            "wall_vertical",
            "tower",
            "gate_horizontal",
            "gate_vertical",
            "core",
            "villager",
            "monster",
        }
        if not required <= self.catalog["prefabs"].keys():
            raise ValueError("Asset manifest is missing required prefabs")
        for name, prefab in self.catalog["prefabs"].items():
            if not isinstance(prefab, dict):
                raise ValueError(f"Prefab {name} must be an object")
            parts = prefab.get("parts", [])
            if not isinstance(parts, list) or not parts:
                raise ValueError(f"Prefab {name} requires named parts")
            names = []
            for part in parts:
                if (
                    not isinstance(part, dict)
                    or not {"name", "position", "scale", "color"} <= part.keys()
                ):
                    raise ValueError(f"Invalid part fields in {name}")
                if not isinstance(part["name"], str) or not part["name"]:
                    raise ValueError("Parts require nonempty names")
                names.append(part["name"])
                for field in ("position", "scale"):
                    _vector(part[field], 3, f"{name}.{field}")
                if min(part["scale"]) <= 0:
                    raise ValueError("Asset scales must be positive")
                if part["color"] != "villager":
                    _vector(part["color"], 3, f"{name}.color", 0, 1)
                if "hpr" in part:
                    _vector(part["hpr"], 3, f"{name}.hpr")
                if "model" in part and not (self.path.parent / part["model"]).is_file():
                    raise ValueError(f"Missing model: {part['model']}")
            if len(set(names)) != len(names):
                raise ValueError(f"Duplicate part names: {name}")
        required_parts = {
            "villager": {"body"},
            "building": {"roof"},
            "core": {"core"},
            "wall_horizontal": {"wall"},
            "wall_vertical": {"wall"},
        }
        for name, parts in required_parts.items():
            if not parts <= {p["name"] for p in self.catalog["prefabs"][name]["parts"]}:
                raise ValueError(f"Missing animated/structural parts in {name}")
        reference = read_json(DATA / "assets/catalog.json")
        if (
            not isinstance(self.catalog.get("style"), dict)
            or not reference["style"].keys() <= self.catalog["style"].keys()
        ):
            raise ValueError("Asset catalog is missing style fields")
        _validate_types(self.catalog["style"], reference["style"], "style")
        for name, value in self.catalog["style"].items():
            if isinstance(value, list) and "color" in name:
                _vector(value, len(reference["style"].get(name, value)), name, 0, 1)
        ui = self.catalog.get("ui")
        if not isinstance(ui, list) or not {
            "title",
            "subtitle",
            "roster",
            "controls",
            "status",
            "feed",
            "entry",
            "hint",
        } <= {v.get("name") for v in ui if isinstance(v, dict)}:
            raise ValueError("Asset catalog is missing required UI widgets")
        for widget in ui:
            if not isinstance(widget, dict) or not isinstance(
                widget.get("options"), dict
            ):
                raise ValueError("UI widgets require an options object")
            if "parent" in widget and widget["parent"] not in {
                "aspect2d",
                "a2dTopLeft",
                "a2dTopRight",
                "a2dBottomLeft",
                "a2dBottomRight",
                "a2dTopCenter",
                "a2dBottomCenter",
            }:
                raise ValueError("Unknown UI parent")
            if widget.get("kind") not in ("OnscreenText", "DirectEntry", "DirectFrame"):
                raise ValueError("Unknown UI widget kind")
            if "command" in widget and widget["command"] != "submit_chat":
                raise ValueError("Unsupported UI command")
        for instance in self.catalog.get("instances", []):
            if not isinstance(instance, dict) or "prefab" not in instance:
                raise ValueError("Asset instances require a prefab")
            if "location" in instance:
                if instance["location"] not in get_settings()["world"]["locations"]:
                    raise ValueError("Unknown instance map location")
            else:
                _vector(instance.get("position"), 3, "asset instance position")
            if instance["prefab"] not in self.catalog["prefabs"]:
                raise ValueError(f"Unknown prefab: {instance['prefab']}")
        for prefab in self.catalog["role_prefabs"].values():
            if prefab not in self.catalog["prefabs"]:
                raise ValueError(f"Unknown role prefab: {prefab}")

    def instantiate(self, game, parent, name, *, color=None, bounds=None):
        """Instantiate a validated prefab and return its named visual parts.

        Args:
            game: Game instance owning scene/UI references.
            parent: Parent scene node, or parent IPC endpoint in worker helpers.
            name: Registered identity or name selected by the caller.
            color: Optional RGB tint for this visual.
            bounds: Optional dimensions used when instantiating geometry.

        Returns:
            Mapping from configured part names to Panda3D node paths.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
        result = {}
        for part in self.catalog["prefabs"][name]["parts"]:
            pos = list(part["position"])
            scale = list(part["scale"])
            if bounds:
                hx, hy = bounds
                if part.get("size_mode") == "building":
                    scale[:2] = [hx, hy]
                if part.get("size_mode") == "roof":
                    scale[:2] = [hx + scale[0], hy + scale[1]]
                if part.get("position_mode") == "front":
                    pos[1] -= hy
            tint = color if part["color"] == "villager" else part["color"]
            if tint is None:
                raise ValueError(f"Prefab {name} requires a villager color")
            if "model" in part:
                from panda3d.core import Filename

                filename = Filename.fromOsSpecific(
                    str((self.path.parent / part["model"]).resolve())
                )
                model = game.loader.loadModel(filename)
                if model.isEmpty():
                    raise ValueError(f"Cannot load model: {part['model']}")
                node = model.copyTo(parent)
                model.removeNode()
                node.setPos(*pos)
                node.setScale(*scale)
                node.setColor(*tint, 1)
            else:
                node = game.box(parent, pos, scale, tint)
            if "hpr" in part:
                node.setHpr(*part["hpr"])
            result[part["name"]] = node
        return result
