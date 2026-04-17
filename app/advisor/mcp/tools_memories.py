"""``search_memories`` — Ada queries her own memory pool on demand.

Plan 2026-04-17-003 Unit 9. Wraps
``MemoryManager.get_relevant_memories`` so the model can pull additional
context beyond what the chat turn's initial memory block provided.
``ctx.user_id`` scopes every pgvector match — the LLM never sees or
passes an identifier.
"""

from __future__ import annotations

from typing import Any

from app.advisor.embedding_port import EmbeddingPort
from app.advisor.llm_port import LLMPort
from app.advisor.mcp.context import McpContext
from app.advisor.memory_manager import MemoryManager, summarize_memory_content

_TOOL_NAME = "search_memories"

_MIN_LIMIT = 1
_MAX_LIMIT = 10
_DEFAULT_LIMIT = 5
_MAX_QUERY_LENGTH = 400

_TOOL_DESCRIPTION = (
    "Searches the authenticated user's stored memories (goals, accepted "
    "suggestions, analysis insights, notes) for the best matches to a "
    "free-text query, using the same hybrid scoring the chat context "
    "builder uses.\n\n"
    "Call this when the user references a past decision or preference you "
    "do not have in the current context ('what did I say about bangs?'), "
    "when you want to check whether a suggestion has already been tried "
    "or dismissed, or when the question is specific enough that the "
    "initial 3-memory block is unlikely to cover it.\n\n"
    "Do NOT call this for topics clearly unrelated to the user's history, "
    "do NOT iterate the same query repeatedly, and do NOT call when the "
    "system memories block already surfaces the answer. Never pass "
    "user_id — the server resolves the authenticated user."
)

TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": _TOOL_DESCRIPTION,
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "maxLength": _MAX_QUERY_LENGTH,
                "description": "Free-text search query.",
            },
            "limit": {
                "type": "integer",
                "minimum": _MIN_LIMIT,
                "maximum": _MAX_LIMIT,
                "description": (
                    f"Maximum number of memories to return (default {_DEFAULT_LIMIT})."
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def _clamp_limit(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT
    return max(_MIN_LIMIT, min(_MAX_LIMIT, n))


def _get_manager(ctx: McpContext) -> MemoryManager:
    """Build or reuse a ``MemoryManager`` tied to the request context.

    The tool surface is additive in v1 — the request already has LLM and
    embedding adapters wired via ``AdvisorService``. Re-resolving them via
    ``app.api.deps`` here keeps the tool module testable in isolation
    without forcing the service layer to pass adapters into every
    handler.
    """
    manager = getattr(ctx, "_memory_manager_cache", None)
    if manager is not None:
        return manager  # type: ignore[return-value]

    from app.api.deps import get_embedding_adapter, get_llm_adapter

    llm: LLMPort = get_llm_adapter()
    embedding: EmbeddingPort = get_embedding_adapter()
    return MemoryManager(
        advisor_repo=ctx.advisor_repo,
        llm_adapter=llm,
        embedding_adapter=embedding,
    )


async def handle(
    ctx: McpContext,
    *,
    query: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the top matching memories as a bulleted text block."""
    q_str = str(query).strip()
    if not q_str:
        return [{"type": "text", "text": "empty query"}]
    if len(q_str) > _MAX_QUERY_LENGTH:
        q_str = q_str[:_MAX_QUERY_LENGTH]

    n_limit = _clamp_limit(limit if limit is not None else _DEFAULT_LIMIT)

    manager = _get_manager(ctx)
    rows = await manager.get_relevant_memories(ctx.user_id, q_str, limit=n_limit)
    if not rows:
        return [{"type": "text", "text": "no matches"}]

    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type", "memory")).strip() or "memory"
        summary = summarize_memory_content(row.get("content") or {})
        summary_one_line = (
            summary.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
        )
        if not summary_one_line:
            continue
        lines.append(f"- ({kind}) {summary_one_line}")
    text = "\n".join(lines) if lines else "no matches"
    return [{"type": "text", "text": text}]
