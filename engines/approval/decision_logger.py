"""
Decision Logger — Immutable audit trail for approval decisions.
Structured JSON logging with timestamps, actors, and reasons.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from shared.logger import get_logger, audit_log
from .schemas import ApprovalRequest, ApprovalDecision, ApprovalStatus

logger = get_logger("approval.decision_logger")


class DecisionLogger:
    """
    Records all approval decisions to an immutable audit trail.
    Logs both to the structured logger and an optional JSON Lines file.
    """

    def __init__(self, log_dir: str | Path | None = None):
        self.log_dir = Path(log_dir) if log_dir else Path("logs/decisions")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "approval_decisions.jsonl"

    def log_request_created(self, request: ApprovalRequest):
        """Log the creation of a new approval request."""
        entry = {
            "event": "approval_request_created",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request.request_id,
            "action_type": request.action_type,
            "action_description": request.action_description,
            "risk_score": request.risk_score,
            "risk_level": request.risk_level,
            "requester_id": request.requester_id,
            "approver_id": request.approver_id,
            "escalation_level": request.escalation_level.value,
        }
        self._write_entry(entry)

        audit_log(
            f"Approval request created: {request.request_id} "
            f"for '{request.action_description}' (risk={request.risk_score})",
            request_id=request.request_id,
        )

    def log_decision(self, decision: ApprovalDecision):
        """Log an approval decision."""
        entry = {
            "event": "approval_decision",
            "timestamp": decision.decided_at.isoformat(),
            "request_id": decision.request_id,
            "decision": decision.decision.value,
            "decided_by": decision.decided_by,
            "reason": decision.reason,
            "metadata": decision.metadata,
        }
        self._write_entry(entry)

        audit_log(
            f"Approval decision: {decision.request_id} → "
            f"{decision.decision.value} by {decision.decided_by}",
            request_id=decision.request_id,
            decision=decision.decision.value,
        )

    def log_escalation(
        self, request_id: str, from_level: str, to_level: str, reason: str
    ):
        """Log an escalation event."""
        entry = {
            "event": "approval_escalated",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
            "from_level": from_level,
            "to_level": to_level,
            "reason": reason,
        }
        self._write_entry(entry)

        audit_log(
            f"Approval escalated: {request_id} "
            f"from {from_level} → {to_level}: {reason}",
            request_id=request_id,
        )

    def log_expiration(self, request_id: str):
        """Log request expiration."""
        entry = {
            "event": "approval_expired",
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": request_id,
        }
        self._write_entry(entry)

        audit_log(
            f"Approval request expired: {request_id}",
            request_id=request_id,
        )

    def _write_entry(self, entry: dict):
        """Write a log entry to the JSON Lines file."""
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write decision log: {e}")

    def get_decisions_for_request(
        self, request_id: str
    ) -> list[dict]:
        """Read all log entries for a specific request ID."""
        entries: list[dict] = []
        if not self._log_file.exists():
            return entries

        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("request_id") == request_id:
                        entries.append(entry)
        except Exception as e:
            logger.error(f"Failed to read decision log: {e}")

        return entries
