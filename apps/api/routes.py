"""
API Routes for Security, Risk & Guardrails.
Provides endpoints for risk scoring, policy evaluation,
sandbox execution, and approval workflow.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from engines.trust_risk.scorer import RiskScorer
from engines.trust_risk.schemas import EmailSecurityContext
from engines.trust_risk.url_scanner import URLScanner
from engines.trust_risk.attachment_scanner import AttachmentScanner

from engines.policy_guardrails.policy_engine import PolicyEngine
from engines.policy_guardrails.schemas import PolicyContext

from engines.approval.approval_manager import ApprovalManager
from engines.approval.schemas import ApprovalStatus

from sandbox.runner import SandboxRunner
from sandbox.schemas import SandboxAction, ExecutionMode

from .schemas import (
    RiskScoreRequest,
    URLScanRequest,
    AttachmentScanRequest,
    PolicyEvaluateRequest,
    SandboxExecuteRequest,
    ApprovalCreateRequest,
    ApprovalDecideRequest,
)

# ─── Initialize engines ──────────────────────────────────────────────────────
risk_scorer = RiskScorer()
url_scanner = URLScanner()
attachment_scanner = AttachmentScanner()
policy_engine = PolicyEngine()
sandbox_runner = SandboxRunner()
approval_manager = ApprovalManager()

# ─── Router ───────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1", tags=["Security & Risk"])


# ═══════════════════════════════════════════════════════════════════════════════
# RISK SCORING
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/risk/score")
async def score_email_risk(request: RiskScoreRequest):
    """
    Score an email for security risk (0–100).
    Runs SPF/DKIM, URL, attachment, header, and domain checks.
    """
    try:
        context = EmailSecurityContext(
            sender_email=request.sender_email,
            sender_domain=request.sender_domain,
            subject=request.subject,
            body=request.body,
            headers=request.headers,
            urls=request.urls,
            attachments=request.attachments,
        )
        report = await risk_scorer.score(context)
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/scan-url")
async def scan_urls(request: URLScanRequest):
    """Scan a list of URLs for threats."""
    try:
        result = await url_scanner.scan(request.urls)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/scan-attachment")
async def scan_attachment(request: AttachmentScanRequest):
    """Scan attachment metadata for threats."""
    try:
        result = attachment_scanner.scan(
            filename=request.filename,
            content_hash=request.content_hash,
            file_size=request.file_size,
        )
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# POLICY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/policy/evaluate")
async def evaluate_policy(request: PolicyEvaluateRequest):
    """Evaluate policies against a context and return the decision."""
    try:
        context = PolicyContext(
            intent_type=request.intent_type,
            action=request.action,
            sender_email=request.sender_email,
            sender_domain=request.sender_domain,
            recipient_domain=request.recipient_domain,
            risk_score=request.risk_score,
            has_attachments=request.has_attachments,
            attachment_count=request.attachment_count,
            url_count=request.url_count,
            is_external=request.is_external,
            amount=request.amount,
            custom_fields=request.custom_fields,
        )
        decision = policy_engine.evaluate(context)
        return decision.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policy/rules")
async def list_policy_rules():
    """List all active policy rules."""
    policies = policy_engine.get_all_policies()
    return {
        "total": len(policies),
        "policies": [p.model_dump() for p in policies],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SANDBOX
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/sandbox/execute")
async def sandbox_execute(request: SandboxExecuteRequest):
    """Execute an action in the secure sandbox."""
    try:
        action = SandboxAction(
            tool_name=request.tool_name,
            operation=request.operation,
            parameters=request.parameters,
            user_id=request.user_id,
            mode=ExecutionMode.DRY_RUN if request.dry_run else ExecutionMode.LIVE,
        )
        result = await sandbox_runner.execute(action)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sandbox/dry-run")
async def sandbox_dry_run(request: SandboxExecuteRequest):
    """Dry-run an action (no side effects)."""
    try:
        action = SandboxAction(
            tool_name=request.tool_name,
            operation=request.operation,
            parameters=request.parameters,
            user_id=request.user_id,
            mode=ExecutionMode.DRY_RUN,
        )
        result = await sandbox_runner.execute(action)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# APPROVAL WORKFLOW
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/approval/request")
async def create_approval_request(request: ApprovalCreateRequest):
    """Create a new approval request."""
    try:
        approval = approval_manager.create_request(
            action_type=request.action_type,
            action_description=request.action_description,
            risk_score=request.risk_score,
            risk_level=request.risk_level,
            policy_ids=request.policy_ids,
            context=request.context,
            requester_id=request.requester_id,
            approver_id=request.approver_id,
            timeout_minutes=request.timeout_minutes,
        )
        return approval.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approval/{request_id}/decide")
async def submit_approval_decision(
    request_id: str, request: ApprovalDecideRequest
):
    """Submit an approval decision (approve/reject)."""
    try:
        decision_status = ApprovalStatus(request.decision)
        decision = approval_manager.decide(
            request_id=request_id,
            decision=decision_status,
            decided_by=request.decided_by,
            reason=request.reason,
        )
        return decision.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/approval/{request_id}")
async def get_approval_status(request_id: str):
    """Get the status of an approval request."""
    approval = approval_manager.get_request(request_id)
    if not approval:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request not found: {request_id}",
        )
    return approval.model_dump()


@router.get("/approval/pending/all")
async def list_pending_approvals():
    """List all pending approval requests."""
    pending = approval_manager.get_pending_requests()
    return {
        "total": len(pending),
        "requests": [r.model_dump() for r in pending],
    }
