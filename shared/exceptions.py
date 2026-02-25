"""
Custom exceptions for the SecureIntent-Orchestrator security layer.
"""


class SecureIntentError(Exception):
    """Base exception for all SecureIntent errors."""
    pass


class PolicyViolationError(SecureIntentError):
    """Raised when an action violates a defined policy rule."""

    def __init__(self, policy_id: str, policy_name: str, message: str = ""):
        self.policy_id = policy_id
        self.policy_name = policy_name
        super().__init__(
            message or f"Policy violation: [{policy_id}] {policy_name}"
        )


class RateLimitExceededError(SecureIntentError):
    """Raised when a rate limit is exceeded."""

    def __init__(self, tool_name: str, limit: int, window_seconds: int):
        self.tool_name = tool_name
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(
            f"Rate limit exceeded for '{tool_name}': "
            f"{limit} requests per {window_seconds}s"
        )


class SandboxExecutionError(SecureIntentError):
    """Raised when sandbox execution fails or is rejected."""

    def __init__(self, action: str, reason: str):
        self.action = action
        self.reason = reason
        super().__init__(f"Sandbox execution denied for '{action}': {reason}")


class ApprovalRequiredError(SecureIntentError):
    """Raised when an action requires human approval before proceeding."""

    def __init__(self, action: str, risk_score: float, reason: str = ""):
        self.action = action
        self.risk_score = risk_score
        super().__init__(
            reason or f"Approval required for '{action}' (risk={risk_score})"
        )


class RiskThresholdExceededError(SecureIntentError):
    """Raised when risk score exceeds the blocking threshold."""

    def __init__(self, score: float, threshold: float, details: str = ""):
        self.score = score
        self.threshold = threshold
        super().__init__(
            details or f"Risk score {score} exceeds threshold {threshold}"
        )


class ValidationError(SecureIntentError):
    """Raised when action validation fails."""

    def __init__(self, action: str, violations: list[str]):
        self.action = action
        self.violations = violations
        super().__init__(
            f"Validation failed for '{action}': {'; '.join(violations)}"
        )
