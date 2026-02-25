"""
Tests for the Policy Engine.
Covers YAML rule loading, policy evaluation, condition matching, priority ordering.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from engines.policy_guardrails.policy_engine import PolicyEngine
from engines.policy_guardrails.schemas import (
    PolicyContext, PolicyAction, PolicyPriority,
)


class TestPolicyEngine:
    @pytest.fixture
    def engine(self):
        return PolicyEngine()

    def test_loads_rules_from_yaml(self, engine):
        assert len(engine.policies) > 0
        assert len(engine.trusted_domains) > 0

    def test_get_all_policies(self, engine):
        policies = engine.get_all_policies()
        assert isinstance(policies, list)
        assert len(policies) > 0

    def test_get_policy_by_id(self, engine):
        policy = engine.get_policy_by_id("block_auto_payment")
        assert policy is not None
        assert policy.name == "Never auto-pay invoices"
        assert policy.action == PolicyAction.REQUIRE_APPROVAL

    def test_payment_request_requires_approval(self, engine):
        context = PolicyContext(intent_type="payment_request")
        decision = engine.evaluate(context)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL
        assert len(decision.matched_policies) > 0

    def test_high_risk_score_blocked(self, engine):
        context = PolicyContext(risk_score=90)
        decision = engine.evaluate(context)
        assert decision.action == PolicyAction.BLOCK
        assert decision.allowed is False

    def test_medium_risk_requires_approval(self, engine):
        context = PolicyContext(risk_score=55)
        decision = engine.evaluate(context)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_low_risk_allowed(self, engine):
        context = PolicyContext(risk_score=10)
        decision = engine.evaluate(context)
        assert decision.allowed is True

    def test_external_email_requires_approval(self, engine):
        context = PolicyContext(
            action="send_email",
            is_external=True,
        )
        decision = engine.evaluate(context)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_many_attachments_flagged(self, engine):
        context = PolicyContext(attachment_count=5)
        decision = engine.evaluate(context)
        assert len(decision.matched_policies) > 0

    def test_most_restrictive_wins(self, engine):
        """High risk + payment = should block (not just require approval)."""
        context = PolicyContext(
            intent_type="payment_request",
            risk_score=85,
        )
        decision = engine.evaluate(context)
        assert decision.action == PolicyAction.BLOCK

    def test_no_matching_policies(self, engine):
        context = PolicyContext(
            intent_type="information_query",
            risk_score=5,
        )
        decision = engine.evaluate(context)
        assert decision.allowed is True
        assert decision.action == PolicyAction.ALLOW

    def test_total_rules_evaluated(self, engine):
        context = PolicyContext()
        decision = engine.evaluate(context)
        assert decision.total_rules_evaluated > 0

    def test_reload_rules(self, engine):
        original_count = len(engine.policies)
        engine.reload_rules()
        assert len(engine.policies) == original_count


class TestPolicyEngineEdgeCases:
    def test_missing_rules_file(self):
        engine = PolicyEngine(rules_path="/nonexistent/path.yaml")
        assert len(engine.policies) == 0

    def test_empty_context(self):
        engine = PolicyEngine()
        context = PolicyContext()
        decision = engine.evaluate(context)
        assert decision is not None
        assert decision.total_rules_evaluated > 0
