"""Explicit, trusted Python extension hooks. Model text can never register code."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from dataclasses import dataclass
from importlib import import_module
from .config import get_settings

if TYPE_CHECKING:
    from .world import World
    from .entities import Villager

# Action names owned by the base simulation cannot be replaced by plugins.
BUILTIN_ACTIONS = frozenset(
    {
        "move",
        "talk",
        "gather",
        "rest",
        "idle",
        "farm",
        "harvest",
        "deposit",
        "eat",
        "repair",
        "guard",
        "attack",
        "rally",
        "request_help",
        "assign_task",
        "claim_task",
        "release_task",
        "dispatch_repair",
        "plan_repairs",
        "defer_strategy",
    }
)


@dataclass(frozen=True)
class Action:
    """available(world, bot) -> list[str]; execute(world, bot, decision) -> bool."""

    available: Callable[[World, Villager], list[str]]
    execute: Callable[[World, Villager, dict], bool]


class Extensions:
    def __init__(self):
        self.actions = {}
        self.policies = {}
        self.systems = {}
        self.states = {}

    def register_action(self, name, *, available, execute):
        if (
            not isinstance(name, str)
            or not name.isidentifier()
            or name in BUILTIN_ACTIONS
            or name in self.actions
        ):
            raise ValueError(f"Action already registered or invalid: {name}")
        if not callable(available) or not callable(execute):
            raise ValueError("Action hooks must be callable")
        self.actions[name] = Action(available, execute)

    def register_policy(self, role, policy):
        if (
            role not in get_settings()["roles"]
            or role in self.policies
            or not callable(policy)
        ):
            raise ValueError(f"Invalid or duplicate role policy: {role}")
        self.policies[role] = policy

    def register_system(self, name, tick):
        if (
            not isinstance(name, str)
            or not name
            or name in self.systems
            or not callable(tick)
        ):
            raise ValueError(f"Invalid or duplicate system: {name}")
        self.systems[name] = tick

    def register_backend(self, name, factory):
        from .models import register_backend

        register_backend(name, factory)

    def register_state(self, name, *, create, restore):
        """create() -> JSON state; restore(saved) -> validated JSON state."""
        if (
            not isinstance(name, str)
            or not name
            or name in self.states
            or not callable(create)
            or not callable(restore)
        ):
            raise ValueError(f"Invalid or duplicate state registration: {name}")
        self.states[name] = (create, restore)


def load_extensions():
    registry = Extensions()
    for module in get_settings()["plugins"]:
        import_module(module).register(registry)
    return registry
