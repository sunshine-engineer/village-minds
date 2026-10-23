"""Compatibility facade. New code should import the owning modules directly.

File: village/simulation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from .entities import Crop, Monster, Villager
from .map_data import (
    BUILDINGS,
    CAST,
    CROP_GROW_SECONDS,
    GATE_MAX,
    GATES,
    HEARING,
    LIMIT,
    LOCATIONS,
    SIGHT,
)
from .navigation import distance, pathfind, walkable
from .world import World

# Stable compatibility exports; prefer owning modules in new code.
__all__ = [
    "BUILDINGS",
    "CAST",
    "CROP_GROW_SECONDS",
    "GATE_MAX",
    "GATES",
    "HEARING",
    "LIMIT",
    "LOCATIONS",
    "SIGHT",
    "Crop",
    "Monster",
    "Villager",
    "World",
    "distance",
    "pathfind",
    "walkable",
]
