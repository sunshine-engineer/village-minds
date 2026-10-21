# Configuration

Defaults live in [`village/data/default.json`](../village/data/default.json).
Supply a small JSON override file rather than editing Python. Configuration loads
once at startup, before world or rendering imports. Restart to apply changes.
There is no live reload or support for multiple configurations in one process.

## Run an example

Windows PowerShell:

```powershell
.\.venv-win\Scripts\python.exe -m village --config examples/custom.json --demo --no-save
```

Linux / WSL:

```bash
.venv/bin/python -m village --config examples/custom.json --demo --no-save
```

The example changes crop timing, the first wave, window size, the harvest key and
simulation pace, and enables the optional `encourage` plugin. Remove `--no-save`
to use the example's separate save slot. It does not overwrite the default slot.

## Settings reference

| Section | Controls |
| --- | --- |
| `runtime` | Simulation pace, seed, save path, autosave interval, step cap |
| `world` | Bounds, sight/hearing, navigation clearance, walls/openings, locations, buildings, crops, work offsets, villager roster/personality/color |
| `rules` | Health, yields, energy costs, food/wood costs, ranges, cooldowns, regeneration, crop timing, hunger, monster damage/speed, wave timing and limits |
| `roles` | Per-role harvest, wood, repair and combat bonuses; rally capability |
| `policy` | Needs thresholds, rest targets, deposit/wood targets and default soldier gates |
| `ai` | Profiles, per-villager profile assignments, system prompt path, objective, social message templates, strategic action allowlist, local routine/social/patrol/model timings |
| `memory` | Recent memories, retained lessons/events/failures, dialogue length |
| `display` | Window, camera, lighting, animation, chat focus timing, feed and roster limits |
| `controls` | Movement, takeover, camera, action, chat, pause, save and quit bindings |
| `assets` | Path to the prefab/style/UI catalog |
| `plugins` | Explicit trusted Python modules to import |
| `extension_settings` | Plugin-owned JSON settings; each plugin validates its own schema |

The asset catalog controls geometry, colors, labels, HUD layout and visual parts.
The model system prompt is a separate text asset; `{{dialogue_chars}}` expands to
the configured dialogue limit. Social message templates accept `{other}`, `{gate}`
and `{supplies}`. Gameplay tuning does not require
changing methods in `World` or `VillageGame`.

Container image, port bindings and server parallelism are deployment configuration
in [`compose.yaml`](../compose.yaml). If you change the host port, update the model
profile URL to match. Docker model installation remains an explicit setup step.

## Override and path rules

Objects merge recursively; arrays replace the whole array. A partial roster array
therefore replaces the roster, not individual villagers. Existing named profiles
can be overridden partially; a new profile must provide all profile fields (see
[`examples/models.json`](../examples/models.json)). Unknown setting names, wrong
types, duplicate keys for controls, and invalid ranges fail before game startup.
Duplicate JSON properties and nonfinite numbers are rejected as well.

A relative `runtime.save_path`, `ai.system_prompt`, or `assets.manifest` explicitly
provided in an override resolves relative to that override file. Unchanged bundled
assets resolve inside the installed package. The unchanged save slot remains
checkout-relative in an editable install. Paths inside an asset manifest resolve
relative to the manifest, including external model files.

`--config` takes precedence over `VILLAGE_CONFIG`. For model selection, precedence
is CLI `--url`/`--model`, then `OLLAMA_URL`/`VILLAGE_MODEL`, then the selected profile.
`--profile` overrides `ai.default_profile`. Explicit per-villager assignments select
their own profiles and do not inherit CLI URL/model overrides. `--pace` and
`--save-path` override their configuration values.

## World and save compatibility

New snapshots use format 2 and store a fingerprint of `world`, `rules`, `roles`,
`memory`, `plugins` and `extension_settings`. Changes in these sections require a
separate save slot. A mismatch fails explicitly without resetting or overwriting
the old campaign. `--new-game` retains lessons and therefore also requires compatible
configuration. To start an independent customized campaign, set a new save path.

Version 1 saves load only under the default world/rules/memory/plugin settings.
They are written as version 2 at the next save. Visuals, controls, policy thresholds,
AI profiles and runtime pace are excluded from the fingerprint. Plugin code changes
are not fingerprinted: plugins must validate/migrate their own saved state.

## Boundaries

Configuration changes supported parameters; it does not replace algorithms. The
navigation grid, action protocol, JSON schema shape, engine workarounds, defensive
response/save-size limits, and test fixtures remain implementation constants.
Custom rules and algorithms belong in plugins or the owning Python module.

Map changes must preserve usable routes. Buildings define navigation obstacles;
visual-only instances do not create collisions. Keep the four named cardinal gates
and required service locations. Wall segment placement follows configured wall and
opening coordinates; custom decorative geometry must be updated in the asset catalog.
The HUD has a finite size: larger rosters may require UI layout changes.

Only load configuration, asset manifests and plugins from trusted contributors.
Plugin module imports execute Python; model responses cannot select modules or code.
