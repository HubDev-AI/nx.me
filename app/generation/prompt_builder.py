"""Prompt builder — thin compositor that delegates to the module registry.

Selects mode based on keyword count, delegates prompt/negative/params
construction to active transformation modules, and applies cross-module
identity phrase rotation with deterministic seeding.
"""

from __future__ import annotations

import importlib.util
import random
import sys
from pathlib import Path

from app.config import settings
from app.face_analysis.models import AnalysisResult
from app.generation.modules import registry

# Ensure StylingModule is imported so it auto-registers via register().
import app.generation.modules.styling  # noqa: F401

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Load keyword_allowlist from absolute path so the import is independent of cwd.
_allowlist_path = _PROMPTS_DIR / "keyword_allowlist.py"
_allowlist_spec = importlib.util.spec_from_file_location(
    "prompts.keyword_allowlist", _allowlist_path
)
_allowlist_module = importlib.util.module_from_spec(_allowlist_spec)  # type: ignore[arg-type]
_allowlist_spec.loader.exec_module(_allowlist_module)  # type: ignore[union-attr]
sys.modules.setdefault("prompts.keyword_allowlist", _allowlist_module)

ALLOWED_KEYWORDS: frozenset[str] = _allowlist_module.ALLOWED_KEYWORDS

# ---------------------------------------------------------------------------
# Template validation — fail fast at import time if templates are missing
# ---------------------------------------------------------------------------

_REQUIRED_TEMPLATES = {
    "glowup_everyday": _PROMPTS_DIR / "glowup_everyday.txt",
    "glowup_polished": _PROMPTS_DIR / "glowup_polished.txt",
    "glowup_editorial": _PROMPTS_DIR / "glowup_editorial.txt",
    "glowup_negative": _PROMPTS_DIR / "glowup_negative.txt",
}


def _validate_templates() -> None:
    for name, path in _REQUIRED_TEMPLATES.items():
        if not path.exists():
            raise RuntimeError(f"Required prompt template missing: {path}")


_validate_templates()  # Fail fast at import time

# ---------------------------------------------------------------------------
# Identity phrase rotation (cross-module concern)
# ---------------------------------------------------------------------------

_IDENTITY_PHRASES = [
    "Photo of this person",
    "Portrait of this person",
    "Real photo of this person",
    "Natural photo of this person",
    "Authentic photo of this person",
    "Candid portrait of this person",
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
# Main builder (compositor)
# ---------------------------------------------------------------------------


def build_prompt(
    analysis_result: AnalysisResult,
    face_ratio: float = 0.30,
    analysis_id: str = "",
) -> tuple[str, str, dict]:
    """Build generation prompt by delegating to the module registry.

    Args:
        analysis_result: Face analysis data used for keyword extraction.
        face_ratio: Ratio of face area to image area.
        analysis_id: Unique analysis identifier for deterministic seeding.

    Returns:
        (prompt, negative_prompt, adaptive_params)
    """
    # Deterministic RNG seeded from analysis_id
    rng = random.Random(hash(analysis_id))

    # Count keywords from analysis to determine mode
    keyword_count = sum(
        1
        for rec in analysis_result.recommendations
        for kw in ALLOWED_KEYWORDS
        if kw in rec.suggestion_text.lower()
    )
    mode = select_mode(min(keyword_count, settings.MAX_PROMPT_KEYWORDS))

    # Resolve active modules from registry
    enabled_slugs = [
        s.strip()
        for s in settings.ENABLED_TRANSFORMATION_MODULES.split(",")
        if s.strip()
    ]
    active_modules = registry.get_active_modules(analysis_result, enabled_slugs)

    if not active_modules:
        raise RuntimeError(
            f"No active transformation modules for slugs {enabled_slugs}"
        )

    module = active_modules[0]

    # Delegate prompt/negative/keywords to module
    output = module.build_output(analysis_result, mode, rng=rng)

    # Adaptive params from module
    params = module.adjust_params(
        face_ratio=face_ratio,
        symmetry_score=analysis_result.symmetry_score,
        keyword_count=len(output.keywords_used),
    )

    # Apply identity phrase (cross-module concern)
    identity_phrase = rng.choice(_IDENTITY_PHRASES)
    prompt = output.prompt_fragment.replace("{identity_phrase}", identity_phrase)

    return prompt, output.negative_fragment, params
