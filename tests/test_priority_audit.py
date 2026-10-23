"""Evidence auditing must detect actual behavior changes, not wall-clock noise.

File: tests/test_priority_audit.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_priority_results import audit


class PriorityAuditTests(unittest.TestCase):
    """Regression cases for priority audit."""

    def write_fixture(self, root, changed):
        """Write paired audit evidence with an optional deliberate behavioral difference.

        Args:
            root: Root artifact directory searched for result files.
            changed: Whether to introduce a deliberate difference into the audit fixture.

        Returns:
            None; performs the side effects described above.
        """
        rows = [
            dict(case="siege", seed=301, condition=c) for c in ("scripted", "model")
        ]
        (root / "summary.json").write_text(json.dumps(dict(runs=rows)))
        for row in rows:
            model = row["condition"] == "model"
            folder = root / f"siege-301-{row['condition']}"
            folder.mkdir()
            decision = dict(
                event="decision",
                sim_time=1,
                actor="Bram",
                source="local",
                outcome="accepted",
                decision=dict(
                    action="claim_task",
                    target="task-2" if model and changed else "task-1",
                ),
                before={},
                after={},
                wall_seconds=20 if model else 1,
            )
            ownership = dict(
                event="task_accepted",
                sim_time=1,
                actor="Bram",
                task=dict(id=decision["decision"]["target"]),
            )
            events = [decision, ownership]
            if model:
                events.append(
                    dict(
                        event="decision",
                        source="model",
                        decision=dict(action="plan_repairs"),
                    )
                )
            (folder / "decisions.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events)
            )

    def test_wall_noise_and_planner_acceptance_are_not_behavior_changes(self):
        """Verify wall noise and planner acceptance are not behavior changes.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_fixture(root, False)
            pair = audit(root)["comparisons"][0]
            self.assertTrue(pair["same_non_planner_decisions"])
            self.assertTrue(pair["same_accepted_task_ownership"])

    def test_real_task_handoff_difference_is_detected(self):
        """Verify real task handoff difference is detected.

        Returns:
            None; unittest assertions report a regression on failure.
        """
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.write_fixture(root, True)
            pair = audit(root)["comparisons"][0]
            self.assertFalse(pair["same_non_planner_decisions"])
            self.assertFalse(pair["same_accepted_task_ownership"])
