"""Loopback prototype server. Only the simulation thread may mutate World.

File: village/server.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import hmac
import json
import math
import queue
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import fingerprint, get_settings

PROTOCOL = 2


@dataclass
class Envelope:
    """Queued HTTP request and one-result reply channel owned by the simulation boundary.

    Attributes:
        route: Allowed HTTP route.
        token: Current session token or structured task-selection token.
        body: Parsed JSON request payload.
        reply: One-result response queue for the originating HTTP handler.
        cancelled: Stored cancelled value.
    """

    route: str
    token: str | None
    body: dict
    reply: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1))
    cancelled: threading.Event = field(default_factory=threading.Event)


class VillageServer:
    """One active client lease; disconnect/release returns control to local AI."""

    def __init__(self, world, brains, store=None, *, clock=time.monotonic):
        """Initialize VillageServer and its owned state.

        Args:
            world: Authoritative simulation world used by this operation.
            brains: Scheduler responsible for local policies and bounded inference.
            store: Optional SaveStore for server persistence.
            clock: Injectable monotonic clock used for leases and tests.

        Returns:
            None.
        """
        self.world, self.brains, self.store, self.clock = world, brains, store, clock
        self.settings = get_settings()["network"]
        self.inbox = queue.Queue(maxsize=self.settings["queue_capacity"])
        self.server_id = uuid.uuid4().hex
        self.token = None
        self.expires = 0.0
        self.sequence = 0
        self.last_reply = None
        self.motion = (0.0, 0.0)
        self.motion_until = 0.0
        self.frame = 0
        self.next_save = clock() + get_settings()["runtime"]["autosave_seconds"]
        self.failure_saved = False

    def expire(self):
        """Expire stale input and release a session whose heartbeat lease elapsed.

        Returns:
            None; returns expired possession to local autonomy.
        """
        if self.token and self.clock() >= self.expires:
            self.release_session()

    def release_session(self):
        """Release ownership, movement and session sequencing state.

        Returns:
            None; invalidates the current session token.
        """
        self.world.possess(None)
        self.token = None
        self.motion = (0.0, 0.0)
        self.sequence = 0
        self.last_reply = None

    def authorized(self, token):
        """Compare a supplied bearer token against the active session in constant time.

        Args:
            token: Current session token or structured task-selection token.

        Returns:
            Whether the token identifies the active session.
        """
        return (
            isinstance(token, str)
            and self.token is not None
            and hmac.compare_digest(token, self.token)
        )

    def state(self):
        """Capture authoritative world state with protocol, frame and possession metadata.

        Returns:
            Snapshot dictionary; must be called by the simulation owner.
        """
        from .persistence import snapshot

        return dict(
            protocol=PROTOCOL,
            server_id=self.server_id,
            frame=self.frame,
            fingerprint=fingerprint(),
            sequence=self.sequence,
            controlled=self.world.controlled,
            world=snapshot(self.world),
            brains=dict(
                status=self.brains.status,
                local_decisions=self.brains.local_decisions,
                model_decisions=self.brains.model_decisions,
            ),
        )

    def handle(self, route, token, body):
        """Handle one validated route on the simulation thread with sequenced idempotence.

        Args:
            route: Allowed HTTP route.
            token: Current session token or structured task-selection token.
            body: Parsed JSON request payload.

        Returns:
            HTTP status and JSON response pair.
        """
        self.expire()
        if route == "/health":
            return 200, dict(
                protocol=PROTOCOL,
                server_id=self.server_id,
                simulated_seconds=self.world.time,
            )
        if route == "/session":
            if self.token and not self.authorized(token):
                return 409, dict(error="A client already owns the session")
            if self.token is None:
                self.token = secrets.token_urlsafe(32)
                self.sequence = 0
                self.last_reply = None
            self.expires = self.clock() + self.settings["lease_seconds"]
            self.motion = (0.0, 0.0)
            return 200, dict(token=self.token, **self.state())
        if not self.authorized(token):
            return 401, dict(error="Session missing or expired")
        self.expires = self.clock() + self.settings["lease_seconds"]
        if route == "/state":
            return 200, self.state()
        if route == "/disconnect":
            self.release_session()
            return 200, dict(ok=True)
        if route != "/command":
            return 404, dict(error="Unknown route")
        sequence = body.get("sequence")
        if type(sequence) is not int or sequence <= 0:
            return 400, dict(error="Invalid command sequence")
        if sequence == self.sequence:
            return self.last_reply
        if sequence != self.sequence + 1:
            return 409, dict(error="Out-of-order command", sequence=self.sequence)
        command = body.get("command")
        result = self.command(command)
        if self.world.decision_log:
            self.world.decision_log.record(
                "server_command",
                self.world.time,
                source="player",
                sequence=sequence,
                kind=command.get("kind") if isinstance(command, dict) else None,
                status=result[0],
            )
        self.sequence = sequence
        self.last_reply = result
        return result

    def command(self, command):
        """Validate and apply a bounded possession, movement, action or dialogue command.

        Args:
            command: Sequenced player input command dictionary.

        Returns:
            HTTP status and acknowledgement/error dictionary pair.
        """
        if not isinstance(command, dict):
            return 400, dict(error="Expected command object")
        kind = command.get("kind")
        if kind == "takeover":
            index = command.get("index")
            if index is not None and (
                type(index) is not int
                or not 0 <= index < len(self.world.villagers)
                or not self.world.villagers[index].alive
            ):
                return 400, dict(error="Invalid villager")
            self.motion = (0.0, 0.0)
            self.world.possess(index)
            return 200, dict(ok=True, controlled=self.world.controlled)
        if self.world.controlled is None:
            return 409, dict(error="Take over a villager first")
        bot = self.world.villagers[self.world.controlled]
        if not bot.alive or self.world.failed:
            return 409, dict(error="Controlled villager unavailable")
        if kind == "move":
            axes = [command.get("dx"), command.get("dy")]
            if any(
                type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1
                for v in axes
            ):
                return 400, dict(error="Movement axes must be finite and in [-1,1]")
            self.motion = tuple(axes)
            self.motion_until = self.clock() + self.settings["input_seconds"]
            return 200, dict(ok=True)
        if kind == "say":
            text = command.get("text")
            if (
                not isinstance(text, str)
                or not text.strip()
                or len(text) > get_settings()["memory"]["dialogue_chars"]
            ):
                return 400, dict(error="Invalid dialogue length")
            self.world.say(bot, text, source="player")
            return 200, dict(ok=True)
        if kind == "action":
            action, target = command.get("action"), command.get("target", "")
            if (
                not isinstance(action, str)
                or not isinstance(target, str)
                or action not in self.world.available_actions(bot)
            ):
                return 400, dict(error="Action unavailable")
            accepted = self.world.apply(
                bot, dict(action=action, target=target), source="player"
            )
            return (200 if accepted else 409), dict(
                ok=accepted, error="" if accepted else "Action no longer available"
            )
        return 400, dict(error="Unknown command kind")

    def step(self, dt):
        """Process queued commands, advance ordinary physics and reply to post-tick exchanges.

        Args:
            dt: Elapsed simulation seconds; rendering overrides receive real frame seconds.

        Returns:
            None; performs world mutations only on the simulation thread.
        """
        self.expire()
        exchanges = []
        for _ in range(self.settings["max_commands_per_tick"]):
            try:
                envelope = self.inbox.get_nowait()
            except queue.Empty:
                break
            if envelope.cancelled.is_set():
                continue
            if envelope.route == "/exchange":
                result = self.handle("/command", envelope.token, envelope.body)
                if result[0] == 200:
                    exchanges.append((envelope, result[1]))
                else:
                    envelope.reply.put_nowait(result)
            else:
                envelope.reply.put_nowait(
                    self.handle(envelope.route, envelope.token, envelope.body)
                )
        if self.clock() < self.motion_until and self.token:
            self.world.move_player(*self.motion, dt)
        self.world.tick(dt)
        self.brains.tick()
        self.frame += 1
        for envelope, reply in exchanges:
            # Another queued disconnect/takeover may have revoked ownership in
            # this tick. Never send the replacement session's private snapshot.
            if self.authorized(envelope.token):
                envelope.reply.put_nowait((200, dict(**reply, state=self.state())))
            else:
                envelope.reply.put_nowait(
                    (401, dict(error="Session ended during exchange"))
                )
        if self.store and (
            self.clock() >= self.next_save
            or self.world.failed
            and not self.failure_saved
        ):
            self.store.save(self.world)
            self.next_save = (
                self.clock() + get_settings()["runtime"]["autosave_seconds"]
            )
            self.failure_saved = self.world.failed


def make_http_server(runtime, host, port):
    """Create a bounded threaded HTTP listener whose handlers enqueue simulation work.

    Args:
        runtime: Authoritative VillageServer serviced by the HTTP listener.
        host: Validated loopback listener host.
        port: Listener port; zero requests an ephemeral port.

    Returns:
        Configured ThreadingHTTPServer; the caller owns serving and shutdown.
    """
    settings = runtime.settings

    class Handler(BaseHTTPRequestHandler):
        """Bounded HTTP parser that forwards requests to the simulation thread."""

        disable_nagle_algorithm = settings["tcp_no_delay"]

        def setup(self):
            """Configure each connection and bound socket read/write waits.

            Returns:
                None; initializes the standard request-handler streams.
            """
            super().setup()
            self.connection.settimeout(settings["request_seconds"])

        def log_message(self, *args):
            """Suppress standard HTTP request logging to avoid exposing session traffic.

            Args:
                *args: Parsed command-line options for this entry point.

            Returns:
                None; request lines are not printed.
            """
            pass

        def do_GET(self):
            """Dispatch an HTTP GET through the bounded queue boundary.

            Returns:
                None; writes a bounded response.
            """
            self.dispatch(False)

        def do_POST(self):
            """Dispatch an HTTP POST through the bounded queue boundary.

            Returns:
                None; parses bounded JSON before enqueueing.
            """
            self.dispatch(True)

        def dispatch(self, post):
            """Parse allowed routes/body/token and enqueue work without touching the world.

            Args:
                post: Whether this request has a POST JSON body.

            Returns:
                None; sends the queued result or an explicit transport error response.
            """
            try:
                allowed = (
                    ("/session", "/command", "/exchange", "/disconnect")
                    if post
                    else ("/health", "/state")
                )
                if self.path not in allowed:
                    return self.respond(404, dict(error="Unknown route"))
                body = {}
                if post:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= settings["max_body_bytes"]:
                        return self.respond(413, dict(error="Invalid body size"))
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        return self.respond(400, dict(error="Expected JSON object"))
                header = self.headers.get("Authorization", "")
                token = (
                    header.removeprefix("Bearer ")
                    if header.startswith("Bearer ")
                    else None
                )
                envelope = Envelope(self.path, token, body)
                try:
                    runtime.inbox.put_nowait(envelope)
                except queue.Full:
                    return self.respond(503, dict(error="Server command queue full"))
                try:
                    status, result = envelope.reply.get(
                        timeout=settings["request_seconds"]
                    )
                except queue.Empty:
                    envelope.cancelled.set()
                    return self.respond(
                        503, dict(error="Server busy; request outcome may be unknown")
                    )
                self.respond(status, result)
            except (ValueError, TypeError, json.JSONDecodeError):
                self.respond(400, dict(error="Invalid request"))
            except (OSError, TimeoutError):
                return

        def respond(self, status, value):
            """Serialize a JSON response with explicit status and content length.

            Args:
                status: HTTP status code.
                value: Value to validate, convert or publish as described above.

            Returns:
                None; writes to the current HTTP response stream.
            """
            payload = json.dumps(value, allow_nan=False).encode("utf-8")
            if len(payload) > settings["max_state_bytes"]:
                status, payload = 503, b'{"error":"State too large"}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main():
    """Run the authoritative loopback simulation until interruption or the bounded run ends.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    from .cli import attach_profile, prepare

    parser = argparse.ArgumentParser(description=__doc__)
    settings = prepare(parser)
    parser.add_argument(
        "--demo", action="store_true", help="Scripted villagers without inference"
    )
    parser.add_argument(
        "--new-game",
        action="store_true",
        help="Archive the saved attempt and retain failure lessons",
    )
    parser.add_argument("--port", type=int, default=settings["network"]["port"])
    parser.add_argument("--save-path", default=settings["network"]["save_path"])
    parser.add_argument("--decision-log", default=settings["telemetry"]["decision_log"])
    parser.add_argument(
        "--run-seconds", type=float, default=0, help="Optional bounded server smoke run"
    )
    args = parser.parse_args()
    attach_profile(parser, args)
    if (
        not 0 <= args.port <= 65535
        or not math.isfinite(args.run_seconds)
        or args.run_seconds < 0
    ):
        parser.error("Invalid port or run duration")
    from .brains import BrainScheduler
    from .persistence import SaveStore
    from .world import World

    store = SaveStore(args.save_path)
    world = (store.new_attempt() if args.new_game else store.load()) or World()
    world.task_board.mode = settings["coordination"]["mode"]
    if args.decision_log:
        from pathlib import Path

        from .telemetry import DecisionLog

        if Path(args.decision_log).resolve() == store.path:
            parser.error("Decision log must differ from save path")
        world.decision_log = DecisionLog(
            args.decision_log,
            max_bytes=settings["telemetry"]["max_bytes"],
            full_observations=settings["telemetry"]["full_observations"],
        )
    brains = BrainScheduler(
        world, args.url, args.model, demo=args.demo, profile=args.model_profile
    )
    runtime = VillageServer(world, brains, store)
    store.save(world)
    server = make_http_server(runtime, settings["network"]["host"], args.port)
    thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="village-http"
    )
    thread.start()
    print(
        json.dumps(
            dict(
                ready=True,
                host=server.server_address[0],
                port=server.server_address[1],
                save=str(store.path),
                simulated_seconds=world.time,
            )
        ),
        flush=True,
    )
    started = time.monotonic()
    next_tick = started
    try:
        while not args.run_seconds or time.monotonic() - started < args.run_seconds:
            runtime.step(settings["network"]["tick_seconds"])
            next_tick += settings["network"]["tick_seconds"]
            time.sleep(max(0, next_tick - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        runtime.release_session()
        store.save(world)
        server.shutdown()
        server.server_close()
        thread.join(timeout=settings["network"]["request_seconds"])
        if world.decision_log:
            world.decision_log.close()


if __name__ == "__main__":
    main()
