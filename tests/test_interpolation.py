"""Deterministic presentation tests use synthetic packets, never physics prediction.

File: tests/test_interpolation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import math
import unittest
from copy import deepcopy

from village.config import fingerprint, get_settings, load_config
from village.interpolation import SnapshotInterpolator


def packet(
    t,
    x,
    *,
    frame=None,
    epoch=1,
    server="server-a",
    controlled=0,
    health=100,
    monster=True,
):
    """Construct a confirmed snapshot with explicit pose, generation and epoch metadata.

    Args:
        t: Controlled simulation/receive timestamp in seconds.
        x: Planar x coordinate.
        frame: Monotonically increasing fixture snapshot number.
        epoch: Connection generation used to reject stale snapshot history.
        server: Stable fixture server identity.
        controlled: Possessed actor index, or None for observer state.
        health: Fixture actor health used to model alive/dead transitions.
        monster: Target living monster.

    Returns:
        Confirmed fixture snapshot dictionary.
    """
    return dict(
        server_id=server,
        frame=round(t * 100) if frame is None else frame,
        controlled=controlled,
        _client_epoch=epoch,
        _client_received_at=t,
        world=dict(
            world=dict(
                time=t,
                villagers=[dict(name="Mira", position=[x, 0], health=health)],
                monsters=[dict(id="m1", position=[x, 5], health=60)] if monster else [],
            )
        ),
    )


class InterpolationTests(unittest.TestCase):
    """Regression cases for interpolation."""

    def setUp(self):
        """Create isolated state for each regression case.

        Returns:
            None.
        """
        self.settings = deepcopy(get_settings()["network"]["interpolation"])
        self.settings["catch_up_rate"] = 1.0
        self.smoother = SnapshotInterpolator(self.settings)

    def push(self, t, x, **kwargs):
        """Push one controlled snapshot into the presentation buffer.

        Args:
            t: Controlled simulation/receive timestamp in seconds.
            x: Planar x coordinate.
            **kwargs: Keyword options forwarded to the owning implementation.

        Returns:
            None; performs the side effects described above.
        """
        self.assertTrue(self.smoother.push(packet(t, x, **kwargs)))

    def test_intermediate_positions_and_animation_time_without_packet_mutation(self):
        """Verify intermediate positions and animation time without packet mutation.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        source = packet(0, 0)
        saved = deepcopy(source)
        self.smoother.push(source)
        self.push(0.2, 1)
        poses, animation = self.smoother.sample(0.3)
        self.assertAlmostEqual(poses["villager", "Mira"][0], 0.5)
        self.assertAlmostEqual(poses["monster", "m1"][0], 0.5)
        self.assertAlmostEqual(animation, 0.1)
        self.assertEqual(source, saved)

    def test_render_updates_between_packets_and_holds_without_extrapolation(self):
        """Verify render updates between packets and holds without extrapolation.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.push(0, 0)
        self.push(0.2, 1)
        xs = []
        for i in range(13):
            poses, _ = self.smoother.sample(0.2 + i / 60)
            xs.append(poses["villager", "Mira"][0])
        self.assertTrue(all(a <= b for a, b in zip(xs, xs[1:])))
        self.assertGreater(len(set(xs)), 10)
        self.assertAlmostEqual(xs[-1], 1.0)
        self.assertEqual(self.smoother.sample(0.5)[0]["villager", "Mira"], (1.0, 0.0))

    def test_jitter_and_lost_packet_do_not_jump_to_latest_position(self):
        """Verify jitter and lost packet do not jump to latest position.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.smoother = SnapshotInterpolator(dict(self.settings, catch_up_rate=1.1))
        self.push(0, 0)
        self.push(0.2, 1)
        self.smoother.sample(0.2)
        for i in range(1, 25):
            self.smoother.sample(0.2 + i / 60)
        before = self.smoother.sample(0.6)[0]["villager", "Mira"][0]
        self.push(0.61, 3.05)
        after = self.smoother.sample(0.62)[0]["villager", "Mira"][0]
        self.assertGreater(after, before)
        self.assertLess(after - before, 0.2)
        self.assertAlmostEqual(after - before, 0.11)
        self.assertLess(after, 3.05)

    def test_teleport_is_immediate_and_new_monsters_do_not_fly_from_origin(self):
        """Verify teleport is immediate and new monsters do not fly from origin.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.push(0, 0, monster=False)
        self.push(0.2, 20)
        poses, _ = self.smoother.sample(0.25)
        self.assertEqual(poses["villager", "Mira"], (20, 0))
        self.assertEqual(poses["monster", "m1"], (20, 5))

    def test_respawn_and_reused_ids_do_not_interpolate_old_lives(self):
        """Verify respawn and reused ids do not interpolate old lives.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.push(0, 0)
        self.push(0.1, 1, health=0, monster=False)
        self.push(0.2, 2, health=100)
        poses, _ = self.smoother.sample(0.25)
        self.assertEqual(poses["villager", "Mira"], (2, 0))
        self.assertEqual(poses["monster", "m1"], (2, 5))

    def test_despawn_is_immediate(self):
        """Verify despawn is immediate.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.push(0, 0)
        self.push(0.2, 1, monster=False)
        self.assertNotIn(("monster", "m1"), self.smoother.sample(0.25)[0])

    def test_reconnect_server_restart_and_possession_reset_history(self):
        """Verify reconnect server restart and possession reset history.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        for change in [
            dict(epoch=2),
            dict(epoch=2, server="server-b"),
            dict(controlled=1),
        ]:
            with self.subTest(change=change):
                smooth = SnapshotInterpolator(self.settings)
                smooth.push(packet(0, 0))
                smooth.push(packet(0.1, 1))
                smooth.push(packet(0.2, 2, **change))
                self.assertEqual(smooth.sample(0.2)[0]["villager", "Mira"], (2, 0))
                self.assertEqual(len(smooth.samples), 1)

    def test_stale_frames_or_epochs_cannot_replace_newer_state(self):
        """Verify stale frames or epochs cannot replace newer state.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.push(0.1, 1, epoch=2, frame=2)
        self.assertFalse(self.smoother.push(packet(0.2, 0, epoch=1, frame=5)))
        self.assertFalse(self.smoother.push(packet(0.2, 0, epoch=2, frame=1)))
        self.assertEqual(self.smoother.sample(0.2)[0]["villager", "Mira"], (1, 0))

    def test_long_gap_or_paused_renderer_snaps_without_replaying_history(self):
        """Verify long gap or paused renderer snaps without replaying history.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.push(0, 0)
        self.push(0.2, 1)
        self.smoother.sample(0.3)
        self.assertEqual(self.smoother.sample(2)[0]["villager", "Mira"], (1, 0))
        self.push(3, 2)
        self.assertEqual(self.smoother.sample(3)[0]["villager", "Mira"], (2, 0))

    def test_buffer_is_bounded_and_disabled_mode_matches_snapshot(self):
        """Verify buffer is bounded and disabled mode matches snapshot.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        self.settings.update(buffer_size=3, enabled=False)
        smooth = SnapshotInterpolator(self.settings)
        for i in range(20):
            smooth.push(packet(i * 0.1, i * 0.1))
        self.assertEqual(len(smooth.samples), 3)
        self.assertAlmostEqual(smooth.sample(2)[0]["villager", "Mira"][0], 1.9)

    def test_straight_line_is_smoother_than_snapshot_snapping_at_multiple_fps(self):
        """Verify straight line is smoother than snapshot snapping at multiple fps.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        for fps in (30, 60, 144):
            smooth = SnapshotInterpolator(self.settings)
            displayed = []
            snapped = []
            next_packet = 0
            for i in range(fps * 2 + 1):
                now = i / fps
                while next_packet * 0.2 <= now + 1e-9:
                    t = next_packet * 0.2
                    smooth.push(packet(t, t * 5))
                    next_packet += 1
                displayed.append(smooth.sample(now)[0]["villager", "Mira"][0])
                snapped.append((next_packet - 1) * 0.2 * 5)
            # Ignore startup buffering; compare actual frame displacement, not acceptance counts.
            start = math.ceil(0.4 * fps)

            def jump(positions):
                """Measure the largest frame displacement after fixture warm-up.

                Args:
                    positions: Consecutive displayed or direct-snapshot x positions.

                Returns:
                    Maximum absolute post-warm-up displacement.
                """
                return max(
                    abs(b - a)
                    for a, b in zip(positions[start:], positions[start + 1 :])
                )

            self.assertLess(jump(displayed), jump(snapped) / 4)
            self.assertTrue(
                all(a <= b + 1e-9 for a, b in zip(displayed, displayed[1:]))
            )

    def test_settings_do_not_change_gameplay_fingerprint(self):
        """Verify settings do not change gameplay fingerprint.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        old = load_config()
        changed = deepcopy(old)
        changed["network"]["interpolation"]["delay_seconds"] = 0.3
        self.assertEqual(fingerprint(old), fingerprint(changed))
