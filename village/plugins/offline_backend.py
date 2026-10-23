"""Contributor example: deterministic adapter contract, not AI inference.

File: village/plugins/offline_backend.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from ..config import get_settings


class OfflineBackend:
    """Deterministic contributor-contract example; performs no AI/provider inference."""

    def decide(self, profile, observation, timeout):
        """Return a deterministic rest intent or defer a repair request for contract testing.

        Args:
            profile: Resolved model profile containing backend and generation options.
            observation: Request-time context containing legal choices and relevant world state.
            timeout: Maximum request wall time in seconds.

        Returns:
            Decision dictionary; never makes a model/provider request.
        """
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
    """Validate the offline adapter example and register its backend factory.

    Args:
        registry: Trusted extension registry receiving this plugin's hooks.

    Returns:
        None; rejects unsupported example options.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    options = get_settings()["extension_settings"].get("offline_backend", {})
    if set(options) != {"action"} or options["action"] != "rest":
        raise ValueError("offline_backend example supports action=rest")
    registry.register_backend("offline_example", OfflineBackend)
