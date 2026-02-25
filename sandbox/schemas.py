"""
Pydantic schemas for the Secure Execution Sandbox.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    LIVE = "live"
    DRY_RUN = "dry_run"


class ActionStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    DRY_RUN = "dry_run"


class SandboxAction(BaseModel):
    """An action to be executed in the sandbox."""
    action_id: str = ""
    tool_name: str
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    user_id: str = ""
    mode: ExecutionMode = ExecutionMode.LIVE
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Result of pre-execution action validation."""
    is_valid: bool = True
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    is_dangerous: bool = False


class RateLimitStatus(BaseModel):
    """Current rate limit status for a tool/user."""
    tool_name: str
    user_id: str = ""
    is_allowed: bool = True
    current_count: int = 0
    max_allowed: int = 0
    window_seconds: int = 0
    retry_after_seconds: float = 0.0


class SandboxResult(BaseModel):
    """Result of a sandbox execution."""
    action_id: str = ""
    status: ActionStatus = ActionStatus.PENDING
    mode: ExecutionMode = ExecutionMode.LIVE
    output: Any = None
    error: str = ""
    execution_time_ms: float = 0.0
    validation: Optional[ValidationResult] = None
    rate_limit: Optional[RateLimitStatus] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
