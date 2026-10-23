"""HUD widget construction from the asset catalog.

File: village/ui.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from direct.gui.DirectGui import DirectEntry, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

from .config import get_settings


def control_help():
    """Build displayed help from the actual configured bindings.

    Returns:
        Multiline controls string.
    """
    keys = get_settings()["controls"]
    move = "/".join(keys[k].upper() for k in ("forward", "left", "backward", "right"))
    lines = [
        f"{'/'.join(keys['takeover_keys'])} / {keys['cycle']} Take over | {keys['observer']} Observe",
        f"{move} Walk | {keys['orbit_left']}/{keys['orbit_right']} Orbit",
        f"{keys['zoom_in']}/{keys['zoom_out']} Zoom",
    ]
    actions = list(keys["actions"].items())
    lines += [
        " | ".join(f"{key.upper()} {action}" for action, key in actions[i : i + 3])
        for i in range(0, len(actions), 3)
    ]
    lines += [
        f"{keys['speak']} Speak | {keys['pause']} Pause | {keys['speed']} Speed",
        f"{keys['save']} Save | {keys['escape']} Quit/cancel",
    ]
    return "\n".join(lines)


def build_ui(game):
    """Create configured HUD widgets and attach named references to the game.

    Args:
        game: Game instance owning scene/UI references.

    Returns:
        None; initializes UI nodes.
    """
    factories = {
        "OnscreenText": OnscreenText,
        "DirectEntry": DirectEntry,
        "DirectFrame": DirectFrame,
    }
    for spec in game.assets.catalog["ui"]:
        options = {
            key: tuple(value) if isinstance(value, list) else value
            for key, value in spec["options"].items()
        }
        if "parent" in spec:
            options["parent"] = getattr(game, spec["parent"])
        if "align" in spec:
            options["align"] = getattr(TextNode, spec["align"])
        if "command" in spec:
            options["command"] = getattr(game, spec["command"])
        if spec["name"] == "controls":
            options["text"] = control_help()
        widget = factories[spec["kind"]](**options)
        if spec["name"]:
            setattr(game, spec["name"], widget)
    game.entry.hide()
