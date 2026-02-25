"""
Risk Scorer — Composite risk scoring engine.
Orchestrates all security checks and produces a weighted risk score (0–100).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared.logger import get_logger, audit_log
from shared.constants import (
    RiskLevel, RiskAction,
    RISK_WEIGHTS, RISK_LEVEL_THRESHOLDS, RISK_ACTION_THRESHOLDS,
)
from .schemas import (
    EmailSecurityContext, RiskReport,
    URLScanBatchResult, HeaderAnalysisResult,
    DomainReputationResult, SPFDKIMResult,
)
from .spf_dkim import SPFDKIMVerifier
from .url_scanner import URLScanner
from .attachment_scanner import AttachmentScanner
from .header_analyzer import HeaderAnalyzer
from .domain_reputation import DomainReputationChecker

logger = get_logger("trust_risk.scorer")


class RiskScorer:
    """
    Composite risk scorer that orchestrates all security checks
    and produces a weighted risk score from 0 (safe) to 100 (critical).

    Scoring weights:
        SPF/DKIM:     25%
        URL:          20%
        Attachments:  20%
        Headers:      15%
        Domain:       20%
    """

    def __init__(self):
        self.spf_dkim_verifier = SPFDKIMVerifier()
        self.url_scanner = URLScanner()
        self.attachment_scanner = AttachmentScanner()
        self.header_analyzer = HeaderAnalyzer()
        self.domain_checker = DomainReputationChecker()

    async def score(self, context: EmailSecurityContext) -> RiskReport:
        """
        Run all security checks and compute a composite risk score.

        Args:
            context: EmailSecurityContext with all email metadata.

        Returns:
            RiskReport with individual results and composite score.
        """
        email_id = context.sender_email or str(uuid.uuid4())
        risk_factors: list[str] = []

        # ── 1. SPF/DKIM Verification ─────────────────────────────────
        spf_dkim_result = await self.spf_dkim_verifier.verify(
            context.headers
        )
        if not spf_dkim_result.spf_pass:
            risk_factors.append("SPF verification failed")
        if not spf_dkim_result.dkim_pass:
            risk_factors.append("DKIM verification failed")

        # ── 2. URL Scanning ──────────────────────────────────────────
        url_result = await self.url_scanner.scan(context.urls)
        if url_result.suspicious_count > 0:
            risk_factors.append(
                f"{url_result.suspicious_count}/{url_result.total_urls} "
                f"suspicious URLs detected"
            )

        # ── 3. Attachment Scanning ───────────────────────────────────
        attachment_results = self.attachment_scanner.scan_batch(
            context.attachments
        )
        malicious_count = sum(1 for a in attachment_results if a.is_malicious)
        if malicious_count > 0:
            risk_factors.append(
                f"{malicious_count} malicious attachment(s) detected"
            )
        # Aggregate attachment risk
        attachment_risk = (
            max(a.risk_contribution for a in attachment_results)
            if attachment_results else 0.0
        )

        # ── 4. Header Analysis ───────────────────────────────────────
        header_result = await self.header_analyzer.analyze(context.headers)
        if header_result.anomalies:
            risk_factors.extend(header_result.anomalies)

        # ── 5. Domain Reputation ─────────────────────────────────────
        sender_domain = context.sender_domain or self._extract_domain(
            context.sender_email
        )
        domain_result = await self.domain_checker.check(sender_domain)
        if domain_result.reasons:
            risk_factors.extend(domain_result.reasons)

        # ── Compute Weighted Score ───────────────────────────────────
        raw_score = (
            spf_dkim_result.risk_contribution * RISK_WEIGHTS["spf_dkim"]
            + url_result.risk_contribution * RISK_WEIGHTS["url"]
            + attachment_risk * RISK_WEIGHTS["attachment"]
            + header_result.risk_contribution * RISK_WEIGHTS["header"]
            + domain_result.risk_contribution * RISK_WEIGHTS["domain"]
        )
        composite_score = round(min(100.0, max(0.0, raw_score)), 2)

        # ── Determine Risk Level ─────────────────────────────────────
        risk_level = self._classify_risk_level(composite_score)

        # ── Determine Recommended Action ─────────────────────────────
        recommended_action = self._determine_action(composite_score)

        # ── Audit Logging ────────────────────────────────────────────
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            audit_log(
                f"High-risk email detected: {email_id} "
                f"(score={composite_score}, level={risk_level.value})",
                email_id=email_id,
                risk_score=composite_score,
                risk_level=risk_level.value,
            )

        logger.info(
            f"Risk assessment complete: {email_id} → "
            f"score={composite_score}, level={risk_level.value}, "
            f"action={recommended_action.value}"
        )

        return RiskReport(
            email_id=email_id,
            timestamp=datetime.utcnow(),
            risk_score=composite_score,
            risk_level=risk_level,
            recommended_action=recommended_action,
            spf_dkim=spf_dkim_result,
            url_scan=url_result,
            attachment_scan=attachment_results,
            header_analysis=header_result,
            domain_reputation=domain_result,
            risk_factors=risk_factors,
            details=(
                f"Composite score {composite_score}/100. "
                f"{len(risk_factors)} risk factor(s) identified."
            ),
        )

    @staticmethod
    def _classify_risk_level(score: float) -> RiskLevel:
        """Map a numeric score to a RiskLevel enum."""
        if score <= RISK_LEVEL_THRESHOLDS[RiskLevel.LOW]:
            return RiskLevel.LOW
        elif score <= RISK_LEVEL_THRESHOLDS[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM
        elif score <= RISK_LEVEL_THRESHOLDS[RiskLevel.HIGH]:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    @staticmethod
    def _determine_action(score: float) -> RiskAction:
        """Map a numeric score to a recommended action."""
        if score <= RISK_ACTION_THRESHOLDS[RiskAction.AUTO_APPROVE]:
            return RiskAction.AUTO_APPROVE
        elif score <= RISK_ACTION_THRESHOLDS[RiskAction.REQUIRE_APPROVAL]:
            return RiskAction.REQUIRE_APPROVAL
        else:
            return RiskAction.BLOCK

    @staticmethod
    def _extract_domain(email: str) -> str:
        """Extract domain from an email address."""
        if "@" in email:
            return email.split("@", 1)[1].lower()
        return email.lower()
