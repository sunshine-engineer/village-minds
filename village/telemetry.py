"""Optional JSONL decision traces with bounded disk usage and aggregate counters.

File: village/telemetry.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import math
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def json_safe(value):
    """Convert observations to bounded-shape JSON values and label unsupported/nonfinite scalars.

    Args:
        value: Value to validate, convert or publish as described above.

    Returns:
        JSON-compatible value.
    """
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "<nonfinite>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return f"<{type(value).__name__}>"


def state_summary(world, bot=None):
    """Capture compact village and optional actor state for decision attribution.

    Args:
        world: Authoritative simulation world used by this operation.
        bot: Villager whose current state or work is being considered.

    Returns:
        Independent summary dictionary.
    """
    result = {
        "village_health": world.village_health,
        "store": world.store.copy(),
        "gates": world.gates.copy(),
        "wave": world.wave,
    }
    if bot is not None:
        result["actor"] = {
            "position": list(bot.position),
            "health": bot.health,
            "energy": bot.energy,
            "hunger": bot.hunger,
            "food": bot.supplies,
            "wood": bot.wood,
            "action": bot.action,
        }
    return result


class DecisionLog:
    """One owner on the simulation thread; no writes from inference workers."""

    def __init__(self, path, *, max_bytes, full_observations=False, run_id=None):
        """Initialize DecisionLog and its owned state.

        Args:
            path: Input/output filesystem path for the described resource.
            max_bytes: Maximum allowed trace file size in bytes.
            full_observations: Whether to include complete request context in trace records.
            run_id: Optional stable identifier for this trace session.

        Returns:
            None.
        """
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex
        self.full_observations = full_observations
        self.max_bytes = max_bytes
        self.bytes_written = self.path.stat().st_size if self.path.exists() else 0
        self.sequence = 0
        self.dropped = 0
        self.counts = Counter()
        self.started = time.monotonic()
        self.handle = self.path.open("a", encoding="utf-8", buffering=1, newline="\n")
        self.record(
            "session_start", 0, started_at=datetime.now(timezone.utc).isoformat()
        )

    def record(self, event, sim_time, **data):
        """Count an event and append JSONL only while the configured byte budget permits.

        Args:
            event: Structured event name.
            sim_time: Simulation timestamp attached to the event.
            **data: Structured payload or versioned save data for the described operation.

        Returns:
            None; counts dropped records when the byte cap is reached.
        """
        self.sequence += 1
        source, outcome = data.get("source", "system"), data.get("outcome", "")
        self.counts[(event, source, outcome)] += 1
        row = {
            "schema_version": 1,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "event": event,
            "sim_time": round(sim_time, 6),
            "wall_seconds": round(time.monotonic() - self.started, 6),
            **data,
        }
        line = (
            json.dumps(
                json_safe(row),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        )
        size = len(line.encode("utf-8"))
        if self.bytes_written + size > self.max_bytes:
            self.dropped += 1
            return
        self.handle.write(line)
        self.bytes_written += size

    def count(self, event, source, outcome):
        """Read the aggregate count for one event/source/outcome combination.

        Args:
            event: Structured event name.
            source: Provenance label identifying the caller or decision layer.
            outcome: Recorded acceptance/error category.

        Returns:
            Integer event count.
        """
        return self.counts[(event, source, outcome)]

    def close(self):
        """Close the trace handle after the simulation owner finishes using it.

        Returns:
            None.
        """
        if not self.handle.closed:
            self.handle.close()
