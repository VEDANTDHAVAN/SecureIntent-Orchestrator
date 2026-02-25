"""
Policy Enforcement Middleware for FastAPI.
Intercepts requests to security-sensitive endpoints and applies policy checks.
"""

from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from shared.logger import get_logger
from .policy_engine import PolicyEngine
from .schemas import PolicyContext, PolicyAction

logger = get_logger("policy_guardrails.middleware")


class PolicyEnforcementMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces policy checks on incoming requests.
    
    Only applies to specific API paths (configurable via `protected_paths`).
    Extracts a PolicyContext from the request and evaluates it against
    the loaded policy rules.
    """

    def __init__(
        self,
        app,
        policy_engine: PolicyEngine | None = None,
        protected_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.policy_engine = policy_engine or PolicyEngine()
        self.protected_paths = protected_paths or [
            "/extract-intent",
            "/api/v1/sandbox/execute",
        ]

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """
        Intercept request, evaluate policies, and block/allow accordingly.
        """
        # Only enforce on protected paths
        if not self._is_protected(request.url.path):
            return await call_next(request)

        try:
            # Build policy context from request
            context = await self._extract_context(request)

            # Evaluate policies
            decision = self.policy_engine.evaluate(context)

            # Store decision in request state for downstream use
            request.state.policy_decision = decision

            if decision.action == PolicyAction.BLOCK:
                logger.warning(
                    f"Request BLOCKED by policy: {request.url.path} → "
                    f"{decision.reason}"
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "policy_violation",
                        "message": decision.reason,
                        "action": decision.action.value,
                        "matched_policies": [
                            m.policy_id for m in decision.matched_policies
                        ],
                    },
                )

            if decision.action == PolicyAction.REQUIRE_APPROVAL:
                # Allow the request but inject approval requirement
                request.state.requires_approval = True
                logger.info(
                    f"Request requires approval: {request.url.path} → "
                    f"{decision.reason}"
                )

        except Exception as e:
            logger.error(
                f"Policy middleware error on {request.url.path}: {e}"
            )
            # Fail-open: allow request if policy evaluation fails
            # (configurable — some orgs may want fail-closed)

        return await call_next(request)

    def _is_protected(self, path: str) -> bool:
        """Check if the request path is protected by policy enforcement."""
        return any(path.startswith(p) for p in self.protected_paths)

    async def _extract_context(self, request: Request) -> PolicyContext:
        """
        Extract PolicyContext from the incoming request.
        Tries to parse the JSON body for relevant fields.
        """
        context_fields: dict = {}

        try:
            if request.method in ("POST", "PUT", "PATCH"):
                body = await request.json()

                context_fields = {
                    "intent_type": body.get("intent_type", ""),
                    "action": body.get("action", ""),
                    "sender_email": body.get("sender_email", ""),
                    "sender_domain": body.get("sender_domain", ""),
                    "recipient_domain": body.get("recipient_domain", ""),
                    "risk_score": float(body.get("risk_score", 0)),
                    "has_attachments": bool(body.get("attachments")),
                    "attachment_count": len(body.get("attachments", [])),
                    "url_count": len(body.get("urls", [])),
                    "is_external": body.get("is_external", False),
                    "amount": float(body.get("amount", 0)),
                }
        except Exception:
            pass  # Non-JSON body or missing fields — use defaults

        return PolicyContext(**context_fields)
