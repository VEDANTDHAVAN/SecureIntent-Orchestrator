"""
Action Validator — Pre-execution safety checks.
Validates actions before they are executed in the sandbox.
"""

from __future__ import annotations

from shared.logger import get_logger
from shared.constants import DANGEROUS_OPERATIONS
from .schemas import SandboxAction, ValidationResult

logger = get_logger("sandbox.validator")


class ActionValidator:
    """
    Validates actions before execution.
    Checks for dangerous operations, parameter bounds, and schema validity.
    """

    # Maximum parameter value bounds
    MAX_RECIPIENTS = 50
    MAX_BULK_COUNT = 100

    def validate(self, action: SandboxAction) -> ValidationResult:
        """
        Validate an action before sandbox execution.

        Args:
            action: The SandboxAction to validate.

        Returns:
            ValidationResult with pass/fail and any violations.
        """
        violations: list[str] = []
        warnings: list[str] = []
        is_dangerous = False

        # ── Check 1: Dangerous operation ─────────────────────────────
        if action.operation in DANGEROUS_OPERATIONS:
            is_dangerous = True
            violations.append(
                f"Dangerous operation detected: '{action.operation}'"
            )

        # ── Check 2: Tool name validation ────────────────────────────
        if not action.tool_name or not action.tool_name.strip():
            violations.append("Tool name is missing or empty")

        # ── Check 3: Operation validation ────────────────────────────
        if not action.operation or not action.operation.strip():
            violations.append("Operation name is missing or empty")

        # ── Check 4: Parameter bounds ────────────────────────────────
        params = action.parameters

        # Check recipient count
        recipients = params.get("recipients", [])
        if isinstance(recipients, list) and len(recipients) > self.MAX_RECIPIENTS:
            violations.append(
                f"Too many recipients ({len(recipients)} > {self.MAX_RECIPIENTS})"
            )

        # Check bulk operation count
        count = params.get("count", 0)
        if isinstance(count, (int, float)) and count > self.MAX_BULK_COUNT:
            violations.append(
                f"Bulk count too high ({count} > {self.MAX_BULK_COUNT})"
            )

        # ── Check 5: Amount validation ───────────────────────────────
        amount = params.get("amount", 0)
        if isinstance(amount, (int, float)) and amount < 0:
            violations.append(f"Negative amount: {amount}")

        # ── Check 6: Suspicious parameter patterns ───────────────────
        for key, value in params.items():
            if isinstance(value, str):
                # Check for potential injection patterns
                if any(pattern in value.lower() for pattern in [
                    "<script", "javascript:", "data:text/html",
                    "; drop ", "' or '1'='1",
                ]):
                    violations.append(
                        f"Suspicious content in parameter '{key}'"
                    )
                    is_dangerous = True

        # ── Warnings (non-blocking) ──────────────────────────────────
        if not action.user_id:
            warnings.append("No user_id specified — action is anonymous")

        if not params:
            warnings.append("No parameters provided for the action")

        is_valid = len(violations) == 0

        if not is_valid:
            logger.warning(
                f"Action validation failed: tool={action.tool_name}, "
                f"op={action.operation}, violations={violations}"
            )

        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            warnings=warnings,
            is_dangerous=is_dangerous,
        )
