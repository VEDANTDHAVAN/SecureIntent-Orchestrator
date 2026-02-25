"""
Pydantic schemas for the Approval Workflow engine.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class EscalationLevel(str, Enum):
    L1_DIRECT = "l1_direct"         # Direct approver
    L2_MANAGER = "l2_manager"       # Manager escalation
    L3_SECURITY = "l3_security"     # Security team
    AUTO_BLOCK = "auto_block"       # Auto-block after max escalation


class ApprovalRequest(BaseModel):
    """A request for human approval of an action."""
    request_id: str = ""
    action_type: str = ""
    action_description: str = ""
    risk_score: float = 0.0
    risk_level: str = ""
    policy_ids: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    requester_id: str = ""
    approver_id: str = ""
    escalation_level: EscalationLevel = EscalationLevel.L1_DIRECT
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    timeout_minutes: int = 60


class ApprovalDecision(BaseModel):
    """A decision made on an approval request."""
    request_id: str
    decision: ApprovalStatus
    decided_by: str = ""
    reason: str = ""
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EscalationPath(BaseModel):
    """Defines the escalation chain for an approval request."""
    levels: list[EscalationLevel] = Field(
        default_factory=lambda: [
            EscalationLevel.L1_DIRECT,
            EscalationLevel.L2_MANAGER,
            EscalationLevel.L3_SECURITY,
            EscalationLevel.AUTO_BLOCK,
        ]
    )
    timeout_per_level_minutes: int = 60
