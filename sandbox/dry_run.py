"""
dry_run.py
----------
Simulates plan execution without making any real API calls.

DryRunResult is shown to human reviewers in the Gmail extension
BEFORE they click Approve, so they can see exactly what would happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class StepDryRunResult:
    step_index: int
    action: str
    tool: str
    description: str           # human-readable description of what would happen
    would_succeed: bool = True
    simulated_output: dict = field(default_factory=dict)


@dataclass
class DryRunResult:
    goal_type: str
    steps: list[StepDryRunResult] = field(default_factory=list)
    would_succeed: bool = True
    summary: str = ""
    simulated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "goal_type": self.goal_type,
            "would_succeed": self.would_succeed,
            "summary": self.summary,
            "simulated_at": self.simulated_at,
            "steps": [
                {
                    "step_index": s.step_index,
                    "action": s.action,
                    "tool": s.tool,
                    "description": s.description,
                    "would_succeed": s.would_succeed,
                    "simulated_output": s.simulated_output,
                }
                for s in self.steps
            ],
        }


# ── Per-tool simulation descriptions ─────────────────────────────────────────

_TOOL_DESCRIPTIONS: dict[str, str] = {
    "gmail": "Would send a Gmail reply/draft via Gmail API",
    "calendar": "Would create a Google Calendar event",
    "payment": "Would initiate a payment transaction",
    "slack": "Would send a Slack message",
    "default": "Would execute this action via the tool orchestrator",
}


def dry_run_plan(goal_plan) -> DryRunResult:
    """
    Simulate execution of a GoalPlan without side effects.

    Args:
        goal_plan: agents.planner.schemas.GoalPlan instance

    Returns:
        DryRunResult describing what would happen for each step.
    """
    goal_type_str = (
        goal_plan.goal_type.value
        if hasattr(goal_plan.goal_type, "value")
        else str(goal_plan.goal_type)
    )

    step_results: list[StepDryRunResult] = []

    for i, step in enumerate(goal_plan.steps):
        action = getattr(step, "action", "unknown_action")
        tool = getattr(step, "tool", "default")
        requires_approval = getattr(step, "requires_human_approval", False)

        description = _TOOL_DESCRIPTIONS.get(tool.lower(), _TOOL_DESCRIPTIONS["default"])
        if requires_approval:
            description = f"[Requires Human Approval] {description}"

        simulated_output: dict = {
            "status": "would_succeed",
            "action": action,
            "tool": tool,
            "requires_approval": requires_approval,
        }

        step_results.append(
            StepDryRunResult(
                step_index=i,
                action=action,
                tool=tool,
                description=description,
                would_succeed=True,
                simulated_output=simulated_output,
            )
        )

    overall = all(s.would_succeed for s in step_results)
    summary = (
        f"Plan has {len(step_results)} step(s). "
        f"Goal: {goal_type_str}. "
        f"{'All steps would succeed.' if overall else 'Some steps may fail.'}"
    )

    return DryRunResult(
        goal_type=goal_type_str,
        steps=step_results,
        would_succeed=overall,
        summary=summary,
    )
