"""Bounded presentation-only interpolation of confirmed network positions.

File: village/interpolation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    """Confirmed position and entity-generation identity used for safe interpolation.

    Attributes:
        position: Planar world coordinates in simulation units.
        generation: Entity incarnation counter preventing interpolation across respawn.
        alive: Whether the confirmed entity had positive health.
    """

    position: tuple
    generation: int
    alive: bool


@dataclass(frozen=True)
class Sample:
    """Received snapshot time and confirmed poses for one presentation history entry.

    Attributes:
        received_at: Local monotonic snapshot receive timestamp.
        simulated_at: Authoritative simulation timestamp for this sample.
        poses: Stable entity keys mapped to confirmed Pose values.
    """

    received_at: float
    simulated_at: float
    poses: dict


class SnapshotInterpolator:
    """A delayed playhead holds on underrun; it never predicts beyond a packet."""

    def __init__(self, settings):
        """Initialize SnapshotInterpolator and its owned state.

        Args:
            settings: Validated configuration for this component.

        Returns:
            None.
        """
        self.settings = dict(settings)
        self.samples = deque(maxlen=settings["buffer_size"])
        self.identity = None
        self.epoch = -1
        self.frame = -1
        self.controlled = None
        self.cursor = None
        self.sampled_at = None
        self.generation_counter = 0

    def push(self, packet):
        """Validate epoch/frame order and add confirmed poses to bounded presentation history.

        Args:
            packet: Authoritative snapshot with local receive-time/epoch metadata.

        Returns:
            Whether the packet was accepted.
        """
        epoch = packet["_client_epoch"]
        identity, frame = packet["server_id"], packet["frame"]
        if epoch < self.epoch or (
            epoch == self.epoch and identity == self.identity and frame < self.frame
        ):
            return False
        world = packet["world"]["world"]
        received = packet["_client_received_at"]
        previous = self.samples[-1] if self.samples else None
        reset = (
            previous is None
            or epoch != self.epoch
            or identity != self.identity
            or packet["controlled"] != self.controlled
        )
        if previous and not reset:
            if received < previous.received_at:
                return False
            reset = (
                received - previous.received_at > self.settings["max_gap_seconds"]
                or world["time"] < previous.simulated_at
            )
        if reset:
            self.samples.clear()
            self.cursor = self.sampled_at = None
            previous = None
        poses = {}
        for kind, rows, identity_key in [
            ("villager", world["villagers"], "name"),
            ("monster", world["monsters"], "id"),
        ]:
            for entity in rows:
                key = (kind, entity[identity_key])
                point, alive = tuple(entity["position"]), entity["health"] > 0
                old = previous.poses.get(key) if previous else None
                generation = old.generation if old else None
                if (
                    old is None
                    or old.alive != alive
                    or math.dist(old.position, point) > self.settings["snap_distance"]
                ):
                    self.generation_counter += 1
                    generation = self.generation_counter
                poses[key] = Pose(point, generation, alive)
        self.samples.append(Sample(received, world["time"], poses))
        self.identity, self.epoch, self.frame, self.controlled = (
            identity,
            epoch,
            frame,
            packet["controlled"],
        )
        return True

    def sample(self, now):
        """Sample confirmed poses at a delayed playhead without extrapolating.

        Args:
            now: Local monotonic render timestamp.

        Returns:
            Pair of position mapping and interpolated simulation time.
        """
        if not self.samples:
            return {}, 0.0
        oldest, newest = self.samples[0], self.samples[-1]
        if not self.settings["enabled"]:
            return {
                key: pose.position for key, pose in newest.poses.items()
            }, newest.simulated_at
        if (
            self.sampled_at is not None
            and now - self.sampled_at > self.settings["max_gap_seconds"]
        ):
            # Resuming a paused renderer must not replay a stale path.
            self.samples.clear()
            self.samples.append(newest)
            oldest = newest
            self.cursor = None
        desired = now - self.settings["delay_seconds"]
        if self.cursor is None:
            self.cursor = max(oldest.received_at, min(desired, newest.received_at))
        else:
            dt = max(0.0, now - self.sampled_at)
            rate = (
                self.settings["catch_up_rate"]
                if desired - self.cursor > self.settings["catch_up_threshold_seconds"]
                else 1.0
            )
            advance = max(
                0.0,
                min(dt * rate, desired - self.cursor, newest.received_at - self.cursor),
            )
            self.cursor = max(oldest.received_at, self.cursor + advance)
        self.sampled_at = now
        left = right = newest
        if self.cursor <= oldest.received_at:
            left = right = oldest
        else:
            for a, b in zip(self.samples, list(self.samples)[1:]):
                if a.received_at <= self.cursor <= b.received_at:
                    left, right = a, b
                    break
        span = right.received_at - left.received_at
        alpha = (self.cursor - left.received_at) / span if span > 0 else 1.0
        poses = {}
        for key, latest in newest.poses.items():
            a, b = left.poses.get(key), right.poses.get(key)
            if (
                a is None
                or b is None
                or a.generation != latest.generation
                or b.generation != latest.generation
            ):
                poses[key] = latest.position
            else:
                poses[key] = tuple(
                    x + (y - x) * alpha for x, y in zip(a.position, b.position)
                )
        return (
            poses,
            left.simulated_at + (right.simulated_at - left.simulated_at) * alpha,
        )
