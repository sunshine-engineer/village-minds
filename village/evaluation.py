"""Bounded, headless comparisons with fixed simulation steps and AI checkpoints.

Run `python -m village.evaluation --help`. No Panda3D import or game saves needed.
"""

from collections import Counter
from datetime import datetime, timezone
import argparse
import csv
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import statistics
import time
import uuid
from .config import configure, get_settings, fingerprint
from .evaluation_schedule import CheckpointSchedule

from .inference import bounded_decision, model_worker, send_result

MODES = ("scripted", "hybrid", "hybrid-memory")


def generate_lessons(seed, seconds, step, deadline):
    """Get factual failure lessons from an idle run, never invent training history."""
    from .world import World

    world = World(seed=seed)
    while (
        not world.failed and world.time < seconds - 1e-9 and time.monotonic() < deadline
    ):
        world.tick(min(step, seconds - world.time))
    return {
        "method": "idle prior attempt, same seed; no learning or weight updates",
        "failed": world.failed,
        "seconds": world.time,
        "reason": world.failure_reason,
        "lessons": (
            {v.name: list(v.lessons) for v in world.villagers} if world.failed else {}
        ),
    }


class Metrics:
    def __init__(self, world):
        self.food_shortage_seconds = 0.0
        self.starvation_villager_seconds = 0.0
        self.gate_breaches = 0
        self.previous_gates = world.gates.copy()
        self.uncovered_threat_gate_seconds = 0.0
        self.threat_gate_seconds = 0.0
        self.travel_villager_seconds = 0.0
        self.store_travel_villager_seconds = 0.0

    def step(self, world, dt):
        # Intervals use the state at the start of a substep.
        from .map_data import GATES
        from .navigation import distance

        rules = get_settings()["rules"]
        self.travel_villager_seconds += dt * sum(
            v.alive and bool(v.path) for v in world.villagers
        )
        self.store_travel_villager_seconds += dt * sum(
            v.alive and bool(v.path) and v.action == "walking to storehouse"
            for v in world.villagers
        )
        self.threat_gate_seconds += dt * len(world.gate_threats())
        self.uncovered_threat_gate_seconds += dt * sum(
            not any(
                v.alive
                and v.action == f"guarding {gate}"
                and v.energy >= rules["attack_energy"]
                and distance(v.position, GATES[gate]) <= rules["attack_range"]
                for v in world.villagers
            )
            for gate in world.gate_threats()
        )
        if world.store["food"] == 0:
            self.food_shortage_seconds += dt
        threshold = get_settings()["rules"]["starvation_threshold"]
        self.starvation_villager_seconds += dt * sum(
            v.alive and v.hunger > threshold for v in world.villagers
        )

    def after_step(self, world):
        self.gate_breaches += sum(
            self.previous_gates[k] > 0 and hp <= 0 for k, hp in world.gates.items()
        )
        self.previous_gates = world.gates.copy()


