"""Shared startup-only config and model options for game and API probe.

File: village/cli.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import os

from .config import configure
from .models import resolve_profile


def prepare(parser):
    """Load startup configuration before simulation imports and register shared CLI options.

    Args:
        parser: ArgumentParser receiving shared flags or reporting invalid CLI values.

    Returns:
        Validated startup settings; malformed configuration exits through argparse.
    """
    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument("--config", default=os.getenv("VILLAGE_CONFIG"))
    initial, _ = preliminary.parse_known_args()
    try:
        settings = configure(initial.config)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(f"Invalid configuration: {exc}")
    parser.add_argument(
        "--config",
        default=initial.config,
        help="JSON override file; also VILLAGE_CONFIG",
    )
    parser.add_argument(
        "--profile",
        default=settings["ai"]["default_profile"],
        help="Named AI profile from config",
    )
    parser.add_argument(
        "--model", default=os.getenv("VILLAGE_MODEL"), help="Override profile model tag"
    )
    parser.add_argument(
        "--url", default=os.getenv("OLLAMA_URL"), help="Override profile API base URL"
    )
    return settings


def attach_profile(parser, args):
    """Resolve model/profile overrides and attach them to parsed CLI arguments.

    Args:
        parser: ArgumentParser receiving shared flags or reporting invalid CLI values.
        args: Parsed command-line options for this entry point.

    Returns:
        None; updates args and reports invalid profiles through argparse.
    """
    try:
        args.model_profile = resolve_profile(
            args.profile, url=args.url, model=args.model
        )
    except ValueError as exc:
        parser.error(str(exc))
    args.url = args.model_profile["url"]
    args.model = args.model_profile["model"]
