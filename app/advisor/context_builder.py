"""Context builder — assembles the LLM message array for each conversation turn.

Spec Section 6: SOUL.md + user_data + memories + conversation + user message.
No prefixes. No labels. No structure.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from app.advisor.memory_manager import summarize_memory_content

logger = logging.getLogger(__name__)

# A-14: Visual context trigger keywords extracted as module-level constant (spec Section 6.4)
VISUAL_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "look at",
    "see my",
    "compare",
    "photo",
    "this picture",
    "my image",
)

# Trajectory hint chance (spec Section 6.3)
_TRAJECTORY_CHANCE = 0.15

# Heuristic fallback used when tiktoken is unavailable: ~4 chars per token.
_CHARS_PER_TOKEN = 4

# Cap on number of recommendations rendered into the user_data block.
# Matches the top-3 convention used in summarize_memory_content (memory_manager).
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
    dropped_count)`` so callers can log eviction (spec §10).

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
    memories: list[dict[str, Any]],
    conversation: list[dict[str, str]],
    message: str,
    rng: random.Random | None = None,
    nudges: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the messages array for the LLM call.

    Structure (spec Section 6.1, Plan 2026-04-17-003 Unit 4):
        [system] SOUL.md
        [system] user_data
        [system] memories (if any)
        [system] nudges (if any — Unit 4 NEW)
        [conversation history]
        [user message]

    The nudges block is provenance-explicit on purpose: each line is
    ``"nudge (<trigger>): <body>"`` so a reviewer can see at a glance
    why Ada referenced a given nudge. Default ``nudges=None`` keeps the
    function signature back-compat for the existing callers/tests that
    do not pass it.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": soul_md},
        {"role": "system", "content": user_data},
    ]

    enhanced_memories = maybe_add_trajectory(memories, rng=rng)

    if enhanced_memories:
        memory_text = "\n".join(format_memory(m) for m in enhanced_memories)
        messages.append({"role": "system", "content": memory_text})

    nudge_block = format_nudges_block(nudges) if nudges else ""
    if nudge_block:
        messages.append({"role": "system", "content": nudge_block})

    messages.extend(conversation)
    messages.append({"role": "user", "content": message})

    return messages


def format_memory(memory: dict[str, Any]) -> str:
    """Format a single memory as a raw fragment — no labels, no verbs (spec Section 6.2)."""
    return summarize_memory_content(memory.get("content", {}))


def format_nudges_block(nudges: list[dict[str, Any]] | None) -> str:
    """Render a nudges list as the 4th system block text (Plan Unit 4).

    Each nudge becomes one line:
        ``nudge (<trigger>): <body>``

    Newlines inside ``body`` are replaced with spaces so a single block
    stays a single logical line per nudge — preserves the overall block
    structure when the LLM parses it as role=system text. Empty / missing
    fields cause the nudge to be skipped rather than rendered with gaps.

    Returns ``""`` when no renderable nudges remain.
    """
    if not nudges:
        return ""

    lines: list[str] = []
    for nudge in nudges:
        if not isinstance(nudge, dict):
            continue
        body = nudge.get("content") or nudge.get("body") or ""
        if not isinstance(body, str):
            body = str(body)
        body = body.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        if not body:
            continue
        trigger = str(nudge.get("trigger", "")).strip().lower()
        if trigger:
            lines.append(f"nudge ({trigger}): {body}")
        else:
            lines.append(f"nudge: {body}")
    return "\n".join(lines)


def build_user_data_block(
    face_shape: str | None,
    symmetry_score: float | None,
    analysis_count: int,
    recommendations: list[str] | None = None,
    summary: str | None = None,
) -> str:
    """Build the user_data system message block (spec Section 6.1).

    Basics-only output is a single comma-joined fragment:
        "oval face, symmetry 0.87, 4 analyses"

    When recommendations or summary are present, output is a label-free
    multi-line fragment (basics first, then recs, then summary):
        "oval face, symmetry 0.87, 4 analyses\n"
        "try bangs, clean up brows, hydrate skin\n"
        "narrow forehead, strong jaw"

    Matches the comma-joined, no-label style of
    ``summarize_memory_content`` / ``format_memory`` per SOUL.md §6.2.
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


def maybe_add_trajectory(
    memories: list[dict[str, Any]],
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Optionally append a soft trajectory hint (spec Section 6.3).

    If 2+ accepted suggestions exist and random chance triggers (15%),
    add a hint typed as user_note. No analytical language.
    """
    _rng = rng or random
    accepted = [m for m in memories if m.get("type") == "accepted_suggestion"]
    if len(accepted) < 2 or _rng.random() > _TRAJECTORY_CHANCE:
        return memories

    # Detect common area from accepted suggestion texts
    contents = [summarize_memory_content(m.get("content", {})) for m in accepted]
    area_hint = _detect_area(contents)
    if not area_hint:
        return memories

    trajectory: dict[str, Any] = {
        "type": "user_note",
        "content": {"text": area_hint},
    }
    return list(memories) + [trajectory]


def _detect_area(texts: list[str]) -> str | None:
    """Detect styling area from a list of accepted suggestion texts.

    Returns a terse hint like "going cleaner with hair" or None.
    """
    combined = " ".join(texts).lower()

    if any(
        w in combined for w in ("hair", "haircut", "bangs", "fringe", "bun", "fade")
    ):
        return "going cleaner with hair"
    if any(w in combined for w in ("beard", "stubble", "shave", "mustache")):
        return "keeping facial hair neat"
    if any(w in combined for w in ("brow", "brows", "eyebrow")):
        return "cleaning up the brows"
    if any(w in combined for w in ("skincare", "moistur", "spf", "serum")):
        return "getting into a skincare routine"

    return None


def has_visual_trigger(message: str) -> bool:
    """Return True if the message suggests the user wants visual context."""
    lower = message.lower()
    return any(trigger in lower for trigger in VISUAL_TRIGGER_KEYWORDS)
