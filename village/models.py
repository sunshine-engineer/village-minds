"""Model transport adapters. Only decision dictionaries cross this boundary.

File: village/models.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Protocol

from .config import get_settings
from .decisions import decision_schema

MAX_RESPONSE_BYTES = 1_048_576  # Defensive protocol bound.


class InferenceDecision(dict):
    """Decision dictionary carrying optional provider timing/token metrics."""

    def __init__(self, decision, metrics=None):
        """Initialize InferenceDecision and its owned state.

        Args:
            decision: Proposed structured action with optional target/dialogue fields.
            metrics: Optional provider latency/token metadata.

        Returns:
            None.
        """
        super().__init__(decision)
        self.metrics = metrics or {}


class ModelBackend(Protocol):
    """Structured-decision protocol implemented by trusted provider adapters."""

    def decide(self, profile: dict, observation: dict, timeout: float) -> dict:
        """Request a structured decision using this backend's profile and output contract.

        Args:
            profile: Resolved model profile containing backend and generation options.
            observation: Request-time context containing legal choices and relevant world state.
            timeout: Maximum request wall time in seconds.

        Returns:
            Decision dictionary; the authoritative world must validate it before execution.
        """
        ...


def messages(observation):
    """Build role-aware or compact repair chat messages from configured prompt assets.

    Args:
        observation: Request-time context containing legal choices and relevant world state.

    Returns:
        System/user message dictionaries ready for a transport request.
    """
    if observation.get("decision_layer") in ("repair_allocation", "repair_priority"):
        prompt = Path(get_settings()["ai"]["repair_strategy"]["prompt"]).read_text(
            encoding="utf-8"
        )
        if observation.get("decision_layer") == "repair_priority":
            prompt = Path(
                get_settings()["ai"]["repair_strategy"]["priority_prompt"]
            ).read_text(encoding="utf-8")
        compact = {
            k: observation[k]
            for k in ("role", "wood", "choices", "lessons")
            if k in observation
        }
        compact["choices"] = [
            {k: v for k, v in c.items() if k not in ("target", "role")}
            for c in observation["choices"]
        ]
        return [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(compact, separators=(",", ":"))},
        ]
    prompt = Path(get_settings()["ai"]["system_prompt"]).read_text(encoding="utf-8")
    prompt = prompt.replace(
        "{{dialogue_chars}}", str(get_settings()["memory"]["dialogue_chars"])
    )
    identity = f"\nYour identity: {observation['name']}. Your personality: {observation['personality']}"
    return [
        {"role": "system", "content": prompt + identity},
        {"role": "user", "content": json.dumps(observation)},
    ]


def post_json(url, payload, timeout, api_key_env=""):
    """POST bounded JSON with optional environment-provided credentials.

    Args:
        url: Configured model endpoint, or loopback server URL for network sessions.
        payload: JSON request object to serialize.
        timeout: Maximum request wall time in seconds.
        api_key_env: Environment variable name containing an optional credential; never the credential itself.

    Returns:
        Decoded response object; no credential value is stored in configuration.

    Raises:
        ValueError: If the named credential is absent or the response exceeds its size bound.
        OSError: If the endpoint cannot complete the HTTP request.
    """
    headers = {"Content-Type": "application/json"}
    if api_key_env:
        key = os.environ.get(api_key_env)
        if not key:
            raise ValueError(f"Missing API key environment variable: {api_key_env}")
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Model response exceeded size limit")
        return json.loads(raw)


class OllamaBackend:
    """Ollama chat adapter using JSON-schema output and optional timing metadata."""

    def decide(self, profile, observation, timeout):
        """Request a structured decision using this backend's profile and output contract.

        Args:
            profile: Resolved model profile containing backend and generation options.
            observation: Request-time context containing legal choices and relevant world state.
            timeout: Maximum request wall time in seconds.

        Returns:
            Decision dictionary; the authoritative world must validate it before execution.
        """
        payload = {
            "model": profile["model"],
            "stream": False,
            "format": decision_schema(observation),
            "messages": messages(observation),
            "options": {
                "temperature": profile["temperature"],
                "num_predict": profile["max_tokens"],
                "num_ctx": profile["context_size"],
            },
            "keep_alive": profile["keep_alive"],
        }
        started = time.monotonic()
        envelope = post_json(
            profile["url"].rstrip("/") + "/api/chat",
            payload,
            timeout,
            profile["api_key_env"],
        )
        metrics = {
            "http_ms": (time.monotonic() - started) * 1000,
            "request_bytes": len(json.dumps(payload).encode()),
        }
        for source, target in (
            ("total_duration", "server_total_ms"),
            ("load_duration", "load_ms"),
            ("prompt_eval_duration", "prompt_ms"),
            ("eval_duration", "generation_ms"),
        ):
            if isinstance(envelope.get(source), (int, float)):
                metrics[target] = envelope[source] / 1e6
        for source, target in (
            ("prompt_eval_count", "prompt_tokens"),
            ("eval_count", "generated_tokens"),
        ):
            if isinstance(envelope.get(source), int):
                metrics[target] = envelope[source]
        return InferenceDecision(json.loads(envelope["message"]["content"]), metrics)


class OpenAICompatibleBackend:
    """For local servers implementing /v1/chat/completions and JSON schema output."""

    def decide(self, profile, observation, timeout):
        """Request a structured decision using this backend's profile and output contract.

        Args:
            profile: Resolved model profile containing backend and generation options.
            observation: Request-time context containing legal choices and relevant world state.
            timeout: Maximum request wall time in seconds.

        Returns:
            Decision dictionary; the authoritative world must validate it before execution.
        """
        payload = {
            "model": profile["model"],
            "stream": False,
            "messages": messages(observation),
            "temperature": profile["temperature"],
            "max_tokens": profile["max_tokens"],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "villager_decision",
                    "strict": True,
                    "schema": decision_schema(observation),
                },
            },
        }
        envelope = post_json(
            profile["url"].rstrip("/") + "/chat/completions",
            payload,
            timeout,
            profile["api_key_env"],
        )
        return json.loads(envelope["choices"][0]["message"]["content"])


BACKENDS = {"ollama": OllamaBackend, "openai_compatible": OpenAICompatibleBackend}


def register_backend(name, factory):
    """Register a callable adapter factory without replacing a different existing factory.

    Args:
        name: Registered identity or name selected by the caller.
        factory: Zero-argument trusted backend/state factory.

    Returns:
        None; repeated registration of the same factory is idempotent.

    Raises:
        ValueError: If the input violates the validation contract described above.
    """
    if BACKENDS.get(name) is factory:
        return  # The same plugin may register for multiple World instances.
    if (
        not isinstance(name, str)
        or not name
        or name in BACKENDS
        or not callable(factory)
    ):
        raise ValueError(f"Invalid or duplicate backend: {name}")
    BACKENDS[name] = factory


def resolve_profile(name=None, *, url=None, model=None):
    """Resolve a named profile and explicit endpoint/model overrides.

    Args:
        name: Registered identity or name selected by the caller.
        url: Configured model endpoint, or loopback server URL for network sessions.
        model: Installed model tag selected for inference.

    Returns:
        Independent profile dictionary.

    Raises:
        ValueError: If the requested profile does not exist.

    Example:
        profile = resolve_profile('local_qwen', model='qwen2.5:1.5b')
    """
    ai = get_settings()["ai"]
    name = name or ai["default_profile"]
    if name not in ai["profiles"]:
        raise ValueError(f"Unknown model profile: {name}")
    result = ai["profiles"][name].copy()
    if url is not None:
        result["url"] = url
    if model is not None:
        result["model"] = model
    return result


def request_decision(url, model, observation, timeout=None, *, profile=None):
    """Request or compute a bounded intent and translate compact strategy choices.

    Args:
        url: Configured model endpoint, or loopback server URL for network sessions.
        model: Installed model tag selected for inference.
        observation: Request-time context containing legal choices and relevant world state.
        timeout: Maximum request wall time in seconds.
        profile: Resolved model profile containing backend and generation options.

    Returns:
        Decision dictionary, with provider metrics when the backend supplies them.

    Raises:
        ValueError: If the backend or structured response is invalid.
        OSError: If provider transport or prompt-file I/O fails.
    """
    profile = (profile or resolve_profile()).copy()
    profile.update(url=url, model=model)
    if profile["backend"] not in BACKENDS:
        raise ValueError(f"Unknown model backend: {profile['backend']}")
    if (
        observation.get("decision_layer") == "repair_priority"
        and get_settings()["ai"]["repair_strategy"]["controller"] == "scripted"
    ):
        choices = observation["choices"]
        return InferenceDecision(
            (
                dict(action="plan_repairs", target=choices[0]["target"], dialogue="")
                if choices
                else dict(action="defer_strategy", target="", dialogue="")
            ),
            {"controller": "scripted_priority", "provider_called": False},
        )
    backend = BACKENDS[profile["backend"]]()
    result = backend.decide(
        profile, observation, profile["timeout"] if timeout is None else timeout
    )
    if not isinstance(result, dict):
        raise ValueError("Expected a decision object")
    if observation.get("decision_layer") in ("repair_allocation", "repair_priority"):
        if set(result) != {"choice"} or not isinstance(result["choice"], str):
            raise ValueError("Expected exactly one strategy choice")
        choice = result["choice"]
        if choice == "defer":
            decision = {"action": "defer_strategy", "target": "", "dialogue": ""}
        else:
            candidate = next(
                (c for c in observation["choices"] if c["id"] == choice), None
            )
            if candidate is None:
                raise ValueError("Unknown strategy choice")
            decision = {
                "action": (
                    "plan_repairs"
                    if observation.get("decision_layer") == "repair_priority"
                    else "dispatch_repair"
                ),
                "target": candidate["target"],
                "dialogue": "",
            }
        return InferenceDecision(decision, getattr(result, "metrics", {}))
    return result
