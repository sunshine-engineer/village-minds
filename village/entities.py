"""Simulation entities; no graphics or network imports."""

from collections import deque
from dataclasses import dataclass, field
from .config import get_settings

R = get_settings()["rules"]
M = get_settings()["memory"]
CROP_GROW_SECONDS = R["crop_grow_seconds"]


@dataclass
class Villager:
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
        return self.health > 0


@dataclass
class Crop:
    position: tuple
    stage: str = "ripe"
    age: float = CROP_GROW_SECONDS


@dataclass
class Monster:
    id: str
    gate: str
    position: tuple
    health: float = R["monster_health"]
