"""Test models.

File: tests/test_models.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import unittest
from unittest.mock import patch

from village.models import BACKENDS, register_backend, request_decision, resolve_profile


class Response:
    """Context-managed mock HTTP response with bounded read behavior."""

    def __init__(self, envelope):
        """Initialize Response and its owned state.

        Args:
            envelope: Structured mock HTTP response returned by the context-manager fixture.

        Returns:
            None.
        """
        self.envelope = envelope

    def __enter__(self):
        """Return the mock HTTP response when entering the request context.

        Returns:
            This mock response instance.
        """
        return self

    def __exit__(self, *args):
        """Complete the mock response context without suppressing exceptions.

        Args:
            *args: Parsed command-line options for this entry point.

        Returns:
            None; performs the side effects described above.
        """
        pass

    def read(self, limit):
        """Return mock response bytes subject to the requested response-read limit.

        Args:
            limit: Maximum number of response bytes requested by the transport.

        Returns:
            Mock response bytes.
        """
        return json.dumps(self.envelope).encode()


class ModelTests(unittest.TestCase):
    """Regression cases for models."""

    def test_openai_compatible_transport_contract(self):
        """Verify openai compatible transport contract.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        profile = resolve_profile()
        profile["backend"] = "openai_compatible"
        profile["api_key_env"] = "TEST_VILLAGE_KEY"
        content = json.dumps({"action": "move", "target": "farm", "dialogue": ""})
        with (
            patch.dict("os.environ", {"TEST_VILLAGE_KEY": "temporary-test-key"}),
            patch(
                "urllib.request.urlopen",
                return_value=Response({"choices": [{"message": {"content": content}}]}),
            ) as send,
        ):
            result = request_decision(
                "http://localhost:8000/v1",
                "local-model",
                {"name": "Mira", "personality": "patient"},
                profile=profile,
            )
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(result["action"], "move")
        self.assertEqual(request.full_url, "http://localhost:8000/v1/chat/completions")
        self.assertEqual(
            request.get_header("Authorization"), "Bearer temporary-test-key"
        )
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["max_tokens"], profile["max_tokens"])
        self.assertEqual(send.call_args.kwargs["timeout"], profile["timeout"])

    def test_custom_backend_registry_and_type_boundary(self):
        """Verify custom backend registry and type boundary.

        Returns:
            None; unittest assertions report a regression on failure.
        """

        class Backend:
            """Deterministic backend fixture exercising the structured decision contract."""

            def decide(self, profile, observation, timeout):
                """Supply a controlled backend response for the enclosing validation case.

                Args:
                    profile: Resolved model profile containing backend and generation options.
                    observation: Request-time context containing legal choices and relevant world state.
                    timeout: Maximum request wall time in seconds.

                Returns:
                    Configured deterministic decision or deliberate invalid response.
                """
                return ["invalid"]

        register_backend("test_invalid", Backend)
        try:
            profile = resolve_profile()
            profile["backend"] = "test_invalid"
            with self.assertRaisesRegex(ValueError, "decision object"):
                request_decision("http://localhost", "model", {}, profile=profile)
            with self.assertRaises(ValueError):
                register_backend("ollama", Backend)
        finally:
            BACKENDS.pop("test_invalid")

    def test_missing_api_key_does_not_make_request(self):
        """Verify missing api key does not make request.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        profile = resolve_profile()
        profile["api_key_env"] = "NONEXISTENT_TEST_VILLAGE_KEY"
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("urllib.request.urlopen") as send,
        ):
            with self.assertRaisesRegex(ValueError, "Missing API key"):
                request_decision(
                    "http://localhost",
                    "model",
                    {"name": "Mira", "personality": "patient"},
                    profile=profile,
                )
            send.assert_not_called()

    def test_oversize_response_is_rejected(self):
        """Verify oversize response is rejected.

        Returns:
            None; unittest assertions report a regression on failure.
        """

        class Large(Response):
            """Oversized mock response used to enforce the transport response limit."""

            def read(self, limit):
                """Return mock response bytes subject to the requested response-read limit.

                Args:
                    limit: Maximum number of response bytes requested by the transport.

                Returns:
                    Mock response bytes.
                """
                return b" " * limit

        with patch("urllib.request.urlopen", return_value=Large({})):
            with self.assertRaisesRegex(ValueError, "size limit"):
                request_decision(
                    "http://localhost",
                    "model",
                    {"name": "Mira", "personality": "patient"},
                )
