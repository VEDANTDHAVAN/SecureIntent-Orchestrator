"""
Tests for the Approval Workflow engine.
Covers request creation, decision processing, escalation, and logging.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timedelta

from engines.approval.approval_manager import ApprovalManager
from engines.approval.decision_logger import DecisionLogger
from engines.approval.schemas import (
    ApprovalStatus, EscalationLevel, ApprovalRequest,
)


class TestApprovalManager:
    @pytest.fixture
    def manager(self):
        return ApprovalManager()

    def test_create_request(self, manager):
        request = manager.create_request(
            action_type="payment",
            action_description="Transfer $5000 to vendor",
            risk_score=65.0,
            risk_level="high",
            requester_id="user_123",
        )
        assert request.request_id != ""
        assert request.status == ApprovalStatus.PENDING
        assert request.escalation_level == EscalationLevel.L1_DIRECT
        assert request.risk_score == 65.0

    def test_approve_request(self, manager):
        request = manager.create_request(
            action_type="email",
            action_description="Send external email",
        )
        decision = manager.decide(
            request_id=request.request_id,
            decision=ApprovalStatus.APPROVED,
            decided_by="admin",
            reason="Verified legitimate",
        )
        assert decision.decision == ApprovalStatus.APPROVED
        assert decision.decided_by == "admin"
        # Should be removed from pending
        assert manager.get_request(request.request_id) is None

    def test_reject_request(self, manager):
        request = manager.create_request(
            action_type="payment",
            action_description="Suspicious transfer",
        )
        decision = manager.decide(
            request_id=request.request_id,
            decision=ApprovalStatus.REJECTED,
            decided_by="security",
            reason="Looks fraudulent",
        )
        assert decision.decision == ApprovalStatus.REJECTED

    def test_decide_nonexistent_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.decide(
                request_id="fake-id",
                decision=ApprovalStatus.APPROVED,
            )

    def test_decide_already_decided_raises(self, manager):
        request = manager.create_request(
            action_type="test", action_description="test",
        )
        manager.decide(request.request_id, ApprovalStatus.APPROVED)
        with pytest.raises(ValueError):
            manager.decide(request.request_id, ApprovalStatus.APPROVED)

    def test_escalation(self, manager):
        request = manager.create_request(
            action_type="payment",
            action_description="Large transfer",
        )
        escalated = manager.escalate(request.request_id)
        assert escalated.escalation_level == EscalationLevel.L2_MANAGER
        assert escalated.status == ApprovalStatus.ESCALATED

    def test_multi_level_escalation(self, manager):
        request = manager.create_request(
            action_type="payment",
            action_description="Very large transfer",
        )
        # L1 → L2
        manager.escalate(request.request_id)
        req = manager.get_request(request.request_id)
        assert req.escalation_level == EscalationLevel.L2_MANAGER

        # L2 → L3
        manager.escalate(request.request_id)
        req = manager.get_request(request.request_id)
        assert req.escalation_level == EscalationLevel.L3_SECURITY

        # L3 → AUTO_BLOCK (max escalation → auto-reject)
        result = manager.escalate(request.request_id)
        assert result.status == ApprovalStatus.REJECTED

    def test_get_pending_requests(self, manager):
        manager.create_request(action_type="a", action_description="a")
        manager.create_request(action_type="b", action_description="b")
        pending = manager.get_pending_requests()
        assert len(pending) == 2

    def test_escalate_nonexistent_raises(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.escalate("fake-id")


class TestDecisionLogger:
    @pytest.fixture
    def logger(self, tmp_path):
        return DecisionLogger(log_dir=tmp_path / "test_decisions")

    def test_log_request_created(self, logger):
        request = ApprovalRequest(
            request_id="test-123",
            action_type="payment",
            action_description="Test payment",
            risk_score=50.0,
        )
        logger.log_request_created(request)
        entries = logger.get_decisions_for_request("test-123")
        assert len(entries) == 1
        assert entries[0]["event"] == "approval_request_created"

    def test_log_decision(self, logger):
        from engines.approval.schemas import ApprovalDecision
        decision = ApprovalDecision(
            request_id="test-456",
            decision=ApprovalStatus.APPROVED,
            decided_by="admin",
            reason="OK",
        )
        logger.log_decision(decision)
        entries = logger.get_decisions_for_request("test-456")
        assert len(entries) == 1
        assert entries[0]["decision"] == "approved"

    def test_log_escalation(self, logger):
        logger.log_escalation("test-789", "l1_direct", "l2_manager", "Timeout")
        entries = logger.get_decisions_for_request("test-789")
        assert len(entries) == 1
        assert entries[0]["event"] == "approval_escalated"

    def test_empty_log(self, logger):
        entries = logger.get_decisions_for_request("nonexistent")
        assert entries == []
