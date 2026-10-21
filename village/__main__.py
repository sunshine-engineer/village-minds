import argparse
import os
from .persistence import DEFAULT_SAVE_PATH


def main():
    parser = argparse.ArgumentParser(description="Village Minds — local AI village")
    parser.add_argument("--demo", action="store_true", help="Use scripted villagers without a model")
    parser.add_argument("--model", default=os.getenv("VILLAGE_MODEL", "qwen2.5:1.5b"))
    parser.add_argument("--url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--smoke-test", action="store_true", help="Render offscreen, exercise takeover, save a screenshot and exit")
    parser.add_argument("--save-path", default=str(DEFAULT_SAVE_PATH), help="Persistent village and failure history JSON")
    parser.add_argument("--new-game", action="store_true", help="Archive current run and begin a fresh attempt retaining failure lessons")
    parser.add_argument("--no-save", action="store_true", help="Temporary session; neither read nor write saves")
    parser.add_argument("--pace", type=float, default=.5, help="Simulation speed relative to real time (default .5)")
    args = parser.parse_args()
    if not 0.1 <= args.pace <= 2:
        parser.error("--pace must be between 0.1 and 2")
    if args.new_game and (args.no_save or args.smoke_test):
        parser.error("--new-game requires saving and cannot be combined with --smoke-test")
    from .game import VillageGame
    try:
        game = VillageGame(args)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Startup failed: {exc}\n")
    print("Village Minds ready. Select the game window; 1-6 take over, WASD move, Enter speaks.", flush=True)
    try:
        game.run()
    finally:
        game.save_world()


if __name__ == "__main__":
    main()
