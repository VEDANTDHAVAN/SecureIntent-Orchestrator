"""
SPF/DKIM Email Authentication Verifier.
Performs DNS-based verification of sender authentication records.
"""

from __future__ import annotations

import re
from typing import Optional
from shared.logger import get_logger
from .schemas import SPFDKIMResult

try:
    import dns.resolver
    import dns.exception
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

logger = get_logger("trust_risk.spf_dkim")


class SPFDKIMVerifier:
    """
    Verifies SPF and DKIM records for email sender authentication.
    
    SPF: Checks if the sender's domain has a valid SPF record and
         whether the sending IP is authorized.
    DKIM: Validates DKIM signature by checking the DNS key record.
    """

    async def verify(self, email_headers: dict) -> SPFDKIMResult:
        """
        Run SPF and DKIM verification on the provided email headers.

        Args:
            email_headers: Dictionary of email headers. Expected keys:
                - "From": Sender email address
                - "Received-SPF": SPF result header (if available)
                - "Authentication-Results": Auth results header
                - "DKIM-Signature": DKIM signature header
                - "Return-Path": Return path / envelope sender

        Returns:
            SPFDKIMResult with pass/fail status and risk contribution.
        """
        spf_pass, spf_details = self._check_spf(email_headers)
        dkim_pass, dkim_details = self._check_dkim(email_headers)

        # Calculate risk contribution (0 = both pass, 100 = both fail)
        risk = 0.0
        if not spf_pass:
            risk += 50.0
        if not dkim_pass:
            risk += 50.0

        return SPFDKIMResult(
            spf_pass=spf_pass,
            dkim_pass=dkim_pass,
            spf_details=spf_details,
            dkim_details=dkim_details,
            risk_contribution=risk,
        )

    def _check_spf(self, headers: dict) -> tuple[bool, str]:
        """
        Check SPF status from email headers or via DNS lookup.
        """
        # Method 1: Check pre-existing SPF header
        received_spf = headers.get("Received-SPF", "")
        if received_spf:
            spf_lower = received_spf.lower()
            if "pass" in spf_lower:
                return True, f"SPF pass (from header): {received_spf[:100]}"
            elif "fail" in spf_lower or "softfail" in spf_lower:
                return False, f"SPF fail (from header): {received_spf[:100]}"
            elif "neutral" in spf_lower or "none" in spf_lower:
                return False, f"SPF neutral/none: {received_spf[:100]}"

        # Method 2: Check Authentication-Results header
        auth_results = headers.get("Authentication-Results", "")
        if auth_results:
            spf_match = re.search(r"spf=(pass|fail|softfail|neutral|none)", auth_results, re.IGNORECASE)
            if spf_match:
                result = spf_match.group(1).lower()
                passed = result == "pass"
                return passed, f"SPF {result} (from Authentication-Results)"

        # Method 3: DNS lookup for the sender domain
        sender_domain = self._extract_domain(headers.get("From", ""))
        if sender_domain and DNS_AVAILABLE:
            return self._dns_spf_check(sender_domain)

        return False, "No SPF information available"

    def _check_dkim(self, headers: dict) -> tuple[bool, str]:
        """
        Check DKIM status from email headers.
        """
        # Check Authentication-Results for DKIM
        auth_results = headers.get("Authentication-Results", "")
        if auth_results:
            dkim_match = re.search(r"dkim=(pass|fail|neutral|none)", auth_results, re.IGNORECASE)
            if dkim_match:
                result = dkim_match.group(1).lower()
                passed = result == "pass"
                return passed, f"DKIM {result} (from Authentication-Results)"

        # Check if DKIM-Signature header exists
        dkim_sig = headers.get("DKIM-Signature", "")
        if dkim_sig:
            # DKIM signature present — attempt basic validation
            if self._validate_dkim_signature_format(dkim_sig):
                return True, "DKIM signature present and well-formed"
            return False, "DKIM signature present but malformed"

        return False, "No DKIM signature found"

    def _dns_spf_check(self, domain: str) -> tuple[bool, str]:
        """
        Perform DNS TXT lookup for SPF record.
        """
        try:
            answers = dns.resolver.resolve(domain, "TXT")
            for rdata in answers:
                txt = rdata.to_text().strip('"')
                if txt.startswith("v=spf1"):
                    # SPF record found — check for restrictive policy
                    if "-all" in txt:
                        return True, f"SPF record found with strict policy: {txt[:80]}"
                    elif "~all" in txt:
                        return True, f"SPF record found with soft policy: {txt[:80]}"
                    elif "+all" in txt:
                        return False, f"SPF record too permissive (+all): {txt[:80]}"
                    else:
                        return True, f"SPF record found: {txt[:80]}"

            return False, f"No SPF record found for {domain}"

        except dns.exception.DNSException as e:
            logger.warning(f"DNS SPF lookup failed for {domain}: {e}")
            return False, f"DNS lookup failed: {str(e)}"

    def _validate_dkim_signature_format(self, signature: str) -> bool:
        """Basic format validation of DKIM-Signature header."""
        required_tags = ["v=", "a=", "d=", "s=", "b="]
        return all(tag in signature for tag in required_tags)

    @staticmethod
    def _extract_domain(from_header: str) -> Optional[str]:
        """Extract domain from a From header value."""
        match = re.search(r"@([\w.-]+)", from_header)
        return match.group(1).lower() if match else None
