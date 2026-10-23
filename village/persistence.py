"""Versioned, atomic JSON snapshots; never deserialize executable objects.

File: village/persistence.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import math
import os
import shutil
import tempfile
from collections import deque
from copy import deepcopy
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path

from .config import fingerprint, get_settings, load_config
from .entities import Crop, Monster, Villager
from .map_data import CAST, GATE_MAX, GATES, LIMIT
from .world import World

S = get_settings()
R, M = S["rules"], S["memory"]

VERSION = 2
DEFAULT_SAVE_PATH = Path(S["runtime"]["save_path"])


def jsonable(value):
    """Convert tuples, deques and nested mappings into JSON-compatible containers.

    Args:
        value: Value to validate, convert or publish as described above.

    Returns:
        Converted value with scalar values preserved.
    """
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, deque)):
        return [jsonable(item) for item in value]
    return value


def number(value, low=0, high=1e12):
    """Validate a finite saved number against inclusive bounds.

    Args:
        value: Value to validate, convert or publish as described above.
        low: Optional inclusive lower bound.
        high: Optional inclusive upper bound.

    Returns:
        The validated numeric value.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"Invalid saved number: {value!r}")
    return value


def point(value):
    """Validate a saved planar position against configured map bounds.

    Args:
        value: Value to validate, convert or publish as described above.

    Returns:
        Two-coordinate tuple.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Invalid saved position")
    return tuple(number(n, -LIMIT, LIMIT) for n in value)


def strings(value, maximum=8, length=2000):
    """Validate bounded saved memories or dialogue strings.

    Args:
        value: Value to validate, convert or publish as described above.
        maximum: Maximum number of saved strings.
        length: Required vector length.

    Returns:
        The validated list of strings.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or any(not isinstance(v, str) or len(v) > length for v in value)
    ):
        raise ValueError("Invalid saved memory/text")
    return value


