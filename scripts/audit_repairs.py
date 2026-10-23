"""Audit actual gate HP restored per wood from a completed validation batch.

File: scripts/audit_repairs.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def audit(summary_path, scenario_name):
    """Reconstruct useful repair HP and actual wood consumption from accepted trace records.

    Args:
        summary_path: Completed validation summary JSON containing scenario evidence references.
        scenario_name: Exact scenario label whose repair traces should be audited.

    Returns:
        Per-strategy efficiency and contribution audit dictionary.
    """
    summary_path = Path(summary_path).resolve()
    root = summary_path.parent
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scenario = next(c for c in summary["scenarios"] if c["name"] == scenario_name)
    config_info = next(
        c for c in summary["manifest"]["scenarios"] if c["name"] == scenario_name
    )
    config = json.loads(
        (root / config_info["frozen_config"]).read_text(encoding="utf-8")
    )
    roles = {v["name"]: v["role"] for v in config["world"]["cast"]}
    result = {}
    for strategy in ("independent", "requests", "assigned"):
        restored, wood, dropped = 0.0, 0, 0
        repairs = Counter()
        for row in scenario["runs"]:
            if row["coordination_mode"] != strategy:
                continue
            dropped += row["log_dropped_records"]
            log = (
                root
                / scenario["evidence"]
                / f"{row['seed']}-scripted-{strategy}"
                / "decisions.jsonl"
            )
            with log.open(encoding="utf-8") as handle:
                for line in handle:
                    event = json.loads(line)
                    if (
                        event["event"] != "decision"
                        or event.get("outcome") != "accepted"
                        or event.get("decision", {}).get("action") != "repair"
                    ):
                        continue
                    gate = event["decision"]["target"]
                    before, after = event["before"], event["after"]
                    restored += after["gates"][gate] - before["gates"][gate]
                    wood += before["store"]["wood"] - after["store"]["wood"]
                    repairs[roles[event["actor"]]] += 1
        result[strategy] = dict(
            gate_hp_restored=restored,
            wood_consumed=wood,
            gate_hp_per_wood=restored / wood if wood else None,
            repairs_by_role=dict(repairs),
            dropped_log_records=dropped,
            complete_logs=dropped == 0,
        )
    return dict(
        scenario=scenario_name,
        source_summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        strategies=result,
    )


def main():
    """Run the audit repairs diagnostic and write its evidence.

    Returns:
        None; writes artifacts or exits with a nonzero status on failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--scenario", default="wood-pressure")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.summary, args.scenario)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
