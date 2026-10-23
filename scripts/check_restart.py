"""Verify actual CLI startup/normal exit saving across two temporary game processes.

File: scripts/check_restart.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHILD = """
import sys
from village.game import VillageGame
from village.__main__ import main
mode,path=sys.argv[1:]
run=VillageGame.run
def checked_run(self):
    if mode=='seed':
        self.world.store['food']=37
        self.world.village_health=162
        self.world.say(self.world.villagers[0],'We must share food next time too.')
    else:
        assert self.world.store['food']==37, 'Shared inventory reset on launch'
        assert self.world.village_health==162, 'Village health reset on launch'
        assert any('share food next time' in line for line in self.world.villagers[0].memory), 'Dialogue memory lost'
    def quit_normally(task):
        self.userExit()
        return task.done
    self.taskMgr.doMethodLater(.3,quit_normally,'normal-exit-check')
    run(self)
VillageGame.run=checked_run
sys.argv=['village','--demo','--save-path',path]
main()
"""


def main():
    """Run the check restart diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as directory:
        path = Path(directory) / "restart.json"
        for mode in ("seed", "resume"):
            result = subprocess.run(
                [sys.executable, "-c", CHILD, mode, str(path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
            )
            print(result.stdout, flush=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            assert path.exists(), "Normal exit did not save"
        report = {
            "passed": [
                "CLI normal exit saves changed state",
                "next CLI launch restores shared food, village health, and dialogue memory",
            ],
            "method": "two actual game processes with scheduled normal userExit; isolated temporary save",
        }
        (output / "restart-check.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
