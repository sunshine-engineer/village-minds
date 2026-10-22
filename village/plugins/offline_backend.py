"""Contributor example: deterministic adapter contract, not AI inference."""

from ..config import get_settings


class OfflineBackend:
    def decide(self, profile, observation, timeout):
        if observation.get("decision_layer") in (
            "repair_allocation",
            "repair_priority",
        ):
            return {"choice": "defer"}
        action = get_settings()["extension_settings"]["offline_backend"]["action"]
        if "" in observation.get("available_actions", {}).get(action, []):
            return dict(action=action, target="", dialogue="")
        return dict(action="idle", target="", dialogue="")


def register(registry):
    options = get_settings()["extension_settings"].get("offline_backend", {})
    if set(options) != {"action"} or options["action"] != "rest":
        raise ValueError("offline_backend example supports action=rest")
    registry.register_backend("offline_example", OfflineBackend)
