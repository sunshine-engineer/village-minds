"""Advance fast simulation using bounded substeps instead of dropping elapsed time.

File: village/timing.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""


class SimulationClock:
    """Fixed-substep accumulator with a per-frame work cap and retained backlog."""

    def __init__(self, step_seconds, max_steps_per_frame):
        """Initialize SimulationClock and its owned state.

        Args:
            step_seconds: Maximum fixed integration step in seconds.
            max_steps_per_frame: Per-frame integration work cap.

        Returns:
            None.
        """
        self.step_seconds = step_seconds
        self.max_steps_per_frame = max_steps_per_frame
        self.pending = 0.0

    def advance(self, world, brains, simulated_seconds):
        """Advance capped fixed substeps while retaining excess simulated time as backlog.

        Args:
            world: Authoritative simulation world used by this operation.
            brains: Scheduler responsible for local policies and bounded inference.
            simulated_seconds: Requested accumulated simulation time.

        Returns:
            Number of substeps executed; no work is performed for a failed world.
        """
        self.pending += max(0, simulated_seconds)
        steps = 0
        while (
            self.pending > 1e-9
            and steps < self.max_steps_per_frame
            and not world.failed
        ):
            dt = min(self.pending, self.step_seconds)
            world.tick(dt)
            brains.tick()
            self.pending = max(0, self.pending - dt)
            steps += 1
        if world.failed:
            self.pending = 0
        return steps
