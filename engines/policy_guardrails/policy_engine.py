"""
policy_engine.py
----------------
Rule-based policy engine that evaluates a GoalPlan against rules.yaml.

The LLM cannot override this layer. All execution decisions are made here.

Decision precedence (most restrictive wins):
  block > require_approval > allow
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"

    @classmethod
    def precedence(cls) -> list["PolicyDecision"]:
        """Most restrictive first."""
        return [cls.BLOCK, cls.REQUIRE_APPROVAL, cls.ALLOW]

    def is_more_restrictive_than(self, other: "PolicyDecision") -> bool:
        order = self.precedence()
        return order.index(self) < order.index(other)


@dataclass
class PolicyResult:
    decision: PolicyDecision
    triggered_rules: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_db_dict(self) -> dict:
        return {
            "policy_decision": self.decision.value,
            "triggered_rules": self.triggered_rules,
        }


_DEFAULT_RULES_PATH = Path(__file__).parent / "rules.yaml"


class PolicyEngine:
    """
    Loads rules.yaml and evaluates plans against it.

    Rules format:
        rules:
          - id: rule_id
            condition: { field: value, ... }
            action: block | require_approval | allow
    """

    def __init__(self, rules_path: Path = _DEFAULT_RULES_PATH):
        self._rules: list[dict[str, Any]] = []
        self._load(rules_path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            logger.warning("rules.yaml not found at %s — all plans will be allowed", path)
            return
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        self._rules = data.get("rules", [])
        logger.info("PolicyEngine loaded %d rules from %s", len(self._rules), path)

    def evaluate(
        self,
        *,
        goal_type: str,
        risk_level: str,
        requires_external_action: bool,
        confidence: float,
        spf: str = "none",
        dkim: str = "none",
        flagged_urls: list[str] | None = None,
    ) -> PolicyResult:
        """
        Evaluate all rules against the given inputs.

        Args:
            goal_type: GoalType enum value (e.g. "SEND_EMAIL_REPLY")
            risk_level: RiskLevel enum value (e.g. "critical")
            requires_external_action: from Intent.requires_external_action
            confidence: intent confidence score (0.0–1.0)
            spf / dkim: authentication results ("pass"|"fail"|"none")
            flagged_urls: list of suspicious URLs found in email

        Returns:
            PolicyResult with most-restrictive decision and all triggered rule IDs.
        """
        decision = PolicyDecision.ALLOW
        triggered: list[str] = []

        for rule in self._rules:
            rule_id: str = rule.get("id", "unnamed")
            condition: dict = rule.get("condition", {})
            action_str: str = rule.get("action", "allow")

            try:
                action = PolicyDecision(action_str)
            except ValueError:
                logger.warning("Unknown action '%s' in rule %s", action_str, rule_id)
                continue

            if self._matches(condition, goal_type=goal_type, risk_level=risk_level,
                             requires_external_action=requires_external_action,
                             confidence=confidence, spf=spf, dkim=dkim,
                             flagged_urls=flagged_urls or []):
                triggered.append(rule_id)
                if action.is_more_restrictive_than(decision):
                    decision = action

        explanation = self._build_explanation(decision, triggered)
        logger.info("PolicyEngine decision=%s rules_triggered=%s", decision.value, triggered)

        return PolicyResult(
            decision=decision,
            triggered_rules=triggered,
            explanation=explanation,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _matches(self, condition: dict, *, goal_type: str, risk_level: str,
                 requires_external_action: bool, confidence: float,
                 spf: str, dkim: str, flagged_urls: list[str]) -> bool:
        """Return True if ALL conditions in the rule match."""
        for key, value in condition.items():
            match key:
                case "risk_level":
                    if risk_level.lower() != str(value).lower():
                        return False
                case "goal_type":
                    if goal_type.upper() != str(value).upper():
                        return False
                case "requires_external_action":
                    if requires_external_action != bool(value):
                        return False
                case "confidence_lt":
                    if confidence >= float(value):
                        return False
                case "confidence_gt":
                    if confidence <= float(value):
                        return False
                case "spf":
                    if spf.lower() != str(value).lower():
                        return False
                case "dkim":
                    if dkim.lower() != str(value).lower():
                        return False
                case "has_flagged_urls":
                    has = len(flagged_urls) > 0
                    if has != bool(value):
                        return False
                case _:
                    logger.debug("Unknown condition key '%s' in rule — skipping", key)
        return True

    def _build_explanation(self, decision: PolicyDecision, triggered: list[str]) -> str:
        if not triggered:
            return "No rules triggered — action automatically allowed."
        rule_list = ", ".join(triggered)
        match decision:
            case PolicyDecision.BLOCK:
                return f"Blocked by policy rules: {rule_list}."
            case PolicyDecision.REQUIRE_APPROVAL:
                return f"Human approval required per rules: {rule_list}."
            case PolicyDecision.ALLOW:
                return f"Allowed. Informational rules triggered: {rule_list}."
