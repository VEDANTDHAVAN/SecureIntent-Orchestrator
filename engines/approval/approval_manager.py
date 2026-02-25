"""
Approval Manager — Human-in-the-loop decision system.
Creates approval requests, tracks decisions, handles escalation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from shared.logger import get_logger
from shared.constants import DEFAULT_APPROVAL_TIMEOUT_MINUTES, MAX_ESCALATION_LEVELS
from .schemas import (
    ApprovalRequest, ApprovalDecision, ApprovalStatus,
    EscalationLevel, EscalationPath,
)
from .decision_logger import DecisionLogger

logger = get_logger("approval.manager")


class ApprovalManager:
    """
    Manages the approval workflow lifecycle:
    1. Create approval requests
    2. Track pending approvals
    3. Process decisions (approve/reject)
    4. Handle escalation on timeout
    5. Log everything to the audit trail
    """

    def __init__(self):
        self.decision_logger = DecisionLogger()
        self.escalation_path = EscalationPath()
        # In-memory store for pending requests
        # In production, use a database
        self._pending: dict[str, ApprovalRequest] = {}

    def create_request(
        self,
        action_type: str,
        action_description: str,
        risk_score: float = 0.0,
        risk_level: str = "",
        policy_ids: list[str] | None = None,
        context: dict | None = None,
        requester_id: str = "",
        approver_id: str = "",
        timeout_minutes: int = DEFAULT_APPROVAL_TIMEOUT_MINUTES,
    ) -> ApprovalRequest:
        """
        Create a new approval request.

        Returns:
            ApprovalRequest with a unique request_id.
        """
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            action_type=action_type,
            action_description=action_description,
            risk_score=risk_score,
            risk_level=risk_level,
            policy_ids=policy_ids or [],
            context=context or {},
            requester_id=requester_id,
            approver_id=approver_id,
            escalation_level=EscalationLevel.L1_DIRECT,
            status=ApprovalStatus.PENDING,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=timeout_minutes),
            timeout_minutes=timeout_minutes,
        )

        self._pending[request.request_id] = request
        self.decision_logger.log_request_created(request)

        logger.info(
            f"Approval request created: {request.request_id} "
            f"for '{action_description}' (risk={risk_score})"
        )

        return request

    def decide(
        self,
        request_id: str,
        decision: ApprovalStatus,
        decided_by: str = "",
        reason: str = "",
    ) -> ApprovalDecision:
        """
        Submit a decision on a pending approval request.

        Args:
            request_id: The ID of the approval request.
            decision: APPROVED or REJECTED.
            decided_by: Who made the decision.
            reason: Optional reason for the decision.

        Returns:
            ApprovalDecision record.

        Raises:
            ValueError: If request not found or already decided.
        """
        request = self._pending.get(request_id)
        if not request:
            raise ValueError(f"Approval request not found: {request_id}")

        if request.status not in (ApprovalStatus.PENDING, ApprovalStatus.ESCALATED):
            raise ValueError(
                f"Request {request_id} is already {request.status.value}"
            )

        # Check expiration
        if request.expires_at and datetime.utcnow() > request.expires_at:
            request.status = ApprovalStatus.EXPIRED
            self.decision_logger.log_expiration(request_id)
            raise ValueError(f"Request {request_id} has expired")

        # Record decision
        approval_decision = ApprovalDecision(
            request_id=request_id,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
            decided_at=datetime.utcnow(),
        )

        # Update request status
        request.status = decision
        self.decision_logger.log_decision(approval_decision)

        logger.info(
            f"Approval decision: {request_id} → {decision.value} "
            f"by {decided_by}"
        )

        # Remove from pending if terminal state
        if decision in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            self._pending.pop(request_id, None)

        return approval_decision

    def escalate(self, request_id: str) -> ApprovalRequest:
        """
        Escalate a pending request to the next level.

        Escalation chain: L1_DIRECT → L2_MANAGER → L3_SECURITY → AUTO_BLOCK

        Returns:
            Updated ApprovalRequest.

        Raises:
            ValueError: If request not found or already at max escalation.
        """
        request = self._pending.get(request_id)
        if not request:
            raise ValueError(f"Approval request not found: {request_id}")

        levels = self.escalation_path.levels
        current_idx = levels.index(request.escalation_level)

        if current_idx >= len(levels) - 1:
            # Max escalation reached — auto-block
            request.status = ApprovalStatus.REJECTED
            self.decision_logger.log_decision(
                ApprovalDecision(
                    request_id=request_id,
                    decision=ApprovalStatus.REJECTED,
                    decided_by="system",
                    reason="Auto-blocked: max escalation reached",
                )
            )
            self._pending.pop(request_id, None)
            return request

        # Escalate to next level
        old_level = request.escalation_level
        new_level = levels[current_idx + 1]

        # If next level is AUTO_BLOCK, auto-reject immediately
        if new_level == EscalationLevel.AUTO_BLOCK:
            request.escalation_level = new_level
            request.status = ApprovalStatus.REJECTED
            self.decision_logger.log_decision(
                ApprovalDecision(
                    request_id=request_id,
                    decision=ApprovalStatus.REJECTED,
                    decided_by="system",
                    reason=f"Auto-blocked: escalated past {old_level.value}",
                )
            )
            self._pending.pop(request_id, None)
            return request

        request.escalation_level = new_level
        request.status = ApprovalStatus.ESCALATED

        # Reset timeout for new level
        request.expires_at = datetime.utcnow() + timedelta(
            minutes=self.escalation_path.timeout_per_level_minutes
        )

        self.decision_logger.log_escalation(
            request_id=request_id,
            from_level=old_level.value,
            to_level=new_level.value,
            reason=f"Escalated due to timeout at {old_level.value}",
        )

        logger.info(
            f"Request escalated: {request_id} "
            f"{old_level.value} → {new_level.value}"
        )

        return request

    def check_expirations(self) -> list[str]:
        """
        Check all pending requests for expiration and auto-escalate.
        Returns list of escalated/expired request IDs.
        """
        now = datetime.utcnow()
        affected: list[str] = []

        for request_id, request in list(self._pending.items()):
            if request.expires_at and now > request.expires_at:
                try:
                    self.escalate(request_id)
                    affected.append(request_id)
                except ValueError:
                    pass

        return affected

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        """Get a pending approval request by ID."""
        return self._pending.get(request_id)

    def get_pending_requests(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return list(self._pending.values())
