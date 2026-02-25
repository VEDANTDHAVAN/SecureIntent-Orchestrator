"""
API request/response schemas for the Security, Risk & Guardrails endpoints.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ─── Risk Scoring ─────────────────────────────────────────────────────────────

class RiskScoreRequest(BaseModel):
    """Request to score an email for risk."""
    sender_email: str
    sender_domain: str = ""
    subject: str = ""
    body: str = ""
    headers: dict = Field(default_factory=dict)
    urls: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)


class URLScanRequest(BaseModel):
    """Request to scan URLs."""
    urls: list[str]


class AttachmentScanRequest(BaseModel):
    """Request to scan attachment metadata."""
    filename: str
    content_hash: str = ""
    file_size: int = 0


# ─── Policy ───────────────────────────────────────────────────────────────────

class PolicyEvaluateRequest(BaseModel):
    """Request to evaluate policies against a context."""
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
    custom_fields: dict[str, Any] = Field(default_factory=dict)


# ─── Sandbox ──────────────────────────────────────────────────────────────────

class SandboxExecuteRequest(BaseModel):
    """Request to execute an action in the sandbox."""
    tool_name: str
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    user_id: str = ""
    dry_run: bool = False


# ─── Approval ─────────────────────────────────────────────────────────────────

class ApprovalCreateRequest(BaseModel):
    """Request to create an approval request."""
    action_type: str
    action_description: str
    risk_score: float = 0.0
    risk_level: str = ""
    policy_ids: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    requester_id: str = ""
    approver_id: str = ""
    timeout_minutes: int = 60


class ApprovalDecideRequest(BaseModel):
    """Request to submit an approval decision."""
    decision: str  # "approved" or "rejected"
    decided_by: str = ""
    reason: str = ""
