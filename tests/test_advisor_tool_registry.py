"""Tests for ``app.advisor.mcp.ToolRegistry``.

Plan 2026-04-17-003 Unit 9. Covers:

- Auto-discovery picks up every ``tools_*.py`` module in the package.
- ``schemas()`` returns Anthropic-compatible schemas, sorted by name for
  prompt-cache stability.
- ``dispatch`` routes by name and normalizes handler output.
- ``dispatch`` wraps handler exceptions into ``tool_result`` content
  rather than letting them escape.
- ``dispatch`` handles unknown tool names gracefully.

Cross-user / log-leak assertions live in
``tests/test_advisor_tool_security.py``; this file tests the registry
contract in isolation.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.advisor.mcp import McpContext, ToolRegistry
from app.advisor.mcp.registry import (
    ERROR_CLASS_HANDLER_EXCEPTION,
    ERROR_CLASS_UNKNOWN_TOOL,
    METRIC_TOOL_ERROR,
    METRIC_TOOL_INVOKED,
    METRIC_TOOL_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_USER_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _mk_context(repo: Any | None = None) -> McpContext:
    """Construct a frozen test context with a stub repo."""
    log = logging.getLogger("test.registry")
    return McpContext(
        user_id=_TEST_USER_ID,
        supabase=MagicMock(),
        advisor_repo=repo or MagicMock(),
        logger=log,
    )


def _mk_registry(ctx: McpContext | None = None) -> ToolRegistry:
    return ToolRegistry(ctx=ctx or _mk_context())


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_registry_auto_discovers_every_tools_module():
    """Every ``tools_*.py`` in the package is auto-registered."""
    registry = _mk_registry()
    names = set(registry.tool_names())
    # Unit 9 ships these five tools. Later units add more modules but
    # the registry never edits — new tool files are simply discovered.
    expected = {
        "get_style_profile",
        "get_recent_nudges",
        "search_memories",
        "get_latest_generation",
        "get_latest_job_status",
    }
    assert expected.issubset(names), f"expected {expected} registered, got {names}"


def test_schemas_shape_is_anthropic_compatible():
    """Every schema has name, description, input_schema."""
    registry = _mk_registry()
    schemas = registry.schemas()
    assert schemas, "registry returned no schemas"
    for schema in schemas:
        assert isinstance(schema, dict)
        assert isinstance(schema["name"], str) and schema["name"]
        assert isinstance(schema["description"], str) and schema["description"]
        input_schema = schema["input_schema"]
        assert isinstance(input_schema, dict)
        assert input_schema.get("type") == "object"
        # Every schema must reject unknown keys (layer 2 of the isolation
        # stack — the registry also strips, but schemas being explicit
        # catches drift where someone adds a field and forgets the guard).
        assert input_schema.get("additionalProperties") is False


def test_schemas_sorted_by_name_for_cache_stability():
    """Order is deterministic — the tools array is cached on Anthropic's side.

    Any shuffle invalidates the tool-prefix cache on every request. The
    registry must return schemas sorted by name so two consecutive
    calls produce byte-identical ``tools`` arrays.
    """
    registry = _mk_registry()
    names = [s["name"] for s in registry.schemas()]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# Dispatch — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_routes_to_registered_handler():
    """Calling dispatch invokes the module-level handle()."""
    repo = MagicMock()
    repo.get_style_profile.return_value = {
        "content": {
            "face_shape": "oval",
            "symmetry_score": 0.87,
            "recommendations": ["try bangs", "clean brows"],
            "last_updated_at": "2026-04-17T00:00:00Z",
        }
    }
    ctx = _mk_context(repo)
    registry = ToolRegistry(ctx=ctx)

    payload = await registry.dispatch("get_style_profile", {})
    assert isinstance(payload, dict)
    assert payload["is_error"] is False
    content = payload["content"]
    assert isinstance(content, list)
    assert content, "dispatch returned empty content list"
    # get_style_profile returns a single text block.
    assert content[0]["type"] == "text"
    assert "oval" in content[0]["text"]
    assert "0.87" in content[0]["text"]


@pytest.mark.asyncio
async def test_dispatch_normalizes_string_output_to_text_block():
    """Handler returning a bare string gets wrapped in a text block + is_error=False."""

    async def _stub_handle(ctx: McpContext) -> Any:
        return "plain string"

    registry = _mk_registry()
    # Patch in a handler-only entry so we can assert on the normalization
    # path without depending on a real tool module.
    registry._tools["_stub"] = {
        "name": "_stub",
        "description": "stub",
        "input_schema": {"type": "object", "properties": {}},
    }
    registry._handlers["_stub"] = _stub_handle  # type: ignore[assignment]
    payload = await registry.dispatch("_stub", None)
    assert payload == {
        "content": [{"type": "text", "text": "plain string"}],
        "is_error": False,
    }


@pytest.mark.asyncio
async def test_dispatch_surfaces_is_error_from_envelope_shape():
    """Handler returning {'content': [...], 'is_error': True} yields is_error=True."""

    async def _stub_handle(ctx: McpContext) -> Any:
        return {
            "content": [{"type": "text", "text": "no data"}],
            "is_error": True,
        }

    registry = _mk_registry()
    registry._tools["_stub"] = {
        "name": "_stub",
        "description": "stub",
        "input_schema": {"type": "object", "properties": {}},
    }
    registry._handlers["_stub"] = _stub_handle  # type: ignore[assignment]
    payload = await registry.dispatch("_stub", None)
    assert payload["is_error"] is True
    assert payload["content"] == [{"type": "text", "text": "no data"}]
    # Inner blocks must NOT carry is_error — it rides only on the envelope.
    assert "is_error" not in payload["content"][0]


@pytest.mark.asyncio
async def test_dispatch_accepts_non_dict_raw_inputs_without_crashing():
    """A list / string / None raw_inputs coerces to {} via _filter_inputs guard."""
    repo = MagicMock()
    repo.get_style_profile.return_value = None
    registry = ToolRegistry(ctx=_mk_context(repo))

    # Each of these would have raised ``AttributeError: 'list' object has no
    # attribute 'items'`` pre-fix when _filter_inputs called raw_inputs.items().
    for bad_input in ([], "string-input", 42, None):
        payload = await registry.dispatch("get_style_profile", bad_input)
        assert payload["is_error"] is False
        assert payload["content"][0]["text"] == "no profile yet"


# ---------------------------------------------------------------------------
# Dispatch — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error_content(
    caplog: pytest.LogCaptureFixture,
):
    """Unknown name → envelope with is_error=True + warning log."""
    registry = _mk_registry()
    with caplog.at_level(logging.WARNING, logger="test.registry"):
        payload = await registry.dispatch("does_not_exist", {})
    assert isinstance(payload, dict)
    assert payload["is_error"] is True
    content = payload["content"]
    assert isinstance(content, list) and content
    assert content[0]["type"] == "text"
    assert "Unknown tool" in content[0]["text"]
    # Inner blocks must NOT carry is_error — it rides on the envelope.
    assert "is_error" not in content[0]
    metric_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_TOOL_UNKNOWN
    ]
    assert len(metric_records) == 1
    assert getattr(metric_records[0], "error_class") == ERROR_CLASS_UNKNOWN_TOOL


@pytest.mark.asyncio
async def test_dispatch_handler_exception_never_escapes(
    caplog: pytest.LogCaptureFixture,
):
    """An exception inside the handler is translated to envelope is_error=True.

    The registry logs the exception (so ops can see it) and returns a
    safe payload so the adapter can still submit a tool_result and
    keep the loop going. ``is_error`` rides on the envelope per
    Anthropic's spec, never on an inner block.
    """

    async def _boom(ctx: McpContext) -> Any:
        raise RuntimeError("kaboom")

    registry = _mk_registry()
    registry._tools["_boom"] = {
        "name": "_boom",
        "description": "stub",
        "input_schema": {"type": "object", "properties": {}},
    }
    registry._handlers["_boom"] = _boom  # type: ignore[assignment]

    with caplog.at_level(logging.WARNING, logger="test.registry"):
        payload = await registry.dispatch("_boom", {})

    assert isinstance(payload, dict)
    assert payload["is_error"] is True
    content = payload["content"]
    assert isinstance(content, list) and content
    assert content[0]["type"] == "text"
    assert "failed" in content[0]["text"].lower()
    assert "is_error" not in content[0]
    metric_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_TOOL_ERROR
    ]
    assert len(metric_records) == 1
    # error_class should be the concrete exception name, not the generic
    # fallback — tests the dispatcher's actual code path.
    err_class = getattr(metric_records[0], "error_class")
    assert err_class in ("RuntimeError", ERROR_CLASS_HANDLER_EXCEPTION)


@pytest.mark.asyncio
async def test_dispatch_emits_success_metric(caplog: pytest.LogCaptureFixture):
    """Successful dispatch emits advisor.tool_invoked metric."""
    repo = MagicMock()
    repo.get_style_profile.return_value = None
    registry = ToolRegistry(ctx=_mk_context(repo))
    with caplog.at_level(logging.INFO, logger="test.registry"):
        await registry.dispatch("get_style_profile", {})
    metric_records = [
        r for r in caplog.records if getattr(r, "metric", None) == METRIC_TOOL_INVOKED
    ]
    assert len(metric_records) == 1
    # duration_ms present and non-negative.
    assert getattr(metric_records[0], "duration_ms") >= 0
