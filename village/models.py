"""Model transport adapters. Only decision dictionaries cross this boundary."""

import json
import os
import time
from pathlib import Path
from typing import Protocol
import urllib.request
from .config import get_settings
from .decisions import decision_schema

MAX_RESPONSE_BYTES = 1_048_576  # Defensive protocol bound.


class InferenceDecision(dict):
    def __init__(self, decision, metrics=None):
        super().__init__(decision)
        self.metrics = metrics or {}


class ModelBackend(Protocol):
    def decide(self, profile: dict, observation: dict, timeout: float) -> dict: ...


def messages(observation):
    if observation.get("decision_layer") == "repair_allocation":
        prompt = Path(get_settings()["ai"]["repair_strategy"]["prompt"]).read_text(
            encoding="utf-8"
        )
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
    def decide(self, profile, observation, timeout):
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
    profile = (profile or resolve_profile()).copy()
    profile.update(url=url, model=model)
    if profile["backend"] not in BACKENDS:
        raise ValueError(f'Unknown model backend: {profile["backend"]}')
    backend = BACKENDS[profile["backend"]]()
    result = backend.decide(
        profile, observation, profile["timeout"] if timeout is None else timeout
    )
    if not isinstance(result, dict):
        raise ValueError("Expected a decision object")
    if observation.get("decision_layer") == "repair_allocation":
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
                "action": "dispatch_repair",
                "target": candidate["target"],
                "dialogue": "",
            }
        return InferenceDecision(decision, getattr(result, "metrics", {}))
    return result
