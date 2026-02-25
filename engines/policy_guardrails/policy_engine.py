"""
Policy Engine — YAML-driven rule evaluation engine.
Loads policies from YAML files and evaluates them against a context.
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import Any

import yaml

from shared.logger import get_logger, audit_log
from .schemas import (
    Policy, PolicyAction, PolicyPriority,
    PolicyContext, PolicyMatch, PolicyDecision,
)

logger = get_logger("policy_guardrails.policy_engine")

# Default rules file path
DEFAULT_RULES_PATH = Path(__file__).parent / "rules.yaml"


class PolicyEngine:
    """
    YAML-driven policy rule engine.
    
    Loads policy definitions from YAML files, evaluates them against
    a PolicyContext, and returns a PolicyDecision with the most
    restrictive matching action.
    """

    # Action restrictiveness ordering (higher = more restrictive)
    ACTION_SEVERITY = {
        PolicyAction.ALLOW: 0,
        PolicyAction.LOG_ONLY: 1,
        PolicyAction.REQUIRE_APPROVAL: 2,
        PolicyAction.BLOCK: 3,
    }

    def __init__(self, rules_path: str | Path | None = None):
        self.rules_path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
        self.policies: list[Policy] = []
        self.trusted_domains: list[str] = []
        self._load_rules()

    def _load_rules(self):
        """Load and parse policy rules from YAML file."""
        if not self.rules_path.exists():
            logger.warning(f"Rules file not found: {self.rules_path}")
            return

        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            raw_policies = data.get("policies", [])
            self.trusted_domains = data.get("trusted_domains", [])

            for p in raw_policies:
                try:
                    policy = Policy(
                        id=p["id"],
                        name=p["name"],
                        condition=p["condition"],
                        action=PolicyAction(p["action"]),
                        priority=PolicyPriority(p.get("priority", "medium")),
                        enabled=p.get("enabled", True),
                        description=p.get("description", ""),
                    )
                    self.policies.append(policy)
                except Exception as e:
                    logger.error(f"Failed to parse policy '{p.get('id', '?')}': {e}")

            logger.info(
                f"Loaded {len(self.policies)} policies from {self.rules_path}"
            )

        except Exception as e:
            logger.error(f"Failed to load rules from {self.rules_path}: {e}")

    def reload_rules(self):
        """Reload policies from the YAML file."""
        self.policies.clear()
        self.trusted_domains.clear()
        self._load_rules()

    def evaluate(self, context: PolicyContext) -> PolicyDecision:
        """
        Evaluate all enabled policies against the given context.
        The most restrictive matching policy wins.

        Args:
            context: PolicyContext with evaluation variables.

        Returns:
            PolicyDecision with the aggregated result.
        """
        matches: list[PolicyMatch] = []
        most_restrictive_action = PolicyAction.ALLOW

        # Inject trusted domains into context if not already set
        if not context.trusted_domains:
            context.trusted_domains = self.trusted_domains

        # Sort policies by priority (highest first)
        sorted_policies = sorted(
            [p for p in self.policies if p.enabled],
            key=lambda p: p.priority.numeric,
            reverse=True,
        )

        for policy in sorted_policies:
            try:
                if self._evaluate_condition(policy.condition, context):
                    match = PolicyMatch(
                        policy_id=policy.id,
                        policy_name=policy.name,
                        action=policy.action,
                        priority=policy.priority,
                        condition=policy.condition,
                    )
                    matches.append(match)

                    # Track most restrictive action
                    if (self.ACTION_SEVERITY[policy.action]
                            > self.ACTION_SEVERITY[most_restrictive_action]):
                        most_restrictive_action = policy.action

            except Exception as e:
                logger.error(
                    f"Error evaluating policy '{policy.id}': {e}"
                )

        # Build decision
        allowed = most_restrictive_action in (
            PolicyAction.ALLOW, PolicyAction.LOG_ONLY
        )

        reason_parts = [
            f"[{m.policy_id}] {m.policy_name}" for m in matches
        ]
        reason = (
            f"Matched {len(matches)} policy(ies): "
            + "; ".join(reason_parts)
        ) if matches else "No policy violations"

        decision = PolicyDecision(
            allowed=allowed,
            action=most_restrictive_action,
            matched_policies=matches,
            reason=reason,
            evaluated_at=datetime.utcnow(),
            total_rules_evaluated=len(sorted_policies),
        )

        # Audit log for blocked or approval-required decisions
        if not allowed:
            audit_log(
                f"Policy enforcement: action={most_restrictive_action.value}, "
                f"matches={len(matches)}, reason={reason}",
                policy_action=most_restrictive_action.value,
                matched_policy_ids=[m.policy_id for m in matches],
            )

        return decision

    def _evaluate_condition(
        self, condition: str, context: PolicyContext
    ) -> bool:
        """
        Safely evaluate a policy condition against the context.

        Uses a restricted eval with only the context fields available
        as variables. No builtins or imports are exposed.
        """
        # Build evaluation namespace from context fields
        namespace: dict[str, Any] = {
            "intent_type": context.intent_type,
            "action": context.action,
            "sender_email": context.sender_email,
            "sender_domain": context.sender_domain,
            "recipient_domain": context.recipient_domain,
            "risk_score": context.risk_score,
            "has_attachments": context.has_attachments,
            "attachment_count": context.attachment_count,
            "url_count": context.url_count,
            "is_external": context.is_external,
            "amount": context.amount,
            "trusted_domains": context.trusted_domains,
            # Expose 'in' and 'not in' operators for domain checks
            **context.custom_fields,
        }

        try:
            # Restricted eval: no builtins, no imports
            result = eval(condition, {"__builtins__": {}}, namespace)
            return bool(result)
        except Exception as e:
            logger.warning(
                f"Condition evaluation failed: '{condition}' → {e}"
            )
            return False

    def get_all_policies(self) -> list[Policy]:
        """Return all loaded policies."""
        return list(self.policies)

    def get_policy_by_id(self, policy_id: str) -> Policy | None:
        """Get a specific policy by its ID."""
        for p in self.policies:
            if p.id == policy_id:
                return p
        return None
