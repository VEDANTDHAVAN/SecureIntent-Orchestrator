"""
Sandbox Runner — Isolated tool execution with safety controls.
Wraps tool execution with validation, rate limiting, and dry-run support.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from shared.logger import get_logger, audit_log
from shared.exceptions import (
    RateLimitExceededError,
    SandboxExecutionError,
    ValidationError,
)
from .schemas import (
    SandboxAction, SandboxResult,
    ActionStatus, ExecutionMode,
)
from .validator import ActionValidator
from .rate_limiter import RateLimiter
from .dry_run import DryRunExecutor

logger = get_logger("sandbox.runner")


class SandboxRunner:
    """
    Secure sandbox for tool execution.
    
    Wraps every tool call with:
    1. Pre-execution validation (dangerous ops, parameter checks)
    2. Rate limiting (per-tool, per-user)
    3. Dry-run mode support
    4. Execution logging and audit trail
    """

    def __init__(self):
        self.validator = ActionValidator()
        self.rate_limiter = RateLimiter()
        self.dry_run_executor = DryRunExecutor()
        # Registry of actual tool executors
        self._tool_registry: dict[str, object] = {}

    def register_tool(self, tool_name: str, executor: object):
        """Register a tool executor for live execution."""
        self._tool_registry[tool_name] = executor
        logger.info(f"Registered tool: {tool_name}")

    async def execute(self, action: SandboxAction) -> SandboxResult:
        """
        Execute an action in the sandbox with all safety controls.

        Pipeline:
            1. Assign action ID
            2. Validate action
            3. Check rate limits
            4. Execute (dry-run or live)
            5. Log and return result

        Args:
            action: SandboxAction to execute.

        Returns:
            SandboxResult with execution outcome.
        """
        start_time = time.time()

        # Assign action ID if not set
        if not action.action_id:
            action.action_id = str(uuid.uuid4())

        logger.info(
            f"Sandbox execute: [{action.action_id}] "
            f"{action.tool_name}.{action.operation} "
            f"(mode={action.mode.value})"
        )

        # ── Step 1: Validate ─────────────────────────────────────────
        validation = self.validator.validate(action)
        if not validation.is_valid:
            audit_log(
                f"Action validation FAILED: {action.tool_name}.{action.operation}",
                action_id=action.action_id,
                violations=validation.violations,
            )
            return SandboxResult(
                action_id=action.action_id,
                status=ActionStatus.BLOCKED,
                mode=action.mode,
                error=f"Validation failed: {'; '.join(validation.violations)}",
                validation=validation,
                execution_time_ms=self._elapsed_ms(start_time),
                timestamp=datetime.utcnow(),
            )

        # ── Step 2: Rate Limit ───────────────────────────────────────
        rate_status = self.rate_limiter.check_and_record(
            action.tool_name, action.user_id
        )
        if not rate_status.is_allowed:
            logger.warning(
                f"Rate limit exceeded: {action.tool_name} "
                f"(user={action.user_id})"
            )
            return SandboxResult(
                action_id=action.action_id,
                status=ActionStatus.BLOCKED,
                mode=action.mode,
                error=(
                    f"Rate limit exceeded for {action.tool_name}. "
                    f"Retry after {rate_status.retry_after_seconds}s"
                ),
                validation=validation,
                rate_limit=rate_status,
                execution_time_ms=self._elapsed_ms(start_time),
                timestamp=datetime.utcnow(),
            )

        # ── Step 3: Dry Run ──────────────────────────────────────────
        if action.mode == ExecutionMode.DRY_RUN:
            result = self.dry_run_executor.execute(action)
            result.validation = validation
            result.rate_limit = rate_status
            result.execution_time_ms = self._elapsed_ms(start_time)
            return result

        # ── Step 4: Live Execution ───────────────────────────────────
        try:
            output = await self._execute_tool(action)
            elapsed = self._elapsed_ms(start_time)

            audit_log(
                f"Action executed: {action.tool_name}.{action.operation}",
                action_id=action.action_id,
                user_id=action.user_id,
                execution_time_ms=elapsed,
            )

            return SandboxResult(
                action_id=action.action_id,
                status=ActionStatus.COMPLETED,
                mode=ExecutionMode.LIVE,
                output=output,
                validation=validation,
                rate_limit=rate_status,
                execution_time_ms=elapsed,
                timestamp=datetime.utcnow(),
            )

        except Exception as e:
            elapsed = self._elapsed_ms(start_time)
            logger.error(
                f"Sandbox execution failed: {action.tool_name}.{action.operation} → {e}"
            )

            return SandboxResult(
                action_id=action.action_id,
                status=ActionStatus.FAILED,
                mode=ExecutionMode.LIVE,
                error=str(e),
                validation=validation,
                rate_limit=rate_status,
                execution_time_ms=elapsed,
                timestamp=datetime.utcnow(),
            )

    async def _execute_tool(self, action: SandboxAction) -> str:
        """
        Execute the actual tool. Looks up the registered executor.
        Falls back to a stub if no executor is registered.
        """
        executor = self._tool_registry.get(action.tool_name)
        if executor and hasattr(executor, "execute"):
            return await executor.execute(
                action.operation, action.parameters
            )

        # Stub execution if no tool is registered
        return (
            f"Executed: {action.tool_name}.{action.operation} "
            f"with params={action.parameters}"
        )

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return round((time.time() - start) * 1000, 2)
