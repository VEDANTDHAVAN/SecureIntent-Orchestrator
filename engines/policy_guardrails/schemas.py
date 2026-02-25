"""
Pydantic schemas for the Policy Engine.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class PolicyAction(str, Enum):
    """Action to take when a policy matches."""
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"
    LOG_ONLY = "log_only"


class PolicyPriority(str, Enum):
    """Priority levels for policy rules."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def numeric(self) -> int:
        return {"low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class Policy(BaseModel):
    """A single policy rule definition."""
    id: str
    name: str
    condition: str  # Condition expression string
    action: PolicyAction
    priority: PolicyPriority = PolicyPriority.MEDIUM
    enabled: bool = True
    description: str = ""


class PolicyContext(BaseModel):
    """
    Context against which policies are evaluated.
    Contains all variables that policy conditions can reference.
    """
    intent_type: str = ""
    action: str = ""
    sender_email: str = ""
    sender_domain: str = ""
    recipient_domain: str = ""
    risk_score: float = 0.0
    has_attachments: bool = False
    attachment_count: int = 0
    url_count: int = 0
    is_external: bool = False
    amount: float = 0.0
    trusted_domains: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class PolicyMatch(BaseModel):
    """A single policy rule that matched the context."""
    policy_id: str
    policy_name: str
    action: PolicyAction
    priority: PolicyPriority
    condition: str


class PolicyDecision(BaseModel):
    """
    Aggregated decision from evaluating all policy rules.
    The most restrictive matching rule wins.
    """
    allowed: bool = True
    action: PolicyAction = PolicyAction.ALLOW
    matched_policies: list[PolicyMatch] = Field(default_factory=list)
    reason: str = ""
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    total_rules_evaluated: int = 0
