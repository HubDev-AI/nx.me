"""Tests for the feature-specific glow-up MCP tools (Plan 2026-04-17-003 Unit 2).

Covers ``get_latest_glowup`` and ``get_latest_photo``:

- Happy paths for both tools — correct shape, correct base64 decode,
  correct feature metadata.
- Error paths — user with no glow-up / no cleared image returns
  ``is_error=True`` text block.
- Schema introspection — neither tool's ``input_schema`` accepts a
  ``user_id``-shaped key (belt-and-suspenders on top of Unit 9's
  registry-wide audit).
- Registry-level dispatch — both tools are discovered from the shared
  ``tools_glowup.py`` module via the plural ``TOOL_SCHEMAS`` +
  ``HANDLERS`` surface.
"""

from __future__ import annotations

import base64
import logging
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.advisor.mcp import McpContext, ToolRegistry
from app.advisor.mcp.registry import (
    FORBIDDEN_INPUT_KEY_FRAGMENTS,
    _schema_contains_forbidden_key,
)
from app.advisor.mcp.tools_glowup import (
    FEATURE_TAG_GLOWUP,
    FEATURE_TAG_SOURCE_PHOTO,
    HANDLERS,
    TOOL_SCHEMAS,
    _handle_get_latest_glowup,
    _handle_get_latest_photo,
)
from app.advisor.mcp.tools_jobs import BUCKET_AFTER, BUCKET_BEFORE

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_USER_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_FAKE_BEFORE_BYTES = b"\xff\xd8\xff\xe0fake-before-jpeg"
_FAKE_AFTER_BYTES = b"\xff\xd8\xff\xe0fake-after-jpeg"
_FAKE_SOURCE_BYTES = b"\xff\xd8\xff\xe0fake-source-jpeg"


def _ctx(repo: Any | None = None) -> McpContext:
    """Construct a test context with a stub repo."""
    return McpContext(
        user_id=_TEST_USER_ID,
        supabase=MagicMock(),
        advisor_repo=repo or MagicMock(),
        logger=logging.getLogger("test.tools_glowup"),
    )


def _completed_glowup_row() -> dict[str, Any]:
    return {
        "id": "job_abc",
        "status": "completed",
        "source_type": "glowup_analysis",
        "created_at": "2026-04-17T00:00:00Z",
        "completed_at": "2026-04-17T00:01:00Z",
        "before_image_url": "user_a/source.jpg",
        "after_image_url": "user_a/after.jpg",
    }


def _stub_repo_with_glowup() -> MagicMock:
    repo = MagicMock()
    repo.get_latest_completed_glowup_with_images.return_value = _completed_glowup_row()

    def _fetch_image_bytes(bucket: str, path: str) -> bytes:
        if bucket == BUCKET_BEFORE:
            return _FAKE_BEFORE_BYTES
        if bucket == BUCKET_AFTER:
            return _FAKE_AFTER_BYTES
        return b""

    repo.fetch_image_bytes.side_effect = _fetch_image_bytes
    return repo


def _stub_repo_with_source_photo() -> MagicMock:
    repo = MagicMock()
    repo.get_cleared_images.return_value = [
        {"id": "img_1", "storage_path": "user_a/selfie.jpg"},
    ]
    repo.fetch_image_bytes.return_value = _FAKE_SOURCE_BYTES
    return repo


