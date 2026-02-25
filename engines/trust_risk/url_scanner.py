"""
url_scanner.py
--------------
Extracts URLs from email body text and scans them against a local
domain blocklist.

Intentionally lightweight — no external API calls by default.
If VIRUSTOTAL_API_KEY is set, will additionally check flagged URLs
against VirusTotal.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger


# ── Blocklist ─────────────────────────────────────────────────────────────────
# Bundled list of known-bad domains/patterns. Extend via blocked_domains.txt.
_BUILTIN_BAD_DOMAINS = {
    # Generic phishing / scam infrastructure
    "bit.ly", "tinyurl.com", "t.co",            # often abused shorteners
    "discord.gg", "telegra.ph",
    # Known malware domains (samples — extend via blocked_domains.txt)
    "malware.com", "phishing-site.net",
    "free-gift-claim.com", "urgent-payment.net",
    "verify-account-now.com", "secure-login-help.com",
}

_BLOCKLIST_FILE = Path(__file__).parent / "blocked_domains.txt"


def _load_blocklist() -> set[str]:
    """Load the bundled domain blocklist, merging file + built-ins."""
    domains = set(_BUILTIN_BAD_DOMAINS)
    if _BLOCKLIST_FILE.exists():
        for line in _BLOCKLIST_FILE.read_text().splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                domains.add(line)
    return domains


_BLOCKLIST: set[str] = _load_blocklist()

# ── URL extraction ─────────────────────────────────────────────────────────────
_URL_RE = re.compile(
    r"https?://[^\s\"'<>\]\[)(\{\}]+",
    re.IGNORECASE,
)

_DOMAIN_RE = re.compile(r"https?://(?:www\.)?([^/?\s]+)", re.IGNORECASE)


@dataclass
class UrlScanResult:
    urls: list[str] = field(default_factory=list)
    flagged: list[str] = field(default_factory=list)
    is_safe: bool = True

    def to_dict(self) -> dict:
        return {
            "urls": self.urls,
            "flagged": self.flagged,
            "is_safe": self.is_safe,
        }


def extract_urls(body: str) -> list[str]:
    """Extract all http(s) URLs from plain text email body."""
    return list(dict.fromkeys(_URL_RE.findall(body)))  # deduplicated, order preserved


def scan_urls(urls: list[str]) -> UrlScanResult:
    """
    Check extracted URLs against the local domain blocklist.
    If VirusTotal key is present, additionally query flagged URLs.

    Returns UrlScanResult with flagged urls and overall is_safe flag.
    """
    flagged: list[str] = []

    for url in urls:
        domain_match = _DOMAIN_RE.match(url)
        if not domain_match:
            continue
        domain = domain_match.group(1).lower()

        # Check full domain and parent domains against blocklist
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            if candidate in _BLOCKLIST:
                flagged.append(url)
                break

    # Optional: VirusTotal lookup for anything flagged locally
    vt_key = os.getenv("VIRUSTOTAL_API_KEY")
    if vt_key and flagged:
        flagged = _virustotal_check(flagged, vt_key)

    return UrlScanResult(
        urls=urls,
        flagged=flagged,
        is_safe=len(flagged) == 0,
    )


def _virustotal_check(urls: list[str], api_key: str) -> list[str]:
    """
    Query VirusTotal URL scan endpoint for each URL.
    Returns the list of URLs confirmed malicious (superset of input).
    Silently skips on network/API errors.
    """
    try:
        import httpx

        confirmed_bad: list[str] = list(urls)  # start with locally-flagged
        headers = {"x-apikey": api_key}

        for url in urls:
            try:
                resp = httpx.post(
                    "https://www.virustotal.com/api/v3/urls",
                    headers=headers,
                    data={"url": url},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    analysis_id = resp.json().get("data", {}).get("id", "")
                    if analysis_id:
                        report = httpx.get(
                            f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
                            headers=headers,
                            timeout=5.0,
                        )
                        stats = (
                            report.json()
                            .get("data", {})
                            .get("attributes", {})
                            .get("stats", {})
                        )
                        # Flag if any engine marks it malicious
                        if stats.get("malicious", 0) > 0:
                            if url not in confirmed_bad:
                                confirmed_bad.append(url)
            except Exception as exc:
                logger.debug("VirusTotal check failed for %s: %s", url, exc)

        return confirmed_bad
    except ImportError:
        return urls
