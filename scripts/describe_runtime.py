"""Record non-secret host/model metadata for local benchmark reproduction.

File: scripts/describe_runtime.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import importlib.metadata
import json
import math
import os
import platform
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    """Run the describe runtime diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    from village.cli import attach_profile, prepare

    prepare(parser)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/portfolio/runtime.json")
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="Metadata HTTP deadline in seconds"
    )
    args = parser.parse_args()
    attach_profile(parser, args)
    if args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("--timeout must be positive and finite")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(
        args.url.rstrip("/") + "/api/ps", timeout=args.timeout
    ) as response:
        payload = json.load(response)
    report = dict(
        platform=platform.platform(),
        processor=platform.processor(),
        logical_cpus=os.cpu_count(),
        python=sys.version,
        panda3d=importlib.metadata.version("panda3d"),
        loaded_models=[
            {
                k: model.get(k)
                for k in ("name", "size", "size_vram", "context_length", "details")
            }
            for model in payload.get("models", [])
        ],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
