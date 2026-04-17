"""Structured payload logging for advisor LLM calls.

Emits one INFO record per Ada LLM call with model + token/block counts + trim
stats. When ``settings.ADVISOR_DEBUG_LOG_PROMPT`` is True the same call also
emits a DEBUG record carrying the full ``system`` string and ``messages``
array so a failure can be reproduced from logs alone without re-running the
paid API call (Plan Unit 5, R5 — ``feedback_no_money_wasted_on_api_tests``).

Safety invariants:

- User IDs are SHA-256 hashed (first 12 hex chars). Raw user IDs never reach
  either log record.
- Signed URLs never appear at INFO — only ``host`` + ``expiry`` parsed from
  the URL surface. Full URL text is only present at DEBUG (which is gated
  behind the env flag + log level).

The module exposes a single function, ``log_llm_call``. No state, no class —
each invocation builds its record, serializes it, and emits it.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlsplit, parse_qs

from app.advisor._hashing import USER_ID_HASH_LENGTH, hash_user_id
from app.advisor.context_builder import _count_tokens
from app.config import settings

# ---------------------------------------------------------------------------
# Named constants (per ``feedback_no_hardcoded_urls``)
# ---------------------------------------------------------------------------

# Dedicated logger name so operators can toggle DEBUG for this channel only
# (``logging.getLogger("app.advisor.payload").setLevel(logging.DEBUG)``)
# without turning on debug globally.
PAYLOAD_LOGGER_NAME = "app.advisor.payload"

# Stable metric key — log aggregators can index on this without parsing the
# human message.
METRIC_KEY_INFO = "advisor.llm_call"
METRIC_KEY_DEBUG = "advisor.llm_call_payload"

# Fallback marker when a field cannot be JSON-serialized and we fall back to
# ``repr()``. Kept as a named constant so operators can grep for it.
JSON_SERIALIZATION_FAILURE_MARKER = "<unserializable:repr>"

# Signed-URL query parameter that commonly carries the token/expiry in
# Supabase storage signed URLs. Parsed explicitly at INFO so we never emit
# the raw token.
SIGNED_URL_EXPIRY_PARAM = "token"

# Re-export USER_ID_HASH_LENGTH so existing callers that imported it from
# this module keep working.
__all__ = [
    "PAYLOAD_LOGGER_NAME",
    "USER_ID_HASH_LENGTH",
    "METRIC_KEY_INFO",
    "METRIC_KEY_DEBUG",
    "JSON_SERIALIZATION_FAILURE_MARKER",
    "SIGNED_URL_EXPIRY_PARAM",
    "log_llm_call",
]


def _hash_user_id(user_id: Any) -> str:
    """Legacy alias — routes to :func:`app.advisor._hashing.hash_user_id`.

    Kept so test modules that monkey-patch ``payload_logger._hash_user_id``
    still work. New callers should import ``hash_user_id`` from
    ``app.advisor._hashing`` directly.
    """
    return hash_user_id(user_id)


def _safe_serialize(value: Any) -> Any:
    """Return a JSON-serializable view of ``value``.

    On serialization failure, swaps the offending value for a marker + repr
    so the logger never crashes the request path. The marker is a named
    constant so audits can grep for degraded records.
    """
    try:
        json.dumps(value, sort_keys=True)
        return value
    except (TypeError, ValueError):
        try:
            return f"{JSON_SERIALIZATION_FAILURE_MARKER}:{value!r}"
        except Exception:
            return JSON_SERIALIZATION_FAILURE_MARKER


def _vision_host_fields(
    vision_content: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Return safe host + expiry fields per vision block for INFO logs.

    Anthropic vision blocks look like ``{"type": "image", "source": {"type":
    "url", "url": "..."}}``. We parse the URL via ``urllib.parse.urlsplit``
    and extract ONLY the scheme+host+path prefix + any ``token`` query param
    presence (existence only; never the token value). Full URL is dropped.

    Blocks with no URL (e.g., base64 sources) return an empty info record.
    """
    if not vision_content:
        return []

    fields: list[dict[str, str]] = []
    for block in vision_content:
        if not isinstance(block, dict):
            fields.append({"type": "unknown"})
            continue
        source = block.get("source") or {}
        url = ""
        if isinstance(source, dict):
            url = str(source.get("url", ""))

        entry: dict[str, str] = {"type": str(block.get("type", ""))}
        if url:
            parts = urlsplit(url)
            entry["host"] = parts.hostname or ""
            # Presence-only; never emit the token value.
            qs = parse_qs(parts.query)
            entry["has_expiry_token"] = str(SIGNED_URL_EXPIRY_PARAM in qs).lower()
        else:
            entry["source_type"] = str(
                source.get("type", "") if isinstance(source, dict) else ""
            )
        fields.append(entry)
    return fields


