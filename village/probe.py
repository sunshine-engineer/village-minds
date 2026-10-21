"""Verify a real local model response without starting graphics."""
import argparse
import json
import os
from .brains import request_decision
from .simulation import World


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=os.getenv('OLLAMA_URL', 'http://localhost:11434'))
    parser.add_argument('--model', default=os.getenv('VILLAGE_MODEL', 'qwen2.5:1.5b'))
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    world = World()
    bot = world.villagers[0]
    world.say(world.villagers[1], 'Mira, will you help me gather at the farm?')
    try:
        decision = request_decision(args.url,args.model,world.observe(bot),timeout=args.timeout)
    except Exception as exc:
        parser.exit(1, f'Model request failed: {type(exc).__name__}: {exc}\n')
    print(json.dumps(decision, indent=2))
    if not world.apply(bot,decision):
        parser.exit(1, 'Response received, but the simulation rejected the action.\n')
    print(f'PASS: real model response accepted; {bot.name} is {bot.action}.')


if __name__ == '__main__':
    main()
