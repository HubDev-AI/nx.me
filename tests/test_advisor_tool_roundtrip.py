"""End-to-end roundtrip tests for the mock adapter's tool-use loop.

Plan 2026-04-17-003 Unit 9. The mock adapter must walk the scripted
tool-use turns exactly like the real Anthropic adapter so the service
layer can be tested against a deterministic harness. These tests
assert:

- A single-round tool_use script dispatches the tool, returns final
  text, and records the dispatch log.
- A multi-round script within the cap dispatches every round.
- A script exceeding ``ADVISOR_MAX_TOOL_ROUNDS`` surfaces the
  round-cap error marker on the over-cap rounds.
- Handler errors inside a round still produce text the model can emit.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.advisor.adapters.mock import MOCK_FINAL_TEXT_AFTER_TOOLS, MockLLMAdapter
from app.advisor.mcp import McpContext, ToolRegistry
from app.advisor.mcp.registry import TOOL_ROUND_CAP_EXCEEDED_MARKER
from app.config import settings


_TEST_USER_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _ctx(repo: Any | None = None) -> McpContext:
    return McpContext(
        user_id=_TEST_USER_ID,
        supabase=MagicMock(),
        advisor_repo=repo or MagicMock(),
        logger=logging.getLogger("test.roundtrip"),
    )


@pytest.mark.asyncio
async def test_single_round_tool_loop_dispatches_and_returns_final_text():
    """One round of tool_use → tool_result → final text."""
    repo = MagicMock()
    repo.get_style_profile.return_value = {
        "content": {
            "face_shape": "oval",
            "symmetry_score": 0.8,
            "recommendations": [],
        }
    }
    registry = ToolRegistry(ctx=_ctx(repo))
    mock_llm = MockLLMAdapter()
    mock_llm.tool_use_script = [
        [{"name": "get_style_profile", "input": {}}],
    ]

    response = await mock_llm.create_message(
        model="claude-sonnet-4-6",
        system="SOUL",
        messages=[{"role": "user", "content": "what fits me?"}],
        max_tokens=256,
        tools=registry.schemas(),
        tool_registry=registry,
    )

    assert response.content == MOCK_FINAL_TEXT_AFTER_TOOLS
    assert len(mock_llm.executed_tool_results) == 1
    assert len(mock_llm.executed_tool_results[0]) == 1
    assert mock_llm.tool_dispatch_log == [("get_style_profile", {})]


@pytest.mark.asyncio
async def test_multi_round_within_cap_runs_every_round():
    """Two rounds of tool_use all execute when under the cap."""
    # Force the cap high enough that both rounds run.
    assert settings.ADVISOR_MAX_TOOL_ROUNDS >= 2, "test requires cap >= 2"

    repo = MagicMock()
    repo.get_style_profile.return_value = None
    repo.get_recent_nudges_for_context.return_value = []
    registry = ToolRegistry(ctx=_ctx(repo))
    mock_llm = MockLLMAdapter()
    mock_llm.tool_use_script = [
        [{"name": "get_style_profile", "input": {}}],
        [{"name": "get_recent_nudges", "input": {"limit": 3}}],
    ]

    await mock_llm.create_message(
        model="claude-sonnet-4-6",
        system="SOUL",
        messages=[{"role": "user", "content": "tell me about me"}],
        max_tokens=256,
        tools=registry.schemas(),
        tool_registry=registry,
    )

    assert len(mock_llm.executed_tool_results) == 2
    assert mock_llm.over_cap_tool_results == []
    assert mock_llm.tool_dispatch_log == [
        ("get_style_profile", {}),
        ("get_recent_nudges", {"limit": 3}),
    ]


@pytest.mark.asyncio
async def test_script_exceeding_cap_marks_over_cap_rounds_as_round_cap_exceeded(
    monkeypatch: pytest.MonkeyPatch,
):
    """Over-cap rounds get the round-cap error marker."""
    # Pin the cap to 1 so the second round is explicitly over cap.
    monkeypatch.setattr(settings, "ADVISOR_MAX_TOOL_ROUNDS", 1)

    repo = MagicMock()
    repo.get_style_profile.return_value = None
    repo.get_recent_nudges_for_context.return_value = []
    registry = ToolRegistry(ctx=_ctx(repo))
    mock_llm = MockLLMAdapter()
    mock_llm.tool_use_script = [
        [{"name": "get_style_profile", "input": {}}],
        [{"name": "get_recent_nudges", "input": {"limit": 2}}],
    ]

    await mock_llm.create_message(
        model="claude-sonnet-4-6",
        system="SOUL",
        messages=[{"role": "user", "content": "…"}],
        max_tokens=256,
        tools=registry.schemas(),
        tool_registry=registry,
    )

    assert len(mock_llm.executed_tool_results) == 1
    assert len(mock_llm.over_cap_tool_results) == 1
    over_cap = mock_llm.over_cap_tool_results[0]
    assert over_cap["is_error"] is True
    assert over_cap["content"] == TOOL_ROUND_CAP_EXCEEDED_MARKER


@pytest.mark.asyncio
async def test_handler_error_produces_text_tool_result_not_exception():
    """A broken handler still produces a tool_result the loop can consume."""

    async def _boom(ctx: McpContext) -> Any:
        raise ValueError("nope")

    registry = ToolRegistry(ctx=_ctx())
    registry._tools["_boom"] = {
        "name": "_boom",
        "description": "stub",
        "input_schema": {"type": "object", "properties": {}},
    }
    registry._handlers["_boom"] = _boom  # type: ignore[assignment]

    mock_llm = MockLLMAdapter()
    mock_llm.tool_use_script = [[{"name": "_boom", "input": {}}]]

    response = await mock_llm.create_message(
        model="claude-sonnet-4-6",
        system="SOUL",
        messages=[{"role": "user", "content": "…"}],
        max_tokens=256,
        tools=registry.schemas() + [registry._tools["_boom"]],
        tool_registry=registry,
    )

    assert response.content == MOCK_FINAL_TEXT_AFTER_TOOLS
    # Exactly one tool_result, and its content is a text block mentioning failure.
    assert len(mock_llm.executed_tool_results) == 1
    round_results = mock_llm.executed_tool_results[0]
    assert len(round_results) == 1
    result_content = round_results[0]["content"]
    assert isinstance(result_content, list)
    assert result_content[0]["type"] == "text"
    assert "failed" in result_content[0]["text"].lower()


@pytest.mark.asyncio
async def test_mock_adapter_records_every_call_for_introspection():
    """``MockLLMAdapter.calls`` captures kwargs for test assertions."""
    registry = ToolRegistry(ctx=_ctx())
    mock_llm = MockLLMAdapter()
    mock_llm.tool_use_script = []  # No tool loop — single-call path.

    await mock_llm.create_message(
        model="claude-sonnet-4-6",
        system="SOUL",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=256,
        tools=registry.schemas(),
        tool_registry=registry,
    )

    assert len(mock_llm.calls) == 1
    assert mock_llm.calls[0]["tools"] == registry.schemas()