def _count_system_blocks(
    system: str,
    messages: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    """Return (system_block_count, system_role_messages).

    A "system block" is a distinct piece of system-role content delivered
    to the LLM. In the advisor flow, ``system`` (SOUL.md) is usually ALSO
    the first role=system entry in ``messages`` — the caller passes the
    full context-builder output to the logger before filtering system
    messages out of ``messages`` for the LLM adapter. Double-counting that
    block is wrong; we de-duplicate when ``system`` content appears at the
    head of the system-role messages list.
    """
    system_role_msgs = [
        m for m in messages if isinstance(m, dict) and m.get("role") == "system"
    ]
    count = len(system_role_msgs)
    if system:
        # Only add the system string as a separate block when it isn't
        # already represented as a system-role message. The heuristic
        # used by ``build_context`` always places SOUL.md first in the
        # messages list AND passes the same text as ``system``, so the
        # common case hits the de-dupe branch.
        already_present = any(
            isinstance(m, dict) and m.get("content") == system for m in system_role_msgs
        )
        if not already_present:
            count += 1
    return count, system_role_msgs


def _count_block_lines(block: dict[str, Any] | None) -> int:
    """Count newline-separated non-empty lines in a system block's content.

    ``build_context`` emits memories and nudges as one fragment per line
    joined with ``\\n``. Counting non-empty lines gives memory_count /
    nudge_count without needing explicit tagging.
    """
    if not block:
        return 0
    content = block.get("content", "")
    if not isinstance(content, str) or not content.strip():
        return 0
    return sum(1 for line in content.split("\n") if line.strip())


def _total_input_tokens(system: str, messages: list[dict[str, Any]]) -> int:
    """Estimate total input tokens across ``system`` + every message.

    Reuses ``context_builder._count_tokens`` (tiktoken when available,
    heuristic fallback). Same function the trim path uses, so INFO counts
    match trim decisions. When ``system`` content is also present as a
    system-role message (the common ``build_context`` layout), it is
    counted once via the message path only — avoids double-counting.
    """
    system_already_in_messages = bool(system) and any(
        isinstance(m, dict) and m.get("role") == "system" and m.get("content") == system
        for m in messages
    )
    total = _count_tokens(system) if (system and not system_already_in_messages) else 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content", "")
        if isinstance(content, str):
            total += _count_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += _count_tokens(str(block.get("text", "")))
    return total


def _role_breakdown(messages: list[dict[str, Any]]) -> dict[str, int]:
    """Return {role: count} across ``messages``."""
    breakdown: dict[str, int] = {}
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role", "unknown"))
        breakdown[role] = breakdown.get(role, 0) + 1
    return breakdown


def _last_user_message_length(messages: list[dict[str, Any]]) -> int:
    """Return character length of the last role=user message's string content.

    Zero when no user message is present or content is non-string (e.g.,
    structured tool result blocks).
    """
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        content = m.get("content", "")
        if isinstance(content, str):
            return len(content)
        return 0
    return 0


def log_llm_call(
    logger: logging.Logger | None,
    *,
    model: str,
    user_id: Any,
    conversation_id: str,
    system: str,
    messages: list[dict[str, Any]],
    vision_content: list[dict[str, Any]] | None,
    trimmed: bool,
    dropped: int,
    memory_count: int | None = None,
    nudge_count: int | None = None,
    tool_call_count: int | None = None,
    tool_names: list[str] | None = None,
    tool_errors: int | None = None,
) -> None:
    """Emit one INFO log record for an Ada LLM call.

    When ``settings.ADVISOR_DEBUG_LOG_PROMPT`` is True, ALSO emits a DEBUG
    record carrying the full ``system`` string + ``messages`` array + raw
    vision URLs.

    ``logger`` may be ``None``; when it is, a module-scoped logger
    ``app.advisor.payload`` is used. Passing an explicit logger makes the
    function testable without monkey-patching ``logging.getLogger``.

    ``memory_count`` / ``nudge_count`` (Plan Unit 4): callers that know
    the canonical counts pass them explicitly — the caller's counts are
    authoritative. When either is ``None`` the logger falls back to
    positional inference over the system-role messages (SOUL.md,
    user_data, memories, nudges), which works when blocks arrive in
    that order but is fragile when an earlier block is absent.

    ``tool_call_count`` / ``tool_names`` / ``tool_errors`` (Plan Unit 9)
    are optional additions describing the advertised or invoked tool
    surface. Unit 9 passes only ``tool_names`` (what was advertised to
    the model); the two counts are reserved for callers that track
    dispatch results directly (future units).

    This function catches every serialization failure (``_safe_serialize``)
    and never raises — the request path must not break because a log field
    was unserializable.
    """
    log = logger if logger is not None else logging.getLogger(PAYLOAD_LOGGER_NAME)

    system_block_count, system_role_msgs = _count_system_blocks(system, messages)

    # Positional convention per ``build_context`` output:
    #   [soul_md, user_data, memories?, nudges?, ...conversation..., user msg]
    # Indices 0-3 of system_role_msgs correspond to SOUL.md, user_data,
    # memories, nudges in that order. Anything shorter means earlier
    # blocks were absent (e.g., no memories → no memories block).
    memories_block = system_role_msgs[2] if len(system_role_msgs) >= 3 else None
    nudges_block = system_role_msgs[3] if len(system_role_msgs) >= 4 else None

    resolved_memory_count = (
        int(memory_count)
        if memory_count is not None
        else _count_block_lines(memories_block)
    )
    resolved_nudge_count = (
        int(nudge_count)
        if nudge_count is not None
        else _count_block_lines(nudges_block)
    )

    vision_blocks = vision_content or []
    vision_block_count = len(vision_blocks)
    vision_hosts = _vision_host_fields(vision_content)

    info_extra: dict[str, Any] = {
        "metric": METRIC_KEY_INFO,
        "model": _safe_serialize(model),
        "user_id_hash": _hash_user_id(user_id),
        "conversation_id": _safe_serialize(conversation_id),
        "message_count": len(messages),
        "role_breakdown": _safe_serialize(_role_breakdown(messages)),
        "system_block_count": system_block_count,
        "memory_count": resolved_memory_count,
        "nudge_count": resolved_nudge_count,
        "vision_block_count": vision_block_count,
        "user_message_length": _last_user_message_length(messages),
        "total_input_tokens_est": _total_input_tokens(system, messages),
        "trimmed": bool(trimmed),
        "dropped": int(dropped),
    }
    if vision_hosts:
        info_extra["vision_sources"] = _safe_serialize(vision_hosts)

    # Plan Unit 9 — optional tool-surface fields. Only emit when the
    # caller explicitly set them so pre-Unit-9 callers produce identical
    # records (test invariant).
    if tool_call_count is not None:
        info_extra["tool_call_count"] = int(tool_call_count)
    if tool_names is not None:
        info_extra["tool_names"] = _safe_serialize(list(tool_names))
    if tool_errors is not None:
        info_extra["tool_errors"] = int(tool_errors)

    # Verify the dict is serializable end-to-end — if any field slipped
    # past per-field ``_safe_serialize`` (unlikely), fall back to repr of
    # that field so log aggregators accept the record.
    try:
        json.dumps(info_extra, sort_keys=True)
    except (TypeError, ValueError):
        info_extra = {
            k: _safe_serialize(v) if not isinstance(v, (str, int, float, bool)) else v
            for k, v in info_extra.items()
        }

    log.info(
        "advisor.llm_call model=%s tokens=%d blocks=%d vision=%d trimmed=%s",
        info_extra["model"],
        info_extra["total_input_tokens_est"],
        info_extra["system_block_count"],
        info_extra["vision_block_count"],
        info_extra["trimmed"],
        extra=info_extra,
    )

    if not settings.ADVISOR_DEBUG_LOG_PROMPT:
        return

    # DEBUG path — full payload. Still hashed user_id, never raw.
    debug_extra: dict[str, Any] = {
        "metric": METRIC_KEY_DEBUG,
        "model": _safe_serialize(model),
        "user_id_hash": _hash_user_id(user_id),
        "conversation_id": _safe_serialize(conversation_id),
        "system": _safe_serialize(system),
        "messages": _safe_serialize(messages),
        "vision_content": _safe_serialize(vision_content),
    }
    if tool_call_count is not None:
        debug_extra["tool_call_count"] = int(tool_call_count)
    if tool_names is not None:
        debug_extra["tool_names"] = _safe_serialize(list(tool_names))
    if tool_errors is not None:
        debug_extra["tool_errors"] = int(tool_errors)
    try:
        json.dumps(debug_extra, sort_keys=True)
    except (TypeError, ValueError):
        # Worst-case: repr every non-scalar. Never raise.
        debug_extra = {
            k: _safe_serialize(v) if not isinstance(v, (str, int, float, bool)) else v
            for k, v in debug_extra.items()
        }

    log.debug(
        "advisor.llm_call_payload model=%s system_len=%d messages=%d",
        debug_extra["model"],
        len(system) if isinstance(system, str) else 0,
        len(messages),
        extra=debug_extra,
    )
