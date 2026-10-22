"""Post-hoc timing control: replay a model run's delays while deferring every plan.

This diagnostic is not a predeclared holdout and makes no provider calls.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from village.config import configure, get_settings
    from village.models import resolve_profile
    from village.evaluation import run_scenario
    from village.validation import source_hashes

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    report = json.loads((args.batch / "summary.json").read_text())
    normalized = lambda x: {k.replace("\\", "/"): v for k, v in x.items()}
    if normalized(source_hashes()) != normalized(report["protocol"]["sources"]):
        parser.error("Source differs from original batch; use its frozen checkout")
    args.output.mkdir(parents=True, exist_ok=False)
    plan = report["protocol"]["plan"]
    rows = []
    for original in report["runs"]:
        if (
            original["condition"] != "model"
            or original["case"] != args.case
            or original["seed"] != args.seed
        ):
            continue
        config = args.batch / f"{original['case']}-model.json"
        configure(config)
        options = deepcopy(get_settings()["evaluation"])
        options.update(
            duration_seconds=plan["duration_seconds"],
            max_model_calls=plan["model_calls"],
            model_timeout_seconds=plan["request_seconds"],
            run_wall_seconds=plan["run_wall_seconds"],
        )
        records = original["inference_records"]
        used = []

        def request(profile, observation, path, timeout):
            if len(used) >= len(records):
                raise RuntimeError("Control diverged: extra checkpoint")
            record = records[len(used)]
            used.append(record)
            return dict(
                status=record["status"],
                latency_ms=record["latency_ms"],
                decision=dict(action="defer_strategy", target="", dialogue=""),
                inference={"provider_called": False},
            )

        folder = args.output / f"{original['case']}-{original['seed']}"
        folder.mkdir()
        row = run_scenario(
            original["seed"],
            "hybrid",
            options,
            resolve_profile(),
            folder,
            config,
            request=request,
        )
        match = [(r["sent_at"], r["role"], r["actor"]) for r in records] == [
            (r["sent_at"], r["role"], r["actor"]) for r in row["inference_records"]
        ]
        rows.append(
            dict(
                case=original["case"],
                seed=original["seed"],
                same_checkpoint_timeline=match,
                original_health=original["village_health"],
                control_health=row["village_health"],
                original_seconds=original["simulated_seconds"],
                control_seconds=row["simulated_seconds"],
                original_failed=original["failed"],
                control_failed=row["failed"],
                control=row,
            )
        )
        (args.output / "summary.json").write_text(
            json.dumps(dict(post_hoc=True, provider_calls=0, runs=rows), indent=2)
            + "\n"
        )
        print(
            json.dumps({k: v for k, v in rows[-1].items() if k != "control"}),
            flush=True,
        )


if __name__ == "__main__":
    main()
