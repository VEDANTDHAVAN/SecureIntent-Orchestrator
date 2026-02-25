"""
Loguru-based structured logger for SecureIntent-Orchestrator.
Provides JSON-formatted structured logging with file rotation.
"""

import sys
from loguru import logger

# Remove default handler
logger.remove()

# ─── Console Handler (human-readable) ────────────────────────────────────────
logger.add(
    sys.stderr,
    level="INFO",
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    colorize=True,
)

# ─── File Handler (structured JSON for audit) ────────────────────────────────
logger.add(
    "logs/secureintent_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    format="{time:YYYY-MM-DDTHH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    rotation="10 MB",
    retention="30 days",
    compression="zip",
    serialize=True,   # JSON output
    enqueue=True,      # Thread-safe
)

# ─── Security Audit Log (critical actions only) ──────────────────────────────
logger.add(
    "logs/security_audit_{time:YYYY-MM-DD}.log",
    level="WARNING",
    format="{time:YYYY-MM-DDTHH:mm:ss.SSS} | {level} | {message}",
    rotation="5 MB",
    retention="90 days",
    compression="zip",
    serialize=True,
    enqueue=True,
    filter=lambda record: record["extra"].get("audit", False),
)


def get_logger(name: str):
    """Get a named logger instance with context binding."""
    return logger.bind(module=name)


def audit_log(message: str, **kwargs):
    """Log a security-auditable event."""
    logger.bind(audit=True, **kwargs).warning(message)