def run_scenario(
    seed,
    mode,
    options,
    profile,
    output,
    config_path,
    lesson_fixture=None,
    *,
    suite_deadline=math.inf,
    request=bounded_decision,
):
    from .allocation import repair_candidates
    from .evaluation_controls import EvaluationWorld
    from .brains import BrainScheduler
    from .telemetry import DecisionLog

    if mode not in MODES:
        raise ValueError(f"Unknown evaluation mode: {mode}")
    control_name = options.get("control", "cooperative")
    control = options["controls"][control_name]
    if mode != "scripted" and (
        control_name != "cooperative"
        or not control["routines"]
        or control["disabled_actions"]
    ):
        raise ValueError(
            "Intervention controls require scripted mode; compare AI in the cooperative control"
        )
    started = time.monotonic()
    deadline = min(suite_deadline, started + options["run_wall_seconds"])
    logger = DecisionLog(
        output / "decisions.jsonl",
        max_bytes=get_settings()["telemetry"]["max_bytes"],
        full_observations=options["full_observations"],
    )
    # All conditions start in the same world. Only the model observation's lesson
    # field differs; local routines/chatter never receive extra remembered lessons.
    world = EvaluationWorld(
        seed=seed,
        disabled_actions=control["disabled_actions"],
        decision_log=logger,
        campaign={
            "attempt": 2 if (lesson_fixture or {}).get("failed") else 1,
            "failures": [],
            "lessons": {},
        },
    )
    world.task_board.mode = options.get(
        "coordination_mode", get_settings()["coordination"]["mode"]
    )
    brains = BrainScheduler(
        world, profile["url"], profile["model"], demo=True, profile=profile
    )
    metrics = Metrics(world)
    schedule = CheckpointSchedule(world, seed, options)
    requests = 0
    latencies = []
    outcomes = Counter()
    circuit_open = False
    inference_records = []
    allocations = []
    memory = (
        (lesson_fixture or {}).get("lessons", {}) if mode == "hybrid-memory" else {}
    )
    reason = "duration_reached"
    logger.record(
        "scenario_start",
        world.time,
        seed=seed,
        mode=mode,
        control=control_name,
        coordination_mode=world.task_board.mode,
        scenario_name=options["scenario_name"],
        disabled_actions=control["disabled_actions"],
        routines=control["routines"],
        timing_policy="paused_checkpoints",
        memory_available=bool(memory),
        checkpoint_strategy=schedule.strategy,
        planned_times=schedule.planned_times,
        role_order=schedule.roles,
    )
    try:
        while world.time < options["duration_seconds"] - 1e-9 and not world.failed:
            if time.monotonic() >= deadline:
                reason = (
                    "suite_wall_time_limit"
                    if time.monotonic() >= suite_deadline
                    else "run_wall_time_limit"
                )
                break
            if (
                mode != "scripted"
                and schedule.ready(world)
                and requests < options["max_model_calls"]
                and not circuit_open
                and (
                    not get_settings()["ai"]["repair_strategy"]["enabled"]
                    or repair_candidates(world.task_board)
                )
            ):
                selection = schedule.take(world)
                if selection is not None:
                    index, checkpoint_context = selection
                    bot = world.villagers[index]
                    if get_settings()["ai"]["repair_strategy"]["enabled"]:
                        from .allocation import strategy_observation

                        observation = strategy_observation(
                            world, bot, memory.get(bot.name, [])
                        )
                    else:
                        observation = world.observe(bot)
                        observation["decision_layer"] = "strategic"
                        observation["lessons_from_previous_failures"] = list(
                            memory.get(bot.name, [])
                        )
                    selected = brains.profile_for(bot.name)
                    request_id = f"checkpoint-{requests+1}"
                    logger.record(
                        "model_request",
                        world.time,
                        source="model",
                        actor=bot.name,
                        request_id=request_id,
                        observation=observation,
                        model=selected["model"],
                        backend=selected["backend"],
                        checkpoint=checkpoint_context,
                    )
                    timeout = min(
                        options["model_timeout_seconds"],
                        selected["timeout"],
                        max(0, deadline - time.monotonic()),
                    )
                    response = request(selected, observation, config_path, timeout)
                    requests += 1
                    latencies.append(response["latency_ms"])
                    # Do not apply a response beyond the scenario's wall deadline.
                    expired = time.monotonic() >= deadline
                    if response["status"] == "ok" and not expired:
                        outcome = brains.consume_decision(
                            index,
                            bot.revision,
                            world.time,
                            response["decision"],
                            request_id=request_id,
                            observation=observation,
                            latency_ms=response["latency_ms"],
                            profile=selected,
                        )
                    else:
                        outcome = "timeout" if expired else response["status"]
                        logger.record(
                            "model_response",
                            world.time,
                            source="model",
                            actor=bot.name,
                            request_id=request_id,
                            outcome=outcome,
                            reason=response.get("error", "Scenario wall-time limit"),
                            latency_ms=response["latency_ms"],
                            model=selected["model"],
                            backend=selected["backend"],
                        )
                    record = dict(
                        role=bot.role,
                        actor=bot.name,
                        request_id=request_id,
                        status=response["status"],
                        outcome=outcome,
                        latency_ms=response["latency_ms"],
                        inference=response.get("inference", {}),
                    )
                    inference_records.append(record)
                    logger.record(
                        "model_inference", world.time, source="model", **record
                    )
                    if (
                        outcome == "accepted"
                        and response["decision"].get("action") == "dispatch_repair"
                    ):
                        gate, _, recipient = response["decision"]["target"].partition(
                            ":"
                        )
                        task = next(
                            t
                            for t in world.task_board.tasks
                            if t["kind"] == "repair"
                            and t["target"] == gate
                            and t["assigned_to"] == recipient
                            and t["status"] in ("offered", "accepted")
                        )
                        person = next(v for v in world.villagers if v.name == recipient)
                        allocations.append(
                            dict(
                                request_id=request_id,
                                role=bot.role,
                                task=task,
                                task_id=task["id"],
                                gate=gate,
                                recipient=recipient,
                                repairs=0,
                                last_repairs=person.contributions["repairs"],
                            )
                        )
                    outcomes[outcome] += 1
                    if (
                        outcome in ("timeout", "error")
                        and options["stop_requests_on_error"]
                    ):
                        circuit_open = True
                    if expired:
                        continue
            dt = min(options["step_seconds"], options["duration_seconds"] - world.time)
            metrics.step(world, dt)
            world.tick(dt)
            if control["routines"]:
                brains.tick()
            metrics.after_step(world)
            for allocation in allocations:
                person = next(
                    v for v in world.villagers if v.name == allocation["recipient"]
                )
                task = allocation["task"]
                if (
                    task["assigned_to"] == person.name
                    and task["status"] in ("offered", "accepted")
                    and person.action == f"repairing {allocation['gate']}"
                ):
                    allocation["repairs"] += max(
                        0, person.contributions["repairs"] - allocation["last_repairs"]
                    )
                allocation["last_repairs"] = person.contributions["repairs"]
        if world.failed:
            reason = "village_destroyed"
        completed = (
            not world.failed and world.time >= options["duration_seconds"] - 1e-9
        )
        contributions = {v.name: v.contributions.copy() for v in world.villagers}
        result = {
            "seed": seed,
            "mode": mode,
            "control": control_name,
            "scenario_name": options["scenario_name"],
            "blocked_actions": dict(world.blocked_actions),
            "coordination_mode": world.task_board.mode,
            "coordination": world.task_board.summary(),
            "uncovered_threat_gate_seconds": round(
                metrics.uncovered_threat_gate_seconds, 6
            ),
            "threat_gate_seconds": round(metrics.threat_gate_seconds, 6),
            "uncovered_threat_fraction": (
                metrics.uncovered_threat_gate_seconds / metrics.threat_gate_seconds
                if metrics.threat_gate_seconds
                else None
            ),
            "stop_reason": reason,
            "failed": world.failed,
            "completed_horizon": completed,
            "censored": not world.failed,
            "simulated_seconds": round(world.time, 6),
            "wall_seconds": round(time.monotonic() - started, 6),
            "village_health": world.village_health,
            "villagers_lost": sum(not v.alive for v in world.villagers),
            "food_shortage_seconds": round(metrics.food_shortage_seconds, 6),
            "starvation_villager_seconds": round(
                metrics.starvation_villager_seconds, 6
            ),
            "gate_breaches": metrics.gate_breaches,
            "waves": world.wave,
            "final_store": world.store.copy(),
            "contributions": contributions,
            "local_actions": brains.local_decisions,
            "model_requests": requests,
            "inference_records": inference_records,
            "model_allocations": [
                {k: v for k, v in a.items() if k not in ("task", "last_repairs")}
                for a in allocations
            ],
            "productive_model_allocations": sum(a["repairs"] > 0 for a in allocations),
            "model_deferrals": (
                sum(r["outcome"] == "accepted" for r in inference_records)
                - len(allocations)
                if get_settings()["ai"]["repair_strategy"]["enabled"]
                else 0
            ),
            "travel_villager_seconds": round(metrics.travel_villager_seconds, 6),
            "store_travel_villager_seconds": round(
                metrics.store_travel_villager_seconds, 6
            ),
            "urgent_partial_deliveries": sum(
                logger.count("urgent_delivery", source, "accepted")
                for source in ("local", "model", "player", "external")
            ),
            "checkpoint_strategy": schedule.strategy,
            "model_coverage": schedule.coverage(),
            "unused_model_calls": (
                options["max_model_calls"] - requests if mode != "scripted" else 0
            ),
            "model_outcomes": dict(outcomes),
            "model_circuit_open": circuit_open,
            "model_acceptance_rate": (
                brains.model_decisions / requests if requests else None
            ),
            "decision_counts": {
                source: {
                    outcome: logger.count("decision", source, outcome)
                    for outcome in ("accepted", "rejected")
                }
                for source in ("local", "model", "player", "external")
            },
            "accepted_model_actions": brains.model_decisions,
            "mean_model_latency_ms": (
                round(statistics.mean(latencies), 3) if latencies else None
            ),
            "memory_available": bool(memory),
            "timing_policy": "paused_checkpoints",
            "decision_log": "decisions.jsonl",
            "log_dropped_records": logger.dropped,
        }
        result["model_evidence"] = (
            "not_requested"
            if mode == "scripted"
            else (
                "accepted_decisions"
                if brains.model_decisions
                else "no_accepted_model_decisions"
            )
        )
        logger.record("scenario_end", world.time, summary=result)
        result["log_dropped_records"] = logger.dropped
        (output / "result.json").write_text(
            json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        return result
    finally:
        logger.close()


def aggregate(results):
    rows = []
    for mode, control, coordination in dict.fromkeys(
        (
            r["mode"],
            r.get("control", "cooperative"),
            r.get("coordination_mode", "independent"),
        )
        for r in results
    ):
        group = [
            r
            for r in results
            if r["mode"] == mode
            and r.get("control", "cooperative") == control
            and r.get("coordination_mode", "independent") == coordination
        ]
        rows.append(
            {
                "mode": mode,
                "control": control,
                "coordination_mode": coordination,
                "mean_final_village_health": round(
                    statistics.mean(r["village_health"] for r in group), 3
                ),
                "mean_uncovered_threat_gate_seconds": round(
                    statistics.mean(
                        r.get("uncovered_threat_gate_seconds", 0) for r in group
                    ),
                    3,
                ),
                "runs": len(group),
                "horizons_completed": sum(r["completed_horizon"] for r in group),
                "village_losses": sum(r["failed"] for r in group),
                "wall_limited_runs": sum(
                    "wall_time_limit" in r["stop_reason"] for r in group
                ),
                "mean_observed_seconds": round(
                    statistics.mean(r["simulated_seconds"] for r in group), 3
                ),
                "mean_villagers_lost": round(
                    statistics.mean(r["villagers_lost"] for r in group), 3
                ),
                "model_requests": sum(r["model_requests"] for r in group),
                "accepted_model_actions": sum(
                    r["accepted_model_actions"] for r in group
                ),
                "timeouts": sum(r["model_outcomes"].get("timeout", 0) for r in group),
                "errors": sum(r["model_outcomes"].get("error", 0) for r in group),
                "roles_requested": sorted(
                    {
                        role
                        for r in group
                        for role in r.get("model_coverage", {}).get(
                            "roles_requested", []
                        )
                    }
                ),
                "roles_expected": sorted(
                    {
                        role
                        for r in group
                        if mode != "scripted"
                        for role in r.get("model_coverage", {}).get(
                            "roles_expected", []
                        )
                    }
                ),
                "active_threat_requests": sum(
                    r.get("model_coverage", {}).get("active_threat_requests", 0)
                    for r in group
                ),
                "quiet_requests": sum(
                    r.get("model_coverage", {}).get("quiet_requests", 0) for r in group
                ),
                "unused_model_calls": sum(
                    r.get("unused_model_calls", 0) for r in group
                ),
            }
        )
    return rows


def paired_coordination(results):
    """Within-seed differences, excluding interrupted/deadline-limited pairs."""
    key = lambda r: (
        r.get("scenario_name", "standard"),
        r["seed"],
        r["mode"],
        r.get("control", "cooperative"),
    )
    baselines = {
        key(r): r
        for r in results
        if r.get("coordination_mode", "independent") == "independent"
    }
    rows = []
    for mode, strategy in dict.fromkeys(
        (r["mode"], r.get("coordination_mode", "independent"))
        for r in results
        if r.get("coordination_mode", "independent") != "independent"
    ):
        candidates = [
            r
            for r in results
            if r["mode"] == mode
            and r.get("coordination_mode") == strategy
            and r.get("control", "cooperative") == "cooperative"
        ]
        pairs = [
            (baselines[key(r)], r)
            for r in candidates
            if key(r) in baselines
            and not any(
                "wall_time_limit" in x["stop_reason"] for x in (baselines[key(r)], r)
            )
        ]
        health = [r["village_health"] - b["village_health"] for b, r in pairs]
        coverage = [
            r["uncovered_threat_fraction"] - b["uncovered_threat_fraction"]
            for b, r in pairs
            if r.get("uncovered_threat_fraction") is not None
            and b.get("uncovered_threat_fraction") is not None
        ]
        rows.append(
            dict(
                mode=mode,
                strategy=strategy,
                matched_seeds=len(pairs),
                excluded_or_missing_pairs=len(
                    {
                        key(r)
                        for r in results
                        if r["mode"] == mode
                        and r.get("control", "cooperative") == "cooperative"
                    }
                )
                - len(pairs),
                survival_gains=sum(
                    r["completed_horizon"] and b["failed"] for b, r in pairs
                ),
                survival_regressions=sum(
                    b["completed_horizon"] and r["failed"] for b, r in pairs
                ),
                mean_final_health_delta=(
                    round(statistics.mean(health), 3) if health else None
                ),
                mean_uncovered_fraction_delta=(
                    round(statistics.mean(coverage), 6) if coverage else None
                ),
            )
        )
    return rows


def write_report(output, results, manifest):
    comparison = aggregate(results)
    paired = paired_coordination(results)
    summary = {
        "manifest": manifest,
        "comparison": comparison,
        "paired_coordination": paired,
        "runs": results,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    fields = [
        "seed",
        "mode",
        "control",
        "scenario_name",
        "coordination_mode",
        "uncovered_threat_gate_seconds",
        "uncovered_threat_fraction",
        "task_requests",
        "tasks_completed",
        "tasks_expired",
        "mean_productive_response_seconds",
        "stop_reason",
        "simulated_seconds",
        "wall_seconds",
        "completed_horizon",
        "failed",
        "village_health",
        "villagers_lost",
        "gate_breaches",
        "food_shortage_seconds",
        "starvation_villager_seconds",
        "local_actions",
        "model_requests",
        "accepted_model_actions",
        "mean_model_latency_ms",
        "memory_available",
        "log_dropped_records",
        "checkpoint_strategy",
        "roles_requested",
        "active_threat_requests",
        "quiet_requests",
        "unused_model_calls",
    ]
    with (output / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {
                **r,
                "task_requests": r.get("coordination", {})
                .get("counts", {})
                .get("requested", 0),
                "tasks_completed": r.get("coordination", {})
                .get("counts", {})
                .get("completed", 0),
                "tasks_expired": r.get("coordination", {})
                .get("counts", {})
                .get("expired", 0),
                "mean_productive_response_seconds": r.get("coordination", {}).get(
                    "mean_productive_response_seconds"
                ),
                "roles_requested": "/".join(
                    r.get("model_coverage", {}).get("roles_requested", [])
                ),
                "active_threat_requests": r.get("model_coverage", {}).get(
                    "active_threat_requests", 0
                ),
                "quiet_requests": r.get("model_coverage", {}).get("quiet_requests", 0),
            }
            for r in results
        )
    scenario_name = manifest.get("options", {}).get("scenario_name", "standard")
    control_names = ", ".join(
        dict.fromkeys(r.get("control", "cooperative") for r in results)
    ) or manifest.get("options", {}).get("control", "cooperative")
    lines = [
        "# Village AI evaluation",
        "",
        f"Scenario: {scenario_name}. Controls: {control_names}",
        "",
        "Fixed substeps without rendering; simulation pauses at bounded model checkpoints.",
        "Observed durations include censored runs: they are not mean time-to-failure estimates.",
        "",
        "| Mode | Control | Coordination | Runs | Horizon completed | Village lost | Wall limited | Model requests | Accepted AI | Timeouts | Errors |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison:
        lines.append(
            "| "
            + " | ".join(
                str(row[k])
                for k in (
                    "mode",
                    "control",
                    "coordination_mode",
                    "runs",
                    "horizons_completed",
                    "village_losses",
                    "wall_limited_runs",
                    "model_requests",
                    "accepted_model_actions",
                    "timeouts",
                    "errors",
                )
            )
            + " |"
        )
    lines += [
        "",
        "| Mode | Control | Coordination | Roles requested | Requested coverage | Threat calls | Quiet calls | Unused budget |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in comparison:
        coverage = (
            f"{len(row['roles_requested'])}/{len(row['roles_expected'])}"
            if row["roles_expected"]
            else "n/a"
        )
        lines.append(
            f"| {row['mode']} | {row['control']} | {row['coordination_mode']} | {', '.join(row['roles_requested']) or '-'} | {coverage} | {row['active_threat_requests']} | {row['quiet_requests']} | {row['unused_model_calls']} |"
        )
    lines += [
        "",
        "| Seed | Mode | Control | Coordination | Village health | Food shared | Wood shared | Repairs | Kills | Rallies |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        totals = Counter()
        for contribution in result["contributions"].values():
            totals.update(contribution)
        lines.append(
            f"| {result['seed']} | {result['mode']} | {result.get('control', 'cooperative')} | {result.get('coordination_mode', 'independent')} | {result['village_health']:.1f} | "
            + " | ".join(
                str(totals[key])
                for key in (
                    "deposited_food",
                    "deposited_wood",
                    "repairs",
                    "kills",
                    "rallies",
                )
            )
            + " |"
        )
    lines += [
        "",
        "| Seed | Mode | Coordination | Completed horizon | Village health | Uncovered threat gate seconds | Help requests | Accepted tasks | Completed / resolved / expired | Mean acknowledgement seconds | Mean productive response seconds |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for result in results:
        board = result.get("coordination", {})
        counts = board.get("counts", {})
        statuses = "/".join(
            str(counts.get(key, 0)) for key in ("completed", "resolved", "expired")
        )
        latency = board.get("mean_response_seconds")
        latency_text = f"{latency:.2f}" if latency is not None else "-"
        productive = board.get("mean_productive_response_seconds")
        productive_text = f"{productive:.2f}" if productive is not None else "-"
        lines.append(
            f"| {result['seed']} | {result['mode']} | {result.get('coordination_mode', 'independent')} | {result['completed_horizon']} | {result['village_health']:.1f} | {result.get('uncovered_threat_gate_seconds', 0):.1f} | {counts.get('requested', 0)} | {counts.get('accepted', 0)} | {statuses} | {latency_text} | {productive_text} |"
        )
    if paired:
        lines += [
            "",
            "Paired differences against independent routines (same seed, mode and action set).",
            "Positive health deltas favor coordination; negative uncovered-fraction deltas mean better coverage.",
            "",
            "| Mode | Strategy | Matched seeds | Excluded/missing | Survival gains | Survival regressions | Mean health delta | Mean uncovered fraction delta |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in paired:
            lines.append(
                "| "
                + " | ".join(
                    str(row[k])
                    for k in (
                        "mode",
                        "strategy",
                        "matched_seeds",
                        "excluded_or_missing_pairs",
                        "survival_gains",
                        "survival_regressions",
                        "mean_final_health_delta",
                        "mean_uncovered_fraction_delta",
                    )
                )
                + " |"
            )
    lines += [
        "",
        "A task completed only when its assignee performed relevant work and the need was resolved; resolutions by others are separate.",
        "Acknowledgement is not productive response time. Latency means use the most recent configured history_capacity samples.",
    ]
    lines += [
        "",
        "Role coverage counts requested roles, not successful decisions or proven benefits.",
        "Threat checkpoints require live monsters at a gate; a short/quiet scenario may have no requests.",
        "",
        f"Skipped scenarios: {manifest['skipped_scenarios']}. Interrupted: {manifest['interrupted']}.",
        "",
        "Interventions disable configured actions or routines; blocked attempts remain in logs and results.",
        "Control losses show dependencies of the tested policy, not proof that every possible strategy needs every role.",
        "A short/call-limited run is a smoke check, not evidence of improved cooperation.",
        "Memory uses factual lessons from a separate idle-failure fixture; no model training occurs.",
        "Changing models, call counts or checkpoint timing changes the experiment.",
        "See summary.json for options, provenance, latency and per-villager contributions.",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    from .cli import prepare, attach_profile

    parser = argparse.ArgumentParser(description=__doc__)
    settings = prepare(parser)
    defaults = settings["evaluation"]
    parser.add_argument(
        "--modes", nargs="+", choices=(*MODES, "all"), default=defaults["modes"]
    )
    parser.add_argument(
        "--checkpoint-strategy",
        choices=("threats", "interval"),
        default=defaults["checkpoint_strategy"],
        help="Threat-aware horizon slots or fixed intervals",
    )
    parser.add_argument(
        "--control",
        choices=tuple(defaults["controls"]),
        default=defaults["control"],
        help="Scripted intervention control; cooperative allows AI modes",
    )
    parser.add_argument(
        "--coordination",
        choices=("independent", "requests", "assigned"),
        default=settings["coordination"]["mode"],
        help="Shared task strategy; all survival actions stay enabled",
    )
    parser.add_argument(
        "--compare-coordination",
        action="store_true",
        help="Compare all three task strategies on identical seeds",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=defaults["seeds"])
    parser.add_argument(
        "--duration",
        type=float,
        default=defaults["duration_seconds"],
        help="Simulated seconds per scenario",
    )
    parser.add_argument(
        "--max-model-calls", type=int, default=defaults["max_model_calls"]
    )
    parser.add_argument(
        "--model-timeout", type=float, default=defaults["model_timeout_seconds"]
    )
    parser.add_argument(
        "--wall-seconds",
        type=float,
        default=defaults["run_wall_seconds"],
        help="Per-scenario wall budget",
    )
    parser.add_argument(
        "--suite-seconds",
        type=float,
        default=defaults["suite_wall_seconds"],
        help="Total simulation/model wall budget",
    )
    parser.add_argument(
        "--output",
        default=defaults["output_dir"],
        help="Parent folder; each invocation gets a unique subfolder",
    )
    parser.add_argument(
        "--full-observations",
        action="store_true",
        default=defaults["full_observations"],
    )
    args = parser.parse_args()
    attach_profile(parser, args)
    for name in ("duration", "model_timeout", "wall_seconds", "suite_seconds"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f'--{name.replace("_","-")} must be finite and positive')
    if args.max_model_calls < 0 or any(seed < 0 for seed in args.seeds):
        parser.error("Call budget and seeds must be nonnegative")
    options = {
        **defaults,
        "duration_seconds": args.duration,
        "max_model_calls": args.max_model_calls,
        "model_timeout_seconds": args.model_timeout,
        "run_wall_seconds": args.wall_seconds,
        "suite_wall_seconds": args.suite_seconds,
        "full_observations": args.full_observations,
        "checkpoint_strategy": args.checkpoint_strategy,
        "control": args.control,
        "coordination_mode": args.coordination,
    }
    modes = list(dict.fromkeys(MODES if "all" in args.modes else args.modes))
    if any(mode != "scripted" for mode in modes) and (
        args.control != "cooperative"
        or not defaults["controls"][args.control]["routines"]
        or defaults["controls"][args.control]["disabled_actions"]
    ):
        parser.error("Intervention controls require --modes scripted")
    if args.compare_coordination and (
        args.control != "cooperative"
        or defaults["controls"][args.control]["disabled_actions"]
        or not defaults["controls"][args.control]["routines"]
    ):
        parser.error(
            "Coordination comparisons require all survival actions and routines enabled"
        )
    seeds = list(dict.fromkeys(args.seeds))
    options.update(seeds=seeds, modes=modes)
    output = Path(args.output).expanduser().resolve() / (
        "run-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    output.mkdir(parents=True)
    config_path = output / "config.json"
    # Keys are environment-variable names, not their secret values. This is a
    # local experiment artifact; never read/write the normal campaign slot.
    config_path.write_text(
        json.dumps(settings, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    prompt = Path(settings["ai"]["system_prompt"]).read_bytes()
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "config_fingerprint": fingerprint(),
        "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
        "options": options,
        "modes": modes,
        "seeds": seeds,
        "selected_profile": args.profile,
        "effective_profile": args.model_profile,
        "profile": {
            "backend": args.model_profile["backend"],
            "model": args.model_profile["model"],
        },
        "timing_policy": "paused_checkpoints",
        "skipped_scenarios": 0,
        "interrupted": False,
    }
    strategies = (
        ["independent", "requests", "assigned"]
        if args.compare_coordination
        else [args.coordination]
    )
    manifest["coordination_strategies"] = strategies
    scenario_count = len(seeds) * len(modes) * len(strategies)
    results = []
    deadline = time.monotonic() + args.suite_seconds
    try:
        for seed in seeds:
            fixture = None
            if "hybrid-memory" in modes:
                fixture = generate_lessons(
                    seed, options["lesson_seconds"], options["step_seconds"], deadline
                )
                (output / f"lessons-{seed}.json").write_text(
                    json.dumps(fixture, indent=2) + "\n", encoding="utf-8"
                )
            for mode, strategy in (
                (mode, strategy) for mode in modes for strategy in strategies
            ):
                if time.monotonic() >= deadline:
                    break
                options_for_run = {**options, "coordination_mode": strategy}
                scenario = output / (
                    f"{seed}-{mode}-{strategy}"
                    if args.compare_coordination
                    else f"{seed}-{mode}"
                )
                scenario.mkdir()
                result = run_scenario(
                    seed,
                    mode,
                    options_for_run,
                    args.model_profile,
                    scenario,
                    config_path,
                    fixture,
                    suite_deadline=deadline,
                )
                results.append(result)
                print(
                    f"seed={seed} {mode}/{strategy}: {result['simulated_seconds']:g}s simulated, {result['wall_seconds']:.2f}s wall, {result['accepted_model_actions']}/{result['model_requests']} AI accepted; roles={','.join(result['model_coverage']['roles_requested']) or '-'}; threat calls={result['model_coverage']['active_threat_requests']}; {result['stop_reason']}",
                    flush=True,
                )
                manifest["skipped_scenarios"] = scenario_count - len(results)
                write_report(output, results, manifest)
            if time.monotonic() >= deadline:
                break
    except KeyboardInterrupt:
        manifest["interrupted"] = True
    finally:
        manifest["skipped_scenarios"] = scenario_count - len(results)
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest["suite_wall_seconds"] = round(
            time.monotonic() - (deadline - args.suite_seconds), 6
        )
        write_report(output, results, manifest)
    print(f'Report: {output / "report.md"}', flush=True)
    if manifest["interrupted"]:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
