"""Context builder — `build_user_data_block` (spec §6.1).

Unit 1 of the advisor context-aware plan: the user_data system block must
surface face_shape, symmetry, analysis count, top recommendations, and
summary — all in the label-free, comma-joined voice required by SOUL.md §6.2.

Unit 4 extension: ``build_context`` accepts a ``nudges`` list and emits a
4th system block (provenance-explicit) when non-empty. Existing callers
that don't pass ``nudges`` keep the 3-block shape.
"""

from __future__ import annotations

from app.advisor.context_builder import (
    build_context,
    build_user_data_block,
    format_nudges_block,
)


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


# ---------------------------------------------------------------------------
# Unit 4 — ``build_context`` emits a 4th system block when nudges are present.
# ---------------------------------------------------------------------------


def _nudge(body: str) -> dict:
    """Minimal nudge row shape returned by ``get_recent_nudges_for_context``."""
    return {
        "body": body,
        "created_at": "2026-04-17T00:00:00Z",
    }


def test_build_context_includes_nudge_block():
    """3 recent nudges → 3rd system block, 3 lines, order preserved."""
    nudges = [
        _nudge("oval face shapes are versatile — try bangs"),
        _nudge("loving how the new fringe lands"),
        _nudge("weekly check-in: what's been landing?"),
    ]
    messages = build_context(
        soul_md="SOUL.md",
        user_data="oval face, symmetry 0.87",
        conversation=[],
        message="What hairstyle would suit me?",
        nudges=nudges,
    )

    system_msgs = [m for m in messages if m.get("role") == "system"]
    # soul + user_data + nudges = 3 system messages.
    assert len(system_msgs) == 3
    nudge_block = system_msgs[-1]["content"]
    lines = nudge_block.split("\n")
    assert len(lines) == 3
    assert lines[0] == "nudge: oval face shapes are versatile — try bangs"
    assert lines[1] == "nudge: loving how the new fringe lands"
    assert lines[2] == "nudge: weekly check-in: what's been landing?"


def test_build_context_no_nudges_preserves_two_block_shape():
    """0 nudges → only soul + user_data system blocks (memories no longer auto-injected)."""
    messages_none = build_context(
        soul_md="SOUL.md",
        user_data="oval face",
        conversation=[],
        message="hi",
        nudges=None,
    )
    messages_empty = build_context(
        soul_md="SOUL.md",
        user_data="oval face",
        conversation=[],
        message="hi",
        nudges=[],
    )

    for messages in (messages_none, messages_empty):
        system_msgs = [m for m in messages if m.get("role") == "system"]
        assert len(system_msgs) == 2
        assert "nudge:" not in system_msgs[-1]["content"]


def test_build_context_caller_enforces_nudge_cap():
    """Builder renders what it is given — the repo applies the cap upstream."""
    top_five = [_nudge(f"nudge #{i}") for i in range(5)]
    messages = build_context(
        soul_md="SOUL.md",
        user_data="oval face",
        conversation=[],
        message="hi",
        nudges=top_five,
    )
    block = [m for m in messages if m.get("role") == "system"][-1]["content"]
    assert len(block.split("\n")) == 5


def test_format_nudges_block_replaces_newlines_in_body_with_spaces():
    """Newlines inside a nudge body must be flattened so block rows stay one-per-line."""
    block = format_nudges_block([{"body": "first line\nsecond line\r\nthird line"}])
    # One line in output, no literal \n / \r\n inside the rendered body.
    assert "\n" not in block
    assert "\r" not in block
    assert block == "nudge: first line second line third line"


def test_format_nudges_block_skips_empty_bodies():
    """Empty / whitespace-only nudge bodies are skipped silently."""
    assert format_nudges_block([{"body": ""}]) == ""
    assert format_nudges_block([{"body": "   "}]) == ""


def test_format_nudges_block_renders_simple_body():
    """Body-only input → ``nudge: <body>``."""
    block = format_nudges_block([{"body": "solo body"}])
    assert block == "nudge: solo body"
