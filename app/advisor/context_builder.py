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
VISUAL_TRIGGER_KEYWORDS: tuple[str, ...] = ("look at", "see my", "compare", "photo", "this picture", "my image")

# Trajectory hint chance (spec Section 6.3)
_TRAJECTORY_CHANCE = 0.15


def build_context(
    soul_md: str,
    user_data: str,
    memories: list[dict[str, Any]],
    conversation: list[dict[str, str]],
    message: str,
) -> list[dict[str, Any]]:
    """Build the messages array for the LLM call.

    Structure (spec Section 6.1):
        [system] SOUL.md
        [system] user_data
        [system] memories (if any)
        [conversation history]
        [user message]
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": soul_md},
        {"role": "system", "content": user_data},
    ]

    enhanced_memories = maybe_add_trajectory(memories)

    if enhanced_memories:
        memory_text = "\n".join(
            format_memory(m) for m in enhanced_memories
        )
        messages.append({"role": "system", "content": memory_text})

    messages.extend(conversation)
    messages.append({"role": "user", "content": message})

    return messages


def format_memory(memory: dict[str, Any]) -> str:
    """Format a single memory as a raw fragment — no labels, no verbs (spec Section 6.2)."""
    return summarize_memory_content(memory.get("content", {}))


def build_user_data_block(
    face_shape: str | None,
    symmetry_score: float | None,
    analysis_count: int,
) -> str:
    """Build the user_data system message block (spec Section 6.1).

    Example output: "oval face, symmetry 0.87, 4 analyses"
    """
    parts: list[str] = []

    if face_shape:
        parts.append(f"{face_shape} face")
    if symmetry_score is not None:
        parts.append(f"symmetry {symmetry_score:.2f}")
    if analysis_count > 0:
        parts.append(f"{analysis_count} {'analysis' if analysis_count == 1 else 'analyses'}")

    return ", ".join(parts) if parts else ""


def maybe_add_trajectory(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Optionally append a soft trajectory hint (spec Section 6.3).

    If 2+ accepted suggestions exist and random chance triggers (15%),
    add a hint typed as user_note. No analytical language.
    """
    accepted = [m for m in memories if m.get("type") == "accepted_suggestion"]
    if len(accepted) < 2 or random.random() > _TRAJECTORY_CHANCE:
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

    if any(w in combined for w in ("hair", "haircut", "bangs", "fringe", "bun", "fade")):
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
