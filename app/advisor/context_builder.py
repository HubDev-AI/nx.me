"""Context builder — assembles the LLM message array for each chat turn.

Structure:
    [system] SOUL.md
    [system] user_data (stable facts: face shape, symmetry, recs)
    [system] nudges (if any)
    [conversation history]
    [user message]

Auto-retrieved memories are no longer injected as a system block. Ada
pulls memories on demand via the ``search_memories`` / ``list_recent_memories``
/ ``save_memory`` MCP tools instead.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Heuristic fallback used when tiktoken is unavailable: ~4 chars per token.
_CHARS_PER_TOKEN = 4

# Cap on number of recommendations rendered into the user_data block.
_USER_DATA_MAX_RECOMMENDATIONS = 3


def _count_tokens(text: str) -> int:
    """Count tokens for ``text``. Uses tiktoken when importable, else a heuristic."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // _CHARS_PER_TOKEN)


def _message_tokens(msg: dict[str, Any]) -> int:
    """Count tokens for a single message dict (string or content-block list)."""
    content = msg.get("content", "")
    if isinstance(content, str):
        return _count_tokens(content)
    total = 0
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "text":
            total += _count_tokens(str(block.get("text", "")))
    return total


def trim_to_budget(
    messages: list[dict[str, Any]], budget: int
) -> tuple[list[dict[str, Any]], int]:
    """Trim conversation history so total tokens fit within ``budget``.

    Preserves system messages, the incoming user message (the last message),
    and drops oldest user/advisor turns first. Returns ``(trimmed_messages,
    dropped_count)`` so callers can log eviction.

    When the irreducible core (system + last user message) already exceeds the
    budget, the core is returned unchanged — the call will still happen; the
    budget is a soft guard, not a hard limit.
    """
    if budget <= 0 or not messages:
        return list(messages), 0

    total = sum(_message_tokens(m) for m in messages)
    if total <= budget:
        return list(messages), 0

    last_idx = len(messages) - 1
    protected_indices: set[int] = {last_idx}
    for i, m in enumerate(messages):
        if m.get("role") == "system":
            protected_indices.add(i)

    trimmable_indices = [i for i in range(len(messages)) if i not in protected_indices]

    dropped = 0
    dropped_indices: set[int] = set()
    for idx in trimmable_indices:  # oldest first
        if total <= budget:
            break
        total -= _message_tokens(messages[idx])
        dropped_indices.add(idx)
        dropped += 1

    return (
        [m for i, m in enumerate(messages) if i not in dropped_indices],
        dropped,
    )


def build_context(
    soul_md: str,
    user_data: str,
    conversation: list[dict[str, str]],
    message: str,
    nudges: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the messages array for the LLM call.

    Structure:
        [system] SOUL.md
        [system] user_data
        [system] nudges (if any)
        [conversation history]
        [user message]

    The nudges block is provenance-explicit on purpose: each line is
    ``"nudge (<trigger>): <body>"`` so a reviewer can see at a glance
    why Ada referenced a given nudge.

    Memories are NOT injected here — the model retrieves via tools.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": soul_md},
        {"role": "system", "content": user_data},
    ]

    nudge_block = format_nudges_block(nudges) if nudges else ""
    if nudge_block:
        messages.append({"role": "system", "content": nudge_block})

    messages.extend(conversation)
    messages.append({"role": "user", "content": message})

    return messages


def format_nudges_block(nudges: list[dict[str, Any]] | None) -> str:
    """Render a nudges list as the 4th system block text.

    Each nudge becomes one line:
        ``nudge: <body>``

    After the v2 actionable-nudges rewrite (migration 0062) there is only
    one nudge trigger (``post_glowup``), so the trigger prefix was dropped.
    Newlines inside ``body`` are replaced with spaces so a single block
    stays a single logical line per nudge. Empty / missing fields cause the
    nudge to be skipped rather than rendered with gaps.

    Returns ``""`` when no renderable nudges remain.
    """
    if not nudges:
        return ""

    lines: list[str] = []
    for nudge in nudges:
        if not isinstance(nudge, dict):
            continue
        body = nudge.get("body") or ""
        if not isinstance(body, str):
            body = str(body)
        body = body.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        if not body:
            continue
        lines.append(f"nudge: {body}")
    return "\n".join(lines)


def build_user_data_block(
    face_shape: str | None,
    symmetry_score: float | None,
    analysis_count: int,
    recommendations: list[str] | None = None,
    summary: str | None = None,
) -> str:
    """Build the user_data system message block.

    Basics-only output is a single comma-joined fragment:
        "oval face, symmetry 0.87, 4 analyses"

    When recommendations or summary are present, output is a label-free
    multi-line fragment (basics first, then recs, then summary):
        "oval face, symmetry 0.87, 4 analyses\\n"
        "try bangs, clean up brows, hydrate skin\\n"
        "narrow forehead, strong jaw"

    Matches the comma-joined, no-label style used by
    ``summarize_memory_content``.
    """
    basics: list[str] = []

    if face_shape:
        basics.append(f"{face_shape} face")
    if symmetry_score is not None:
        basics.append(f"symmetry {symmetry_score:.2f}")
    if analysis_count > 0:
        basics.append(
            f"{analysis_count} {'analysis' if analysis_count == 1 else 'analyses'}"
        )

    lines: list[str] = []
    if basics:
        lines.append(", ".join(basics))

    rec_line = ""
    if recommendations:
        rec_items = [str(r).strip() for r in recommendations if str(r).strip()]
        if rec_items:
            rec_line = ", ".join(rec_items[:_USER_DATA_MAX_RECOMMENDATIONS])
    if rec_line:
        lines.append(rec_line)

    summary_line = summary.strip() if summary else ""
    if summary_line:
        lines.append(summary_line)

    return "\n".join(lines)
