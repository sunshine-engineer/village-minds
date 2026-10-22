"""Validated startup configuration. Import this module before simulation/rendering."""

from copy import deepcopy
import hashlib
import json
import math
from string import Formatter
from pathlib import Path
from urllib.parse import urlparse

DATA = Path(__file__).with_name("data")
PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = DATA / "default.json"


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON setting: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Invalid JSON number: {value}")

    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=unique,
        parse_constant=invalid_constant,
    )


def _merge(base, override, prefix=""):
    if not isinstance(override, dict):
        raise ValueError(f'{prefix or "config"} must be an object')
    for key, value in override.items():
        name = f"{prefix}.{key}".strip(".")
        if key not in base:
            # These are named extension catalogs, not fixed settings schemas.
            if prefix in (
                "ai.profiles",
                "roles",
                "world.locations",
                "controls.actions",
                "ai.villager_profiles",
                "ai.social_messages.roles",
                "extension_settings",
            ):
                base[key] = deepcopy(value)
                continue
            raise ValueError(f"Unknown configuration setting: {name}")
        if isinstance(base[key], dict):
            _merge(base[key], value, name)
        else:
            base[key] = deepcopy(value)


def _validate_types(value, reference, path="config"):
    """Reject wrong types/nonfinite values before importing game modules."""
    if isinstance(reference, dict):
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        missing = set(reference) - set(value)
        if missing:
            raise ValueError(f"{path} is missing: {sorted(missing)}")
        for key, item in reference.items():
            _validate_types(value[key], item, f"{path}.{key}")
    elif isinstance(reference, list):
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
    elif isinstance(reference, bool):
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be boolean")
    elif isinstance(reference, (int, float)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{path} must be a finite number")
        if isinstance(reference, int) and not isinstance(value, int):
            raise ValueError(f"{path} must be an integer")
        positive = {
            "crop_grow_seconds",
            "wave_growth_every",
            "max_step_seconds",
            "villager_max",
            "gate_health",
            "village_health",
            "monster_health",
            "limit",
            "wall_coordinate",
            "timeout",
            "max_tokens",
            "context_size",
            "model_history_limit",
            "recent_capacity",
            "lesson_capacity",
            "event_capacity",
            "failure_capacity",
            "dialogue_chars",
            "feed_lines",
            "roster_action_chars",
            "zoom",
            "zoom_min",
            "zoom_max",
            "near",
            "far",
            "fov",
            "max_pace",
            "max_steps_per_frame",
            "max_bytes",
            "duration_seconds",
            "step_seconds",
            "checkpoint_seconds",
            "model_timeout_seconds",
            "run_wall_seconds",
            "suite_wall_seconds",
            "lesson_seconds",
            "update_seconds",
            "maintenance_seconds",
            "task_ttl_seconds",
            "history_capacity",
            "max_active_tasks",
        }
        if value < 0 or (path.rsplit(".", 1)[-1] in positive and value == 0):
            raise ValueError(f"{path} is outside its valid range")
    elif not isinstance(value, str):
        raise ValueError(f"{path} must be text")


def _vector(value, length, name, low=None, high=None):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{name} must contain {length} numbers")
    for item in value:
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            or (low is not None and item < low)
            or (high is not None and item > high)
        ):
            raise ValueError(f"Invalid {name}")


