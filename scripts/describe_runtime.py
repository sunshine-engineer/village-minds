"""Record non-secret host/model metadata for local benchmark reproduction."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/portfolio/runtime.json")
    )
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(args.url + "/api/ps", timeout=5) as response:
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
