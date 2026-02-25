"""
cost_tracker.py
---------------
Token cost tracking per user/session.

Records prompt + completion token counts and converts to USD cost
using gpt-4o-mini pricing. Useful for monitoring and billing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from loguru import logger


# gpt-4o-mini pricing (as of 2024) — per 1M tokens
_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {
        "input":  0.150,   # $0.15 per 1M input tokens
        "output": 0.600,   # $0.60 per 1M output tokens
    },
    "gpt-4o": {
        "input":  5.00,
        "output": 15.00,
    },
    "gpt-3.5-turbo": {
        "input":  0.50,
        "output": 1.50,
    },
}


@dataclass
class UsageRecord:
    prompt_tokens: int
    completion_tokens: int
    model: str
    cost_usd: float


@dataclass
class UserCostSummary:
    user_id: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    records: list[UsageRecord] = field(default_factory=list)


class CostTracker:
    """Tracks cumulative LLM token usage and cost per user."""

    def __init__(self):
        self._summaries: dict[str, UserCostSummary] = defaultdict(
            lambda: UserCostSummary(user_id="")
        )

    def record(
        self,
        user_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "gpt-4o-mini",
    ) -> float:
        """
        Record a single LLM call and return the cost in USD.

        Args:
            user_id: Supabase user ID (or "system" for unattributed calls)
            prompt_tokens: Input token count from response.usage
            completion_tokens: Output token count from response.usage
            model: Model name (for pricing lookup)

        Returns:
            Cost of this specific call in USD.
        """
        pricing = _PRICING.get(model, _PRICING["gpt-4o-mini"])
        cost = (
            (prompt_tokens / 1_000_000) * pricing["input"]
            + (completion_tokens / 1_000_000) * pricing["output"]
        )

        summary = self._summaries[user_id]
        summary.user_id = user_id
        summary.total_prompt_tokens += prompt_tokens
        summary.total_completion_tokens += completion_tokens
        summary.total_cost_usd += cost
        summary.call_count += 1
        summary.records.append(
            UsageRecord(prompt_tokens, completion_tokens, model, cost)
        )

        logger.debug(
            "LLM cost: user=%s model=%s prompt=%d completion=%d cost=$%.6f",
            user_id, model, prompt_tokens, completion_tokens, cost,
        )
        return cost

    def get_session_cost(self, user_id: str) -> float:
        """Return cumulative cost in USD for a user."""
        return round(self._summaries[user_id].total_cost_usd, 6)

    def get_summary(self, user_id: str) -> UserCostSummary:
        return self._summaries[user_id]

    def reset(self, user_id: str) -> None:
        """Reset cost tracking for a user (e.g. between sessions)."""
        self._summaries.pop(user_id, None)


# Module-level singleton
cost_tracker = CostTracker()
