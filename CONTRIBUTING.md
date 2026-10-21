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
`python scripts/check_restart.py`. These produce ignored artifacts.

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
