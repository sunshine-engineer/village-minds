"""Authoritative simulation, bounded commands, disconnect and real HTTP checks."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from village.config import get_settings
from village.world import World
from village.brains import BrainScheduler
from village.server import VillageServer, make_http_server
from village.network import RemoteSession, RemoteError


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.world = World(seed=301)
        self.brains = BrainScheduler(self.world, "", "", demo=True)
        self.now = 10.0
        self.server = VillageServer(self.world, self.brains, clock=lambda: self.now)
        self.server.settings = deepcopy(self.server.settings)
        self.token = self.server.handle("/session", None, {})[1]["token"]

    def command(self, kind, **fields):
        return self.server.handle(
            "/command",
            self.token,
            dict(sequence=self.server.sequence + 1, command=dict(kind=kind, **fields)),
        )

    def test_exclusive_session_and_forged_token(self):
        self.assertEqual(self.server.handle("/session", None, {})[0], 409)
        self.assertEqual(
            self.server.handle(
                "/command",
                "wrong",
                dict(sequence=1, command=dict(kind="takeover", index=0)),
            )[0],
            401,
        )
        self.assertIsNone(self.world.controlled)
        self.assertEqual(self.command("takeover", index=0)[0], 200)
        self.assertEqual(self.world.controlled, 0)

    def test_duplicate_command_is_idempotent(self):
        self.command("takeover", index=0)
        body = dict(sequence=2, command=dict(kind="say", text="Hello"))
        a = self.server.handle("/command", self.token, body)
        events = list(self.world.events)
        b = self.server.handle("/command", self.token, body)
        self.assertEqual(a, b)
        self.assertEqual(events, list(self.world.events))
        self.assertEqual(
            self.server.handle(
                "/command",
                self.token,
                dict(sequence=4, command=dict(kind="say", text="Skipped")),
            )[0],
            409,
        )

    def test_movement_uses_server_time_and_expires(self):
        self.command("takeover", index=0)
        self.assertEqual(self.command("move", dx=float("nan"), dy=0)[0], 400)
        before = self.world.villagers[0].position
        self.assertEqual(self.command("move", dx=1, dy=0, dt=100000)[0], 200)
        self.server.step(0.05)
        after = self.world.villagers[0].position
        from village.navigation import distance

        self.assertLessEqual(
            distance(before, after),
            get_settings()["rules"]["player_speed"] * 0.05 + 1e-6,
        )
        self.now += self.server.settings["input_seconds"] + 0.01
        self.server.step(0.05)
        self.assertEqual(self.world.villagers[0].position, after)

    def test_disconnect_and_lease_expiry_restore_autonomy(self):
        self.command("takeover", index=0)
        self.now += self.server.settings["lease_seconds"] + 0.01
        self.server.step(0.05)
        self.assertIsNone(self.world.controlled)
        self.assertIsNone(self.server.token)
        self.assertEqual(self.server.handle("/state", self.token, {})[0], 401)
        self.assertGreater(self.brains.local_decisions, 0)

    def test_invalid_action_and_possession_cannot_mutate_world(self):
        self.assertEqual(self.command("takeover", index=True)[0], 400)
        self.assertEqual(self.command("action", action="harvest", target="")[0], 409)
        self.command("takeover", index=0)
        before = self.world.store.copy()
        self.assertEqual(
            self.command("action", action="invent_wood", target="")[0], 400
        )
        self.assertEqual(self.world.store, before)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        world = World(seed=301)
        self.runtime = VillageServer(world, BrainScheduler(world, "", "", demo=True))
        self.http = make_http_server(self.runtime, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()

        def simulate():
            while not self.stop.is_set():
                self.runtime.step(0.02)
                self.stop.wait(0.02)

        self.sim = threading.Thread(target=simulate, daemon=True)
        self.sim.start()

    def tearDown(self):
        self.stop.set()
        self.sim.join(timeout=3)
        self.http.shutdown()
        self.http.server_close()
        self.worker.join(timeout=3)

    def test_http_takeover_reconnect_and_continuous_world(self):
        session = RemoteSession(self.url, autostart=False)
        try:
            with self.assertRaises(RemoteError):
                RemoteSession(self.url, autostart=False)
            session.command(dict(kind="takeover", index=1))
            before = session.request("/state")
            self.assertEqual(before["controlled"], 1)
            # Resume with the existing token; this must not reset the village.
            resumed = session.connect()
            self.assertEqual(resumed["server_id"], before["server_id"])
            session.close()
            time.sleep(0.12)
            session = RemoteSession(self.url, autostart=False)
            after = session.request("/state")
            self.assertGreater(
                after["world"]["world"]["time"], before["world"]["world"]["time"]
            )
            self.assertIsNone(after["controlled"])
        finally:
            session.close()

    def test_background_client_receives_snapshots_and_releases_on_close(self):
        session = RemoteSession(self.url)
        try:
            self.assertTrue(session.submit(dict(kind="takeover", index=0)))
            deadline = time.monotonic() + 3
            state = None
            while time.monotonic() < deadline:
                state = session.poll() or state
                if state and state["controlled"] == 0:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(state)
            self.assertEqual(state["controlled"], 0)
        finally:
            session.close()
        other = RemoteSession(self.url, autostart=False)
        try:
            self.assertIsNone(other.latest["controlled"])
        finally:
            other.close()

    def test_incompatible_client_is_rejected_and_releases_session(self):
        from unittest.mock import patch

        with patch("village.network.fingerprint", return_value="wrong"):
            with self.assertRaises(ValueError):
                RemoteSession(self.url, autostart=False)
        session = RemoteSession(self.url, autostart=False)
        session.close()

    def test_malformed_and_oversized_requests_do_not_claim_session(self):
        import urllib.request, urllib.error

        for body in [
            b"[]",
            b"{oops",
            b"x" * (get_settings()["network"]["max_body_bytes"] + 1),
        ]:
            request = urllib.request.Request(self.url + "/session", data=body)
            with self.assertRaises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(request, timeout=2)
            self.assertIn(exc.exception.code, (400, 413))
            exc.exception.close()
        session = RemoteSession(self.url, autostart=False)
        session.close()


class ServerProcessTests(unittest.TestCase):
    def test_server_restart_resumes_saved_time_and_memories(self):
        from village.persistence import SaveStore

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "server.json"
            world = World(seed=301)
            world.villagers[0].lessons.append("Protect the village")
            SaveStore(path).save(world)
            cmd = [
                sys.executable,
                "-m",
                "village.server",
                "--demo",
                "--port",
                "0",
                "--save-path",
                str(path),
                "--run-seconds",
                ".3",
            ]
            first = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_save = SaveStore(path).load()
            second = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(second.returncode, 0, second.stderr)
            final = SaveStore(path).load()
            self.assertGreater(final.time, first_save.time)
            self.assertIn("Protect the village", final.villagers[0].lessons)
            self.assertIsNone(final.controlled)

    def test_new_attempt_archives_existing_server_save(self):
        from village.persistence import SaveStore

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "server.json"
            world = World(seed=301)
            world.campaign["lessons"] = {
                world.villagers[0].name: ["Share food during danger"]
            }
            SaveStore(path).save(world)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "village.server",
                    "--demo",
                    "--new-game",
                    "--port",
                    "0",
                    "--save-path",
                    str(path),
                    "--run-seconds",
                    ".1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            recovered = SaveStore(path).load()
            self.assertEqual(recovered.campaign["attempt"], 2)
            self.assertIn("Share food during danger", recovered.villagers[0].lessons)
            self.assertTrue(list(path.parent.glob("server.*Z.json")))
