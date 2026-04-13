"""Disposable email domain detection.

Uses the community-maintained `disposable-email-domains` package (~3000+ domains)
as the primary blocklist. Falls back to a minimal hardcoded set if the package
is not installed (should not happen in production).

CS-1 T-1: Replaces the original ~60-domain hardcoded list.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from disposable_email_domains import blocklist as _DISPOSABLE_DOMAINS

    if len(_DISPOSABLE_DOMAINS) < 100:
        raise RuntimeError(
            f"Disposable email blocklist has only {len(_DISPOSABLE_DOMAINS)} domains. "
            "Expected 100+. Check disposable-email-domains package."
        )
    else:
        logger.info(
            "Loaded disposable email blocklist: %d domains", len(_DISPOSABLE_DOMAINS)
        )
except ImportError:
    from app.config import settings as _settings

    if _settings.APP_ENV not in ("development", "test"):
        raise RuntimeError(
            "disposable-email-domains package required in non-development environments. "
            "Run: pip install disposable-email-domains"
        )
    logger.critical(
        "disposable-email-domains package not installed — using minimal fallback blocklist."
    )
    _DISPOSABLE_DOMAINS: set[str] = {
        "mailinator.com",
        "guerrillamail.com",
        "yopmail.com",
        "tempmail.com",
        "throwaway.email",
        "sharklasers.com",
        "10minutemail.com",
        "maildrop.cc",
        "trashmail.com",
    }


def is_disposable_email(email: str) -> bool:
    """Return True if the email's domain is a known disposable provider."""
    parts = email.lower().rsplit("@", maxsplit=1)
    if len(parts) != 2:
        return False
    domain = parts[1].strip()
    return domain in _DISPOSABLE_DOMAINS
