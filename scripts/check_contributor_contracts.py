"""Verify packaged action/backend extension contracts without a model or renderer.

File: scripts/check_contributor_contracts.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    """Run the check contributor contracts diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("examples/contributor.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/contributor-contracts.json")
    )
    args = parser.parse_args()
    from village.config import configure

    configure(args.config)
    import village
    from village.models import request_decision, resolve_profile
    from village.persistence import SaveStore
    from village.world import World

    w = World(seed=301)
    giver, receiver = w.villagers[:2]
    giver.position = (0, 0)
    receiver.position = (1, 0)
    receiver.energy = 50
    before = receiver.energy
    intent = dict(action="encourage", target=receiver.name)
    assert w.apply(giver, intent)
    assert receiver.energy > before
    assert not w.apply(giver, intent), "Plugin cooldown was ignored"
    profile = resolve_profile()
    decision = request_decision(
        profile["url"], profile["model"], w.observe(receiver), profile=profile
    )
    assert decision["action"] == "rest"
    assert w.apply(receiver, decision)
    w.tick(0.1)
    with tempfile.TemporaryDirectory() as temp:
        store = SaveStore(Path(temp) / "world.json")
        store.save(w)
        restored = store.load()
        assert restored.extension_state == w.extension_state
        assert not restored.apply(restored.villagers[0], intent)
    report = dict(
        package=str(Path(village.__file__).resolve()),
        provider_calls=0,
        checked=[
            "custom action costs/effect",
            "plugin cooldown rejection",
            "custom backend intent",
            "world validation",
            "persistent plugin cooldown",
        ],
        backend="offline_example",
        ai_quality_evidence=False,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
