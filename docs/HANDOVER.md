# Developer handover

Reviewed 22 October 2026. This is a handover for a portfolio prototype, not a
production service. Use the [documentation index](INDEX.md) for all guides and
historical studies. The validated production snapshot is `e1cc748`; release
fixture/evidence fixes are in `28d766a`. Subsequent documentation revisions do not
constitute new model or performance measurements.

## Receive the right source

[PR #4](https://github.com/sunshine-engineer/village-minds/pull/4) is the readiness
review and is stacked on [PR #3](https://github.com/sunshine-engineer/village-minds/pull/3).
At this audit both are open drafts. Do not assume `main` contains their changes.
Review/merge the dependency chain deliberately; no automatic merge is authorized.

For a new checkout:

```bash
git clone https://github.com/sunshine-engineer/village-minds.git
cd village-minds
git switch --track origin/feature/portfolio-readiness
git rev-parse HEAD
```

If using an existing checkout, preserve local changes first. Read the PR's current
head and [Actions checks](https://github.com/sunshine-engineer/village-minds/actions)
rather than treating old red entries as the current result. The final pre-audit
[release CI](https://github.com/sunshine-engineer/village-minds/actions/runs/39779302815)
passed all four Windows/Ubuntu, Python 3.11/3.14 combinations. New commits have their
own checks. See [validation](../VALIDATION.md) for exact evidence boundaries.

## Install and launch

Requirements: Git, Python 3.11+ with venv/pip, and a desktop/OpenGL backend for
Panda3D. Python/Panda3D installation requires package-index access. WSL graphical
play requires working WSLg; native Windows is an alternative. Linux and Windows
need separate virtual environments. Docker is needed only for the model.

From the repository root, Windows PowerShell:

```powershell
py -3 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e .
.\.venv-win\Scripts\python.exe -m village --demo --no-save
```

Linux/WSL Bash:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m village --demo --no-save
```

This first check uses no model and neither loads nor writes a campaign. Expect a
village window, active local role routines and takeover with keys 1–6; **0** releases
control. The [README](../README.md) lists work, dialogue and camera controls.
`python -m village.py` is incorrect; the module is `village`.

For server/client, use two terminals and the same environment/config:

```bash
python -m village.server --demo --save-path saves/handover-server.json
python -m village.client
```

Here and below, `python` means the explicit virtual-environment executable above.
The server defaults to `127.0.0.1:8765`; its console prints the actual save path.
Stop the server with Ctrl+C for graceful save. Closing the client leaves the
server running. The server advances fixed simulation ticks; single-player `--pace`
and client speed/pause/save keys do not control it. Use
`python -m village.client --server http://127.0.0.1:PORT` if the port changes.

For model use, start Docker Desktop/the Docker daemon, then:

```bash
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:1.5b
docker compose exec ollama ollama list
python -m village.probe
```

The first pull downloads model weights and needs disk space/network access. The
probe makes a real local model request; failure does not mean the scripted game
is broken. For compact repair planning, launch server and client with
`--config configs/repair-priority.json`; omit server `--demo`. The server's model
endpoint receives observations/dialogue, so review endpoint configuration before
using personal text. Never store provider credentials in config or committed logs.
Only registered/validated actions can execute; generated Python is not supported.

## Saves, backup, restore and rollback

- Single-player default: `saves/village.json`; server default:
  `saves/server-village.json`. CLI `--save-path` is relative to the terminal;
  explicitly configured relative paths resolve beside the config. Unchanged
  defaults are rooted at the installed package's project directory. For a wheel
  install, supply a known writable explicit save path; do not assume it is the
  current directory. [Path rules](CONFIGURATION.md) explain the other assets/logs.
- Run one writer per save slot. Stop the server/game gracefully before copying
  saves. Copy the complete `saves` directory, including `.bak` and archived
  attempts, to a new dated backup destination using your OS file-copy tool.
  Back up custom JSON, trusted plugin source and asset files alongside it.
- Normal restart resumes the same attempt, including a lost village. `--new-game`
  archives the previous attempt and retains lessons; it does not erase history or
  bypass a configuration fingerprint mismatch. Use a distinct save slot for an
  incompatible map/rules/role/plugin configuration.
- Corrupt primary: the loader tries `.bak`; if both are invalid, preserve both
  and investigate the printed error. To restore a known-good backup, stop all
  writers, archive the current primary/backup, restore the matched saved pair and
  use its compatible source/config/plugins. Never edit a fingerprint to force load.
- To roll back a release, preserve current source/config/saves, select the earlier
  reviewed commit in a separate checkout, and test a copy of its compatible save.
  Do not point old code at the only copy of a newer campaign. Only the documented
  format 1→2 upgrade exists; there is no general downgrade/migration framework.
- Autosave is every ten real seconds by default, plus graceful exit/failure and
  single-player F5. Abrupt termination may lose progress after the last save.
  AI revision/next-think scheduling refreshes on restore; possession is released.
  Physical state/memories persist, but this is not model-weight learning.

`docker compose down` stops the model service while retaining its named volume.
Deleting the volume removes downloaded models. It does not contain campaign saves.
There is no offline progression while the game/server is stopped.

## Verify a contribution

Routine provider-free checks, from the repository root:

```bash
python -m unittest discover -s tests -v
python -m compileall -q village scripts tests
python scripts/check_contributor_contracts.py
python -m village.evaluation --modes scripted --seeds 7 --duration 30
```

Use the [contribution guide](../CONTRIBUTING.md) to select renderer, persistence,
network or model checks for the change. Unit socket tests need loopback access.
Do not run timing acceptance checks concurrently with test suites or inference.

For a distributable release, build into a directory containing exactly one project
wheel, then run the isolated installer check:

```bash
python -m pip wheel --no-deps . --wheel-dir artifacts/release/dist
python scripts/check_wheel_install.py --wheel-directory artifacts/release/dist
python scripts/check_release_soak.py --simulated-seconds 1800 --wall-seconds 300
```

Use a new wheel directory for a new version; the helper rejects multiple project
wheels. Native Windows can add `--render-smoke` to the install helper. Installation
needs dependency-index access or `--wheelhouse PATH` with compatible wheels. The
soak exercises direct authority, not sustained HTTP, human play or inference load.
[Readiness](PORTFOLIO_READINESS.md) has the isolated latency commands and targets.

## Evidence and private/local artifacts

Committed `docs/results/` contains published summaries, audits, CSVs, the contention
trace archive and the installed Windows screenshot. Inspect logs before sharing:
observations can contain dialogue, memories and local paths. Credentials must be
redacted. `saves/`, `artifacts/`, model volumes and venvs are intentionally ignored.
A new developer will not receive them by cloning Git.

The contention audit can be replayed from its committed archive without model calls;
see [the benchmark](CONTENTION_BENCHMARK.md). Older full raw trace folders cited in
historical reports remain local-only; their committed summaries do not recreate
missing traces. If exact older trace reproduction is required, the current maintainer
must provide a reviewed archive plus its matching source/config hashes. Fresh
provider runs have nondeterministic responses/latencies and are new measurements.

## Known limits and receiving-developer acceptance

The default interpolated client measured 239 ms median / 452 ms p95 and misses the
400 ms p95 target. The model matched the scripted planner in the controlled repair
fixture; broad survival benefit, learned cooperation and dialogue quality are not
established. The server supports one loopback client, no LAN/internet deployment,
accounts, TLS, remote asset distribution or multiple players. Plugins are trusted
Python. Autonomous construction/self-evolving terrain has been discussed but is
not implemented. Keep it out of present feature claims.

Human sign-off is still pending. The receiving developer should record:

| Item | Required record | Status |
| --- | --- | --- |
| Ownership | Maintainer/reviewer and issue/PR channel | Assign during handover; GitHub issues/PRs are the project channel |
| Independent setup | Commit, OS/Python, exact commands and result | Pending |
| Normal-window playtest | 30 wall minutes, roles, possession/reconnect, stop/reverse, model outage and restart issues | Pending |
| Demonstration | Three-minute recording matching measured claims | Pending |
| Latency acceptance | Fresh isolated ≥50-sample default-interpolation run meeting predefined target | Not passed |
| Acceptance decision | Reviewer/date and accepted limitations or blocking issues | Pending |

Use [the demo checklist](PORTFOLIO_DEMO.md) for the manual session. This runbook makes
technical handover reviewable; it cannot substitute for the receiving person's sign-off.
