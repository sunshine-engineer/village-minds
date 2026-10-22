"""Compare non-planner decisions and task ownership in a frozen strategy batch."""

import argparse
import hashlib
import json
from pathlib import Path


def digest(rows):
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def audit(root):
    report = json.loads((root / "summary.json").read_text())
    rows = []
    for run in report["runs"]:
        folder = root / f"{run['case']}-{run['seed']}-{run['condition']}"
        trace = next(folder.rglob("decisions.jsonl"))
        decisions, ownership = [], []
        for line in trace.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["event"] == "decision" and event.get("source") != "model":
                decisions.append(
                    {
                        k: event.get(k)
                        for k in (
                            "sim_time",
                            "actor",
                            "source",
                            "outcome",
                            "decision",
                            "before",
                            "after",
                        )
                    }
                )
            if event["event"] == "task_accepted":
                ownership.append(
                    {k: event.get(k) for k in ("sim_time", "actor", "task")}
                )
        rows.append(
            dict(
                case=run["case"],
                seed=run["seed"],
                condition=run["condition"],
                decision_count=len(decisions),
                decision_sha256=digest(decisions),
                ownership_count=len(ownership),
                ownership_sha256=digest(ownership),
            )
        )
    comparisons = []
    for row in rows:
        if row["condition"] == "scripted":
            continue
        baseline = next(
            r
            for r in rows
            if (r["case"], r["seed"], r["condition"])
            == (row["case"], row["seed"], "scripted")
        )
        comparisons.append(
            dict(
                case=row["case"],
                seed=row["seed"],
                condition=row["condition"],
                same_non_planner_decisions=row["decision_sha256"]
                == baseline["decision_sha256"],
                same_accepted_task_ownership=row["ownership_sha256"]
                == baseline["ownership_sha256"],
            )
        )
    return dict(
        method="ordered sim_time/actor/source/outcome/decision/before/after; ordered accepted task records; wall timings and planner decisions excluded",
        rows=rows,
        comparisons=comparisons,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.batch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["comparisons"], indent=2))


if __name__ == "__main__":
    main()
