"""Fallback chat seeds — backend-deploy-editable defaults.

Plan 2026-04-20-001 Unit 5. Used when the user has no completed glow-up
yet, so there is nothing for Haiku to vision-ground against. These seeds
are served directly without any LLM call or Redis write.

Remote-config contract: this file is the authoritative source for the
fallback strings. Editing it and redeploying the backend immediately
changes what new users see — no mobile release required.

Shape invariants (validated by tests/test_advisor_chat_seeds.py):
  - Exactly 3 items.
  - Each item: {"label": str (≤24 chars), "text": str (≤140 chars, ends '?')}.
  - Female-coded, warm, first-person curious register.
  - No SaaS filler ('Learn more', 'Explore', 'Try this').
"""

from __future__ import annotations

from typing import TypedDict


class _FallbackSeed(TypedDict):
    """Shape of a single fallback seed — mirrors the ChatSeed Pydantic model."""

    label: str
    text: str


FALLBACK_SEEDS: tuple[_FallbackSeed, ...] = (
    {
        "label": "Where to start?",
        "text": "what's one quick change I could try before my next glow-up?",
    },
    {
        "label": "How Ada helps",
        "text": "how do you figure out what actually works for my face shape?",
    },
    {
        "label": "Upload tip",
        "text": "what makes a good photo for you to work from?",
    },
)
