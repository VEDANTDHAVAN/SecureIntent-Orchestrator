"""
Dry Run Executor — Simulated tool execution with no side effects.
Returns what *would* happen without actually performing the action.
"""

from __future__ import annotations

from datetime import datetime

from shared.logger import get_logger
from .schemas import SandboxAction, SandboxResult, ActionStatus, ExecutionMode

logger = get_logger("sandbox.dry_run")


class DryRunExecutor:
    """
    Simulates tool execution in dry-run mode.
    No actual side effects are produced — only a projection
    of what would happen is returned.
    """

    # Simulated outcomes per tool type
    TOOL_SIMULATIONS = {
        "gmail_tool": {
            "send_email": "Would send email to {recipients}",
            "reply": "Would reply to thread {thread_id}",
            "forward": "Would forward email to {recipients}",
            "delete": "Would delete email {email_id}",
            "label": "Would apply label '{label}' to {email_id}",
        },
        "calendar_tool": {
            "create_event": "Would create event '{title}' on {date}",
            "update_event": "Would update event {event_id}",
            "delete_event": "Would delete event {event_id}",
            "invite": "Would send invitation to {attendees}",
        },
        "payment_tool": {
            "transfer": "Would transfer ${amount} to {recipient}",
            "invoice": "Would generate invoice for ${amount}",
        },
        "slack_tool": {
            "send_message": "Would send message to {channel}",
            "create_channel": "Would create channel '{name}'",
        },
    }

    def execute(self, action: SandboxAction) -> SandboxResult:
        """
        Simulate execution and return projected outcome.

        Args:
            action: The SandboxAction to simulate.

        Returns:
            SandboxResult with dry-run status and simulated output.
        """
        simulation = self._get_simulation(action)

        logger.info(
            f"[DRY RUN] {action.tool_name}.{action.operation}: {simulation}"
        )

        return SandboxResult(
            action_id=action.action_id,
            status=ActionStatus.DRY_RUN,
            mode=ExecutionMode.DRY_RUN,
            output={
                "simulation": simulation,
                "tool": action.tool_name,
                "operation": action.operation,
                "parameters": action.parameters,
                "note": "This is a dry-run simulation. No actions were performed.",
            },
            error="",
            execution_time_ms=0.0,
            timestamp=datetime.utcnow(),
        )

    def _get_simulation(self, action: SandboxAction) -> str:
        """Generate a human-readable simulation description."""
        tool_sims = self.TOOL_SIMULATIONS.get(action.tool_name, {})
        template = tool_sims.get(
            action.operation,
            f"Would execute {action.tool_name}.{action.operation}",
        )

        # Try to format with parameters
        try:
            return template.format(**action.parameters)
        except (KeyError, IndexError):
            return template
