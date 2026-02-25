"""
Attachment Scanner — File-based threat detection.
Checks for blocked extensions, double extensions, size anomalies.
"""

from __future__ import annotations

import os
from shared.logger import get_logger
from shared.constants import (
    BLOCKED_FILE_EXTENSIONS,
    SUSPICIOUS_DOUBLE_EXTENSIONS,
    MAX_ATTACHMENT_SIZE_BYTES,
)
from .schemas import AttachmentScanResult

logger = get_logger("trust_risk.attachment_scanner")


class AttachmentScanner:
    """
    Scans email attachments for potential malware indicators.
    Uses file metadata heuristics (no content inspection).
    Optionally hooks into ClamAV for deep scanning.
    """

    # Known malicious file hashes (example — in production, use a threat intel feed)
    KNOWN_MALICIOUS_HASHES: frozenset[str] = frozenset({
        "e3b0c44298fc1c149afbf4c8996fb924",  # Example placeholder
    })

    def scan(
        self,
        filename: str,
        content_hash: str = "",
        file_size: int = 0,
    ) -> AttachmentScanResult:
        """
        Scan an attachment's metadata for threat indicators.

        Args:
            filename: The attachment filename (e.g., "report.pdf.exe").
            content_hash: SHA256 or MD5 hash of the file content.
            file_size: File size in bytes.

        Returns:
            AttachmentScanResult with risk assessment.
        """
        reasons: list[str] = []
        risk = 0.0

        # ── Check 1: Blocked extension ───────────────────────────────
        ext = self._get_extension(filename)
        blocked_ext = ext in BLOCKED_FILE_EXTENSIONS
        if blocked_ext:
            reasons.append(f"Blocked file extension: {ext}")
            risk += 50.0

        # ── Check 2: Double extension detection ──────────────────────
        double_ext = self._check_double_extension(filename)
        if double_ext:
            reasons.append(f"Double extension detected: {filename}")
            risk += 40.0

        # ── Check 3: Size anomaly ────────────────────────────────────
        size_anomaly = False
        if file_size > MAX_ATTACHMENT_SIZE_BYTES:
            size_anomaly = True
            reasons.append(
                f"File size ({file_size / (1024*1024):.1f} MB) exceeds "
                f"limit ({MAX_ATTACHMENT_SIZE_BYTES / (1024*1024):.0f} MB)"
            )
            risk += 15.0
        elif file_size == 0 and filename:
            size_anomaly = True
            reasons.append("Zero-byte attachment (potentially suspicious)")
            risk += 10.0

        # ── Check 4: Known malicious hash ────────────────────────────
        if content_hash and content_hash.lower() in self.KNOWN_MALICIOUS_HASHES:
            reasons.append(f"Known malicious file hash: {content_hash[:16]}...")
            risk += 80.0

        # ── Check 5: Suspicious filename patterns ────────────────────
        name_lower = filename.lower()
        suspicious_names = [
            "invoice", "payment", "wire_transfer", "urgent",
            "confidential", "password", "credentials",
        ]
        if any(kw in name_lower for kw in suspicious_names):
            reasons.append(f"Suspicious filename pattern: {filename}")
            risk += 10.0

        risk = min(100.0, risk)
        is_malicious = risk >= 40.0

        if is_malicious:
            logger.warning(
                f"Malicious attachment detected: {filename} "
                f"(risk={risk}, reasons={reasons})"
            )

        return AttachmentScanResult(
            filename=filename,
            is_malicious=is_malicious,
            reasons=reasons,
            blocked_extension=blocked_ext,
            double_extension=double_ext,
            size_anomaly=size_anomaly,
            risk_contribution=round(risk, 2),
        )

    def scan_batch(
        self, attachments: list[dict]
    ) -> list[AttachmentScanResult]:
        """
        Scan multiple attachments.

        Args:
            attachments: List of dicts with keys:
                "filename", "content_hash", "file_size"
        """
        return [
            self.scan(
                filename=att.get("filename", "unknown"),
                content_hash=att.get("content_hash", ""),
                file_size=att.get("file_size", 0),
            )
            for att in attachments
        ]

    @staticmethod
    def _get_extension(filename: str) -> str:
        """Get the file extension (lowercase, including dot)."""
        _, ext = os.path.splitext(filename)
        return ext.lower()

    @staticmethod
    def _check_double_extension(filename: str) -> bool:
        """
        Check if the filename has a double extension trick.
        e.g., "report.pdf.exe"
        """
        name_lower = filename.lower()
        return any(name_lower.endswith(de) for de in SUSPICIOUS_DOUBLE_EXTENSIONS)
