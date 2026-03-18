"""Prompt builder — assembles generation prompts from face analysis data.

3 modes (everyday/polished/editorial), identity phrase rotation,
style theme injection, adaptive parameter computation.
"""
from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

from app.config import settings
from app.face_analysis.models import AnalysisResult

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Load keyword_allowlist from absolute path so the import is independent of cwd.
_allowlist_path = _PROMPTS_DIR / "keyword_allowlist.py"
_allowlist_spec = importlib.util.spec_from_file_location("prompts.keyword_allowlist", _allowlist_path)
_allowlist_module = importlib.util.module_from_spec(_allowlist_spec)  # type: ignore[arg-type]
_allowlist_spec.loader.exec_module(_allowlist_module)  # type: ignore[union-attr]
sys.modules.setdefault("prompts.keyword_allowlist", _allowlist_module)

HAIR_KEYWORDS: frozenset[str] = _allowlist_module.HAIR_KEYWORDS
ALLOWED_KEYWORDS: frozenset[str] = _allowlist_module.ALLOWED_KEYWORDS

# ---------------------------------------------------------------------------
# Identity phrase rotation
# ---------------------------------------------------------------------------

_IDENTITY_PHRASES = [
    "This same person",
    "The same individual",
    "Clearly the same person",
    "This exact person",
    "Recognizably the same face",
    "The same person, unmistakably",
]

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

# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


def select_mode(keyword_count: int) -> str:
    """Auto-select prompt mode based on keyword count."""
    if keyword_count <= 2:
        return "everyday"
    if keyword_count <= 4:
        return "polished"
    return "editorial"


# ---------------------------------------------------------------------------
# Adaptive parameters
# ---------------------------------------------------------------------------


def compute_adaptive_params(
    face_ratio: float,
    symmetry_score: float,
    keyword_count: int,
) -> dict:
    """Adjust generation parameters based on input characteristics."""
    id_weight = 0.86
    guidance = 4.0

    # Keyword scaling
    if keyword_count >= 5:
        id_weight = 0.82
        guidance = 4.5
    elif keyword_count in (3, 4):
        id_weight = 0.85
        guidance = 4.0
    elif keyword_count <= 2:
        id_weight = 0.87
        guidance = 3.8

    # Symmetry adjustment
    if symmetry_score < 0.75:
        id_weight = min(id_weight + 0.04, 0.93)
        guidance = max(guidance - 0.2, 3.5)

    # Face size adjustment
    if face_ratio < 0.15:
        id_weight = min(id_weight + 0.02, 0.93)

    # Clamp to safe ranges
    id_weight = max(0.80, min(0.93, round(id_weight, 2)))
    guidance = max(3.5, min(4.8, round(guidance, 1)))

    return {
        "id_weight": id_weight,
        "guidance_scale": guidance,
        "num_inference_steps": 30,
    }


# ---------------------------------------------------------------------------
# Keyword preparation
# ---------------------------------------------------------------------------


def prepare_keywords(keywords: list[str]) -> list[str]:
    """Optimize keyword list: hair first, cap at 5, add style theme if sparse."""
    # Hair keywords first (most visible change)
    hair_first = [k for k in keywords if k in HAIR_KEYWORDS]
    rest = [k for k in keywords if k not in HAIR_KEYWORDS]
    ordered = hair_first + rest

    # Inject style theme when sparse (before cap to ensure it counts)
    if len(ordered) <= 4:
        ordered.append(random.choice(_STYLE_THEMES))

    # Cap at MAX_PROMPT_KEYWORDS (after theme injection)
    if len(ordered) > settings.MAX_PROMPT_KEYWORDS:
        ordered = ordered[:settings.MAX_PROMPT_KEYWORDS]

    return ordered


# ---------------------------------------------------------------------------
# Lighting keyword from symmetry
# ---------------------------------------------------------------------------


def select_lighting_keyword(symmetry_score: float) -> str:
    """Choose lighting keyword based on face symmetry."""
    if symmetry_score > 0.85:
        return random.choice(["studio lighting", "golden hour glow"])
    return random.choice(["soft natural lighting", "even skin lighting"])


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_prompt(
    analysis_result: AnalysisResult,
    face_ratio: float = 0.30,
) -> tuple[str, str, dict]:
    """Build generation prompt from face analysis.

    Returns:
        (prompt, negative_prompt, adaptive_params)
    """
    from app.generation.modules.styling import StylingModule

    module = StylingModule()

    # Extract and prepare keywords
    keywords = []
    for rec in analysis_result.recommendations:
        text = rec.suggestion_text.lower()
        for kw in ALLOWED_KEYWORDS:
            if kw in text and kw not in keywords:
                keywords.append(kw)

    # Add lighting
    keywords.append(select_lighting_keyword(analysis_result.symmetry_score))

    # Prepare (order, cap, inject theme)
    keywords = prepare_keywords(keywords)

    # Select mode
    mode = select_mode(len(keywords))

    # Load template and build prompt
    template = (_PROMPTS_DIR / f"glowup_{mode}.txt").read_text().strip()
    identity_phrase = random.choice(_IDENTITY_PHRASES)
    prompt = template.replace("{identity_phrase}", identity_phrase)
    prompt = prompt.replace("{keywords}", ", ".join(keywords))

    # Negative prompt
    negative = (_PROMPTS_DIR / "glowup_negative.txt").read_text().strip()

    # Adaptive params
    params = compute_adaptive_params(
        face_ratio=face_ratio,
        symmetry_score=analysis_result.symmetry_score,
        keyword_count=len(keywords),
    )

    return prompt, negative, params
