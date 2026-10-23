"""Simulation entities; no graphics or network imports.

File: village/entities.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from collections import deque
from dataclasses import dataclass, field

from .config import get_settings

R = get_settings()["rules"]
M = get_settings()["memory"]
CROP_GROW_SECONDS = R["crop_grow_seconds"]


@dataclass
class Villager:
    """Persistent villager identity, needs, inventory, movement and bounded prompt memory.

    Attributes:
        name: Registered identity or name selected by the caller.
        role: Configured villager role name.
        personality: Role-play instructions included in model observations.
        color: Optional RGB tint for this visual.
        position: Planar world coordinates in simulation units.
        energy: Available work/combat energy.
        supplies: Carried private food units.
        action: Registered action name.
        path: Input/output filesystem path for the described resource.
        memory: Bounded recent dialogue/event deque.
        speech: Currently displayed dialogue text.
        speech_until: Simulation timestamp when the speech bubble expires.
        next_think: Next eligible simulation time for model consideration.
        revision: Actor revision captured when inference was requested.
        health: Remaining health; zero marks the entity dead.
        hunger: Current hunger level used by needs policies and starvation.
        wood: Carried private wood units.
        lessons: Prior factual lesson strings, bounded by configuration.
        contributions: Per-action productive contribution counters.
        work_at: Earliest next work-action simulation timestamp.
        attack_at: Earliest next attack simulation timestamp.
        rally_at: Earliest next rally simulation timestamp.
    """

    name: str
    role: str
    personality: str
    color: tuple
    position: tuple
    energy: float = R["villager_max"]
    supplies: int = 0
    action: str = "idle"
    path: list = field(default_factory=list)
    memory: deque = field(default_factory=lambda: deque(maxlen=M["recent_capacity"]))
    speech: str = ""
    speech_until: float = 0
    next_think: float = 0
    revision: int = 0
    health: float = R["villager_max"]
    hunger: float = 0
    wood: int = 0
    lessons: deque = field(default_factory=lambda: deque(maxlen=M["lesson_capacity"]))
    contributions: dict = field(
        default_factory=lambda: {
            "planted": 0,
            "harvested": 0,
            "deposited_food": 0,
            "deposited_wood": 0,
            "repairs": 0,
            "kills": 0,
            "rallies": 0,
        }
    )
    work_at: float = 0
    attack_at: float = 0
    rally_at: float = 0

    @property
    def alive(self):
        """Check whether this villager still has positive health.

        Returns:
            True when health is greater than zero.
        """
        return self.health > 0


@dataclass
class Crop:
    """Persistent crop plot with empty/growing/ripe stage and simulation age.

    Attributes:
        position: Planar world coordinates in simulation units.
        stage: Required crop stage.
        age: Elapsed crop growth time in simulation seconds.
    """

    position: tuple
    stage: str = "ripe"
    age: float = CROP_GROW_SECONDS


@dataclass
class Monster:
    """Persistent enemy identity, target gate, planar position and remaining health.

    Attributes:
        id: Stable monster identifier.
        gate: Configured cardinal gate name.
        position: Planar world coordinates in simulation units.
        health: Remaining health; zero marks the entity dead.
    """

    id: str
    gate: str
    position: tuple
    health: float = R["monster_health"]
