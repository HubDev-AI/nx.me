"""Memory MCP tools — save_memory, list_recent_memories, search_memories.

Coverage:
  * save_memory round-trips with authored_by='model' on the insert.
  * save_memory dedup paths surface the reason in the tool_result.
  * save_memory whitelist rejects non-writable types (style_profile /
    analysis_insight) with is_error=True.
  * list_recent_memories paginates with a cursor and renders the
    provenance prefix ((user) marker only for authored_by='user').
  * search_memories excludes style_profile rows.
  * Line rendering format: ``{prefix}{(user)?}: {summary}``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.advisor.mcp.context import McpContext
from app.advisor.mcp.tools_memories import (
    HANDLERS,
    TOOL_NAME_LIST_RECENT,
    TOOL_NAME_SAVE,
    TOOL_NAME_SEARCH,
    TOOL_SCHEMAS,
    _format_memory_line,
)
from app.advisor.models import MemoryType


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _ToolRepo:
    """Minimal repo used by all three tools."""

    def __init__(self) -> None:
        self.memories: list[dict] = []
        self.inserted: list[dict] = []
        self._exact_match: dict | None = None
        self._semantic_match: dict | None = None

    # Write-path hooks consumed by MemoryManager.write_memory.
    def find_memory_by_content_hash(
        self, *, user_id: str, memory_type: str, content_hash: str
    ) -> dict | None:
        return self._exact_match

    def find_semantic_duplicate(
        self,
        *,
        user_id: str,
        memory_type: str,
        embedding: list[float],
        threshold: float,
    ) -> dict | None:
        return self._semantic_match

    def count_memories(self, user_id: str) -> int:
        return 0

    def delete_oldest_memory_by_authored_by(
        self, user_id: str, *, authored_by: str, exclude_types: tuple[str, ...]
    ) -> list[dict]:
        return []

    def insert_memory(self, row: dict) -> dict:
        self.inserted.append(row)
        created = {**row, "id": str(uuid4()), "created_at": "2026-04-18T00:00:00+00:00"}
        self.memories.append(created)
        return created

    # Read-path hook consumed by list_recent_memories.
    def get_memories_page(
        self,
        user_id: str,
        fetch_limit: int,
        cursor: str | None = None,
        type_filter: str | None = None,
        authored_by: str | None = None,
    ) -> list[dict]:
        rows = [m for m in self.memories if m["user_id"] == user_id]
        if type_filter is not None:
            rows = [m for m in rows if m["type"] == type_filter]
        if authored_by is not None:
            rows = [m for m in rows if m.get("authored_by") == authored_by]
        rows.sort(key=lambda m: (m["created_at"], m["id"]), reverse=True)
        if cursor:
            cursor_created_at, cursor_id = cursor.split("|", 1)
            rows = [
                m
                for m in rows
                if (m["created_at"], m["id"]) < (cursor_created_at, cursor_id)
            ]
        return rows[:fetch_limit]

    # Read-path hook consumed by search_memories (via MemoryManager).
    def match_memories(
        self, user_id: str, embedding: list[float], limit: int
    ) -> list[dict]:
        # Return all memories as candidates with fake similarity 0.9 so
        # the ranker keeps them.
        return [{**m, "similarity": 0.9} for m in self.memories][:limit]


def _make_ctx(repo: _ToolRepo, user_id: UUID | None = None) -> McpContext:
    return McpContext(
        user_id=user_id or uuid4(),
        supabase=object(),
        advisor_repo=repo,  # type: ignore[arg-type]
        logger=logging.getLogger("test"),
    )


@pytest.fixture(autouse=True)
def _stub_embedding_adapter(monkeypatch):
    """Stub ``get_embedding_adapter`` so handlers build a real MemoryManager
    without reaching into the deps container (which requires settings that
    aren't populated in unit tests)."""

    def _fake_adapter():
        return SimpleNamespace(compute_embedding=AsyncMock(return_value=[0.1] * 8))

    # Patch at both the symbol's origin and the site tools_memories imports
    # from — the handler does a local `from app.api.deps import ...` inside
    # ``_get_manager``, so replacing the attribute on ``app.api.deps`` is
    # the reliable hook.
    import app.api.deps

    monkeypatch.setattr(app.api.deps, "get_embedding_adapter", _fake_adapter)


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_three_tools_registered_with_expected_names():
    names = {s["name"] for s in TOOL_SCHEMAS}
    assert names == {TOOL_NAME_SEARCH, TOOL_NAME_LIST_RECENT, TOOL_NAME_SAVE}
    # HANDLERS is a 1:1 map of name → async handler.
    assert set(HANDLERS) == names
    for handler in HANDLERS.values():
        assert callable(handler)


def test_save_memory_schema_whitelists_only_writable_types():
    save_schema = next(s for s in TOOL_SCHEMAS if s["name"] == TOOL_NAME_SAVE)
    type_enum = set(save_schema["input_schema"]["properties"]["type"]["enum"])
    assert type_enum == {
        "goal",
        "user_note",
        "accepted_suggestion",
        "dismissed_suggestion",
    }
    # style_profile + analysis_insight are NOT model-writable — they are
    # system-only and must be absent from the schema.
    assert "style_profile" not in type_enum
    assert "analysis_insight" not in type_enum


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_memory_writes_with_model_provenance():
    repo = _ToolRepo()
    ctx = _make_ctx(repo)

    result = await HANDLERS[TOOL_NAME_SAVE](
        ctx, type="goal", text="grow my hair this year"
    )

    assert result["is_error"] is False
    assert "saved=true" in result["content"][0]["text"]
    assert len(repo.inserted) == 1
    assert repo.inserted[0]["authored_by"] == "model"
    assert repo.inserted[0]["type"] == "goal"


@pytest.mark.asyncio
async def test_save_memory_surfaces_dedup_reason_on_exact_match():
    repo = _ToolRepo()
    repo._exact_match = {
        "id": "existing",
        "content": {"text": "grow my hair"},
        "type": "goal",
    }
    ctx = _make_ctx(repo)

    result = await HANDLERS[TOOL_NAME_SAVE](
        ctx, type="goal", text="grow my hair"
    )

    assert result["is_error"] is False
    text = result["content"][0]["text"]
    assert "saved=false" in text
    assert "dedup=exact_content" in text
    assert repo.inserted == []


@pytest.mark.asyncio
async def test_save_memory_rejects_non_writable_type():
    repo = _ToolRepo()
    ctx = _make_ctx(repo)

    result = await HANDLERS[TOOL_NAME_SAVE](
        ctx, type="style_profile", text="anything"
    )

    assert result["is_error"] is True
    assert "invalid type" in result["content"][0]["text"]
    assert repo.inserted == []


@pytest.mark.asyncio
async def test_save_memory_rejects_empty_text():
    repo = _ToolRepo()
    ctx = _make_ctx(repo)

    result = await HANDLERS[TOOL_NAME_SAVE](ctx, type="goal", text="   ")

    assert result["is_error"] is True
    assert "empty text" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# list_recent_memories
# ---------------------------------------------------------------------------


def _seed_memories(repo: _ToolRepo, user_id: UUID) -> None:
    """Three rows, different types + provenance."""
    repo.memories.extend(
        [
            {
                "id": "m1",
                "user_id": str(user_id),
                "type": "goal",
                "content": {"text": "grow my hair this year"},
                "created_at": "2026-04-18T10:00:00+00:00",
                "authored_by": "user",
            },
            {
                "id": "m2",
                "user_id": str(user_id),
                "type": "accepted_suggestion",
                "content": {"text": "got the side-swept fringe"},
                "created_at": "2026-04-17T10:00:00+00:00",
                "authored_by": "model",
            },
            {
                "id": "m3",
                "user_id": str(user_id),
                "type": "dismissed_suggestion",
                "content": {"text": "short crop"},
                "created_at": "2026-04-16T10:00:00+00:00",
                "authored_by": "model",
            },
        ]
    )


@pytest.mark.asyncio
async def test_list_recent_renders_provenance_prefix():
    user_id = uuid4()
    repo = _ToolRepo()
    _seed_memories(repo, user_id)
    ctx = _make_ctx(repo, user_id)

    result = await HANDLERS[TOOL_NAME_LIST_RECENT](ctx)

    assert result["is_error"] is False
    body = result["content"][0]["text"]
    # User-authored row carries (user) flag.
    assert "goal (user): grow my hair this year" in body
    # Model-authored rows render WITHOUT (user) — the model should not
    # mistake its own inference for user-declared intent.
    assert "tried: got the side-swept fringe" in body
    assert "avoid: short crop" in body
    # Newest first.
    lines = [line for line in body.split("\n") if line and not line.startswith("cursor:")]
    assert lines[0].startswith("goal (user):")


@pytest.mark.asyncio
async def test_list_recent_paginates_with_cursor():
    user_id = uuid4()
    repo = _ToolRepo()
    # 3 rows, limit=1 per page.
    _seed_memories(repo, user_id)
    ctx = _make_ctx(repo, user_id)

    page1 = await HANDLERS[TOOL_NAME_LIST_RECENT](ctx, limit=1)
    # Cursor rides on its own content block so memory text that
    # happens to contain "cursor:" can't fool the parser.
    assert len(page1["content"]) == 2
    body1 = page1["content"][0]["text"]
    cursor_block = page1["content"][1]["text"]
    assert cursor_block.startswith("next_cursor=")
    assert "goal (user):" in body1
    cursor = cursor_block.split("next_cursor=", 1)[1].strip()

    page2 = await HANDLERS[TOOL_NAME_LIST_RECENT](ctx, limit=1, cursor=cursor)
    body2 = page2["content"][0]["text"]
    # Page 2 has the middle row.
    assert "tried: got the side-swept fringe" in body2
    assert "goal (user):" not in body2


@pytest.mark.asyncio
async def test_list_recent_filters_by_type():
    user_id = uuid4()
    repo = _ToolRepo()
    _seed_memories(repo, user_id)
    ctx = _make_ctx(repo, user_id)

    result = await HANDLERS[TOOL_NAME_LIST_RECENT](ctx, type="dismissed_suggestion")

    body = result["content"][0]["text"]
    assert "avoid: short crop" in body
    assert "goal (user)" not in body
    assert "tried:" not in body


@pytest.mark.asyncio
async def test_list_recent_reports_empty_when_no_memories():
    user_id = uuid4()
    repo = _ToolRepo()
    ctx = _make_ctx(repo, user_id)

    result = await HANDLERS[TOOL_NAME_LIST_RECENT](ctx)

    assert result["content"][0]["text"] == "no memories"


# ---------------------------------------------------------------------------
# search_memories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_memories_excludes_style_profile():
    user_id = uuid4()
    repo = _ToolRepo()
    # style_profile + one goal — ranker returns both as high-similarity.
    repo.memories.extend(
        [
            {
                "id": "p1",
                "user_id": str(user_id),
                "type": "style_profile",
                "content": {
                    "face_shape": "oval",
                    "symmetry_score": 0.87,
                    "recommendations": ["try bangs"],
                },
                "created_at": "2026-04-18T10:00:00+00:00",
                "authored_by": "analysis",
            },
            {
                "id": "g1",
                "user_id": str(user_id),
                "type": "goal",
                "content": {"text": "grow my hair"},
                "created_at": "2026-04-17T10:00:00+00:00",
                "authored_by": "user",
            },
        ]
    )
    ctx = _make_ctx(repo, user_id)

    result = await HANDLERS[TOOL_NAME_SEARCH](ctx, query="hair")

    body = result["content"][0]["text"]
    # style_profile row must not surface — user_data already carries it.
    assert "oval" not in body
    assert "face:" not in body
    # The goal still surfaces with its provenance prefix.
    assert "goal (user): grow my hair" in body


@pytest.mark.asyncio
async def test_search_memories_empty_query_short_circuits():
    ctx = _make_ctx(_ToolRepo())

    result = await HANDLERS[TOOL_NAME_SEARCH](ctx, query="   ")

    assert result["is_error"] is False
    assert "empty query" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Render helper invariants
# ---------------------------------------------------------------------------


def test_format_memory_line_user_marker_only_for_user_provenance():
    user_row = {
        "type": MemoryType.GOAL.value,
        "content": {"text": "x"},
        "authored_by": "user",
    }
    model_row = {
        "type": MemoryType.GOAL.value,
        "content": {"text": "x"},
        "authored_by": "model",
    }
    assert _format_memory_line(user_row) == "goal (user): x"
    assert _format_memory_line(model_row) == "goal: x"


def test_format_memory_line_flattens_newlines_in_summary():
    row = {
        "type": MemoryType.USER_NOTE.value,
        "content": {"text": "line1\nline2\r\nline3"},
        "authored_by": "user",
    }
    rendered = _format_memory_line(row)
    assert "\n" not in rendered
    assert "\r" not in rendered
    assert "line1" in rendered and "line3" in rendered
