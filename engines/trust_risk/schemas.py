"""
Pydantic schemas for the Trust & Risk Engine.
Models for email security analysis results and composite risk scoring.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from shared.constants import RiskLevel, RiskAction


# ─── SPF / DKIM Verification ─────────────────────────────────────────────────

class SPFDKIMResult(BaseModel):
    """Result of SPF and DKIM email authentication checks."""
    spf_pass: bool = False
    dkim_pass: bool = False
    spf_details: str = ""
    dkim_details: str = ""
    risk_contribution: float = Field(0.0, ge=0.0, le=100.0)


# ─── URL Scanning ────────────────────────────────────────────────────────────

class URLScanResult(BaseModel):
    """Result of scanning a single URL for threats."""
    url: str
    is_suspicious: bool = False
    reasons: list[str] = Field(default_factory=list)
    is_shortener: bool = False
    has_ip_address: bool = False
    suspicious_tld: bool = False
    homograph_detected: bool = False
    risk_contribution: float = Field(0.0, ge=0.0, le=100.0)


class URLScanBatchResult(BaseModel):
    """Aggregated results from scanning multiple URLs."""
    results: list[URLScanResult] = Field(default_factory=list)
    total_urls: int = 0
    suspicious_count: int = 0
    risk_contribution: float = Field(0.0, ge=0.0, le=100.0)


# ─── Attachment Scanning ─────────────────────────────────────────────────────

class AttachmentScanResult(BaseModel):
    """Result of scanning a single attachment."""
    filename: str
    is_malicious: bool = False
    reasons: list[str] = Field(default_factory=list)
    blocked_extension: bool = False
    double_extension: bool = False
    size_anomaly: bool = False
    risk_contribution: float = Field(0.0, ge=0.0, le=100.0)


# ─── Header Analysis ─────────────────────────────────────────────────────────

class HeaderAnalysisResult(BaseModel):
    """Result of email header anomaly detection."""
    anomalies: list[str] = Field(default_factory=list)
    from_reply_to_mismatch: bool = False
    missing_message_id: bool = False
    suspicious_x_mailer: bool = False
    relay_hop_anomaly: bool = False
    encoding_anomaly: bool = False
    risk_contribution: float = Field(0.0, ge=0.0, le=100.0)


# ─── Domain Reputation ───────────────────────────────────────────────────────

class DomainReputationResult(BaseModel):
    """Result of sender domain reputation check."""
    domain: str
    is_disposable: bool = False
    is_blocklisted: bool = False
    is_trusted: bool = False
    reasons: list[str] = Field(default_factory=list)
    risk_contribution: float = Field(0.0, ge=0.0, le=100.0)


# ─── Composite Risk Report ───────────────────────────────────────────────────

class EmailSecurityContext(BaseModel):
    """Input context for risk assessment — describes the email being analyzed."""
    sender_email: str
    sender_domain: str = ""
    subject: str = ""
    body: str = ""
    headers: dict = Field(default_factory=dict)
    urls: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)
    # Each attachment: {"filename": str, "content_hash": str, "file_size": int}


class RiskReport(BaseModel):
    """Composite risk assessment report combining all security checks."""
    email_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    risk_score: float = Field(0.0, ge=0.0, le=100.0)
    risk_level: RiskLevel = RiskLevel.LOW
    recommended_action: RiskAction = RiskAction.AUTO_APPROVE

    # Individual check results
    spf_dkim: Optional[SPFDKIMResult] = None
    url_scan: Optional[URLScanBatchResult] = None
    attachment_scan: list[AttachmentScanResult] = Field(default_factory=list)
    header_analysis: Optional[HeaderAnalysisResult] = None
    domain_reputation: Optional[DomainReputationResult] = None

    # Summary
    risk_factors: list[str] = Field(default_factory=list)
    details: str = ""
