"""Anthropic adapter role normalization — advisor → assistant at API boundary."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.advisor.adapters.anthropic_adapter import AnthropicAdapter


def _fake_response() -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text="ok")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


@pytest.mark.asyncio
async def test_advisor_role_mapped_to_assistant(monkeypatch):
    """Internal role 'advisor' must become 'assistant' before calling Claude."""
    adapter = AnthropicAdapter.__new__(AnthropicAdapter)
    create_mock = AsyncMock(return_value=_fake_response())
    adapter._anthropic = SimpleNamespace(messages=SimpleNamespace(create=create_mock))

    await adapter.create_message(
        model="claude-sonnet",
        system="sys",
        messages=[
            {"role": "system", "content": "extra"},
            {"role": "user", "content": "hi"},
            {"role": "advisor", "content": "prior reply"},
            {"role": "user", "content": "again"},
        ],
        max_tokens=16,
    )

    sent = create_mock.await_args.kwargs["messages"]
    roles = [m["role"] for m in sent]
    assert roles == ["user", "assistant", "user"]
    assert "extra" in create_mock.await_args.kwargs["system"]
