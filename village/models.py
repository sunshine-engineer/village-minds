"""Model transport adapters. Only decision dictionaries cross this boundary."""

import json
import os
from pathlib import Path
from typing import Protocol
import urllib.request
from .config import get_settings
from .decisions import decision_schema

MAX_RESPONSE_BYTES = 1_048_576  # Defensive protocol bound.


class ModelBackend(Protocol):
    def decide(self, profile: dict, observation: dict, timeout: float) -> dict: ...


def messages(observation):
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
        envelope = post_json(
            profile["url"].rstrip("/") + "/api/chat",
            payload,
            timeout,
            profile["api_key_env"],
        )
        return json.loads(envelope["message"]["content"])


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
    return result
