"""Advance fast simulation using bounded substeps instead of dropping elapsed time."""


class SimulationClock:
    def __init__(self, step_seconds, max_steps_per_frame):
        self.step_seconds = step_seconds
        self.max_steps_per_frame = max_steps_per_frame
        self.pending = 0.0

    def advance(self, world, brains, simulated_seconds):
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
