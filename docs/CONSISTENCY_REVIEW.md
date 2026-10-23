<!--
File: docs/CONSISTENCY_REVIEW.md
Purpose: Record scope, preservation checks and validation for the project consistency pass.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Project-wide consistency review — 23 October 2026

Branch: `chore/project-consistency`, based on readiness commit `adaac94`.
This is a maintenance PR stacked on `feature/portfolio-readiness`; `main` does not
contain the full prototype. It adds no gameplay feature, model prompt, rule change,
new scenario or change to saved-world compatibility.

## Scope and organization

- Reviewed every tracked file by type and purpose. Added a complete
  [file inventory](FILE_INVENTORY.md) and README directory map. Existing placement
  already separates runtime code, plugins, packaged assets, examples, protocols,
  diagnostics, tests and published evidence; no moves were needed.
- Added purpose/file/maintainer/date metadata to Python, Markdown and supported
  comment formats. `sunshine-engineer` is the requested maintainer default;
  existing legal attribution remains unchanged. Strict JSON, prompts, frozen data
  and binary artifacts use inventory context instead of injected headers.
- Documented every explicit class, function, method, property and nested callback:
  78 Python files, 607 definitions. Parameters/returns and applicable failure
  contracts are recorded; representative startup/plugin/save examples explain
  non-obvious boundaries. Generated dataclass methods are not hand-edited.
- Applied pinned Ruff import/lint/format conventions, retaining startup-only lazy
  imports and compatibility names. Added editor defaults and CI checks. Explicit
  aliases preserve legacy imports from `brains.py` and other existing modules;
  `simulation.py` retains its documented compatibility export list.
- Removed duplicated endpoint/model defaults from autonomy, X11 and metadata
  diagnostics. They now resolve shared config/profile/CLI/environment options
  before importing runtime modules. The metadata request has a configurable finite
  timeout. `.env.example` documents optional variables; no dotenv dependency was added.

## Behavior preservation

Executable ASTs were compared with the base after removing documentation and
import-only changes. The remaining differences are confined to nine existing files:
three diagnostic config entry points, the priority-server fixture's variable name,
two assigned-lambda helper replacements, an unused settings assignment, one
identical duplicate result key, and the compatibility facade's explicit exports.
The test helper lambda replacement is included in that count. No survival,
movement, ownership, persistence, inference, prompt or scoring algorithm changed.

Every baseline file under `configs/`, `examples/`, `village/data/`, `docs/results/`
and `LICENSE` was checked byte-for-byte and remains unchanged. Reformatting source
changes source hashes; it does not revalidate historical experiments or authorize
rewriting their provenance. Existing source-match replay diagnostics still require
the matching frozen checkout; the committed contention archive remains usable.

## Checks completed before opening the PR

| Check | Result |
| --- | --- |
| Full Linux regression suite | 176 passed, Python 3.14.4 |
| Full native Windows regression suite | 176 passed, Python 3.14.7 |
| Ruff lint/import/docstring checks and formatting | Passed using pinned 0.17.2 |
| Documentation/header checker | 78 Python files / 607 definitions; no issues; intentionally undocumented negative fixture rejected |
| CLI/config validation | Nine module entry points, three refactored helper CLI help checks and 12 startup overrides passed; invalid metadata timeout rejected |
| Contributor contract and scripted evaluator | Passed; zero provider calls; 30 simulated seconds on seed 7 |
| Fresh isolated Linux wheel install | Passed package isolation, plugin/backend contracts, client entry point and server start/save |
| Fresh isolated Windows wheel install | Same checks plus installed offscreen Panda3D rendering passed |
| Custom-config autonomy rendering | All six villagers moved in the native offscreen fixture; zero model decisions |
| Direct-authority persistence soak | 1,800 simulated seconds, ten possessions, three reconnects and six restores passed; no village failure occurred |
| Ollama metadata helper | Shared config resolved and `/api/ps` completed; no model was loaded at the time |

The built wheel's packaged source files were compared against the working tree;
there were no mismatches. The new dev extra is exercised by branch CI separately
from runtime-only fresh installations. CI runs Ubuntu/Windows with Python 3.11/3.14;
local runtime validation uses the installed Python 3.14 environments.

## Live-model attempt and remaining limits

The first generic real-model probe timed out at its unchanged 25-second deadline.
Immediately preceding metadata showed no model loaded, but that alone does not
prove cold loading caused the timeout. A subsequent probe from unchanged base
`adaac94` succeeded against the same service. The modified-source retry also succeeded within the same 25-second deadline,
with a real action accepted by the world. The unsuccessful first attempt remains
retained in local `artifacts/consistency/` rather than being discarded.

These smoke checks do not measure reliability or strategic benefit. No 80-run model
benchmark or latency acceptance study was repeated for documentation/formatting.
The X11 helper's shared CLI was checked; targeted desktop keyboard automation and
a human playtest were not repeated. Existing 452 ms default-interpolation p95,
independent setup, normal-window playtest and demo-recording gates remain open.
See [readiness](PORTFOLIO_READINESS.md); maintenance checks do not close those gates.
