"""Install a wheel in a new venv and exercise it outside the source checkout.

Requires a local wheel; dependencies come from --wheelhouse or pip's configured
index. This is an automated clean-install check, not another developer's review.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-directory", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/portfolio/clean-install.json")
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--render-smoke", action="store_true")
    args = parser.parse_args()
    wheels = list(args.wheel_directory.resolve().glob("village_minds-*.whl"))
    if len(wheels) != 1:
        parser.error("Expected exactly one village_minds wheel")
    root = Path(__file__).resolve().parents[1]
    started = time.monotonic()
    env = os.environ.copy()
    for name in ("PYTHONPATH", "VILLAGE_CONFIG"):
        env.pop(name, None)
    checks = []

    def execute(cmd, cwd):
        result = subprocess.run(
            [str(p) for p in cmd],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        if result.returncode:
            raise RuntimeError(
                f"Clean install command failed: {cmd[1:3]}\n{result.stderr[-2000:]}"
            )
        return result

    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        venv = work / "venv"
        demo = work / "demo"
        demo.mkdir()
        execute([sys.executable, "-m", "venv", venv], work)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [python, "-m", "pip", "install"]
        if args.wheelhouse:
            install += ["--no-index", "--find-links", args.wheelhouse.resolve()]
        install.append(wheels[0])
        execute(install, work)
        checks.append("fresh venv installs built wheel and pinned dependency")
        (demo / "scripts").mkdir()
        (demo / "examples").mkdir()
        for source, target in [
            (
                "scripts/check_contributor_contracts.py",
                "scripts/check_contributor_contracts.py",
            ),
            ("examples/contributor.json", "examples/contributor.json"),
        ]:
            shutil.copyfile(root / source, demo / target)
        contract = demo / "contract.json"
        execute(
            [
                python,
                demo / "scripts/check_contributor_contracts.py",
                "--output",
                contract,
            ],
            demo,
        )
        result = json.loads(contract.read_text())
        assert Path(result["package"]).is_relative_to(venv), result
        checks += result["checked"]
        execute([python, "-m", "village.client", "--help"], demo)
        checks.append("client entry point loads packaged startup configuration")
        save = demo / "world.json"
        execute(
            [
                python,
                "-m",
                "village.server",
                "--demo",
                "--port",
                "0",
                "--run-seconds",
                "0.3",
                "--save-path",
                save,
            ],
            demo,
        )
        data = json.loads(save.read_text())
        assert data["world"]["time"] > 0
        checks.append("installed authoritative server starts, advances and saves")
        if args.render_smoke:
            execute(
                [python, "-m", "village", "--demo", "--smoke-test", "--no-save"], demo
            )
            image = demo / "artifacts" / "village-smoke.png"
            assert image.exists()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image, args.output.with_suffix(".png"))
            checks.append("installed single-player offscreen render smoke")
        version = execute(
            [
                python,
                "-c",
                'import importlib.metadata,json; print(json.dumps({n:importlib.metadata.version(n) for n in ["village-minds","panda3d"]}))',
            ],
            demo,
        )
        report = dict(
            passed=True,
            independent_human_setup=False,
            platform=sys.platform,
            python=sys.version,
            versions=json.loads(version.stdout),
            checks=checks,
            seconds=time.monotonic() - started,
            wheel=wheels[0].name,
            package_from_isolated_venv=True,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
