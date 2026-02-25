"""
middleware.py
-------------
Integration shim that wires the PolicyEngine into the agent pipeline.

Called from:
  - webhooks._run_agent_pipeline()  (automatic email processing)
  - agent_routes.POST /plans/{id}/execute  (manual execution)

Usage:
    from engines.policy_guardrails.middleware import apply_policy_gate

    result = apply_policy_gate(
        goal_plan=goal_plan,
        risk_score=risk_score,
        intent=intent_obj,
    )
    if result.decision == PolicyDecision.BLOCK:
        # stop here, persist explanation
    elif result.decision == PolicyDecision.REQUIRE_APPROVAL:
        # persist plan as pending_approval, notify human
"""

from engines.policy_guardrails.policy_engine import PolicyDecision, PolicyEngine, PolicyResult
from engines.trust_risk.scorer import RiskScore

# Module-level singleton — rules.yaml loaded once at startup
_engine = PolicyEngine()


def apply_policy_gate(
    *,
    goal_type: str,
    risk_score: RiskScore,
    requires_external_action: bool,
    confidence: float,
) -> PolicyResult:
    """
    Evaluate the policy engine against a planned action.

    Args:
        goal_type: GoalType value (e.g. "SEND_EMAIL_REPLY")
        risk_score: RiskScore from the trust/risk scorer
        requires_external_action: from intent.requires_external_action
        confidence: intent confidence score

    Returns:
        PolicyResult with decision (allow / require_approval / block).
    """
    return _engine.evaluate(
        goal_type=goal_type,
        risk_level=risk_score.level.value,
        requires_external_action=requires_external_action,
        confidence=confidence,
        spf=risk_score.spf,
        dkim=risk_score.dkim,
        flagged_urls=risk_score.flagged_urls,
    )


__all__ = ["apply_policy_gate", "PolicyDecision", "PolicyResult"]
