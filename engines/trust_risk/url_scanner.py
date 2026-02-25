"""
URL Scanner — Heuristic-based URL threat detection.
Checks for suspicious TLDs, IP-based URLs, shorteners, homograph attacks.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse
from shared.logger import get_logger
from shared.constants import SUSPICIOUS_TLDS, URL_SHORTENER_DOMAINS
from .schemas import URLScanResult, URLScanBatchResult

logger = get_logger("trust_risk.url_scanner")


class URLScanner:
    """
    Scans URLs extracted from emails for potential security threats.
    Uses heuristic checks that work without external API keys.
    """

    # Regex to detect IP-based URLs (IPv4)
    IP_URL_PATTERN = re.compile(
        r"https?://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    )

    # Common IDN homograph characters (Cyrillic lookalikes for Latin)
    HOMOGRAPH_MAP = {
        "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
        "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
        "\u0455": "s", "\u0458": "j", "\u04bb": "h", "\u0501": "d",
    }

    async def scan(self, urls: list[str]) -> URLScanBatchResult:
        """
        Scan a list of URLs and produce aggregated results.

        Args:
            urls: List of URL strings extracted from the email.

        Returns:
            URLScanBatchResult with per-URL results and aggregate risk.
        """
        if not urls:
            return URLScanBatchResult(
                results=[], total_urls=0,
                suspicious_count=0, risk_contribution=0.0,
            )

        results = [self._scan_single(url) for url in urls]
        suspicious_count = sum(1 for r in results if r.is_suspicious)

        # Aggregate risk: proportional to suspicious ratio, scaled to 100
        if results:
            ratio = suspicious_count / len(results)
            max_individual = max(r.risk_contribution for r in results)
            risk = min(100.0, (ratio * 60) + (max_individual * 0.4))
        else:
            risk = 0.0

        return URLScanBatchResult(
            results=results,
            total_urls=len(urls),
            suspicious_count=suspicious_count,
            risk_contribution=round(risk, 2),
        )

    def _scan_single(self, url: str) -> URLScanResult:
        """Run all heuristic checks on a single URL."""
        reasons: list[str] = []
        risk = 0.0

        try:
            parsed = urlparse(url)
            domain = (parsed.hostname or "").lower()
            full_domain = f"{parsed.hostname}" if parsed.hostname else ""
        except Exception:
            return URLScanResult(
                url=url, is_suspicious=True,
                reasons=["Malformed URL"], risk_contribution=80.0,
            )

        # Check 1: IP-based URL
        has_ip = bool(self.IP_URL_PATTERN.match(url))
        if has_ip:
            reasons.append("IP-based URL (no domain name)")
            risk += 30.0

        # Check 2: Suspicious TLD
        suspicious_tld = any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS)
        if suspicious_tld:
            reasons.append(f"Suspicious TLD: .{domain.split('.')[-1]}")
            risk += 25.0

        # Check 3: URL shortener
        is_shortener = domain in URL_SHORTENER_DOMAINS
        if is_shortener:
            reasons.append(f"URL shortener: {domain}")
            risk += 20.0

        # Check 4: Homograph attack detection
        homograph = self._check_homograph(full_domain)
        if homograph:
            reasons.append(f"Possible homograph attack: {full_domain}")
            risk += 40.0

        # Check 5: Excessive subdomains (potential phishing)
        subdomain_count = len(domain.split(".")) - 2 if domain else 0
        if subdomain_count >= 3:
            reasons.append(f"Excessive subdomains ({subdomain_count})")
            risk += 15.0

        # Check 6: Suspicious path patterns
        path = parsed.path.lower()
        if any(keyword in path for keyword in [
            "login", "signin", "verify", "account",
            "secure", "update", "confirm", "banking",
        ]):
            reasons.append("Suspicious path keywords (potential phishing)")
            risk += 15.0

        # Check 7: Port in URL (non-standard)
        if parsed.port and parsed.port not in (80, 443):
            reasons.append(f"Non-standard port: {parsed.port}")
            risk += 10.0

        risk = min(100.0, risk)
        is_suspicious = len(reasons) > 0

        return URLScanResult(
            url=url,
            is_suspicious=is_suspicious,
            reasons=reasons,
            is_shortener=is_shortener,
            has_ip_address=has_ip,
            suspicious_tld=suspicious_tld,
            homograph_detected=homograph,
            risk_contribution=round(risk, 2),
        )

    def _check_homograph(self, domain: str) -> bool:
        """
        Detect IDN homograph attacks by checking for mixed-script characters.
        """
        if not domain:
            return False
        has_latin = bool(re.search(r"[a-zA-Z]", domain))
        has_non_latin = any(c in self.HOMOGRAPH_MAP for c in domain)
        return has_latin and has_non_latin
