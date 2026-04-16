"""Context-token budget enforcement — spec §10.

Tests `trim_to_budget` preserves system + current user message and evicts
oldest history pairs first.
"""

from __future__ import annotations


from app.advisor.context_builder import trim_to_budget, _count_tokens


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def test_noop_when_under_budget():
    msgs = [_msg("system", "s"), _msg("user", "hi"), _msg("advisor", "hey")]
    out, dropped = trim_to_budget(msgs, 10_000)
    assert out == msgs
    assert dropped == 0


def test_trims_oldest_turns_first():
    long_body = "word " * 2_000  # ~2k tokens under any sensible tokenizer
    history = [
        _msg("user", long_body),
        _msg("advisor", long_body),
        _msg("user", long_body),
        _msg("advisor", long_body),
    ]
    msgs = [
        _msg("system", "soul"),
        _msg("system", "user_data"),
        *history,
        _msg("user", "new question"),
    ]

    out, dropped = trim_to_budget(msgs, 5000)

    # Dropped at least some oldest history
    assert dropped >= 1
    # Kept all system messages
    systems = [m for m in out if m["role"] == "system"]
    assert len(systems) == 2
    # Kept the incoming user message (last in input)
    assert out[-1]["content"] == "new question"
    # Total tokens below budget after trim
    total = sum(
        _count_tokens(m["content"]) for m in out if isinstance(m["content"], str)
    )
    assert total <= 5000


def test_preserves_core_when_core_alone_exceeds_budget():
    """If system + current user already > budget, return core unchanged."""
    huge = "word " * 10_000
    msgs = [_msg("system", huge), _msg("user", huge)]
    out, dropped = trim_to_budget(msgs, 100)
    assert out == msgs
    # dropped counts refer to history eviction; system/core are protected.
    assert dropped == 0


def test_zero_budget_is_noop():
    msgs = [_msg("user", "hi")]
    out, dropped = trim_to_budget(msgs, 0)
    assert out == msgs
    assert dropped == 0


def test_vision_content_block_counts_only_text_tokens():
    vision_msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "look at this"},
            {"type": "image", "source": {"type": "base64", "data": "x" * 10_000}},
        ],
    }
    history = [_msg("user", "old " * 2_000), _msg("advisor", "older " * 2_000)]
    msgs = [_msg("system", "s"), *history, vision_msg]

    out, dropped = trim_to_budget(msgs, 500)

    # History dropped; vision message preserved with image block intact.
    assert dropped >= 1
    preserved = [m for m in out if m is vision_msg or m == vision_msg]
    assert preserved, "Vision (last user) message must be preserved"
