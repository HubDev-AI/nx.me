"""Content filter for advisor input/output safety.

Input: strip prompt injection, enforce max length, rate-limit.
Output: scan for C-2 violations (forbidden terms from SOUL.md).
"""
from __future__ import annotations

import logging
import re
import unicodedata

import redis.asyncio as aioredis

from app.api.errors import RateLimitExceeded
from app.config import settings

logger = logging.getLogger(__name__)

# Curation principle: block terms that rate/judge the person's appearance,
# NOT terms that describe aesthetics. "Your hair looks beautiful" is fine;
# "you're ugly" is not.
_FORBIDDEN_OUTPUT_TERMS: tuple[str, ...] = (
    "ugly",
    "hideous",
    "unattractive",
    "beauty score",
    "out of ten",
    "/10",
    "ranking",
    "rating",
)

# Pre-compiled patterns for word-boundary matching (single words)
_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
    for term in _FORBIDDEN_OUTPUT_TERMS
    if " " not in term and "/" not in term
)
# Multi-word and special terms use simple containment (word boundaries are natural)
_FORBIDDEN_EXACT: tuple[str, ...] = tuple(
    term for term in _FORBIDDEN_OUTPUT_TERMS
    if " " in term or "/" in term
)

# Prompt injection patterns (AC-SEC: block system-override attempts)
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a)\s+", re.IGNORECASE),
    re.compile(r"forget\s+everything", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(previous|prior)\s+", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"override\s+(previous|system)\s+", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system|prompt|instructions?)", re.IGNORECASE),
    re.compile(r"what\s+(are|is)\s+your\s+(system|initial)\s+(prompt|instructions?)", re.IGNORECASE),
    re.compile(r"repeat\s+(your|the)\s+(system|initial)\s+", re.IGNORECASE),
    re.compile(r"(print|output|show|display)\s+(your|the)\s+(system|initial)\s+", re.IGNORECASE),
    re.compile(r"bypass\s+(safety|content|filter)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|any)\s+", re.IGNORECASE),
    re.compile(r"base64\s*:", re.IGNORECASE),
    re.compile(r"<<\s*SYS\s*>>", re.IGNORECASE),
    # A-10: RTL override, zero-width joiners, math alphanumeric variants
    re.compile(r"[\u202e\u202d\u200f\u200e]"),  # Bidi overrides
    re.compile(r"[\u2066-\u2069]"),  # Bidi isolates
    re.compile(r"[\U0001d400-\U0001d7ff]"),  # Math alphanumeric symbols (homoglyphs)
]

# Redis key templates
# A-13: Rate limit keys cleaned up in DELETE /auth/account (auth.py).
_RATE_KEY_TEMPLATE = "advisor_chat_rate:{user_id}"


def sanitize_input(text: str) -> str:
    """Strip prompt-injection patterns and enforce max length.

    Returns cleaned text. Raises ValueError if text exceeds max length.
    """
    if len(text) > settings.ADVISOR_MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message too long: {len(text)} chars (max {settings.ADVISOR_MAX_MESSAGE_LENGTH})"
        )

    # Normalize unicode to NFC to defeat homoglyph attacks
    cleaned = unicodedata.normalize("NFC", text)
    # Strip zero-width characters (including zero-width joiners, A-10)
    cleaned = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]", "", cleaned)
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Collapse extra whitespace introduced by stripping
    cleaned = re.sub(r"\s{3,}", " ", cleaned).strip()

    if not cleaned:
        raise ValueError("Message is empty after sanitization")

    return cleaned


async def check_rate_limit(user_id: str, redis_client: aioredis.Redis) -> None:
    """Enforce per-user hourly chat rate limit (atomic INCR-first).

    Raises RateLimitExceeded with the remaining TTL so the caller can include
    a ``Retry-After`` header in the 429 response (LE-1).
    """
    key = _RATE_KEY_TEMPLATE.format(user_id=user_id)
    new_count = await redis_client.incr(key)
    if new_count == 1:
        await redis_client.expire(key, settings.ADVISOR_CHAT_RATE_LIMIT_WINDOW_SECONDS)

    if new_count > settings.ADVISOR_CHAT_RATE_LIMIT:
        # Do NOT decr — that would gift the next request a free attempt (M-11).
        # The count will naturally expire with the key TTL.
        ttl: int = await redis_client.ttl(key)
        # A-12: Log rate limit hits for visibility
        logger.warning(
            "Rate limit hit for user %s: %d messages (limit %d)",
            user_id, new_count, settings.ADVISOR_CHAT_RATE_LIMIT,
        )
        raise RateLimitExceeded(retry_after=max(ttl, 0))

    # H-4: Track daily message count for model degradation (separate from hourly rate limit)
    from datetime import datetime, timezone
    daily_key = f"advisor_daily_msgs:{user_id}:{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}"
    daily_count = await redis_client.incr(daily_key)
    if daily_count == 1:
        await redis_client.expire(daily_key, 86400)


def scan_output(text: str) -> bool:
    """Return True if the text contains C-2 violations (forbidden terms)."""
    lower = text.lower()
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern.search(lower):
            logger.warning("C-2 violation detected: forbidden pattern '%s'", pattern.pattern)
            return True
    for term in _FORBIDDEN_EXACT:
        if term in lower:
            logger.warning("C-2 violation detected: forbidden term '%s'", term)
            return True
    return False


# A-15: Violation-type-specific fallback messages
_FALLBACK_RESPONSES: dict[str, str] = {
    "c2_violation": "Hard to say without more context — want to try describing what you're going for?",
    "rate_limited": "Let's slow down a bit — I'll be here when you're ready.",
    "content_violation": "I can't go there — want to try a different angle?",
    "default": "Hard to say without more context — want to try describing what you're going for?",
}


def get_fallback_response(violation_type: str = "default") -> str:
    """Return a fallback response appropriate to the violation type."""
    return _FALLBACK_RESPONSES.get(violation_type, _FALLBACK_RESPONSES["default"])
