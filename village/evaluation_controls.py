"""Evaluation-only interventions; ordinary game worlds keep every action.

File: village/evaluation_controls.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

from collections import Counter

from .world import World


class EvaluationWorld(World):
    """Ordinary World with explicit evaluation-only action interventions."""

    def __init__(self, *args, disabled_actions=(), **kwargs):
        """Initialize EvaluationWorld and its owned state.

        Args:
            disabled_actions: Action names deliberately blocked by an evaluation-only control.
            *args: Parsed command-line options for this entry point.
            **kwargs: Keyword options forwarded to the owning implementation.

        Returns:
            None.
        """
        self.disabled_actions = frozenset(disabled_actions)
        self.blocked_actions = Counter()
        super().__init__(*args, **kwargs)

    def _apply(self, bot, decision):
        """Block configured intervention actions while preserving ordinary validation for others.

        Args:
            bot: Villager whose current state or work is being considered.
            decision: Proposed structured action with optional target/dialogue fields.

        Returns:
            Whether the action was allowed and accepted.
        """
        action = decision.get("action") if isinstance(decision, dict) else None
        if isinstance(action, str) and action in self.disabled_actions:
            self.blocked_actions[decision["action"]] += 1
            if self.decision_log:
                self.decision_log.record(
                    "evaluation_intervention",
                    self.time,
                    actor=bot.name,
                    action=decision["action"],
                    outcome="blocked",
                    reason="control_disabled_action",
                )
            return False
        return super()._apply(bot, decision)
