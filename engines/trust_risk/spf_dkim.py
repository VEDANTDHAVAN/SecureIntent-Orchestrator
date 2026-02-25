"""
spf_dkim.py
-----------
Parses Gmail API message headers to extract SPF, DKIM, and DMARC
authentication results.

These are used by the risk scorer to penalize unauthenticated senders
BEFORE the LLM is ever invoked.
"""

import re
from dataclasses import dataclass
from typing import Literal


AuthStatus = Literal["pass", "fail", "none"]


@dataclass
class SpfDkimResult:
    spf: AuthStatus = "none"
    dkim: AuthStatus = "none"
    dmarc: AuthStatus = "none"

    @property
    def is_fully_authenticated(self) -> bool:
        return self.spf == "pass" and self.dkim == "pass"

    @property
    def is_suspicious(self) -> bool:
        """True if ANY mechanism fails (not just missing)."""
        return self.spf == "fail" or self.dkim == "fail" or self.dmarc == "fail"

    def to_dict(self) -> dict:
        return {"spf": self.spf, "dkim": self.dkim, "dmarc": self.dmarc}


def extract_auth_results(headers: list[dict]) -> SpfDkimResult:
    """
    Parse `Authentication-Results` (and `ARC-Authentication-Results`) headers
    from a Gmail API message payload's headers list.

    Gmail API header format:
        [{"name": "Authentication-Results", "value": "mx.google.com; spf=pass ... dkim=fail ..."}]

    Returns a SpfDkimResult with pass/fail/none per mechanism.
    """
    result = SpfDkimResult()

    auth_header_names = {
        "authentication-results",
        "arc-authentication-results",
        "dkim-signature",        # presence implies DKIM attempted
        "received-spf",          # fallback plain-text SPF header
    }

    for header in headers:
        name = header.get("name", "").lower()
        value = header.get("value", "").lower()

        if name not in auth_header_names:
            continue

        # ── SPF ──────────────────────────────────────────────────────────────
        if result.spf == "none":
            if name == "received-spf":
                # "Received-SPF: pass ..." or "Received-SPF: fail ..."
                if value.startswith("pass"):
                    result.spf = "pass"
                elif value.startswith("fail") or value.startswith("softfail"):
                    result.spf = "fail"
            else:
                spf_match = re.search(r"spf=(pass|fail|softfail|neutral|none|permerror|temperror)", value)
                if spf_match:
                    raw = spf_match.group(1)
                    result.spf = "fail" if raw in ("fail", "softfail", "permerror", "temperror") else (
                        "pass" if raw == "pass" else "none"
                    )

        # ── DKIM ─────────────────────────────────────────────────────────────
        if result.dkim == "none":
            if name == "dkim-signature":
                # Header presence means DKIM was attempted; result is in Authentication-Results
                pass
            else:
                dkim_match = re.search(r"dkim=(pass|fail|neutral|none|permerror|temperror)", value)
                if dkim_match:
                    raw = dkim_match.group(1)
                    result.dkim = "fail" if raw in ("fail", "permerror", "temperror") else (
                        "pass" if raw == "pass" else "none"
                    )

        # ── DMARC ────────────────────────────────────────────────────────────
        if result.dmarc == "none":
            dmarc_match = re.search(r"dmarc=(pass|fail|none)", value)
            if dmarc_match:
                raw = dmarc_match.group(1)
                result.dmarc = "fail" if raw == "fail" else ("pass" if raw == "pass" else "none")

    return result
