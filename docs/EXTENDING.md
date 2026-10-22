# Adding assets, gameplay and models

Choose the smallest extension point for the change. Simulation modules never import
Panda3D or contact a model. Scene code never decides survival rules. Model adapters
return dictionaries; the world checks whether an action is currently allowed.

## Add or replace a visual asset

1. Copy [`catalog.json`](../village/data/assets/catalog.json) to a folder for your assets.
2. Add a named prefab containing named `parts`. Each part supplies `position`,
   `scale` and RGB `color`. Optional `hpr` rotates it.
3. Add an entry to `instances`, with `prefab` and either `position` (XYZ) or
   `location` (a configured map location).
4. Set `assets.manifest` in your override to that catalog path.
5. Run `--smoke-test` with that configuration and inspect the generated screenshot.

Example prefab and instance (merge these into your copied catalog):

```json
{
  "prefabs": {
    "hay_bale": {
      "parts": [
        {"name":"bale", "position":[0,0,0.5], "scale":[1,0.6,0.5], "color":[0.8,0.7,0.2]}
      ]
    }
  },
  "instances": [{"prefab":"hay_bale", "position":[-18,14,0]}]
}
```

This snippet is not a complete replacement manifest: keep the required core prefabs,
styles and UI entries. To use a Panda3D-compatible model, add `"model":"models/bale.bam"`
to a part. The path is manifest-relative. Scaling, tinting and rotation still apply.
Built-in procedural cubes remain available as the fallback when no model is specified.
A missing or unloadable model is an error, not a silent substitution.

`role_prefabs` maps a role to accessories. The base `villager` prefab needs a named
`body` and may contain `leg_*` parts for walking animation. `building` needs `roof`,
`core` needs `core`, and wall prefabs need `wall`. Crop `stalk_*` parts grow and hide
with the simulation. Preserve these names when replacing dynamic visuals. Complex
skeletal animation needs a new scene implementation; static model loading does not
provide an animation controller. Visual-only props do not affect navigation.

`style` controls scene labels, dialogue cards and state colors. `ui` describes HUD
widgets and their positions, colors and sizes. Controls help is generated from the
actual key bindings rather than duplicated text.

## Add a gameplay action

See the runnable [`encourage` plugin](../village/plugins/encourage.py) and its
[`example config`](../examples/custom.json). A plugin exports `register(registry)`.
Enable its importable module name through `plugins` and put its parameters under
`extension_settings`. The package need not be in this repository; an installed
Python package is also importable.

```python
def register(registry):
    registry.register_action(
        "my_action", available=available, execute=execute)
```

- `available(world, bot) -> list[str]` returns current legal targets. Use `[""]`
  for an available action without a target, or `[]` when unavailable. Keep it pure:
  perception, model schema construction and validation may call it repeatedly.
- `execute(world, bot, decision) -> bool` performs the action after world validation.
  It must enforce its own costs/cooldowns and return whether it succeeded.
- Built-in names cannot be replaced. Dead actors and failed worlds cannot act.
- To expose it to the strategic model, add its name to `ai.strategic_actions`.
  Otherwise the background model cannot choose it. Add a prompt description so the
  model understands it; a schema name alone does not teach its effect.
- Add a binding under `controls.actions` if the player should use it. The game
  chooses the first available target for custom actions; richer targeting needs UI work.

Plugins are trusted application code, not sandboxed code. Model output can only
choose registered action names and legal targets.

## Add a role, policy or ongoing system

Add the role's bonuses in `roles`, a villager profile in `world.cast`, a takeover key,
and optionally an accessory prefab. New roles use the default general survival policy
until a plugin registers `registry.register_policy(role, policy)`.

A policy has signature `policy(world, bot) -> decision | None`. Keep it free of
state mutations: observations may also call it for recommended tasks. Returning `None`
keeps the current work order eligible for the normal idle/patrol behavior. Reuse
`village.policies.default_policy` when adding one priority instead of duplicating
all needs logic. Soldiers are assigned by their index within the role, not a name.

Use `registry.register_system(name, tick)` for a timed mechanic.
`tick(world, dt)` runs after built-in survival updates and before movement, once per
simulation step, and stops running when the world fails. Keep it short: it runs on
the game thread. No HTTP requests, rendering calls or blocking I/O belong here.

## Persist plugin state

Call `registry.register_state(name, create=factory, restore=validator)`.
`create()` returns fresh JSON-compatible state; `restore(saved)` validates and returns
restored state. Access it through `world.extension_state[name]`. Registration names
must match the save, and non-JSON state cannot be saved. The example persists actor
cooldowns and rejects unknown identities, negative times and nonfinite numbers.

Do not add arbitrary attributes to entities and expect them to persist. Entity fields
and contribution counters have a fixed save schema. Extend that schema with migration
tests when a mechanic needs deeper entity changes. Plugin code changes require explicit
state migration in its validator; the config fingerprint cannot detect source changes.

## Add another model or provider

For another Ollama model, add or override a profile with `backend: "ollama"` and its
installed model tag. Docker manages the server/model weights; profiles select the
endpoint and inference options. This branch does not download new models automatically.

Run a named profile using `--profile NAME`. Assign independent profiles to villagers
with `ai.villager_profiles` (see [`examples/models.json`](../examples/models.json)).
One worker still serializes inference requests across all profiles to limit load;
local role routines and movement remain concurrent. Switching a model on a shared
Ollama server can add model-loading latency.

Two transports are provided:

| Backend | URL convention | Output contract |
| --- | --- | --- |
| `ollama` | Server root, e.g. `http://localhost:11434` | `/api/chat` with `format` JSON schema |
| `openai_compatible` | API base, e.g. `http://localhost:8000/v1` | `/chat/completions` with `response_format.json_schema` |

The second transport targets local servers implementing that contract. Support for
strict schemas, the schema's `oneOf`, and generation fields varies by server/model.
Its mocked contract tests do not prove compatibility with every server; run
`python -m village.probe --config YOUR_CONFIG --profile NAME` against your actual
server. `context_size` and `keep_alive` are Ollama-only options. Keep API keys in the
environment variable named by `api_key_env`, never inside the config.

For a different protocol, implement `decide(profile, observation, timeout) -> dict`
and register a zero-argument factory with `registry.register_backend(name, factory)`
inside a trusted plugin. Re-registering the same factory is idempotent across worlds;
replacing an existing backend with another factory is rejected. Enforce response limits
and timeouts, return only a decision object, and let the world validate it. The shared
`village.decisions.decision_schema` is available for structured-output APIs.

Test unavailable targets, insufficient resources, takeover during a pending response,
save/reload and model failure. Record what was actually exercised in validation docs.


## Executable contributor contract

[`examples/contributor.json`](../examples/contributor.json) enables the packaged
`encourage` action and a minimal custom backend. The backend is a deterministic
adapter example, **not a model or AI-quality result**. It returns a validated rest
intent or defers a planning request and never calls a provider.

```bash
python scripts/check_contributor_contracts.py
```

The check exercises action cost/effect, cooldown rejection, backend registration,
world validation and cooldown persistence after save/reload. It uses temporary
saves. No core simulation or renderer change is needed to enable the examples.
The clean-wheel release check executes this same contract from outside the source
checkout and asserts that the imported package lives in the new virtual environment.
The built-in `plan_repairs` name is reserved against plugin replacement.
