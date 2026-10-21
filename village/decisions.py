"""JSON action schema shared by model backends; Python revalidates results."""

from .config import get_settings


def decision_schema(observation):
    """Constrain choices at request time; Python rechecks them on arrival."""
    branches = []

    def add(action, targets=None, speaking=False):
        branches.append(
            {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": [action]},
                    "target": {"type": "string", "enum": targets or [""]},
                    "dialogue": (
                        {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": get_settings()["memory"]["dialogue_chars"],
                        }
                        if speaking
                        else {"type": "string", "enum": [""]}
                    ),
                },
                "required": ["action", "target", "dialogue"],
                "additionalProperties": False,
            }
        )

    if "available_actions" in observation:
        for action, targets in observation["available_actions"].items():
            if (
                observation.get("decision_layer") == "strategic"
                and action not in get_settings()["ai"]["strategic_actions"]
            ):
                continue
            add(action, targets, speaking=action == "talk")
        if not branches:
            add("idle")
        return {"type": "object", "oneOf": branches}
    destinations = list(observation.get("village_map", {})) + [
        other["name"] for other in observation.get("nearby_villagers", [])
    ]
    if destinations:
        add("move", destinations)
    partners = observation.get("conversation_partners", [])
    if partners:
        add("talk", partners, speaking=True)
    if observation.get("gather_here"):
        add("gather")
    if observation.get("energy", 100) < get_settings()["rules"]["rest_available_below"]:
        add("rest")
    if not branches:
        add("idle")
    return {"type": "object", "oneOf": branches}
