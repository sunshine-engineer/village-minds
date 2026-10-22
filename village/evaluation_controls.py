"""Evaluation-only interventions; ordinary game worlds keep every action."""

from collections import Counter
from .world import World


class EvaluationWorld(World):
    def __init__(self, *args, disabled_actions=(), **kwargs):
        self.disabled_actions = frozenset(disabled_actions)
        self.blocked_actions = Counter()
        super().__init__(*args, **kwargs)

    def _apply(self, bot, decision):
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
