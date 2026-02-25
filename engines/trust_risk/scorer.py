"""
scorer.py
---------
Composite trust/risk scorer for incoming emails.

Aggregates signals from:
  - SPF / DKIM / DMARC authentication results
  - URL scan (local blocklist + optional VirusTotal)
  - Sender domain analysis

Produces a RiskScore with a 0.0–1.0 score and a RiskLevel enum.

The risk score gates the LLM: CRITICAL emails are BLOCKED before
the intent extractor is ever called.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from engines.trust_risk.spf_dkim import SpfDkimResult
from engines.trust_risk.url_scanner import UrlScanResult

if TYPE_CHECKING:
    pass


class RiskLevel(str, Enum):
    LOW = "low"           # score < 0.30  → allow, LLM runs
    MEDIUM = "medium"     # score < 0.55  → allow + flag for monitoring
    HIGH = "high"         # score < 0.80  → require human approval
    CRITICAL = "critical" # score >= 0.80 → block, LLM never invoked

    @classmethod
    def from_score(cls, score: float) -> "RiskLevel":
        if score >= 0.80:
            return cls.CRITICAL
        if score >= 0.55:
            return cls.HIGH
        if score >= 0.30:
            return cls.MEDIUM
        return cls.LOW


@dataclass
class RiskScore:
    score: float                      # 0.0 – 1.0
    level: RiskLevel
    reasons: list[str] = field(default_factory=list)
    spf: str = "none"
    dkim: str = "none"
    dmarc: str = "none"
    flagged_urls: list[str] = field(default_factory=list)

    @property
    def blocks_pipeline(self) -> bool:
        """CRITICAL risk blocks everything — LLM is never called."""
        return self.level == RiskLevel.CRITICAL

    @property
    def requires_approval(self) -> bool:
        return self.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def to_db_dict(self, email_id: str) -> dict:
        """Format for db.models.create_risk_score()."""
        return {
            "email_id": email_id,
            "score": round(self.score, 4),
            "level": self.level.value,
            "reasons": self.reasons,
            "spf": self.spf,
            "dkim": self.dkim,
            "dmarc": self.dmarc,
            "flagged_urls": self.flagged_urls,
        }


# ── Known-safe domains (Google, Microsoft, major providers) ───────────────────
_TRUSTED_DOMAINS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "icloud.com", "me.com",
    "amazon.com", "apple.com", "microsoft.com",
    "github.com", "stripe.com", "notion.so",
}

# ── Suspicious sender keywords (BEC / impersonation signals) ─────────────────
_SUSPICIOUS_SENDER_KEYWORDS = {
    "urgent", "wire", "transfer", "payment", "invoice",
    "ceo", "cfo", "boss", "manager", "hr", "finance",
    "verify", "confirm", "suspended", "locked",
}


def _sender_domain(sender: str) -> str:
    """Extract domain from 'Display Name <email@domain.com>' or 'email@domain.com'."""
    import re
    match = re.search(r"@([\w.\-]+)", sender)
    return match.group(1).lower() if match else ""


def calculate_risk(
    spf_dkim: SpfDkimResult,
    url_scan: UrlScanResult,
    sender: str,
    subject: str = "",
) -> RiskScore:
    """
    Calculate composite risk score.

    Scoring weights (cumulative, capped at 1.0):
      SPF fail         → +0.25
      DKIM fail        → +0.20
      DMARC fail       → +0.15
      Flagged URL      → +0.30 each (capped at +0.60)
      Unknown domain   → +0.10
      Suspicious kw    → +0.05 each (capped at +0.15)
    """
    score = 0.0
    reasons: list[str] = []

    # ── SPF ──────────────────────────────────────────────────────────────────
    if spf_dkim.spf == "fail":
        score += 0.25
        reasons.append("SPF authentication failed")
    elif spf_dkim.spf == "none":
        score += 0.08
        reasons.append("No SPF record found")

    # ── DKIM ─────────────────────────────────────────────────────────────────
    if spf_dkim.dkim == "fail":
        score += 0.20
        reasons.append("DKIM signature invalid")
    elif spf_dkim.dkim == "none":
        score += 0.05
        reasons.append("No DKIM signature")

    # ── DMARC ────────────────────────────────────────────────────────────────
    if spf_dkim.dmarc == "fail":
        score += 0.15
        reasons.append("DMARC policy failed")

    # ── Flagged URLs ─────────────────────────────────────────────────────────
    url_penalty = min(len(url_scan.flagged) * 0.30, 0.60)
    if url_penalty > 0:
        score += url_penalty
        reasons.append(f"{len(url_scan.flagged)} suspicious URL(s) detected")

    # ── Sender domain analysis ────────────────────────────────────────────────
    domain = _sender_domain(sender)
    if domain and domain not in _TRUSTED_DOMAINS:
        score += 0.10
        reasons.append(f"Sender domain '{domain}' is not in trusted list")

    # ── Suspicious keyword check (subject + sender display name) ─────────────
    combined_text = f"{sender} {subject}".lower()
    keyword_hits = [kw for kw in _SUSPICIOUS_SENDER_KEYWORDS if kw in combined_text]
    keyword_penalty = min(len(keyword_hits) * 0.05, 0.15)
    if keyword_penalty > 0:
        score += keyword_penalty
        reasons.append(f"Suspicious keywords in sender/subject: {', '.join(keyword_hits[:3])}")

    # ── Clamp and classify ────────────────────────────────────────────────────
    score = min(round(score, 4), 1.0)
    level = RiskLevel.from_score(score)

    return RiskScore(
        score=score,
        level=level,
        reasons=reasons,
        spf=spf_dkim.spf,
        dkim=spf_dkim.dkim,
        dmarc=spf_dkim.dmarc,
        flagged_urls=url_scan.flagged,
    )
