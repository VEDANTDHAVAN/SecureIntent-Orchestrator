from __future__ import annotations

from .schemas import Intent

CONFIDENCE_THRESHOLD = 0.6


class IntentValidationResult:
    def __init__(self, intent: Intent, status: str, reason: str | None = None):
        self.intent = intent
        self.status = status  # valid | review | reject
        self.reason = reason


def validate_intent(intent: Intent) -> IntentValidationResult:
    """
    Applies business validation rules beyond schema validation.
    """

    # Low confidence
    if intent.confidence_score < CONFIDENCE_THRESHOLD:
        return IntentValidationResult(
            intent=intent,
            status="review",
            reason="Low confidence score"
        )

    return IntentValidationResult(
        intent=intent,
        status="valid"
    )
