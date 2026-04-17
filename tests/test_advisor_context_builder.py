"""Context builder — `build_user_data_block` (spec §6.1).

Unit 1 of the advisor context-aware plan: the user_data system block must
surface face_shape, symmetry, analysis count, top recommendations, and
summary — all in the label-free, comma-joined voice required by SOUL.md §6.2.
"""

from __future__ import annotations

from app.advisor.context_builder import build_user_data_block


# ---------------------------------------------------------------------------
# Back-compat: basics-only output is unchanged — still a single comma-joined
# line. These guard the existing consumers that only pass the first three args.
# ---------------------------------------------------------------------------


def test_basics_only_emits_single_comma_joined_line():
    """Happy path: basics-only matches the pre-Unit-1 terse output (back-compat)."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
    )
    assert block == "oval face, symmetry 0.87, 4 analyses"
    assert "\n" not in block


def test_basics_only_with_only_face_shape():
    """Only face_shape present → single-fragment terse output."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=None,
        analysis_count=0,
    )
    assert block == "oval face"
    assert "\n" not in block


def test_empty_inputs_return_empty_string():
    """Nothing to say → empty string (downstream treats as no block)."""
    block = build_user_data_block(
        face_shape=None,
        symmetry_score=None,
        analysis_count=0,
    )
    assert block == ""


def test_analysis_count_zero_omits_analyses_clause():
    """analysis_count=0 must not emit '0 analyses'."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=0,
    )
    assert "analyses" not in block
    assert "analysis" not in block
    assert block == "oval face, symmetry 0.87"


def test_symmetry_none_omits_symmetry_clause():
    """symmetry_score=None must not emit the symmetry fragment."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=None,
        analysis_count=2,
    )
    assert "symmetry" not in block
    assert block == "oval face, 2 analyses"


def test_analysis_count_one_uses_singular():
    """analysis_count=1 renders as '1 analysis' (singular)."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=None,
        analysis_count=1,
    )
    assert block == "oval face, 1 analysis"


# ---------------------------------------------------------------------------
# Unit 1 — recommendations + summary are surfaced, still label-free.
# ---------------------------------------------------------------------------


def test_user_data_block_includes_recommendations_and_summary():
    """Full analysis_insight → all five signals, no 'Key:' labels."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
        recommendations=["try bangs", "clean up brows", "hydrate skin"],
        summary="narrow forehead, strong jaw",
    )

    # All five signals present.
    assert "oval face" in block
    assert "symmetry 0.87" in block
    assert "4 analyses" in block
    assert "try bangs" in block
    assert "clean up brows" in block
    assert "hydrate skin" in block
    assert "narrow forehead, strong jaw" in block

    # Label-free per SOUL.md §6.2 — no "Key:" prefixes, no verbose labels.
    lower = block.lower()
    for label in (
        "face shape:",
        "face:",
        "symmetry:",
        "analyses:",
        "recommendations:",
        "summary:",
        "recs:",
        "top 3:",
    ):
        assert label not in lower, f"unexpected label in block: {label!r}"


def test_recommendations_capped_at_top_three():
    """More than 3 recs → first 3 only, matching summarize_memory_content convention."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
        recommendations=[
            "try bangs",
            "clean up brows",
            "hydrate skin",
            "grow out the fringe",
            "neat stubble",
        ],
    )
    assert "try bangs" in block
    assert "clean up brows" in block
    assert "hydrate skin" in block
    assert "grow out the fringe" not in block
    assert "neat stubble" not in block


def test_empty_recommendations_and_summary_emits_basics_only():
    """Edge case: rec=[] and summary='' → terse single-line output (back-compat)."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
        recommendations=[],
        summary="",
    )
    assert block == "oval face, symmetry 0.87, 4 analyses"
    assert "\n" not in block


def test_whitespace_only_recommendations_and_summary_emits_basics_only():
    """Edge case: whitespace-only recs and summary are treated as empty."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
        recommendations=["   ", "\t"],
        summary="   \n",
    )
    assert block == "oval face, symmetry 0.87, 4 analyses"
    assert "\n" not in block


def test_summary_present_without_recommendations():
    """Summary alone surfaces on its own line below basics."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
        recommendations=None,
        summary="narrow forehead, strong jaw",
    )
    assert block == (
        "oval face, symmetry 0.87, 4 analyses\nnarrow forehead, strong jaw"
    )


def test_recommendations_present_without_summary():
    """Recommendations alone surface on their own line below basics."""
    block = build_user_data_block(
        face_shape="oval",
        symmetry_score=0.87,
        analysis_count=4,
        recommendations=["try bangs", "clean up brows"],
    )
    assert block == ("oval face, symmetry 0.87, 4 analyses\ntry bangs, clean up brows")
