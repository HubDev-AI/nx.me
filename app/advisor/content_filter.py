"""Content filter for advisor input/output safety.

Input: strip prompt injection, enforce max length, rate-limit.
Output: scan for C-2 violations (forbidden terms from SOUL.md).
"""
from __future__ import annotations

import logging
import re

import redis.asyncio as aioredis

from app.api.errors import RateLimitExceeded
from app.config import settings

logger = logging.getLogger(__name__)

# Forbidden output terms (C-2 violations — from SOUL.md rules)
_FORBIDDEN_OUTPUT_TERMS: frozenset[str] = frozenset([
    "attractive",
    "unattractive",
    "beauty score",
    "rating",
    "ugly",
    "pretty",
    "hot",
    "ranking",
    "beautiful",
    "gorgeous",
    "hideous",
    "out of ten",
    "/10",
])

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
]

# Redis key templates
_RATE_KEY_TEMPLATE = "advisor_chat_rate:{user_id}"


def sanitize_input(text: str) -> str:
    """Strip prompt-injection patterns and enforce max length.

    Returns cleaned text. Raises ValueError if text exceeds max length.
    """
    if len(text) > settings.ADVISOR_MAX_MESSAGE_LENGTH:
        raise ValueError(
            f"Message too long: {len(text)} chars (max {settings.ADVISOR_MAX_MESSAGE_LENGTH})"
        )

    cleaned = text
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
        await redis_client.expire(key, 3600)  # 1-hour window

    if new_count > settings.ADVISOR_CHAT_RATE_LIMIT:
        await redis_client.decr(key)
        ttl: int = await redis_client.ttl(key)
        raise RateLimitExceeded(retry_after=max(ttl, 0))


def scan_output(text: str) -> bool:
    """Return True if the text contains C-2 violations (forbidden terms).

    False means the response is clean and safe to return.
    """
    lower = text.lower()
    for term in _FORBIDDEN_OUTPUT_TERMS:
        if term in lower:
            logger.warning("C-2 violation detected: forbidden term '%s'", term)
            return True
    return False


_GENERIC_FALLBACK = (
    "Hard to say without more context — want to try describing what you're going for?"
)


def get_fallback_response() -> str:
    """Return the generic fallback response used after a C-2 violation retry."""
    return _GENERIC_FALLBACK
