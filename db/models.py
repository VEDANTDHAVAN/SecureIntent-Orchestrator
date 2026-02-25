"""
Pydantic models matching the database schema.
Used for application-level data transfer (no ORM — wire up separately).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class RiskAssessmentRecord(BaseModel):
    """Maps to the risk_assessments table."""
    id: Optional[int] = None
    email_id: str = ""
    sender_email: str = ""
    sender_domain: str = ""
    risk_score: float = 0.0
    risk_level: str = "low"
    recommended_action: str = "auto_approve"
    spf_pass: bool = False
    dkim_pass: bool = False
    suspicious_url_count: int = 0
    malicious_attachment_count: int = 0
    header_anomaly_count: int = 0
    risk_factors: list[str] = Field(default_factory=list)
    full_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PolicyDecisionRecord(BaseModel):
    """Maps to the policy_decisions table."""
    id: Optional[int] = None
    action_type: str = ""
    policy_action: str = "allow"
    matched_policy_ids: list[str] = Field(default_factory=list)
    matched_policy_names: list[str] = Field(default_factory=list)
    reason: str = ""
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    total_rules_evaluated: int = 0
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class ApprovalRequestRecord(BaseModel):
    """Maps to the approval_requests table."""
    id: Optional[int] = None
    request_id: str = ""
    action_type: str = ""
    action_description: str = ""
    risk_score: float = 0.0
    risk_level: str = ""
    policy_ids: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    requester_id: str = ""
    approver_id: str = ""
    escalation_level: str = "l1_direct"
    status: str = "pending"
    timeout_minutes: int = 60
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class ApprovalDecisionRecord(BaseModel):
    """Maps to the approval_decisions table."""
    id: Optional[int] = None
    request_id: str = ""
    decision: str = ""
    decided_by: str = ""
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionAuditRecord(BaseModel):
    """Maps to the execution_audit_log table."""
    id: Optional[int] = None
    action_id: str = ""
    tool_name: str = ""
    operation: str = ""
    user_id: str = ""
    execution_mode: str = "live"
    status: str = "pending"
    parameters: dict[str, Any] = Field(default_factory=dict)
    output: Optional[dict[str, Any]] = None
    error: str = ""
    execution_time_ms: float = 0.0
    validation_passed: bool = True
    rate_limited: bool = False
    executed_at: datetime = Field(default_factory=datetime.utcnow)
