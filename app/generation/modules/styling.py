"""Styling transformation module — the default glow-up.

Changes: hair, grooming, clothing, lighting, composition.
Preserves: face, bone structure, skin (freckles, moles, texture).

Contains the full keyword extraction, hair-first ordering, style theme
injection, lighting selection, and adaptive parameter computation that
were previously spread across prompt_builder.py.
"""
from __future__ import annotations

import random
from pathlib import Path

from app.config import settings
from app.generation.modules.base import TransformationOutput
from app.generation.modules.registry import register
from prompts.keyword_allowlist import ALLOWED_KEYWORDS, HAIR_KEYWORDS

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"

# ---------------------------------------------------------------------------
# Style themes (injected when keyword_count <= 4)
# ---------------------------------------------------------------------------

_STYLE_THEMES = [
    "modern clean aesthetic",
    "relaxed streetwear vibe",
    "elegant and refined",
    "minimal and sharp",
    "warm and approachable",
    "contemporary and bold",
]


def _load_template(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text().strip()


# ---------------------------------------------------------------------------
# Keyword extraction and preparation
# ---------------------------------------------------------------------------


def _extract_keywords(recommendations: list) -> list[str]:
    """Extract allowed keywords from face analysis recommendations."""
    keywords: list[str] = []
    for rec in recommendations:
        text = rec.suggestion_text.lower()
        for kw in ALLOWED_KEYWORDS:
            if kw in text and kw not in keywords:
                keywords.append(kw)
    return keywords


def _select_lighting_keyword(
    symmetry_score: float,
    rng: random.Random | None = None,
) -> str:
    """Choose lighting keyword based on face symmetry."""
    _choice = rng.choice if rng is not None else random.choice
    if symmetry_score > 0.85:
        return _choice(["studio lighting", "golden hour glow"])
    return _choice(["soft natural lighting", "even skin lighting"])


def _prepare_keywords(
    keywords: list[str],
    rng: random.Random | None = None,
) -> list[str]:
    """Optimize keyword list: hair first, cap at MAX_PROMPT_KEYWORDS, add
    style theme if sparse.
    """
    _choice = rng.choice if rng is not None else random.choice

    # Hair keywords first (most visible change)
    hair_first = [k for k in keywords if k in HAIR_KEYWORDS]
    rest = [k for k in keywords if k not in HAIR_KEYWORDS]
    ordered = hair_first + rest

    # Inject style theme when sparse (before cap to ensure it counts)
    if len(ordered) <= 4:
        ordered.append(_choice(_STYLE_THEMES))

    # Cap at MAX_PROMPT_KEYWORDS (after theme injection)
    if len(ordered) > settings.MAX_PROMPT_KEYWORDS:
        ordered = ordered[: settings.MAX_PROMPT_KEYWORDS]

    return ordered


# ---------------------------------------------------------------------------
# Module class
# ---------------------------------------------------------------------------


class StylingModule:
    """Default glow-up — styling changes only."""

    slug = "styling"
    display_name = "Style Glow-Up"

    def is_applicable(self, analysis_result) -> bool:
        return True

    def build_output(
        self,
        analysis_result,
        mode: str,
        rng: random.Random | None = None,
    ) -> TransformationOutput:
        # Extract keywords from recommendations
        keywords = _extract_keywords(analysis_result.recommendations)

        # Add lighting keyword based on symmetry
        keywords.append(
            _select_lighting_keyword(analysis_result.symmetry_score, rng=rng)
        )

        # Prepare: hair-first ordering, style theme injection, cap
        keywords = _prepare_keywords(keywords, rng=rng)

        # Load template and assemble prompt
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
        return ALLOWED_KEYWORDS

    def get_blocked_keywords(self) -> frozenset[str]:
        from prompts.keyword_allowlist import BLOCKED_KEYWORDS

        return BLOCKED_KEYWORDS

    def adjust_params(
        self,
        face_ratio: float,
        symmetry_score: float,
        keyword_count: int,
    ) -> dict:
        """Adjust generation parameters for FLUX.2 Flex Edit.

        BFL recommendations for portrait identity-preserving edits:
        - guidance_scale 3.5-4.5: sweet spot for portraits
        - num_inference_steps 30-40: good facial detail fidelity
        - Higher guidance = more prompt adherence, less identity drift
        """
        guidance = 4.0
        steps = 35

        # Keyword count — more changes requested = slightly higher guidance
        if keyword_count >= 5:
            guidance = 4.2
            steps = 40
        elif keyword_count in (3, 4):
            guidance = 4.0
            steps = 35
        elif keyword_count <= 2:
            guidance = 3.8
            steps = 30

        # Lower symmetry faces benefit from higher guidance to lock in features
        if symmetry_score < 0.75:
            guidance = min(guidance + 0.2, 4.5)

        # Clamp to BFL recommended ranges
        guidance = max(3.5, min(4.5, round(guidance, 1)))
        steps = max(28, min(50, steps))

        return {
            "id_weight": 0.95,  # unused by FLUX.2 but kept for interface compat
            "guidance_scale": guidance,
            "num_inference_steps": steps,
        }


# Auto-register on import
register(StylingModule())
