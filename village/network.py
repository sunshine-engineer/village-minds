"""Bounded HTTP transport and one background client worker; no rendering imports."""

import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .config import get_settings, fingerprint
from .server import PROTOCOL


class RemoteError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class RemoteSession:
    def __init__(self, url, *, autostart=True):
        parsed = urllib.parse.urlparse(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Prototype client requires a loopback HTTP server URL")
        self.url = url.rstrip("/")
        self.settings = get_settings()["network"]
        self.token = None
        self.sequence = 0
        self.connection_epoch = 0
        self.frames = queue.Queue(maxsize=1)
        self.commands = queue.Queue(maxsize=self.settings["queue_capacity"])
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.motion = (0.0, 0.0)
        self.status = "CONNECTING"
        self.connected = False
        self.thread = None
        self.latest = self.connect()
        if autostart:
            self.thread = threading.Thread(
                target=self._worker, daemon=True, name="village-client"
            )
            self.thread.start()

    @property
    def motion(self):
        return self._motion

    @motion.setter
    def motion(self, value):
        changed = getattr(self, "_motion", None) != value
        self._motion = value
        if changed and self.settings["wake_on_input"]:
            self.wake.set()

    def request(self, route, body=None):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = json.dumps(body, allow_nan=False).encode() if body is not None else None
        request = urllib.request.Request(self.url + route, data=data, headers=headers)
        # Ignore machine proxy settings for a local game connection.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            response = opener.open(request, timeout=self.settings["request_seconds"])
        except urllib.error.HTTPError as exc:
            with exc:
                value = json.loads(exc.read(self.settings["max_body_bytes"]))
            raise RemoteError(
                exc.code, value.get("error", "Remote request failed")
            ) from exc
        with response:
            raw = response.read(self.settings["max_state_bytes"] + 1)
            if len(raw) > self.settings["max_state_bytes"]:
                raise ValueError("Server state exceeds configured size limit")
            return json.loads(raw)

    def connect(self):
        try:
            state = self.request("/session", {})
        except RemoteError as exc:
            if exc.status != 401:
                raise
            self.token = None
            state = self.request("/session", {})
        self.token = state["token"]
        if (
            state.get("protocol") != PROTOCOL
            or state.get("fingerprint") != fingerprint()
        ):
            try:
                self.request("/disconnect", {})
            finally:
                self.token = None
            raise ValueError(
                "Server protocol or world settings differ; use the same --config"
            )
        self.sequence = state["sequence"]
        self.connected = True
        self.status = "CONNECTED"
        self.connection_epoch += 1
        return self.stamp(state)

    def stamp(self, state):
        return dict(
            state,
            _client_received_at=time.monotonic(),
            _client_epoch=self.connection_epoch,
        )

    def submit(self, command):
        if not self.connected:
            return False
        try:
            self.commands.put_nowait(command)
            if self.settings["wake_on_input"]:
                self.wake.set()
            return True
        except queue.Full:
            self.status = "Command queue full"
            return False

    def command(self, command):
        self.sequence += 1
        route = (
            "/exchange"
            if command.get("kind") == "move" and self.settings["exchange_motion"]
            else "/command"
        )
        return self.request(route, dict(sequence=self.sequence, command=command))

    def poll(self):
        try:
            state = self.frames.get_nowait()
        except queue.Empty:
            return None
        return state

    def publish(self, state):
        try:
            self.frames.get_nowait()
        except queue.Empty:
            pass
        state = self.stamp(state)
        self.latest = state
        self.frames.put_nowait(state)

    def _worker(self):
        reconnect = False
        while not self.stop.is_set():
            self.wake.clear()
            try:
                if reconnect:
                    self.publish(self.connect())
                    reconnect = False
                for _ in range(self.settings["max_commands_per_tick"]):
                    if self.stop.is_set():
                        break
                    try:
                        command = self.commands.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        self.command(command)
                    except RemoteError as exc:
                        if exc.status in (400, 409):
                            self.status = str(exc)
                        else:
                            raise
                if self.stop.is_set():
                    break
                reply = None
                if self.latest.get("controlled") is not None:
                    reply = self.command(
                        dict(kind="move", dx=self.motion[0], dy=self.motion[1])
                    )
                state = (
                    reply["state"]
                    if reply is not None and "state" in reply
                    else self.request("/state")
                )
                self.publish(state)
                if self.status.startswith(("DISCONNECTED", "CONNECTING")):
                    self.status = "CONNECTED"
                self.wake.wait(self.settings["poll_seconds"])
            except (OSError, ValueError, RemoteError, KeyError) as exc:
                self.connected = False
                self.status = "DISCONNECTED: " + str(exc)[:100]
                self.motion = (0.0, 0.0)
                while True:
                    try:
                        self.commands.get_nowait()
                    except queue.Empty:
                        break
                if isinstance(exc, RemoteError) and exc.status == 401:
                    self.token = None
                reconnect = True
                self.stop.wait(self.settings["reconnect_seconds"])
        try:
            if self.token:
                self.request("/disconnect", {})
        except (OSError, ValueError, RemoteError):
            pass
        self.connected = False

    def close(self):
        self.motion = (0.0, 0.0)
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(
                timeout=2 * self.settings["request_seconds"]
                + self.settings["poll_seconds"]
            )
        elif self.token:
            self.request("/disconnect", {})
            self.connected = False
