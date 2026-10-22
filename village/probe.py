"""Verify a real local model response without starting graphics."""

import argparse
import json
from .cli import prepare, attach_profile
from .models import request_decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    prepare(parser)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args()
    attach_profile(parser, args)
    from .world import World

    world = World()
    bot = world.villagers[0]
    world.say(world.villagers[1], "Mira, will you help me gather at the farm?")
    try:
        decision = request_decision(
            args.url,
            args.model,
            world.observe(bot),
            timeout=args.timeout,
            profile=args.model_profile,
        )
    except Exception as exc:
        parser.exit(1, f"Model request failed: {type(exc).__name__}: {exc}\n")
    print(json.dumps(decision, indent=2))
    if not world.apply(bot, decision):
        parser.exit(1, "Response received, but the simulation rejected the action.\n")
    print(f"PASS: real model response accepted; {bot.name} is {bot.action}.")


if __name__ == "__main__":
    main()