def validate(config, reference):
    _validate_types(config, reference)
    if not 1 <= config["ai"]["repair_strategy"]["max_choices"] <= 12:
        raise ValueError("repair_strategy.max_choices must be between 1 and 12")
    strategy = config["ai"]["repair_strategy"]
    if strategy["mode"] not in ("assignment", "priority_plan") or strategy[
        "controller"
    ] not in ("model", "scripted"):
        raise ValueError("Invalid repair strategy mode or controller")
    if strategy["plan_seconds"] <= 0:
        raise ValueError("Repair plan duration must be positive")
    probe = config["inference_probe"]
    if (
        probe["rounds"] < 1
        or not probe["roles"]
        or len(set(probe["roles"])) != len(probe["roles"])
        or any(r not in config["roles"] for r in probe["roles"])
    ):
        raise ValueError("Invalid inference probe roles or rounds")
    for value in (
        probe["request_seconds"],
        probe["suite_seconds"],
        config["ai"]["repair_strategy"]["lease_seconds"],
    ):
        if value <= 0:
            raise ValueError("Inference deadlines and leases must be positive")
    if probe["gate_health"] > config["rules"]["gate_health"]:
        raise ValueError("Probe gate health exceeds maximum")
    network = config["network"]
    if network["host"] not in ("127.0.0.1", "localhost"):
        raise ValueError("Prototype network host must be loopback")
    if not 0 <= network["port"] <= 65535:
        raise ValueError("Invalid network port")
    for key in (
        "tick_seconds",
        "poll_seconds",
        "request_seconds",
        "lease_seconds",
        "input_seconds",
        "reconnect_seconds",
        "queue_capacity",
        "max_commands_per_tick",
        "max_body_bytes",
        "max_state_bytes",
    ):
        if network[key] <= 0:
            raise ValueError(f"network.{key} must be positive")
    if network["tick_seconds"] > config["runtime"]["max_step_seconds"]:
        raise ValueError("Network tick exceeds safe physics step")
    if (
        network["lease_seconds"] <= network["poll_seconds"]
        or network["input_seconds"] <= network["poll_seconds"]
    ):
        raise ValueError("Network leases must exceed polling interval")
    smoothing = network["interpolation"]
    if not 2 <= smoothing["buffer_size"] <= 512:
        raise ValueError("Interpolation buffer_size must be between 2 and 512")
    if (
        smoothing["max_gap_seconds"] <= 0
        or smoothing["snap_distance"] <= 0
        or smoothing["catch_up_threshold_seconds"] <= 0
    ):
        raise ValueError(
            "Interpolation gap, snap distance and catch-up threshold must be positive"
        )
    if (
        smoothing["delay_seconds"] > smoothing["max_gap_seconds"]
        or not 1 <= smoothing["catch_up_rate"] <= 2
    ):
        raise ValueError("Invalid interpolation delay or catch-up rate")
    coordination = config["coordination"]
    if coordination["mode"] not in ("independent", "requests", "assigned"):
        raise ValueError("Unknown coordination mode")
    if (
        set(coordination["priority"]) != {"defend", "repair", "wood", "food"}
        or len(coordination["priority"]) != 4
    ):
        raise ValueError("coordination.priority must contain each task kind once")
    for roles in [
        coordination["assigner_roles"],
        *coordination["role_preferences"].values(),
    ]:
        if (
            not roles
            or any(not isinstance(r, str) or r not in config["roles"] for r in roles)
            or len(set(roles)) != len(roles)
        ):
            raise ValueError("Invalid coordination role preferences")
    if config["evaluation"]["timing_policy"] not in (
        "paused_checkpoints",
        "fixed_delay",
        "measured_delay",
    ):
        raise ValueError("Unknown evaluation timing policy")
    world, display = config["world"], config["display"]
    runtime, evaluation = config["runtime"], config["evaluation"]
    if not runtime["speed_steps"] or any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not math.isfinite(v)
        or not 0.1 <= v <= runtime["max_pace"]
        for v in runtime["speed_steps"]
    ):
        raise ValueError("runtime.speed_steps must contain supported pace values")
    if not evaluation["seeds"] or any(
        isinstance(v, bool) or not isinstance(v, int) or v < 0
        for v in evaluation["seeds"]
    ):
        raise ValueError("evaluation.seeds must contain nonnegative integers")
    if not evaluation["modes"] or any(
        v not in ("scripted", "hybrid", "hybrid-memory") for v in evaluation["modes"]
    ):
        raise ValueError("Unknown evaluation mode")
    if evaluation["control"] not in evaluation["controls"]:
        raise ValueError("Unknown evaluation control")
    if not evaluation["scenario_name"].strip():
        raise ValueError("evaluation.scenario_name cannot be empty")
    for control in evaluation["controls"].values():
        actions = control["disabled_actions"]
        if any(not isinstance(a, str) or not a for a in actions) or len(
            set(actions)
        ) != len(actions):
            raise ValueError(
                "Control disabled_actions must contain unique action names"
            )
    if evaluation["checkpoint_strategy"] not in ("threats", "interval"):
        raise ValueError("evaluation.checkpoint_strategy must be threats or interval")
    roles = evaluation["role_order"]
    if (
        not roles
        or any(not isinstance(r, str) or r not in config["roles"] for r in roles)
        or len(set(roles)) != len(roles)
    ):
        raise ValueError(
            "evaluation.role_order must contain unique configured role names"
        )
    if evaluation["step_seconds"] > runtime["max_step_seconds"]:
        raise ValueError(
            "evaluation.step_seconds cannot exceed runtime.max_step_seconds"
        )
    if not 0.1 <= config["runtime"]["pace"] <= config["runtime"]["max_pace"]:
        raise ValueError("runtime.pace must be between 0.1 and runtime.max_pace")
    if config["runtime"]["max_step_seconds"] > 0.1:
        raise ValueError("runtime.max_step_seconds cannot exceed 0.1")
    if display["zoom_min"] > display["zoom"] or display["zoom"] > display["zoom_max"]:
        raise ValueError("display.zoom must lie between zoom_min and zoom_max")
    if display["near"] >= display["far"] or not 1 <= display["fov"] < 180:
        raise ValueError("Invalid camera clipping planes or field of view")
    _vector(display["window_size"], 2, "window_size", 1)
    _vector(display["background"], 3, "background", 0, 1)
    _vector(display["ambient"], 4, "ambient", 0, 1)
    _vector(display["sun"], 4, "sun", 0, 1)
    _vector(display["sun_hpr"], 3, "sun_hpr")
    required = {
        "square",
        "farm",
        "orchard",
        "storehouse",
        "well",
        "rest",
        "tavern",
        "north_gate",
        "south_gate",
        "east_gate",
        "west_gate",
    }
    if not required <= world["locations"].keys():
        raise ValueError("Missing required map locations")
    for name, pos in world["locations"].items():
        _vector(pos, 2, f"location {name}", -world["limit"], world["limit"])
        if name.endswith("_gate") and (
            max(abs(v) for v in pos) == 0 or (pos[0] != 0 and pos[1] != 0)
        ):
            raise ValueError("Gates must lie on one nonzero cardinal axis")
    for bounds in world["buildings"]:
        _vector(bounds, 4, "building")
        if min(bounds[2:]) <= 0:
            raise ValueError("Building half sizes must be positive")
    for name in ("crops", "work_offsets"):
        if not world[name]:
            raise ValueError(f"world.{name} cannot be empty")
        for pos in world[name]:
            _vector(pos, 2, name, -world["limit"], world["limit"])
    if not world["gate_half_opening"] < world["wall_coordinate"]:
        raise ValueError("Gate opening must fit inside walls")
    if config["rules"]["monster_spawn_coordinate"] > world["limit"]:
        raise ValueError("Monster spawns must be within map bounds")
    if (
        not world["wall_coordinate"]
        < config["rules"]["monster_gate_coordinate"]
        <= config["rules"]["monster_spawn_coordinate"]
    ):
        raise ValueError("Monster approach/spawn coordinates must be outside walls")
    if world["wall_coordinate"] >= world["limit"]:
        raise ValueError("Walls must be inside the map")
    names = []
    if not world["cast"]:
        raise ValueError("At least one villager is required")
    for bot in world["cast"]:
        if not isinstance(bot, dict) or set(bot) != {
            "name",
            "role",
            "personality",
            "color",
            "position",
        }:
            raise ValueError("Invalid villager profile fields")
        if not all(
            isinstance(bot[k], str) and bot[k] for k in ("name", "role", "personality")
        ):
            raise ValueError("Villager identity/personality must be nonempty text")
        if bot["role"] not in config["roles"]:
            raise ValueError(f'Unknown role: {bot["role"]}')
        names.append(bot["name"])
        _vector(
            bot["position"], 2, "villager position", -world["limit"], world["limit"]
        )
        _vector(bot["color"], 3, "villager color", 0, 1)
    if len(set(names)) != len(names):
        raise ValueError("Villager names must be unique")
    controls = config["controls"]
    if len(controls["takeover_keys"]) < len(names):
        raise ValueError("Supply one takeover key per villager")
    keys = (
        [v for k, v in controls.items() if isinstance(v, str)]
        + list(controls["actions"].values())
        + controls["takeover_keys"]
    )
    if any(not isinstance(k, str) or not k.strip() for k in keys) or len(
        set(keys)
    ) != len(keys):
        raise ValueError("Control bindings must be unique nonempty key names")
    ai = config["ai"]
    if ai["default_profile"] not in ai["profiles"]:
        raise ValueError("ai.default_profile does not exist")
    for name, profile in ai["profiles"].items():
        _validate_types(
            profile, reference["ai"]["profiles"]["local_qwen"], f"ai.profiles.{name}"
        )
        if set(profile) != set(reference["ai"]["profiles"]["local_qwen"]):
            raise ValueError(f"Unknown fields in model profile {name}")
        if (
            urlparse(profile["url"]).scheme not in ("http", "https")
            or not urlparse(profile["url"]).netloc
        ):
            raise ValueError(f"Invalid model URL in {name}")
    for role, values in config["roles"].items():
        if not isinstance(values, dict) or set(values) - {
            "harvest_yield",
            "wood_yield",
            "repair_amount",
            "attack_damage",
            "can_rally",
        }:
            raise ValueError(f"Invalid role settings: {role}")
        for key, value in values.items():
            if key == "can_rally":
                if not isinstance(value, bool):
                    raise ValueError("can_rally must be boolean")
            elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"Invalid role bonus: {role}.{key}")
    if any(
        name not in names
        or not isinstance(profile, str)
        or profile not in ai["profiles"]
        for name, profile in ai["villager_profiles"].items()
    ):
        raise ValueError(
            "Villager model assignments must reference known names and profiles"
        )
    if config["memory"]["dialogue_chars"] > 2000:
        raise ValueError("memory.dialogue_chars exceeds protocol safety bound")
    if any(not isinstance(p, str) or not p for p in config["plugins"]):
        raise ValueError("plugins must contain Python module names")
    if any(
        g not in world["locations"] or not g.endswith("_gate")
        for g in config["policy"]["soldier_gates"]
    ):
        raise ValueError("policy.soldier_gates must reference gates")
    if not config["policy"]["soldier_gates"]:
        raise ValueError("At least one patrol gate is required")
    if any(not isinstance(a, str) for a in ai["strategic_actions"]):
        raise ValueError("ai.strategic_actions must contain action names")
    templates = ai["social_messages"]
    for template in [v for k, v in templates.items() if k != "roles"] + list(
        templates["roles"].values()
    ):
        if not isinstance(template, str):
            raise ValueError("Social message templates must be text")
        try:
            for _, field, spec, conversion in Formatter().parse(template):
                if field is not None and (
                    field not in {"other", "gate", "supplies"} or spec or conversion
                ):
                    raise ValueError("Unsupported social template placeholder")
        except ValueError as exc:
            raise ValueError(f"Invalid social message template: {exc}") from exc
    for offset in ai["activity_offsets"]:
        _vector(offset, 2, "activity offset")
    if not ai["activity_offsets"]:
        raise ValueError("ai.activity_offsets cannot be empty")


