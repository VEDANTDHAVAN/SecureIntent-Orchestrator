"""
Shared constants for SecureIntent-Orchestrator security layer.
Risk thresholds, rate limits, blocked extensions, suspicious indicators.
"""

from enum import Enum


# ─── Risk Scoring ─────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"             # 0–30
    MEDIUM = "medium"       # 31–60
    HIGH = "high"           # 61–85
    CRITICAL = "critical"   # 86–100


class RiskAction(str, Enum):
    AUTO_APPROVE = "auto_approve"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


# Risk thresholds (inclusive upper bounds)
RISK_LEVEL_THRESHOLDS = {
    RiskLevel.LOW: 30,
    RiskLevel.MEDIUM: 60,
    RiskLevel.HIGH: 85,
    RiskLevel.CRITICAL: 100,
}

# Scoring weights (must sum to 1.0)
RISK_WEIGHTS = {
    "spf_dkim": 0.25,
    "url": 0.20,
    "attachment": 0.20,
    "header": 0.15,
    "domain": 0.20,
}

# Action routing thresholds
RISK_ACTION_THRESHOLDS = {
    RiskAction.AUTO_APPROVE: 30,       # score <= 30 → auto-approve
    RiskAction.REQUIRE_APPROVAL: 75,   # score 31–75 → require approval
    RiskAction.BLOCK: 100,             # score > 75 → block
}


# ─── Rate Limiting ────────────────────────────────────────────────────────────

DEFAULT_RATE_LIMIT_MAX_REQUESTS = 60       # per window
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60     # 1-minute sliding window
DEFAULT_RATE_LIMIT_PER_TOOL_MAX = 20       # per tool per window


# ─── Blocked / Suspicious Lists ──────────────────────────────────────────────

BLOCKED_FILE_EXTENSIONS = frozenset({
    ".exe", ".bat", ".cmd", ".scr", ".pif", ".com",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".cpl", ".hta", ".inf", ".reg",
    ".ps1", ".psm1", ".psd1", ".lnk", ".dll",
})

SUSPICIOUS_DOUBLE_EXTENSIONS = frozenset({
    ".pdf.exe", ".doc.exe", ".docx.exe", ".xls.exe",
    ".jpg.exe", ".png.exe", ".txt.exe", ".zip.exe",
    ".pdf.scr", ".doc.scr", ".pdf.bat", ".doc.js",
})

SUSPICIOUS_TLDS = frozenset({
    ".tk", ".ml", ".ga", ".cf", ".gq",      # Free TLDs (high abuse)
    ".top", ".xyz", ".club", ".work",        # Cheap TLDs
    ".buzz", ".cam", ".icu", ".monster",     # Spam-heavy TLDs
    ".bid", ".click", ".loan", ".download",
})

URL_SHORTENER_DOMAINS = frozenset({
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly",
    "is.gd", "buff.ly", "rebrand.ly", "cutt.ly",
    "short.io", "tiny.cc", "bl.ink", "rb.gy",
})

DISPOSABLE_EMAIL_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "tempmail.com",
    "throwaway.email", "yopmail.com", "sharklasers.com",
    "guerrillamailblock.com", "grr.la", "dispostable.com",
    "trashmail.com", "10minutemail.com", "temp-mail.org",
    "fakeinbox.com", "mailnesia.com", "maildrop.cc",
    "discard.email", "mailsac.com", "getnada.com",
})

TRUSTED_DOMAINS_DEFAULT = frozenset({
    "gmail.com", "outlook.com", "yahoo.com",
    "hotmail.com", "protonmail.com", "icloud.com",
})

SUSPICIOUS_X_MAILERS = frozenset({
    "PHPMailer", "SwiftMailer", "Mass Mailer",
    "Bulk Sender", "Email Blaster",
})


# ─── Approval ─────────────────────────────────────────────────────────────────

DEFAULT_APPROVAL_TIMEOUT_MINUTES = 60
MAX_ESCALATION_LEVELS = 3


# ─── Sandbox ──────────────────────────────────────────────────────────────────

DANGEROUS_OPERATIONS = frozenset({
    "bulk_delete", "mass_send", "export_all_data",
    "delete_account", "transfer_funds", "modify_permissions",
})

MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
