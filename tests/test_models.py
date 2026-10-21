import json
import unittest
from unittest.mock import patch
from village.models import request_decision, resolve_profile, register_backend, BACKENDS


class Response:
    def __init__(self, envelope):
        self.envelope = envelope

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return json.dumps(self.envelope).encode()


class ModelTests(unittest.TestCase):
    def test_openai_compatible_transport_contract(self):
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
        class Backend:
            def decide(self, profile, observation, timeout):
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
        class Large(Response):
            def read(self, limit):
                return b" " * limit

        with patch("urllib.request.urlopen", return_value=Large({})):
            with self.assertRaisesRegex(ValueError, "size limit"):
                request_decision(
                    "http://localhost",
                    "model",
                    {"name": "Mira", "personality": "patient"},
                )
