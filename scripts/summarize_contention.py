"""Audit paired fixture identity and actual event order in a frozen contention batch."""

import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def summarize(root):
    data = json.loads((root / "summary.json").read_text())
    rows = data["runs"]
    plan = data["protocol"]["plan"]
    results = []
    pairs = []
    for row in rows:
        events = [
            json.loads(line)
            for line in (
                root
                / f"{row['case']}-{row['seed']}-{row['condition']}"
                / "decisions.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        owner = row["first_repair_owner"]
        response = next((e for e in events if e["event"] == "model_response"), None)
        claim = next(
            (
                e
                for e in events
                if e["event"] == "task_accepted"
                and e["task"]["kind"] == "repair"
                and owner
                and e["actor"] == owner["actor"]
            ),
            None,
        )
        early = bool(
            response
            and claim
            and response["sequence"] < claim["sequence"]
            and response["outcome"] == "accepted"
            and response["decision"]["action"] == "plan_repairs"
        )
        results.append(
            dict(
                case=row["case"],
                seed=row["seed"],
                condition=row["condition"],
                role=row["role"],
                primary_gate=row["primary_gate"],
                selected_gate=row["selected_gate"],
                first_owned_gate=owner["gate"] if owner else None,
                primary_gate_breached=row["primary_gate_breached"],
                outcome=row["outcome"],
                response_ms=row["response"]["latency_ms"] if row["response"] else None,
                valid_plan_before_claim=early,
                actual_response_at=response["sim_time"] if response else None,
                first_claim_at=claim["sim_time"] if claim else None,
                stop_reason=row["stop_reason"],
                log_dropped_records=row["log_dropped_records"],
            )
        )
    for case in plan["cases"]:
        for seed in plan["seeds"]:
            match = {
                r["condition"]: r
                for r in rows
                if r["case"] == case["name"] and r["seed"] == seed
            }
            complete = set(match) == set(plan["conditions"])
            same = complete and all(
                r["initial"] == match["baseline"]["initial"] for r in match.values()
            )
            eligible = same and all(
                r["stop_reason"] == "duration_reached" and r["log_dropped_records"] == 0
                for r in match.values()
            )
            pairs.append(
                dict(
                    case=case["name"],
                    seed=seed,
                    complete=complete,
                    identical_initial_state=same,
                    eligible=eligible,
                    adverse_changes_ownership=eligible
                    and match["adverse"]["first_repair_owner"]["gate"]
                    != match["scripted"]["first_repair_owner"]["gate"],
                    adverse_worsens_outcome=eligible
                    and match["adverse"]["primary_gate_breached"]
                    and not match["scripted"]["primary_gate_breached"],
                    model_improves_baseline=eligible
                    and match["baseline"]["primary_gate_breached"]
                    and not match["model"]["primary_gate_breached"],
                    model_improves_scripted=eligible
                    and match["scripted"]["primary_gate_breached"]
                    and not match["model"]["primary_gate_breached"],
                )
            )
    groups = []
    for case in plan["cases"]:
        for condition in plan["conditions"]:
            group = [
                r
                for r in results
                if r["case"] == case["name"] and r["condition"] == condition
            ]
            groups.append(
                dict(
                    case=case["name"],
                    condition=condition,
                    runs=len(group),
                    breaches=sum(r["primary_gate_breached"] for r in group),
                    early_valid_plans=sum(r["valid_plan_before_claim"] for r in group),
                )
            )
    calls = [r for r in rows if r["condition"] == "model"]
    lat = sorted(r["response"]["latency_ms"] for r in calls)
    return dict(
        expected_runs=data["protocol"]["expected_runs"],
        completed_runs=len(rows),
        failures=data["failures"],
        method="exact initial snapshot equality; plan-before-claim uses event sequence, not requested-delay estimates",
        by_condition=groups,
        paired_controls=pairs,
        rows=results,
        model=dict(
            requests=len(calls),
            valid_in_deadline=sum(
                r["response"]["status"] == "ok"
                and r["response"]["latency_ms"] <= plan["request_seconds"] * 1000
                for r in calls
            ),
            median_ms=statistics.median(lat),
            p95_ms=lat[math.ceil(0.95 * len(lat)) - 1],
            max_ms=max(lat),
            deferrals=sum(
                r["response"].get("decision", {}).get("action") == "defer_strategy"
                for r in calls
            ),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.batch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    with args.output.with_suffix(".csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report["rows"][0]))
        writer.writeheader()
        writer.writerows(report["rows"])
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("rows", "paired_controls")},
            indent=2,
        )
    )
    if (
        report["failures"]
        or report["completed_runs"] != report["expected_runs"]
        or any(not p["eligible"] for p in report["paired_controls"])
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
