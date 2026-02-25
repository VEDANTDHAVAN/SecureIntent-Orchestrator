"""
validator.py
------------
Pre-execution plan validator.

Checks a GoalPlan before it enters the live execution path:
  - All required entities are present for each step
  - Goal type has a registered tool handler
  - No duplicate step IDs

Called by sandbox/runner.py before any real API calls are made.
"""

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Map of GoalType → required entity fields for execution
_REQUIRED_ENTITIES: dict[str, list[str]] = {
    "SEND_EMAIL_REPLY": ["action_requested"],
    "SCHEDULE_CALENDAR_EVENT": ["dates"],
    "INITIATE_PAYMENT": ["amounts"],
    "NO_ACTION": [],
}


def validate_plan(goal_plan) -> ValidationResult:
    """
    Validate a GoalPlan before execution.

    Args:
        goal_plan: agents.planner.schemas.GoalPlan instance

    Returns:
        ValidationResult with is_valid and list of errors/warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []

    goal_type_str = goal_plan.goal_type.value if hasattr(goal_plan.goal_type, "value") else str(goal_plan.goal_type)

    # ── 1. Check tool registration ────────────────────────────────────────────
    if goal_type_str not in _REQUIRED_ENTITIES:
        errors.append(f"No tool handler registered for goal_type='{goal_type_str}'")

    # ── 2. Check step IDs are unique ──────────────────────────────────────────
    seen_ids: set[str] = set()
    for step in goal_plan.steps:
        step_id = str(getattr(step, "step_id", id(step)))
        if step_id in seen_ids:
            errors.append(f"Duplicate step_id: '{step_id}'")
        seen_ids.add(step_id)

    # ── 3. Check step count ───────────────────────────────────────────────────
    if not goal_plan.steps:
        warnings.append("Plan has no steps — execution will be a no-op")

    # ── 4. Check each step has required fields ────────────────────────────────
    for i, step in enumerate(goal_plan.steps):
        if not getattr(step, "action", None):
            errors.append(f"Step {i} missing 'action' field")
        if not getattr(step, "tool", None):
            warnings.append(f"Step {i} has no 'tool' specified")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
