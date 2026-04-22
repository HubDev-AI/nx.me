"""Advisor MCP tool: get_latest_makeup — Plan 2026-04-21-001 Unit 10."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


_TEST_USER_ID = uuid4()
_TEST_BEFORE_KEY = "raw-selfies/before.jpg"
_TEST_AFTER_KEY = "generated/after.jpg"
_FAKE_BYTES = b"fake-image-bytes"


def _make_ctx(
    *,
    row: dict | None,
    before_bytes: bytes = _FAKE_BYTES,
    after_bytes: bytes = _FAKE_BYTES,
    fetch_raises: bool = False,
):
    repo = MagicMock()
    repo.get_latest_completed_makeup_with_images = MagicMock(return_value=row)
    if fetch_raises:
        repo.fetch_image_bytes = MagicMock(side_effect=RuntimeError("storage down"))
    else:

        def _fetch(bucket, key):
            return before_bytes if "before" in key else after_bytes

        repo.fetch_image_bytes = MagicMock(side_effect=_fetch)

    return SimpleNamespace(
        user_id=_TEST_USER_ID,
        advisor_repo=repo,
        logger=MagicMock(),
    )


def _completed_row(**kwargs) -> dict[str, Any]:
    base = {
        "id": str(uuid4()),
        "status": "completed",
        "source_type": "makeup_session",
        "before_image_url": _TEST_BEFORE_KEY,
        "after_image_url": _TEST_AFTER_KEY,
        "completed_at": "2026-04-21T10:00:00+00:00",
        "created_at": "2026-04-21T09:55:00+00:00",
        "preset_slug": "natural_glow",
        "intensity": "medium",
    }
    base.update(kwargs)
    return base


@pytest.mark.asyncio
async def test_returns_before_after_images():
    """Happy path: completed row → two image blocks + text metadata."""
    from app.advisor.mcp.tools_makeup import handle

    ctx = _make_ctx(row=_completed_row())
    result = await handle(ctx)

    assert result["is_error"] is False
    blocks = result["content"]
    image_blocks = [b for b in blocks if b["type"] == "image"]
    text_blocks = [b for b in blocks if b["type"] == "text"]
    assert len(image_blocks) == 2
    assert len(text_blocks) == 1

    text = text_blocks[0]["text"]
    assert "feature=makeup" in text
    assert "preset=natural_glow" in text
    assert "intensity=medium" in text


@pytest.mark.asyncio
async def test_no_completed_session_returns_is_error():
    """Edge case: user has no makeup session → is_error=True."""
    from app.advisor.mcp.tools_makeup import handle

    ctx = _make_ctx(row=None)
    result = await handle(ctx)

    assert result["is_error"] is True
    assert "no completed makeup session" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_image_bytes_base64_encoded():
    """Image bytes are properly base64-encoded in the block."""
    from app.advisor.mcp.tools_makeup import handle

    ctx = _make_ctx(row=_completed_row())
    result = await handle(ctx)

    image_blocks = [b for b in result["content"] if b["type"] == "image"]
    for block in image_blocks:
        data = block["source"]["data"]
        decoded = base64.b64decode(data)
        assert decoded == _FAKE_BYTES


@pytest.mark.asyncio
async def test_fetch_failure_returns_is_error():
    """Both image fetches fail → is_error=True with text block."""
    from app.advisor.mcp.tools_makeup import handle

    ctx = _make_ctx(row=_completed_row(), fetch_raises=True)
    result = await handle(ctx)

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "feature=makeup" in text
    assert "unavailable" in text


@pytest.mark.asyncio
async def test_post_purge_row_missing_analyzer_fields():
    """Edge case: preset_slug and intensity are NULL post-purge — tool returns job without them."""
    from app.advisor.mcp.tools_makeup import handle

    ctx = _make_ctx(row=_completed_row(preset_slug=None, intensity=None))
    result = await handle(ctx)

    assert result["is_error"] is False
    text_blocks = [b for b in result["content"] if b["type"] == "text"]
    text = text_blocks[0]["text"]
    assert "feature=makeup" in text
    assert "preset=" not in text
    assert "intensity=" not in text


@pytest.mark.asyncio
async def test_tool_schema_has_no_user_id_property():
    """Registry invariant: input_schema must not accept user_id."""
    from app.advisor.mcp.tools_makeup import TOOL_SCHEMA

    props = TOOL_SCHEMA["input_schema"].get("properties", {})
    forbidden = {"user_id", "uid", "account"}
    overlap = forbidden & {k.lower() for k in props}
    assert not overlap, f"Schema exposes forbidden key(s): {overlap}"
