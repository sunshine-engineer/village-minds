"""Fast-forward authority/persistence soak; not a wall-time or human playtest."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulated-seconds", type=float, default=1800.0)
    parser.add_argument("--step", type=float, default=0.05)
    parser.add_argument("--wall-seconds", type=float, default=180.0)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/portfolio/authority-soak.json")
    )
    args = parser.parse_args()
    from village.config import get_settings

    if (
        not 0 < args.step <= get_settings()["runtime"]["max_step_seconds"]
        or args.simulated_seconds < 20
    ):
        parser.error("Invalid soak duration/step")
    from village.world import World
    from village.brains import BrainScheduler
    from village.server import VillageServer
    from village.persistence import SaveStore, snapshot

    elapsed = [0.0]
    switches = 0
    reconnects = 0
    restores = 0
    attempts = 1
    started = time.monotonic()

    def runtime(world, store):
        return VillageServer(
            world,
            BrainScheduler(world, "", "", demo=True),
            store,
            clock=lambda: elapsed[0],
        )

    with tempfile.TemporaryDirectory() as temp:
        store = SaveStore(Path(temp) / "world.json")
        server = runtime(World(seed=301), store)
        token = server.handle("/session", None, {})[1]["token"]
        while elapsed[0] < args.simulated_seconds - 1e-9:
            if time.monotonic() - started > args.wall_seconds:
                raise RuntimeError("Soak wall budget exceeded")
            if switches < 10 and elapsed[0] >= switches:
                status, _ = server.handle(
                    "/command",
                    token,
                    dict(
                        sequence=server.sequence + 1,
                        command=dict(
                            kind="takeover",
                            index=switches % len(server.world.villagers),
                        ),
                    ),
                )
                assert status == 200
                switches += 1
            if reconnects < 3 and elapsed[0] >= 5 * (reconnects + 1):
                assert server.handle("/disconnect", token, {})[0] == 200
                token = server.handle("/session", None, {})[1]["token"]
                reconnects += 1
            assert server.handle("/state", token, {})[0] == 200
            dt = min(args.step, args.simulated_seconds - elapsed[0])
            server.step(dt)
            elapsed[0] += dt
            if elapsed[0] >= (restores + 1) * 300:
                before = snapshot(server.world)
                store.save(server.world)
                loaded = store.load()
                after = snapshot(loaded)
                # Loading intentionally invalidates in-flight model work and
                # schedules fresh thinking; possession never survives a session.
                for bot in before["world"]["villagers"]:
                    bot["revision"] += 1
                    bot["next_think"] = before["world"]["time"]
                    if bot["action"] == "player":
                        bot["action"] = "idle"
                for key in ("time", "villagers", "gates", "store", "village_health"):
                    assert before["world"][key] == after["world"][key], key
                assert before["campaign"] == after["campaign"]
                restores += 1
                server = runtime(loaded, store)
                token = server.handle("/session", None, {})[1]["token"]
            if server.world.failed:
                store.save(server.world)
                previous = server.world.campaign
                new = store.new_attempt()
                assert new.campaign["attempt"] == previous["attempt"] + 1
                assert new.campaign["lessons"] == previous["lessons"]
                attempts += 1
                server = runtime(new, store)
                token = server.handle("/session", None, {})[1]["token"]
        store.save(server.world)
        assert switches == 10 and reconnects == 3
        report = dict(
            passed=True,
            simulated_seconds=elapsed[0],
            wall_seconds=time.monotonic() - started,
            method="direct authority API, fixed simulation steps, temporary JSON saves",
            http_transport_test=False,
            human_playtest=False,
            possessions=switches,
            reconnects=reconnects,
            save_restore_checks=restores,
            attempts=attempts,
            campaign_failures=len(server.world.campaign["failures"]),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
