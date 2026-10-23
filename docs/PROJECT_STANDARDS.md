<!--
File: docs/PROJECT_STANDARDS.md
Purpose: Maintained-file documentation, formatting, configuration and organization conventions.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Project consistency conventions

These conventions apply to maintained source. Historical experiment evidence,
model prompts and legal text have preservation rules below. The maintainer label
`sunshine-engineer` is the user's requested maintenance default, not a claim of
original authorship or exclusive ownership. Preserve existing license attribution.

## File types and headers

| File type | Convention |
| --- | --- |
| Python | Module docstring explains purpose and includes repository-relative File, Maintainer and ISO Modified fields. Imports follow, then configuration/constants, definitions and entry point. |
| Markdown | HTML comment header with File, Purpose, Maintainer and Modified; visible headings and links remain readable. |
| TOML, YAML, ignore/editor/env files | Leading comment header; retain the syntax expected by the consuming tool. |
| JSON configuration and asset catalogs | Keep strict JSON with two-space indentation and no comments or extra metadata properties. Unknown config fields are rejected. File purpose is recorded in the inventory. |
| Batch protocols | Preserve frozen JSON bytes and declared seeds/budgets; create a new named protocol for a new experiment. |
| Model prompt text | Preserve exact prompt content; a comment-looking header would become model input and alter behavior. Use the inventory for maintenance context. |
| Result JSON/CSV, ZIP and PNG | Treat committed results as immutable evidence. Never add headers, reformat rows or rewrite embedded source hashes to match newer code. |
| LICENSE | Preserve its legal wording and existing attribution; do not insert an editorial header. |

[The file inventory](FILE_INVENTORY.md) covers every tracked file, including formats
where inline headers would corrupt data, contracts or reproducibility. Runtime
venvs, caches, saves, downloaded weights, build output and `artifacts/` are not
maintained source. Keep them ignored. No file relocations were needed: production,
diagnostics, tests, examples, protocols and evidence already have separate owners.

Update Modified only when editing a maintained file; do not churn dates on every
CI run. Dates are maintenance metadata, not a replacement for Git history. New
source files require a real purpose description, not just a renamed template.

## Python documentation and ordering

Use Google-style Args, Returns (including explicit side effects/None) and Raises
when a failure propagates to callers. Document private helpers and nested callbacks
as well as public interfaces. Exclude implicit `self`/`cls` from Args. Classes
explain responsibility; dataclasses document their persisted/transport fields.
Examples should clarify non-obvious startup, persistence or plugin contracts.

Keep type/range validation in implementation; docstrings do not enforce it.
Tests describe the expectation they protect, and fixture helpers describe their
controlled response rather than claiming model quality. Hand-written protocol
methods and properties need contracts too; generated dataclass methods do not
require editing generated code.

Startup ordering is functional: initialize configuration **before** importing
world/rendering/persistence modules that cache settings. Such deliberate lazy
imports remain inside entry points. Do not move them to the top merely to satisfy
an import sorter. The `simulation.py` facade and existing imports from `brains.py`
retain explicit compatibility exports; new code should use owning modules.

## Configuration review

Gameplay and presentation tuning live in `village/data/default.json` plus validated
startup JSON overrides. Provider credentials come from the environment variable
named by a profile's `api_key_env`; never put a credential in a profile or report.
Paths, service URLs and model tags for the game and diagnostics use shared config,
CLI or environment overrides. `check_autonomy.py`, `check_window.py` and
`describe_runtime.py` accept the shared config/profile/model/URL flags. The runtime
metadata diagnostic targets Ollama's `/api/ps`; `--timeout` bounds that request.

Keep fixed protocol versions, HTTP route names, schema fields, defensive response
limits, navigation algorithms, floating-point comparison tolerances and controlled
test/benchmark fixtures in code. They are contracts or designed controls, not
operator tuning. Integration fixture horizons/delays and temporary paths remain
explicit in their helper or existing CLI flags; moving them into game settings
would change the game's config schema without a gameplay need.

[Configuration](CONFIGURATION.md) is the settings/path reference. The diagnostic
refactor removes duplicated endpoint/tag defaults but does not change profile
precedence. Existing no-override calls still select the same local Qwen profile.

## Environment variables

No environment variable is required for the default local demo or loopback model.
`.env.example` documents optional overrides. The application **does not load .env**;
export variables in your shell, or use the matching CLI flag instead.

| Variable | Purpose | Precedence / requirement |
| --- | --- | --- |
| `VILLAGE_CONFIG` | Startup JSON override path | `--config` wins; unset uses bundled defaults |
| `VILLAGE_MODEL` | Installed model tag override | `--model` wins; unset uses selected profile |
| `OLLAMA_URL` | Model API base override (despite its legacy name, applies to selected profile) | `--url` wins; unset uses selected profile |
| Profile-specific `api_key_env` name | Secret used by the configured transport | Required only when that profile names a credential variable |

Explicit per-villager profile assignments retain their own endpoint/tag; default
profile overrides do not rewrite them. Docker's `OLLAMA_NUM_PARALLEL` is service
configuration in `compose.yaml`, separate from host CLI overrides. `PYTHONPATH`,
Python display/backend variables and CI variables are environment/tool concerns,
not application secrets or additional game configuration requirements.

PowerShell examples (omit overrides you do not need):

```powershell
$env:VILLAGE_CONFIG = "examples/custom.json"
$env:VILLAGE_MODEL = "qwen2.5:1.5b"
$env:OLLAMA_URL = "http://localhost:11434"
# Remove an override after testing:
Remove-Item Env:VILLAGE_CONFIG
```

Bash:

```bash
export VILLAGE_CONFIG=examples/custom.json
export VILLAGE_MODEL=qwen2.5:1.5b
export OLLAMA_URL=http://localhost:11434
unset VILLAGE_CONFIG
```

## Tooling and repeatable checks

Install from the repository root with the platform's venv Python:

```bash
python -m pip install -e ".[dev]"
python -m ruff check village scripts tests
python -m ruff format --check village scripts tests
python scripts/check_consistency.py
python -m compileall -q village scripts tests
python -m unittest discover -s tests -v
```

The `dev` extra pins Ruff for consistent local/CI behavior. To format, run
`python -m ruff format village scripts tests`. Review import fixes with care:
startup imports and compatibility exports are deliberate. Ruff checks ordinary
lint/import/docstring rules; the standard-library consistency check additionally
covers every private/nested definition, parameter and module metadata field.
These checks do not prove semantic documentation accuracy; reviewers must compare
contracts to code. Avoid stock filler or unsupported exception/ownership claims.

For new releases also run the contributor, renderer, server/client and isolated
wheel checks in [the handover runbook](HANDOVER.md). Do not edit frozen evidence
merely because the current formatted source has different hashes. AST equivalence
and regression tests support behavioral preservation; they do not establish new
AI benefit or human acceptance.
