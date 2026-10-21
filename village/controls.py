"""Configured keyboard bindings; simulation actions remain engine independent."""

from .config import get_settings


def bind_controls(game):
    keys = get_settings()["controls"]
    display = get_settings()["display"]
    for name in ("forward", "left", "backward", "right", "orbit_left", "orbit_right"):
        key = keys[name]
        game.accept(key, game.keys.add, [key])
        game.accept(key + "-up", game.keys.discard, [key])
    for index, key in enumerate(keys["takeover_keys"][: len(game.world.villagers)]):
        game.accept(key, game.takeover, [index])
    for name, handler, args in (
        ("cycle", game.cycle, []),
        ("observer", game.takeover, [None]),
        ("speak", game.open_chat, []),
        ("escape", game.escape, []),
        ("save", game.save_world, []),
        ("pause", game.toggle_pause, []),
        ("speed", game.cycle_speed, []),
        ("zoom_in", game.change_zoom, [-display["zoom_step"]]),
        ("zoom_out", game.change_zoom, [display["zoom_step"]]),
    ):
        game.accept(keys[name], handler, args)
    for action, key in keys["actions"].items():
        game.accept(key, game.player_action, [action])