def validate_campaign(value):
    """Validate attempts, failure records and per-villager lessons.

    Args:
        value: Value to validate, convert or publish as described above.

    Returns:
        Independent campaign dictionary.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    if not isinstance(value, dict) or set(value) != {"attempt", "failures", "lessons"}:
        raise ValueError("Invalid campaign")
    number(value["attempt"], 1, 1e9)
    if (
        not isinstance(value["attempt"], int)
        or not isinstance(value["failures"], list)
        or len(value["failures"]) > M["failure_capacity"]
    ):
        raise ValueError("Invalid attempt history")
    if not isinstance(value["lessons"], dict) or set(value["lessons"]) - {
        c[0] for c in CAST
    }:
        raise ValueError("Unknown villager lessons")
    for lessons in value["lessons"].values():
        strings(lessons, M["lesson_capacity"])
    # Failure records are descriptive JSON, never executable configuration.
    if any(not isinstance(record, dict) for record in value["failures"]):
        raise ValueError("Invalid failure records")
    return deepcopy(value)


def snapshot(world):
    """Capture simulation, RNG, task and campaign state in the versioned JSON format.

    Args:
        world: Authoritative simulation world used by this operation.

    Returns:
        JSON-compatible save envelope including configuration fingerprint.

    Example:
        saved = snapshot(world)
        restored = restore(saved)  # compatible startup config must remain active
    """
    return jsonable(
        {
            "version": VERSION,
            "config_fingerprint": fingerprint(),
            "campaign": world.campaign,
            "world": {
                "extension_state": world.extension_state,
                "task_board": world.task_board.snapshot(),
                "time": world.time,
                "villagers": [asdict(bot) for bot in world.villagers],
                "crops": [asdict(crop) for crop in world.crops],
                "monsters": [asdict(monster) for monster in world.monsters],
                "resources": world.resources,
                "regen_at": world.regen_at,
                "store": world.store,
                "gates": world.gates,
                "village_health": world.village_health,
                "wave": world.wave,
                "next_wave": world.next_wave,
                "next_monster_id": world.next_monster_id,
                "failed": world.failed,
                "failure_reason": world.failure_reason,
                "events": list(world.events),
                "rng_state": world.rng.getstate(),
            },
        }
    )


def restore(data):
    """Validate save compatibility and reconstruct a world with refreshed AI scheduling.

    Args:
        data: Structured payload or versioned save data for the described operation.

    Returns:
        Restored World; possession is intentionally not restored.

    Raises:
        ValueError: If save structure, identities, bounds or configuration compatibility are invalid.
    """
    if not isinstance(data, dict) or data.get("version") not in (1, VERSION):
        raise ValueError("Unsupported save format version")
    expected = (
        data.get("config_fingerprint")
        if data["version"] == VERSION
        else fingerprint(load_config())
    )
    if expected != fingerprint():
        raise ValueError(
            "Save configuration differs from current map/rules/roster/plugins. Use its original config or a separate --save-path."
        )
    campaign = validate_campaign(data["campaign"])
    state = data["world"]
    world = World(campaign=campaign)
    saved_extensions = state.get("extension_state", {})
    if not isinstance(saved_extensions, dict) or set(saved_extensions) != set(
        world.extensions.states
    ):
        raise ValueError("Save extension state registrations changed")
    for name, (_, validate) in world.extensions.states.items():
        world.extension_state[name] = validate(saved_extensions[name])
    for name in ("time", "regen_at", "next_wave"):
        setattr(world, name, number(state[name]))
    for name in ("wave", "next_monster_id"):
        value = number(state[name], 0 if name == "wave" else 1, 1e9)
        if not isinstance(value, int):
            raise ValueError("Invalid integer counter")
        setattr(world, name, value)
    for name, keys, maximum in (
        ("store", {"food", "wood"}, 1e9),
        ("resources", {"orchard"}, R["orchard_capacity"]),
        ("gates", set(GATES), GATE_MAX),
    ):
        values = state[name]
        if not isinstance(values, dict) or set(values) != keys:
            raise ValueError(f"Invalid saved {name}")
        setattr(
            world,
            name,
            {key: number(value, 0, maximum) for key, value in values.items()},
        )
        if name != "gates" and any(not isinstance(v, int) for v in values.values()):
            raise ValueError("Resource quantities must be integers")
    world.village_health = number(state["village_health"], 0, R["village_health"])
    if not isinstance(state["failed"], bool) or not isinstance(
        state["failure_reason"], str
    ):
        raise ValueError("Invalid failure state")
    world.failed, world.failure_reason = state["failed"], state["failure_reason"][:2000]
    if len(state["villagers"]) != len(CAST):
        raise ValueError("Villager roster changed")
    for bot, saved, profile in zip(world.villagers, state["villagers"], CAST):
        if not isinstance(saved, dict) or set(saved) != {
            f.name for f in fields(Villager)
        }:
            raise ValueError("Invalid villager fields")
        if saved["name"] != profile[0] or saved["role"] != profile[1]:
            raise ValueError("Invalid villager identity")
        bot.position = point(saved["position"])
        if not isinstance(saved["path"], list) or len(saved["path"]) > 500:
            raise ValueError("Invalid path")
        bot.path = [point(p) for p in saved["path"]]
        for name in ("energy", "health", "hunger"):
            setattr(bot, name, number(saved[name], 0, R["villager_max"]))
        for name in ("supplies", "wood", "revision"):
            value = number(saved[name], 0, 1e9)
            if not isinstance(value, int):
                raise ValueError("Invalid villager counter")
            setattr(bot, name, value)
        for name in ("speech_until", "next_think", "work_at", "attack_at", "rally_at"):
            setattr(bot, name, number(saved[name]))
        for name, maximum in (("action", 80), ("speech", M["dialogue_chars"])):
            value = saved[name]
            if not isinstance(value, str) or len(value) > maximum:
                raise ValueError("Invalid villager text")
            setattr(bot, name, value)
        bot.memory = deque(
            strings(saved["memory"], M["recent_capacity"]), maxlen=M["recent_capacity"]
        )
        bot.lessons = deque(
            strings(saved["lessons"], M["lesson_capacity"]), maxlen=M["lesson_capacity"]
        )
        if not isinstance(saved["contributions"], dict) or set(
            saved["contributions"]
        ) != set(bot.contributions):
            raise ValueError("Invalid contribution counters")
        for key, value in saved["contributions"].items():
            number(value, 0, 1e9)
            if not isinstance(value, int):
                raise ValueError("Invalid contribution count")
        bot.contributions = saved["contributions"].copy()
        bot.revision += 1
        # Player possession is a session choice; resume this villager under AI.
        if bot.action == "player":
            bot.action = "idle"
        bot.next_think = world.time
    if not isinstance(state["crops"], list) or len(state["crops"]) != len(
        S["world"]["crops"]
    ):
        raise ValueError("Invalid crop plots")
    world.crops = []
    for crop in state["crops"]:
        if crop["stage"] not in ("empty", "growing", "ripe"):
            raise ValueError("Invalid crop stage")
        world.crops.append(
            Crop(
                point(crop["position"]),
                crop["stage"],
                number(crop["age"], 0, R["crop_grow_seconds"]),
            )
        )
    if (
        not isinstance(state["monsters"], list)
        or len(state["monsters"]) > R["max_monsters"]
    ):
        raise ValueError("Invalid monster list")
    world.monsters = []
    ids = set()
    for monster in state["monsters"]:
        identity = monster["id"]
        if (
            not isinstance(identity, str)
            or len(identity) > 50
            or identity in ids
            or monster["gate"] not in GATES
        ):
            raise ValueError("Invalid monster identity")
        ids.add(identity)
        world.monsters.append(
            Monster(
                identity,
                monster["gate"],
                point(monster["position"]),
                number(monster["health"], 0, R["monster_health"]),
            )
        )
    world.events = deque(
        strings(state["events"], M["event_capacity"], 2000), maxlen=M["event_capacity"]
    )

    def tuples(value):
        """Rebuild nested tuples required by random-generator state restoration.

        Args:
            value: Value to validate, convert or publish as described above.

        Returns:
            Nested tuple/scalar value.
        """
        return tuple(tuples(v) for v in value) if isinstance(value, list) else value

    world.rng.setstate(tuples(state["rng_state"]))
    world.controlled = None
    if "task_board" in state:
        world.task_board.restore(state["task_board"])
    return world


class SaveStore:
    """One-writer atomic JSON campaign storage with backup recovery and archived attempts."""

    def __init__(self, path):
        """Initialize SaveStore and its owned state.

        Args:
            path: Input/output filesystem path for the described resource.

        Returns:
            None.
        """
        self.path = Path(path).expanduser().resolve()
        self.recovered = False

    def load(self):
        """Load a primary save or valid backup without overwriting damaged input.

        Returns:
            Restored World, or None when neither save file exists.

        Raises:
            ValueError: If files exist but neither primary nor backup is a valid compatible save.
        """
        if not self.path.exists():
            return None
        errors = []
        for candidate in (self.path, self.path.with_suffix(self.path.suffix + ".bak")):
            try:
                if candidate.stat().st_size > 5_000_000:
                    raise ValueError("Save exceeded 5 MB size limit")
                data = json.loads(candidate.read_text(encoding="utf-8"))
                world = restore(data)
                self.recovered = candidate != self.path
                if self.recovered:
                    print(
                        f"Recovered previous snapshot from {candidate}; damaged primary retained until next save.",
                        flush=True,
                    )
                return world
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                OverflowError,
                AttributeError,
            ) as exc:
                errors.append(f"{candidate.name}: {exc}")
        raise ValueError(
            "Cannot load save. No files were overwritten. " + "; ".join(errors)
        )

    def save(self, world):
        """Atomically write a versioned snapshot and retain the preceding backup.

        Args:
            world: Authoritative simulation world used by this operation.

        Returns:
            None; does not silently suppress I/O or serialization errors.

        Raises:
            OSError: If snapshot creation, backup or atomic replacement cannot complete.
            ValueError: If state is not valid finite JSON.
        """
        data = json.dumps(
            snapshot(world), ensure_ascii=False, indent=2, allow_nan=False
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists() and not self.recovered:
                shutil.copy2(
                    self.path, self.path.with_suffix(self.path.suffix + ".bak")
                )
            os.replace(temporary, self.path)
            self.recovered = False
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def new_attempt(self):
        """Archive an existing compatible attempt and carry factual lessons into a fresh world.

        Returns:
            New World with retained campaign history and incremented attempt.
        """
        previous = self.load()
        if previous is None:
            return World()
        campaign = deepcopy(previous.campaign)
        campaign["attempt"] += 1
        # Archiving before replacement preserves the old run even on an early restart.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        archive = self.path.with_name(self.path.stem + "." + stamp + self.path.suffix)
        source = (
            self.path.with_suffix(self.path.suffix + ".bak")
            if self.recovered
            else self.path
        )
        shutil.copy2(source, archive)
        return World(campaign=campaign)