# ---------------------------------------------------------------------------
# get_latest_glowup — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_glowup_returns_before_after_and_feature_metadata() -> None:
    """User with a completed glow-up → two base64 blocks + feature=glowup."""
    repo = _stub_repo_with_glowup()
    result = await _handle_get_latest_glowup(_ctx(repo=repo))

    image_blocks = [b for b in result if b.get("type") == "image"]
    text_blocks = [b for b in result if b.get("type") == "text"]

    assert len(image_blocks) == 2, f"expected 2 image blocks, got {len(image_blocks)}"
    assert len(text_blocks) == 1, f"expected 1 text block, got {len(text_blocks)}"

    # First image is the "before" (source); second is "after".
    before_block, after_block = image_blocks
    assert before_block["source"]["type"] == "base64"
    assert before_block["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(before_block["source"]["data"]) == _FAKE_BEFORE_BYTES

    assert after_block["source"]["type"] == "base64"
    assert base64.b64decode(after_block["source"]["data"]) == _FAKE_AFTER_BYTES

    # Feature metadata is the trailing text block.
    assert f"feature={FEATURE_TAG_GLOWUP}" in text_blocks[0]["text"]
    assert "completed_at=2026-04-17T00:01:00Z" in text_blocks[0]["text"]


@pytest.mark.asyncio
async def test_get_latest_glowup_uses_authenticated_user_id() -> None:
    """Handler passes ``ctx.user_id`` to the repo — not any caller-provided id."""
    repo = _stub_repo_with_glowup()
    await _handle_get_latest_glowup(_ctx(repo=repo))

    repo.get_latest_completed_glowup_with_images.assert_called_once_with(
        str(_TEST_USER_ID)
    )


# ---------------------------------------------------------------------------
# get_latest_glowup — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_glowup_returns_is_error_when_no_glowup_exists() -> None:
    """No completed glow-up → single text block with is_error=True."""
    repo = MagicMock()
    repo.get_latest_completed_glowup_with_images.return_value = None

    result = await _handle_get_latest_glowup(_ctx(repo=repo))
    assert result == [
        {
            "type": "text",
            "text": "no completed glow-up",
            "is_error": True,
        }
    ]


@pytest.mark.asyncio
async def test_get_latest_glowup_degrades_when_both_downloads_fail() -> None:
    """Both storage downloads fail → recoverable text block with is_error=True."""
    repo = MagicMock()
    repo.get_latest_completed_glowup_with_images.return_value = _completed_glowup_row()
    repo.fetch_image_bytes.side_effect = RuntimeError("storage outage")

    result = await _handle_get_latest_glowup(_ctx(repo=repo))
    assert len(result) == 1
    assert result[0]["type"] == "text"
    assert result[0]["is_error"] is True
    assert FEATURE_TAG_GLOWUP in result[0]["text"]


# ---------------------------------------------------------------------------
# get_latest_photo — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_photo_returns_single_base64_block_plus_metadata() -> None:
    """User with a cleared image → one base64 block + feature=source_photo."""
    repo = _stub_repo_with_source_photo()
    result = await _handle_get_latest_photo(_ctx(repo=repo))

    image_blocks = [b for b in result if b.get("type") == "image"]
    text_blocks = [b for b in result if b.get("type") == "text"]

    assert len(image_blocks) == 1, f"expected 1 image block, got {len(image_blocks)}"
    assert len(text_blocks) == 1

    assert image_blocks[0]["source"]["type"] == "base64"
    assert base64.b64decode(image_blocks[0]["source"]["data"]) == _FAKE_SOURCE_BYTES
    assert text_blocks[0]["text"] == f"feature={FEATURE_TAG_SOURCE_PHOTO}"


@pytest.mark.asyncio
async def test_get_latest_photo_fetches_from_before_bucket() -> None:
    """Source photo download targets ``BUCKET_BEFORE`` (raw-selfies)."""
    repo = _stub_repo_with_source_photo()
    await _handle_get_latest_photo(_ctx(repo=repo))

    repo.fetch_image_bytes.assert_called_once_with(BUCKET_BEFORE, "user_a/selfie.jpg")


# ---------------------------------------------------------------------------
# get_latest_photo — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_photo_returns_is_error_when_no_cleared_images() -> None:
    """Empty cleared-images list → is_error text block."""
    repo = MagicMock()
    repo.get_cleared_images.return_value = []
    result = await _handle_get_latest_photo(_ctx(repo=repo))

    assert result == [
        {
            "type": "text",
            "text": "no source photo",
            "is_error": True,
        }
    ]


@pytest.mark.asyncio
async def test_get_latest_photo_returns_is_error_when_storage_path_missing() -> None:
    """Row present but empty storage_path → treated as no source photo."""
    repo = MagicMock()
    repo.get_cleared_images.return_value = [
        {"id": "img_1", "storage_path": ""},
    ]
    result = await _handle_get_latest_photo(_ctx(repo=repo))

    assert result[0]["is_error"] is True


@pytest.mark.asyncio
async def test_get_latest_photo_degrades_when_download_fails() -> None:
    """Download error → recoverable text block with is_error=True."""
    repo = MagicMock()
    repo.get_cleared_images.return_value = [
        {"id": "img_1", "storage_path": "user_a/selfie.jpg"},
    ]
    repo.fetch_image_bytes.side_effect = RuntimeError("storage outage")
    result = await _handle_get_latest_photo(_ctx(repo=repo))

    assert len(result) == 1
    assert result[0]["is_error"] is True
    assert FEATURE_TAG_SOURCE_PHOTO in result[0]["text"]


# ---------------------------------------------------------------------------
# Schema introspection — belt-and-suspenders on Unit 9's registry audit
# ---------------------------------------------------------------------------


def test_glowup_module_declares_two_tools() -> None:
    """TOOL_SCHEMAS lists both tools; HANDLERS maps each by name."""
    names = {schema["name"] for schema in TOOL_SCHEMAS}
    assert names == {"get_latest_glowup", "get_latest_photo"}
    assert set(HANDLERS) == names


def test_glowup_tool_schemas_reject_user_id_shaped_keys() -> None:
    """Neither tool's input_schema accepts user_id / uid / account."""
    for schema in TOOL_SCHEMAS:
        forbidden = _schema_contains_forbidden_key(schema)
        assert forbidden is None, (
            f"tool {schema['name']!r} declares forbidden input key "
            f"{forbidden!r} (matches one of {FORBIDDEN_INPUT_KEY_FRAGMENTS})"
        )


def test_glowup_tool_schemas_have_empty_properties() -> None:
    """Both tools expose zero LLM-facing inputs (per plan)."""
    for schema in TOOL_SCHEMAS:
        props = schema["input_schema"].get("properties") or {}
        assert props == {}, (
            f"tool {schema['name']!r} unexpectedly declared input properties: {props}"
        )
        assert schema["input_schema"].get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Registry-level integration — plural TOOL_SCHEMAS / HANDLERS auto-discovery
# ---------------------------------------------------------------------------


def test_registry_auto_discovers_both_glowup_tools() -> None:
    """The registry picks up both tools from the shared module."""
    registry = ToolRegistry(ctx=_ctx())
    names = set(registry.tool_names())
    assert {"get_latest_glowup", "get_latest_photo"}.issubset(names)


@pytest.mark.asyncio
async def test_registry_dispatch_routes_get_latest_glowup_to_handler() -> None:
    """Dispatching by name returns the glow-up handler's output verbatim."""
    repo = _stub_repo_with_glowup()
    registry = ToolRegistry(ctx=_ctx(repo=repo))
    result = await registry.dispatch("get_latest_glowup", {})

    image_blocks = [b for b in result if b.get("type") == "image"]
    text_blocks = [b for b in result if b.get("type") == "text"]
    assert len(image_blocks) == 2
    assert any(FEATURE_TAG_GLOWUP in b["text"] for b in text_blocks)


@pytest.mark.asyncio
async def test_registry_dispatch_strips_hostile_keys_for_glowup_tools() -> None:
    """An LLM-hallucinated user_id is stripped before the handler runs."""
    repo = _stub_repo_with_glowup()
    registry = ToolRegistry(ctx=_ctx(repo=repo))

    # Hostile args the model might try — all must be filtered out.
    await registry.dispatch(
        "get_latest_glowup",
        {"user_id": "stranger", "uid": "stranger", "admin": True},
    )
    # Repo was called with the authenticated user's id, never the attacker's.
    repo.get_latest_completed_glowup_with_images.assert_called_once_with(
        str(_TEST_USER_ID)
    )
