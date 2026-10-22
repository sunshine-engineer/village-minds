# Contributing

Start with [README.md](README.md) for native Windows or Linux setup. Keep local
virtual environments, saves, generated screenshots and model files out of commits.

## Development checks

After installing the project in your environment, run:

```bash
python -m unittest discover -s tests -v
python -m compileall -q village scripts tests
```

Use your environment's explicit Python path if needed. The unit suite does not
require Docker or a display. CI runs it on Windows and Ubuntu with Python 3.11
and 3.14. A CI configuration is not a claim that a remote run has passed.

For rendering changes, run `python -m village --smoke-test` with a graphics backend.
For autonomy changes, run `python scripts/check_autonomy.py --headless` and, with
Ollama ready, add `--wait-for-model`. For persistence, run
`python scripts/check_restart.py`. For asset/plugin changes, run
`python scripts/check_extensions.py`. These produce ignored artifacts.

Run `python -m village.probe` to check the real model API separately. The X11
keyboard checker `scripts/check_window.py` is Linux-specific. Use temporary save
slots or `--no-save` during manual experiments to protect your campaign.

## Changes and reports

Explain the behavior being fixed, steps to reproduce it and checks actually run.
Keep simulation rules independent of rendering and validate model output in Python.
Add meaningful regression tests for changes to behavior, persistence or ownership.
Do not label scripted routines as model decisions or prompt memories as training.

Open an issue with OS, Python/Panda3D versions, launch command, relevant traceback
and whether `--demo --no-save` reproduces the issue. Remove private dialogue or
paths before sharing logs. Never submit credentials or personal save files.

## Choose an extension point

Read [architecture](docs/ARCHITECTURE.md), [configuration](docs/CONFIGURATION.md), and
[extension recipes](docs/EXTENDING.md) before adding features. Put tunable values in
the appropriate configuration section and visual content in a prefab catalog. Keep
new model transports separate from scheduling and simulation. The optional
`village.plugins.encourage` example demonstrates an action with persistent state.

When changing configuration defaults, verify save compatibility. New settings need
validation and a documented default. Do not loosen a save validator just to make a
new test pass. Tests that load a different startup config must use a fresh process.

For evaluation or timing changes, run the unit suite, a scripted headless scenario and
`python scripts/check_speed.py` with a graphics backend. The [evaluation guide](docs/EVALUATION.md)
explains the checkpoint policy, budget semantics, metrics and logs. AI integration
checks require a real model; mocked response tests alone do not verify server behavior.

For server/client changes, keep world mutations and persistence on the server's
simulation thread. HTTP handlers enqueue bounded requests; the rendering client
sends commands and consumes snapshots. Extend the protocol with explicit validation
and lifecycle tests rather than letting clients upload world state. Run
`python -m unittest discover -s tests` in an environment that permits loopback
sockets. The [server/client guide](docs/SERVER_CLIENT.md) describes the current
single-session boundary. Preserve frozen experiment data and use separate named
plans/seeds for new policy experiments; see [evaluation gaps](docs/EVALUATION_GAPS.md).
