<!--
File: docs/DOCUMENTATION_AUDIT.md
Purpose: Documentation handover audit — 22 October 2026.
Maintainer: sunshine-engineer
Modified: 2026-10-23
-->

# Documentation handover audit — 22 October 2026

The audit covers all root Markdown guides and every top-level `docs/*.md` guide:
22 documents including the new index, runbook and this record. It compares current
instructions with source, packaged defaults, examples, CLI help and committed
release evidence. It does not certify third-party documentation, every historical
raw log, model licensing, or a receiving developer's independent setup.

## Corrections

| Confirmed gap | Correction |
| --- | --- |
| No central reading order or receiving-developer runbook | Added index, setup/operations/recovery/rollback/evidence transfer and sign-off record |
| README said there was no multiplayer without naming the network prototype | Clarified one loopback client versus unsupported multi-player hosting |
| README implied every model used the repair-only interface | Distinguished ordinary strategic actions/dialogue from opt-in repair priorities |
| Server guide said O released possession | Corrected to configured **0 (zero)** |
| Protocol table omitted `/exchange`; legacy comparison omitted TCP_NODELAY | Added protocol-2 endpoint and all three transport toggles |
| Configuration section table omitted coordination/logistics/probe/network | Added all missing top-level sections and probe acceptance threshold |
| Timing prose described every evaluator run as paused | Distinguished default paused checkpoints from fixed/measured replay |
| Siege guide implied `--new-game` could bypass changed rules | Required compatible fingerprints or a separate save slot |
| README migration statements contradicted format 1→2 support | Documented the one supported upgrade and lack of a general migration framework |
| v2 text presented already-fixed requester filtering as a current limitation | Kept historical result and linked the v3 correction |
| Old studies and eight-sample latency could look like current acceptance | Added scope markers, ordered experiment index and current separate-process evidence |
| Latest validation was buried beneath older test totals | Put release evidence first; retained dated historical records |
| Readiness linked an earlier CI revision | Linked verified final pre-audit CI at `28d766a` |
| Handover did not distinguish committed evidence from ignored local logs | Identified transfer requirements and limits of historical reproducibility |

All other guides are mapped in [the index](INDEX.md). Preserved result tables and
frozen protocols were not retuned or relabeled as fresh validation. Autonomous
construction/self-evolution remains an idea, not a documented implemented feature.

## Verification performed

- All 203 local Markdown link targets, 101 inline `scripts/`, `configs/`,
  `examples/` path references and fenced-code delimiter balance checked after edits;
  no missing targets or unbalanced fences. External URL availability
  and browser-rendered formatting were not exhaustively tested.
- CLI `--help` passed in fresh processes for game, server, client, evaluation,
  validation, strategy experiment, priority benchmark, inference probe and model probe.
- All 12 ordinary JSON overrides under `examples/` and `configs/` loaded through
  the actual configuration validator in fresh interpreters. Batch protocol files
  are not game overrides; their full experiments were not rerun for this docs audit.
- The documented provider-free contributor contract passed: action effects/cost,
  cooldown rejection, backend intent validation and persistent cooldown; zero model calls.
- The documented 30-second seed-7 scripted evaluator command completed without
  model requests. No campaign save was loaded or written by that evaluator.
- GitHub readback confirmed PRs #3/#4 were open drafts and all four pre-audit CI
  lanes passed at `28d766a`. Historical Windows failures were fixed before that head.
- Runtime/architecture/default descriptions checked against `cli.py`, entry points,
  `server.py`, `config.py`, `persistence.py`, `data/default.json` and `compose.yaml`.

The audit does not claim a new full regression run, native rendering benchmark or
live inference study. Those are separately versioned evidence in
[validation](../VALIDATION.md) and [readiness](PORTFOLIO_READINESS.md).

## Handover conclusion

Documentation is organized and current for **technical prototype handover**, with
known limits made explicit. Receiving-person acceptance remains pending: assign
ownership, perform a clean setup and normal-window playtest, record issues and a
three-minute demo, and decide whether to accept the unmet default-interpolation
p95 target. See [the handover checklist](HANDOVER.md). A documentation review cannot
confirm those activities happened or make the prototype production-ready.
