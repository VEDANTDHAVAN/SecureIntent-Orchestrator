"""
Domain Reputation Checker — Sender domain trust assessment.
Checks disposable domains, blocklists, and trust status.
"""

from __future__ import annotations

from shared.logger import get_logger
from shared.constants import (
    DISPOSABLE_EMAIL_DOMAINS,
    TRUSTED_DOMAINS_DEFAULT,
)
from .schemas import DomainReputationResult

logger = get_logger("trust_risk.domain_reputation")


class DomainReputationChecker:
    """
    Evaluates the reputation of an email sender's domain.
    Uses local lists for disposable/blocklisted/trusted domains.
    Extensible with external reputation APIs.
    """

    def __init__(
        self,
        custom_blocklist: set[str] | None = None,
        custom_trusted: set[str] | None = None,
    ):
        self.blocklist = set(custom_blocklist) if custom_blocklist else set()
        self.trusted_domains = (
            set(custom_trusted) if custom_trusted
            else set(TRUSTED_DOMAINS_DEFAULT)
        )

    async def check(self, domain: str) -> DomainReputationResult:
        """
        Check the reputation of a sender domain.

        Args:
            domain: The sender's email domain (e.g., "example.com").

        Returns:
            DomainReputationResult with reputation flags and risk score.
        """
        domain = domain.lower().strip()
        reasons: list[str] = []
        risk = 0.0

        # ── Check 1: Disposable email domain ─────────────────────────
        is_disposable = domain in DISPOSABLE_EMAIL_DOMAINS
        if is_disposable:
            reasons.append(f"Disposable email domain: {domain}")
            risk += 50.0

        # ── Check 2: Custom blocklist ────────────────────────────────
        is_blocklisted = domain in self.blocklist
        if is_blocklisted:
            reasons.append(f"Domain is blocklisted: {domain}")
            risk += 60.0

        # ── Check 3: Trusted domain check ────────────────────────────
        is_trusted = domain in self.trusted_domains
        if is_trusted:
            # Trusted domains reduce risk
            risk = max(0.0, risk - 20.0)

        # ── Check 4: Domain structure heuristics ─────────────────────
        parts = domain.split(".")
        if len(parts) > 4:
            reasons.append(f"Unusual domain depth ({len(parts)} levels): {domain}")
            risk += 15.0

        # Check for very short domain names (potential typosquatting)
        base_domain = parts[0] if parts else ""
        if len(base_domain) <= 2 and not is_trusted:
            reasons.append(f"Very short domain name: {domain}")
            risk += 10.0

        # ── Check 5: Numeric-heavy domain (often spam) ───────────────
        if base_domain and sum(c.isdigit() for c in base_domain) > len(base_domain) * 0.5:
            reasons.append(f"Numeric-heavy domain name: {domain}")
            risk += 15.0

        # ── Check 6: Hyphen-heavy domain (potential phishing) ────────
        if base_domain.count("-") >= 3:
            reasons.append(f"Excessive hyphens in domain: {domain}")
            risk += 10.0

        risk = min(100.0, risk)

        if risk >= 40.0:
            logger.warning(f"Low reputation domain: {domain} (risk={risk})")

        return DomainReputationResult(
            domain=domain,
            is_disposable=is_disposable,
            is_blocklisted=is_blocklisted,
            is_trusted=is_trusted,
            reasons=reasons,
            risk_contribution=round(risk, 2),
        )
