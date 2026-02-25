"""
Tests for the Trust & Risk Engine.
Covers SPF/DKIM, URL scanning, attachment scanning,
header analysis, domain reputation, and composite risk scoring.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio

from engines.trust_risk.spf_dkim import SPFDKIMVerifier
from engines.trust_risk.url_scanner import URLScanner
from engines.trust_risk.attachment_scanner import AttachmentScanner
from engines.trust_risk.header_analyzer import HeaderAnalyzer
from engines.trust_risk.domain_reputation import DomainReputationChecker
from engines.trust_risk.scorer import RiskScorer
from engines.trust_risk.schemas import EmailSecurityContext


# ═══════════════════════════════════════════════════════════════════════════════
# SPF / DKIM VERIFIER
# ═══════════════════════════════════════════════════════════════════════════════

class TestSPFDKIMVerifier:
    @pytest.fixture
    def verifier(self):
        return SPFDKIMVerifier()

    @pytest.mark.asyncio
    async def test_spf_pass_from_header(self, verifier):
        headers = {"Received-SPF": "pass (domain of example.com)"}
        result = await verifier.verify(headers)
        assert result.spf_pass is True
        assert result.risk_contribution < 100

    @pytest.mark.asyncio
    async def test_spf_fail_from_header(self, verifier):
        headers = {"Received-SPF": "fail (domain of spam.com)"}
        result = await verifier.verify(headers)
        assert result.spf_pass is False

    @pytest.mark.asyncio
    async def test_dkim_pass_from_auth_results(self, verifier):
        headers = {"Authentication-Results": "mx.google.com; dkim=pass; spf=pass"}
        result = await verifier.verify(headers)
        assert result.dkim_pass is True
        assert result.spf_pass is True
        assert result.risk_contribution == 0.0

    @pytest.mark.asyncio
    async def test_both_fail_max_risk(self, verifier):
        headers = {}
        result = await verifier.verify(headers)
        assert result.spf_pass is False
        assert result.dkim_pass is False
        assert result.risk_contribution == 100.0

    @pytest.mark.asyncio
    async def test_dkim_signature_format(self, verifier):
        headers = {
            "DKIM-Signature": "v=1; a=rsa-sha256; d=example.com; s=selector; b=abc123"
        }
        result = await verifier.verify(headers)
        assert result.dkim_pass is True


# ═══════════════════════════════════════════════════════════════════════════════
# URL SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

class TestURLScanner:
    @pytest.fixture
    def scanner(self):
        return URLScanner()

    @pytest.mark.asyncio
    async def test_clean_urls(self, scanner):
        urls = ["https://www.google.com", "https://github.com"]
        result = await scanner.scan(urls)
        assert result.total_urls == 2
        assert result.suspicious_count == 0
        assert result.risk_contribution == 0.0

    @pytest.mark.asyncio
    async def test_ip_based_url(self, scanner):
        urls = ["http://192.168.1.1/login"]
        result = await scanner.scan(urls)
        assert result.suspicious_count == 1
        assert result.results[0].has_ip_address is True

    @pytest.mark.asyncio
    async def test_suspicious_tld(self, scanner):
        urls = ["http://evil-site.tk/phishing"]
        result = await scanner.scan(urls)
        assert result.suspicious_count == 1
        assert result.results[0].suspicious_tld is True

    @pytest.mark.asyncio
    async def test_url_shortener(self, scanner):
        urls = ["https://bit.ly/abc123"]
        result = await scanner.scan(urls)
        assert result.suspicious_count == 1
        assert result.results[0].is_shortener is True

    @pytest.mark.asyncio
    async def test_empty_urls(self, scanner):
        result = await scanner.scan([])
        assert result.total_urls == 0
        assert result.risk_contribution == 0.0

    @pytest.mark.asyncio
    async def test_phishing_path(self, scanner):
        urls = ["https://example.com/secure/login/verify"]
        result = await scanner.scan(urls)
        assert result.suspicious_count == 1
        assert any("phishing" in r.lower() for r in result.results[0].reasons)

    @pytest.mark.asyncio
    async def test_non_standard_port(self, scanner):
        urls = ["http://example.com:8888/admin"]
        result = await scanner.scan(urls)
        assert result.suspicious_count == 1
        assert any("port" in r.lower() for r in result.results[0].reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# ATTACHMENT SCANNER
# ═══════════════════════════════════════════════════════════════════════════════

class TestAttachmentScanner:
    @pytest.fixture
    def scanner(self):
        return AttachmentScanner()

    def test_clean_attachment(self, scanner):
        result = scanner.scan("report.pdf", file_size=1024)
        assert result.is_malicious is False
        assert result.blocked_extension is False

    def test_blocked_extension(self, scanner):
        result = scanner.scan("malware.exe")
        assert result.is_malicious is True
        assert result.blocked_extension is True

    def test_double_extension(self, scanner):
        result = scanner.scan("invoice.pdf.exe")
        assert result.is_malicious is True
        assert result.double_extension is True

    def test_size_anomaly(self, scanner):
        # 30 MB — exceeds 25 MB limit
        result = scanner.scan("big_file.zip", file_size=30 * 1024 * 1024)
        assert result.size_anomaly is True

    def test_zero_byte_file(self, scanner):
        result = scanner.scan("empty.txt", file_size=0)
        assert result.size_anomaly is True

    def test_suspicious_filename(self, scanner):
        result = scanner.scan("urgent_invoice_payment.pdf", file_size=1024)
        assert any("suspicious" in r.lower() for r in result.reasons)

    def test_batch_scanning(self, scanner):
        attachments = [
            {"filename": "report.pdf", "file_size": 1024},
            {"filename": "malware.exe", "file_size": 512},
            {"filename": "notes.txt", "file_size": 256},
        ]
        results = scanner.scan_batch(attachments)
        assert len(results) == 3
        assert results[1].is_malicious is True


# ═══════════════════════════════════════════════════════════════════════════════
# HEADER ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeaderAnalyzer:
    @pytest.fixture
    def analyzer(self):
        return HeaderAnalyzer()

    @pytest.mark.asyncio
    async def test_clean_headers(self, analyzer):
        headers = {
            "From": "user@example.com",
            "Reply-To": "user@example.com",
            "Message-ID": "<abc123@example.com>",
            "Date": "Mon, 24 Feb 2026 10:00:00 +0000",
            "Received": "from mx.example.com\nfrom relay.example.com",
        }
        result = await analyzer.analyze(headers)
        assert len(result.anomalies) == 0
        assert result.risk_contribution == 0.0

    @pytest.mark.asyncio
    async def test_from_reply_to_mismatch(self, analyzer):
        headers = {
            "From": "ceo@company.com",
            "Reply-To": "attacker@evil.com",
            "Message-ID": "<abc123>",
            "Date": "Mon, 24 Feb 2026 10:00:00 +0000",
            "Received": "from mx1\nfrom mx2",
        }
        result = await analyzer.analyze(headers)
        assert result.from_reply_to_mismatch is True
        assert result.risk_contribution > 0

    @pytest.mark.asyncio
    async def test_missing_message_id(self, analyzer):
        headers = {
            "From": "user@example.com",
            "Date": "Mon, 24 Feb 2026 10:00:00 +0000",
            "Received": "from mx1",
        }
        result = await analyzer.analyze(headers)
        assert result.missing_message_id is True

    @pytest.mark.asyncio
    async def test_suspicious_x_mailer(self, analyzer):
        headers = {
            "From": "user@example.com",
            "X-Mailer": "PHPMailer 6.0",
            "Message-ID": "<abc>",
            "Date": "Mon, 24 Feb 2026 10:00:00 +0000",
            "Received": "from mx1",
        }
        result = await analyzer.analyze(headers)
        assert result.suspicious_x_mailer is True


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN REPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestDomainReputation:
    @pytest.fixture
    def checker(self):
        return DomainReputationChecker()

    @pytest.mark.asyncio
    async def test_trusted_domain(self, checker):
        result = await checker.check("gmail.com")
        assert result.is_trusted is True
        assert result.risk_contribution == 0.0

    @pytest.mark.asyncio
    async def test_disposable_domain(self, checker):
        result = await checker.check("mailinator.com")
        assert result.is_disposable is True
        assert result.risk_contribution >= 50.0

    @pytest.mark.asyncio
    async def test_blocklisted_domain(self):
        checker = DomainReputationChecker(custom_blocklist={"spam.com"})
        result = await checker.check("spam.com")
        assert result.is_blocklisted is True
        assert result.risk_contribution >= 60.0

    @pytest.mark.asyncio
    async def test_normal_domain(self, checker):
        result = await checker.check("company.com")
        assert result.is_disposable is False
        assert result.is_blocklisted is False

    @pytest.mark.asyncio
    async def test_suspicious_numeric_domain(self, checker):
        result = await checker.check("123456.com")
        assert result.risk_contribution > 0

    @pytest.mark.asyncio
    async def test_hyphen_heavy_domain(self, checker):
        result = await checker.check("my-very-long-phishing-domain.com")
        assert any("hyphen" in r.lower() for r in result.reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPOSITE RISK SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskScorer:
    @pytest.fixture
    def scorer(self):
        return RiskScorer()

    @pytest.mark.asyncio
    async def test_low_risk_email(self, scorer):
        context = EmailSecurityContext(
            sender_email="user@gmail.com",
            sender_domain="gmail.com",
            headers={
                "Authentication-Results": "dkim=pass; spf=pass",
                "Message-ID": "<abc123>",
                "From": "user@gmail.com",
                "Date": "Mon, 24 Feb 2026",
                "Received": "from mx1\nfrom mx2",
            },
        )
        report = await scorer.score(context)
        assert report.risk_score <= 30
        assert report.risk_level.value == "low"
        assert report.recommended_action.value == "auto_approve"

    @pytest.mark.asyncio
    async def test_high_risk_email(self, scorer):
        context = EmailSecurityContext(
            sender_email="scammer@mailinator.com",
            sender_domain="mailinator.com",
            headers={},
            urls=["http://192.168.1.1/login", "http://evil.tk/phish"],
            attachments=[{"filename": "invoice.pdf.exe", "file_size": 1024}],
        )
        report = await scorer.score(context)
        assert report.risk_score > 50
        assert report.risk_level.value in ("high", "critical")
        assert len(report.risk_factors) > 0

    @pytest.mark.asyncio
    async def test_score_range(self, scorer):
        context = EmailSecurityContext(
            sender_email="test@example.com",
            headers={},
        )
        report = await scorer.score(context)
        assert 0 <= report.risk_score <= 100

    @pytest.mark.asyncio
    async def test_report_contains_all_checks(self, scorer):
        context = EmailSecurityContext(
            sender_email="user@example.com",
            headers={"From": "user@example.com"},
            urls=["https://example.com"],
            attachments=[{"filename": "doc.pdf", "file_size": 100}],
        )
        report = await scorer.score(context)
        assert report.spf_dkim is not None
        assert report.url_scan is not None
        assert report.header_analysis is not None
        assert report.domain_reputation is not None
