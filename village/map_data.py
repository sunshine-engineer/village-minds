"""Shared map and roster loaded from startup configuration.

File: village/map_data.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from .config import get_settings

S = get_settings()
W = S["world"]
LIMIT, SIGHT, HEARING = W["limit"], W["sight"], W["hearing"]
LOCATIONS = {k: tuple(v) for k, v in W["locations"].items()}
GATES = {k: v for k, v in LOCATIONS.items() if k.endswith("_gate")}
BUILDINGS = [tuple(v) for v in W["buildings"]]
CAST = [
    (v["name"], v["role"], v["personality"], tuple(v["color"]), tuple(v["position"]))
    for v in W["cast"]
]
GATE_MAX = S["rules"]["gate_health"]
CROP_GROW_SECONDS = S["rules"]["crop_grow_seconds"]