def load_config(path=None):
    reference = read_json(DEFAULT_PATH)
    result = deepcopy(reference)
    override = {}
    if path:
        path = Path(path).expanduser().resolve()
        override = read_json(path)
        _merge(result, override)
    validate(result, reference)
    for section, key in (("ai", "system_prompt"), ("assets", "manifest")):
        base = (
            path.parent
            if path and key in override.get(section, {})
            else DEFAULT_PATH.parent
        )
        result[section][key] = str((base / result[section][key]).resolve())
        if not Path(result[section][key]).is_file():
            raise ValueError(f"Missing {section}.{key}: {result[section][key]}")
    strategy_prompt = result["ai"]["repair_strategy"]["prompt"]
    strategy_base = (
        path.parent
        if path and "prompt" in override.get("ai", {}).get("repair_strategy", {})
        else DEFAULT_PATH.parent
    )
    result["ai"]["repair_strategy"]["prompt"] = str(
        (strategy_base / strategy_prompt).resolve()
    )
    if not Path(result["ai"]["repair_strategy"]["prompt"]).is_file():
        raise ValueError("Missing repair strategy prompt")
    priority_prompt = result["ai"]["repair_strategy"]["priority_prompt"]
    priority_base = (
        path.parent
        if path
        and "priority_prompt" in override.get("ai", {}).get("repair_strategy", {})
        else DEFAULT_PATH.parent
    )
    result["ai"]["repair_strategy"]["priority_prompt"] = str(
        (priority_base / priority_prompt).resolve()
    )
    if not Path(result["ai"]["repair_strategy"]["priority_prompt"]).is_file():
        raise ValueError("Missing priority prompt")

    network_base = (
        path.parent if path and "save_path" in override.get("network", {}) else PROJECT
    )
    result["network"]["save_path"] = str(
        (network_base / result["network"]["save_path"]).resolve()
    )
    save_base = (
        path.parent if path and "save_path" in override.get("runtime", {}) else PROJECT
    )
    result["runtime"]["save_path"] = str(
        (save_base / result["runtime"]["save_path"]).resolve()
    )
    if result["telemetry"]["decision_log"]:
        log_base = (
            path.parent
            if path and "decision_log" in override.get("telemetry", {})
            else PROJECT
        )
        result["telemetry"]["decision_log"] = str(
            (log_base / result["telemetry"]["decision_log"]).resolve()
        )
    output_base = (
        path.parent
        if path and "output_dir" in override.get("evaluation", {})
        else PROJECT
    )
    result["evaluation"]["output_dir"] = str(
        (output_base / result["evaluation"]["output_dir"]).resolve()
    )
    return result


def configure(path=None):
    """Call once at startup, before importing world, rendering or persistence."""
    import sys

    loaded = load_config(path)
    if "village.world" in sys.modules:
        if loaded == SETTINGS:
            return SETTINGS
        raise RuntimeError(
            "Configuration is startup-only; start a new process to change it"
        )
    SETTINGS.clear()
    SETTINGS.update(loaded)
    return SETTINGS


def fingerprint(config=None):
    # Visual/backend/runtime overrides are safe across restarts; rule/map changes aren't.
    content = {
        k: (config or get_settings())[k]
        for k in ("world", "rules", "roles", "memory", "plugins", "extension_settings")
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


SETTINGS = {}  # Populated by CLI or lazily by get_settings, after files are installed.


def get_settings():
    if not SETTINGS:
        SETTINGS.update(load_config())
    return SETTINGS


def configure_snapshot(settings):
    """Initialize a spawned worker from trusted parent settings, before World imports."""
    import sys

    loaded = deepcopy(settings)
    validate(loaded, read_json(DEFAULT_PATH))
    if "village.world" in sys.modules and loaded != SETTINGS:
        raise RuntimeError("Configuration is startup-only")
    SETTINGS.clear()
    SETTINGS.update(loaded)
    return SETTINGS
