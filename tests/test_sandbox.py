"""
Tests for the Secure Execution Sandbox.
Covers rate limiter, action validator, dry-run executor, sandbox runner.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
import time

from sandbox.validator import ActionValidator
from sandbox.rate_limiter import RateLimiter
from sandbox.dry_run import DryRunExecutor
from sandbox.runner import SandboxRunner
from sandbox.schemas import SandboxAction, ExecutionMode, ActionStatus


# ═══════════════════════════════════════════════════════════════════════════════
# ACTION VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionValidator:
    @pytest.fixture
    def validator(self):
        return ActionValidator()

    def test_valid_action(self, validator):
        action = SandboxAction(
            tool_name="gmail_tool",
            operation="send_email",
            parameters={"to": "user@example.com", "subject": "Hello"},
        )
        result = validator.validate(action)
        assert result.is_valid is True
        assert result.is_dangerous is False

    def test_dangerous_operation(self, validator):
        action = SandboxAction(
            tool_name="admin_tool",
            operation="bulk_delete",
        )
        result = validator.validate(action)
        assert result.is_valid is False
        assert result.is_dangerous is True

    def test_missing_tool_name(self, validator):
        action = SandboxAction(tool_name="", operation="send")
        result = validator.validate(action)
        assert result.is_valid is False

    def test_too_many_recipients(self, validator):
        action = SandboxAction(
            tool_name="gmail_tool",
            operation="send_email",
            parameters={"recipients": [f"user{i}@test.com" for i in range(100)]},
        )
        result = validator.validate(action)
        assert result.is_valid is False
        assert any("recipient" in v.lower() for v in result.violations)

    def test_injection_detection(self, validator):
        action = SandboxAction(
            tool_name="gmail_tool",
            operation="send_email",
            parameters={"body": "<script>alert('xss')</script>"},
        )
        result = validator.validate(action)
        assert result.is_valid is False
        assert result.is_dangerous is True

    def test_negative_amount(self, validator):
        action = SandboxAction(
            tool_name="payment_tool",
            operation="transfer",
            parameters={"amount": -100},
        )
        result = validator.validate(action)
        assert result.is_valid is False

    def test_warnings_for_anonymous(self, validator):
        action = SandboxAction(
            tool_name="test_tool",
            operation="test_op",
        )
        result = validator.validate(action)
        assert len(result.warnings) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    def test_allows_within_limit(self):
        limiter = RateLimiter(per_tool_max=5, window_seconds=60)
        for _ in range(5):
            status = limiter.check_and_record("test_tool")
            assert status.is_allowed is True

    def test_blocks_over_limit(self):
        limiter = RateLimiter(per_tool_max=3, window_seconds=60)
        for _ in range(3):
            limiter.check_and_record("test_tool")
        status = limiter.check_and_record("test_tool")
        assert status.is_allowed is False
        assert status.retry_after_seconds > 0

    def test_per_user_isolation(self):
        limiter = RateLimiter(per_tool_max=2, window_seconds=60)
        limiter.check_and_record("tool", "user_a")
        limiter.check_and_record("tool", "user_a")
        # user_a is at limit
        status_a = limiter.check("tool", "user_a")
        assert status_a.is_allowed is False
        # user_b should still be allowed
        status_b = limiter.check("tool", "user_b")
        assert status_b.is_allowed is True

    def test_reset(self):
        limiter = RateLimiter(per_tool_max=1, window_seconds=60)
        limiter.check_and_record("tool")
        limiter.reset("tool")
        status = limiter.check("tool")
        assert status.is_allowed is True

    def test_status_fields(self):
        limiter = RateLimiter(per_tool_max=10, window_seconds=30)
        status = limiter.check("my_tool", "my_user")
        assert status.tool_name == "my_tool"
        assert status.user_id == "my_user"
        assert status.max_allowed == 10
        assert status.window_seconds == 30


# ═══════════════════════════════════════════════════════════════════════════════
# DRY RUN EXECUTOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestDryRunExecutor:
    @pytest.fixture
    def executor(self):
        return DryRunExecutor()

    def test_dry_run_gmail(self, executor):
        action = SandboxAction(
            tool_name="gmail_tool",
            operation="send_email",
            parameters={"recipients": "user@example.com"},
        )
        result = executor.execute(action)
        assert result.status == ActionStatus.DRY_RUN
        assert result.mode == ExecutionMode.DRY_RUN
        assert "simulation" in result.output

    def test_dry_run_unknown_tool(self, executor):
        action = SandboxAction(
            tool_name="unknown_tool",
            operation="do_thing",
        )
        result = executor.execute(action)
        assert result.status == ActionStatus.DRY_RUN
        assert "unknown_tool" in result.output["simulation"]

    def test_dry_run_payment(self, executor):
        action = SandboxAction(
            tool_name="payment_tool",
            operation="transfer",
            parameters={"amount": "500", "recipient": "vendor@example.com"},
        )
        result = executor.execute(action)
        assert result.status == ActionStatus.DRY_RUN


# ═══════════════════════════════════════════════════════════════════════════════
# SANDBOX RUNNER (Integration)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSandboxRunner:
    @pytest.fixture
    def runner(self):
        return SandboxRunner()

    @pytest.mark.asyncio
    async def test_successful_execution(self, runner):
        action = SandboxAction(
            tool_name="gmail_tool",
            operation="send_email",
            parameters={"to": "user@test.com"},
            user_id="test_user",
        )
        result = await runner.execute(action)
        assert result.status == ActionStatus.COMPLETED
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_dry_run_mode(self, runner):
        action = SandboxAction(
            tool_name="gmail_tool",
            operation="send_email",
            parameters={"to": "user@test.com"},
            mode=ExecutionMode.DRY_RUN,
        )
        result = await runner.execute(action)
        assert result.status == ActionStatus.DRY_RUN

    @pytest.mark.asyncio
    async def test_blocked_by_validation(self, runner):
        action = SandboxAction(
            tool_name="admin_tool",
            operation="bulk_delete",
        )
        result = await runner.execute(action)
        assert result.status == ActionStatus.BLOCKED
        assert "validation" in result.error.lower()

    @pytest.mark.asyncio
    async def test_blocked_by_rate_limit(self, runner):
        runner.rate_limiter = RateLimiter(per_tool_max=1, window_seconds=60)
        action = SandboxAction(
            tool_name="test_tool",
            operation="test_op",
            user_id="user",
        )
        await runner.execute(action)  # first — allowed
        result = await runner.execute(action)  # second — blocked
        assert result.status == ActionStatus.BLOCKED
        assert "rate limit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_action_id_assigned(self, runner):
        action = SandboxAction(
            tool_name="test_tool",
            operation="test_op",
        )
        result = await runner.execute(action)
        assert result.action_id != ""
