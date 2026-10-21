import argparse
from .cli import prepare, attach_profile


def main():
    parser = argparse.ArgumentParser(description="Village Minds — local AI village")
    settings = prepare(parser)
    parser.add_argument(
        "--demo", action="store_true", help="Use scripted villagers without a model"
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Render offscreen, exercise takeover, save a screenshot and exit",
    )
    parser.add_argument(
        "--save-path",
        default=settings["runtime"]["save_path"],
        help="Persistent village and failure history JSON",
    )
    parser.add_argument(
        "--new-game",
        action="store_true",
        help="Archive current run and begin a fresh attempt retaining failure lessons",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Temporary session; neither read nor write saves",
    )
    parser.add_argument(
        "--pace",
        type=float,
        default=settings["runtime"]["pace"],
        help="Simulation speed relative to real time",
    )
    args = parser.parse_args()
    attach_profile(parser, args)
    if not 0.1 <= args.pace <= 2:
        parser.error("--pace must be between 0.1 and 2")
    if args.new_game and (args.no_save or args.smoke_test):
        parser.error(
            "--new-game requires saving and cannot be combined with --smoke-test"
        )
    try:
        from .game import VillageGame

        game = VillageGame(args)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f"Startup failed: {exc}\n")
    print(
        "Village Minds ready. Select the game window; use the on-screen controls to take over, walk and speak.",
        flush=True,
    )
    try:
        game.run()
    finally:
        game.save_world()


if __name__ == "__main__":
    main()
