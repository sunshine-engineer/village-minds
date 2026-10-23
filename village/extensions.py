"""Explicit, trusted Python extension hooks. Model text can never register code.

File: village/extensions.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

from .config import get_settings

if TYPE_CHECKING:
    from .entities import Villager
    from .world import World

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
    """available(world, bot) -> list[str]; execute(world, bot, decision) -> bool.

    Attributes:
        available: Pure callback returning currently legal target tokens.
        execute: Validated-action callback returning whether its effect succeeded.
    """

    available: Callable[[World, Villager], list[str]]
    execute: Callable[[World, Villager, dict], bool]


class Extensions:
    """Registry of trusted action, role policy, system, backend and persistence hooks."""

    def __init__(self):
        """Initialize Extensions and its owned state.

        Returns:
            None.
        """
        self.actions = {}
        self.policies = {}
        self.systems = {}
        self.states = {}

    def register_action(self, name, *, available, execute):
        """Register pure availability and validated execution hooks for a new action.

        Args:
            name: Registered identity or name selected by the caller.
            available: Pure callback returning currently legal target tokens.
            execute: Validated-action callback returning whether its effect succeeded.

        Returns:
            None; built-in or duplicate action names are rejected.

        Raises:
            ValueError: If the input violates the validation contract described above.

        Example:
            registry.register_action('encourage', available=available, execute=execute)
        """
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
        """Register a local policy for a configured role.

        Args:
            role: Configured villager role name.
            policy: Pure local policy callback returning an intent or None.

        Returns:
            None; policy callbacks must be callable and unique.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
        if (
            role not in get_settings()["roles"]
            or role in self.policies
            or not callable(policy)
        ):
            raise ValueError(f"Invalid or duplicate role policy: {role}")
        self.policies[role] = policy

    def register_system(self, name, tick):
        """Register a short nonblocking callback for each simulation step.

        Args:
            name: Registered identity or name selected by the caller.
            tick: Nonblocking simulation-step callback.

        Returns:
            None; callbacks execute on the simulation thread.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
        if (
            not isinstance(name, str)
            or not name
            or name in self.systems
            or not callable(tick)
        ):
            raise ValueError(f"Invalid or duplicate system: {name}")
        self.systems[name] = tick

    def register_backend(self, name, factory):
        """Register a model-adapter factory through the shared transport registry.

        Args:
            name: Registered identity or name selected by the caller.
            factory: Zero-argument trusted backend/state factory.

        Returns:
            None; conflicting registrations are rejected.
        """
        from .models import register_backend

        register_backend(name, factory)

    def register_state(self, name, *, create, restore):
        """create() -> JSON state; restore(saved) -> validated JSON state.

        Args:
            name: Registered identity or name selected by the caller.
            create: Factory returning fresh JSON-compatible extension state.
            restore: Callback validating and rebuilding saved extension state.

        Returns:
            None; names must be unique and callbacks callable.

        Raises:
            ValueError: If the input violates the validation contract described above.
        """
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
    """Import explicitly configured trusted plugins and collect their registrations.

    Returns:
        Extensions registry populated by register hooks.
    """
    registry = Extensions()
    for module in get_settings()["plugins"]:
        import_module(module).register(registry)
    return registry
