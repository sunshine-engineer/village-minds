"""Optional JSONL decision traces with bounded disk usage and aggregate counters."""

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import uuid


def json_safe(value):
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
        return self.counts[(event, source, outcome)]

    def close(self):
        if not self.handle.closed:
            self.handle.close()
