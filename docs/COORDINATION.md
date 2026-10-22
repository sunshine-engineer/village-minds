# Help requests and task assignments

Example: a worker sees insufficient shared wood and posts `wood:storehouse`. An elder offers that request to a villager. The recipient accepts, collects wood, delivers it, and closes the request when the shared stock reaches the configured goal. Food, repair and defense requests follow the same structure.

The task board is a public village communication channel. It shares structured requests and a roster; it does not pretend that spoken dialogue can be heard across the map. These data are available to models under every strategy. Free-form dialogue never executes an instruction.

## Actions

| Action | Target | Who can use it |
| --- | --- | --- |
| `request_help` | An available `kind:place` token | Any living villager |
| `assign_task` | An available `task-id:recipient` token | Roles in `coordination.assigner_roles`, initially elder |
| `claim_task` | An open task ID or your own offer | A villager without another owned task |
| `release_task` | Your owned task ID | Its recipient |

Only current `available_actions` tokens are valid. Models receive these choices through the same JSON schema as other actions. The strategic allowlist must include these actions in custom model configs; the packaged defaults do.

Requests are deduplicated by kind and destination. An assignment is an offer, not forced movement. One task can have one owner; a villager can hold one offer/accepted task. Local routines accept offers when personal needs permit and carry out accepted jobs. Hunger, exhaustion and player control take precedence. A player-controlled villager receives no automatic assignment, but can claim a job manually.

A task closes as:

- **Completed:** its assignee performed relevant work and the resource/defense need was resolved.
- **Resolved:** someone else resolved the need without productive work by its assignee.
- **Expired:** its time limit elapsed. This releases its owner; a continuing need can be requested again.

Death releases ownership. Recipients can release a job themselves. Acknowledgement time measures accepting the job; productive response time measures the first relevant attack, repair or resource delivery. They are different metrics. Completion does not imply the assignee alone caused the result.

## Automatic strategies

| Strategy | Behavior |
| --- | --- |
| `independent` | Existing role routines. No automatic task posting or claiming. Explicit player/model requests and offers remain legal; accepted jobs are still honored. |
| `requests` | Villagers post needs; available volunteers use role preference and travel distance to claim jobs. |
| `assigned` | Same request board; a living, available elder offers jobs using role preference and travel distance. Recipients accept when ready. |

Every strategy retains farming, harvesting, eating, sharing, gathering, repairs, attacks and guarding. The scripted strategies are transparent Python policies, not model reasoning. Models can make structured coordination decisions in `hybrid` / `hybrid-memory` runs; their contribution must be measured separately.

All thresholds, time limits, priorities, role preferences, capacity and distance weights live in `coordination` in [the defaults](../village/data/default.json). Standard games keep independent routines unless you select a strategy. For example:

```powershell
.\.venv-win\Scripts\python.exe -m village --config configs/cooperation-siege.json --coordination requests --demo
```

On Linux replace the executable with `.venv/bin/python`. Remove `--demo` for the configured local model.

## Player controls

Default keys: **Q** posts the first current need, **U** offers the highest-priority task to the preferred available recipient (elder only), **Y** claims a task, and **X** releases your task. These are contextual shortcuts using current legal tokens. Remap them in `controls.actions`. The task mode/count appear in the HUD; offers and acknowledgements appear in the event feed and speech bubbles.

## Save and logs

Active tasks, owners, request cooldowns, expiry times, counters and bounded latency histories are saved with the world. Previous snapshots without a task board load with an empty board. Normal map/rules/roster fingerprints remain unchanged by this feature. The startup config or `--coordination` chooses the automatic strategy when resuming; the saved jobs still exist.

Decision logs distinguish task transitions (`task_requested`, `task_offered`, `task_accepted`, `task_progress`, `task_completed`, `task_resolved`, `task_expired`, `task_released`) from model response acceptance. Automatic transitions use the `task_board` source. The surrounding validated action record identifies `model`, `player`, `local` or `coordination` provenance. A log of scripted requests is not evidence of successful AI teamwork.

Use [the evaluation guide](COOPERATION_SCENARIO.md) to compare strategies on matched seeds.
