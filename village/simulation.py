"""Compatibility facade. New code should import the owning modules directly."""

from .entities import Villager, Crop, Monster
from .map_data import (
    LIMIT,
    SIGHT,
    HEARING,
    LOCATIONS,
    GATES,
    GATE_MAX,
    CROP_GROW_SECONDS,
    BUILDINGS,
    CAST,
)
from .navigation import distance, walkable, pathfind
from .world import World
