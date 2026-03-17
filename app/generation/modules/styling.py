"""Styling transformation module — the default glow-up.

Changes: hair, grooming, clothing, lighting, composition.
Preserves: face, bone structure, skin (freckles, moles, texture).
"""
from __future__ import annotations

import os
from pathlib import Path

from app.generation.modules.base import TransformationModule, TransformationOutput
from app.generation.modules.registry import register

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def _load_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text().strip()


def _extract_keywords(recommendations, max_count: int = 6) -> list[str]:
    """Extract allowed keywords from face analysis recommendations."""
    from prompts.keyword_allowlist import ALLOWED_KEYWORDS

    keywords = []
    for rec in recommendations:
        text = rec.suggestion_text.lower()
        for kw in ALLOWED_KEYWORDS:
            if kw in text and kw not in keywords:
                keywords.append(kw)
                if len(keywords) >= max_count:
                    return keywords
    return keywords


class StylingModule:
    """Default glow-up — styling changes only."""

    slug = "styling"
    display_name = "Style Glow-Up"

    def is_applicable(self, analysis_result) -> bool:
        return True

    def build_output(self, analysis_result, mode: str) -> TransformationOutput:
        keywords = _extract_keywords(analysis_result.recommendations)
        keyword_str = ", ".join(keywords)

        template = _load_template(f"glowup_{mode}.txt")
        prompt = template.replace("{keywords}", keyword_str)
        negative = _load_template("glowup_negative.txt")

        return TransformationOutput(
            prompt_fragment=prompt,
            negative_fragment=negative,
            keywords_used=keywords,
            wow_weight=1.0,
        )

    def get_allowed_keywords(self) -> frozenset[str]:
        from prompts.keyword_allowlist import ALLOWED_KEYWORDS
        return ALLOWED_KEYWORDS

    def get_blocked_keywords(self) -> frozenset[str]:
        from prompts.keyword_allowlist import BLOCKED_KEYWORDS
        return BLOCKED_KEYWORDS

    def adjust_params(self, base_params: dict) -> dict:
        return base_params


# Auto-register on import
register(StylingModule())
