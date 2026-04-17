"""Unit tests for ``app.advisor._json_utils.strip_json_code_fence``.

Regression surface: Haiku wraps strict-JSON responses in ``\u0060\u0060\u0060json ... \u0060\u0060\u0060``
fences despite explicit "no markdown" prompts. Observed 2026-04-17 on
the vision nudge path (every nudge silently dropped) — the same shape
would have silently dropped memory extraction too.
"""

from __future__ import annotations

from app.advisor._json_utils import strip_json_code_fence


def test_plain_json_unchanged():
    raw = '{"a": 1}'
    assert strip_json_code_fence(raw) == '{"a": 1}'


def test_strips_json_tagged_fence():
    raw = '```json\n{"a": 1}\n```'
    assert strip_json_code_fence(raw) == '{"a": 1}'


def test_strips_bare_fence():
    raw = '```\n{"a": 1}\n```'
    assert strip_json_code_fence(raw) == '{"a": 1}'


def test_tolerates_leading_and_trailing_whitespace():
    raw = '   \n```json\n{"a": 1}\n```\n  '
    assert strip_json_code_fence(raw) == '{"a": 1}'


def test_open_fence_without_close():
    raw = '```json\n{"a": 1}'
    assert strip_json_code_fence(raw) == '{"a": 1}'


def test_unfenced_payload_with_backticks_inside_unchanged():
    # Payload starts with ``{``, not a fence — leave it alone.
    raw = '{"a": "```"}'
    assert strip_json_code_fence(raw) == '{"a": "```"}'


def test_empty_input():
    assert strip_json_code_fence("") == ""
    assert strip_json_code_fence("   ") == ""
