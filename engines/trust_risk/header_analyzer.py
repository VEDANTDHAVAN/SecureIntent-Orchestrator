"""
Header Analyzer — Email header anomaly detection.
Detects mismatched From/Reply-To, missing Message-ID, suspicious X-Mailer, etc.
"""

from __future__ import annotations

import re
from shared.logger import get_logger
from shared.constants import SUSPICIOUS_X_MAILERS
from .schemas import HeaderAnalysisResult

logger = get_logger("trust_risk.header_analyzer")


class HeaderAnalyzer:
    """
    Analyzes email headers for anomalies that indicate
    phishing, spoofing, or spam.
    """

    async def analyze(self, headers: dict) -> HeaderAnalysisResult:
        """
        Analyze email headers for security anomalies.

        Args:
            headers: Dictionary of email headers (case-insensitive keys).

        Returns:
            HeaderAnalysisResult with detected anomalies and risk score.
        """
        # Normalize header keys to lower-case for consistent lookup
        h = {k.lower(): v for k, v in headers.items()}
        anomalies: list[str] = []
        risk = 0.0

        # ── Check 1: From / Reply-To mismatch ───────────────────────
        from_mismatch = self._check_from_reply_to_mismatch(h)
        if from_mismatch:
            anomalies.append(from_mismatch)
            risk += 25.0

        # ── Check 2: Missing Message-ID ──────────────────────────────
        missing_msg_id = not h.get("message-id", "").strip()
        if missing_msg_id:
            anomalies.append("Missing Message-ID header")
            risk += 20.0

        # ── Check 3: Suspicious X-Mailer ─────────────────────────────
        x_mailer = h.get("x-mailer", "")
        suspicious_mailer = any(
            sm.lower() in x_mailer.lower()
            for sm in SUSPICIOUS_X_MAILERS
        ) if x_mailer else False
        if suspicious_mailer:
            anomalies.append(f"Suspicious X-Mailer: {x_mailer}")
            risk += 20.0

        # ── Check 4: Relay hop anomaly ───────────────────────────────
        relay_anomaly = self._check_relay_hops(h)
        if relay_anomaly:
            anomalies.append(relay_anomaly)
            risk += 15.0

        # ── Check 5: Encoding anomaly ────────────────────────────────
        encoding_anomaly = self._check_encoding_anomaly(h)
        if encoding_anomaly:
            anomalies.append(encoding_anomaly)
            risk += 10.0

        # ── Check 6: Missing or suspicious Date header ───────────────
        date_issue = self._check_date_header(h)
        if date_issue:
            anomalies.append(date_issue)
            risk += 10.0

        risk = min(100.0, risk)

        return HeaderAnalysisResult(
            anomalies=anomalies,
            from_reply_to_mismatch=from_mismatch is not None,
            missing_message_id=missing_msg_id,
            suspicious_x_mailer=suspicious_mailer,
            relay_hop_anomaly=relay_anomaly is not None,
            encoding_anomaly=encoding_anomaly is not None,
            risk_contribution=round(risk, 2),
        )

    def _check_from_reply_to_mismatch(self, h: dict) -> str | None:
        """Check if From and Reply-To domains differ."""
        from_addr = h.get("from", "")
        reply_to = h.get("reply-to", "")

        if not reply_to:
            return None

        from_domain = self._extract_domain(from_addr)
        reply_domain = self._extract_domain(reply_to)

        if from_domain and reply_domain and from_domain != reply_domain:
            return (
                f"From/Reply-To domain mismatch: "
                f"From={from_domain}, Reply-To={reply_domain}"
            )
        return None

    def _check_relay_hops(self, h: dict) -> str | None:
        """
        Check for suspicious number of relay hops in Received headers.
        Normal emails typically have 3–7 hops.
        """
        received_headers = []
        # Received headers may be a single string or multiple
        received = h.get("received", "")
        if isinstance(received, list):
            received_headers = received
        elif received:
            # Count "from" occurrences as a rough hop count
            received_headers = received.split("\n")

        hop_count = len([r for r in received_headers if r.strip()])

        if hop_count > 10:
            return f"Excessive relay hops ({hop_count}) — possible relay abuse"
        elif hop_count == 0:
            return "No Received headers — possible direct injection"

        return None

    def _check_encoding_anomaly(self, h: dict) -> str | None:
        """Check for unusual content encoding that may hide malicious content."""
        content_type = h.get("content-type", "")
        content_encoding = h.get("content-transfer-encoding", "")

        # Flag unusual encodings
        if "utf-7" in content_type.lower():
            return "Unusual encoding: UTF-7 (potential XSS vector)"

        if content_encoding.lower() in ("8bit", "binary"):
            return f"Unusual content-transfer-encoding: {content_encoding}"

        return None

    def _check_date_header(self, h: dict) -> str | None:
        """Check for missing or suspicious Date header."""
        date_header = h.get("date", "")
        if not date_header.strip():
            return "Missing Date header"
        return None

    @staticmethod
    def _extract_domain(email_str: str) -> str | None:
        """Extract domain from an email address string."""
        match = re.search(r"@([\w.-]+)", email_str)
        return match.group(1).lower() if match else None
