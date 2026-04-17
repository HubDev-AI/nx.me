"""Memory tools — Ada's read + write + list surface for user_memories.

Plan 2026-04-18: memory is fully model-driven. Ada calls these tools to
retrieve (``search_memories`` for semantic, ``list_recent_memories``
for chronological) and to persist (``save_memory``). The prior post-turn
Haiku extraction is gone; the model decides what's worth remembering.

Every handler scopes to ``ctx.user_id`` — the LLM never sees, passes,
or spoofs an identifier. Schema-level filtering in the registry drops
any hallucinated ``user_id`` key before it reaches these handlers.
"""

from __future__ import annotations

from typing import Any

from app.advisor.embedding_port import EmbeddingPort
from app.advisor.mcp.context import McpContext
from app.advisor.memory_manager import MemoryManager, summarize_memory_content
from app.advisor.models import MemoryType

# ---------------------------------------------------------------------------
# Shared constants — render order + provenance prefixes keep Ada's view of
# memories structured rather than flattened into raw text fragments.
# ---------------------------------------------------------------------------

# Tool names exposed to the model. Kept as module constants so the
# registry's auto-discovery finds them under their canonical form.
TOOL_NAME_SEARCH = "search_memories"
TOOL_NAME_LIST_RECENT = "list_recent_memories"
TOOL_NAME_SAVE = "save_memory"

# Limit bounds (per-tool). Semantic search uses a smaller default than
# the chronological list because similarity scoring is more selective
# and pulling too many low-score hits dilutes relevance.
_SEARCH_MIN_LIMIT = 1
_SEARCH_MAX_LIMIT = 10
_SEARCH_DEFAULT_LIMIT = 5
_LIST_MIN_LIMIT = 1
_LIST_MAX_LIMIT = 20
_LIST_DEFAULT_LIMIT = 10

# Query / text length caps — consistent across the tool surface and
# the user-facing POST /v1/memories.
_MAX_QUERY_LENGTH = 400
_MAX_SAVE_TEXT_LENGTH = 400

# Types the model is allowed to pass to save_memory. style_profile and
# analysis_insight are system-only — the face-analysis pipeline owns
# them and the model would undermine the retrieval ranker if it could
# write to either type.
_MODEL_SAVABLE_TYPES: frozenset[str] = frozenset(
    {
        MemoryType.GOAL.value,
        MemoryType.USER_NOTE.value,
        MemoryType.ACCEPTED_SUGGESTION.value,
        MemoryType.DISMISSED_SUGGESTION.value,
    }
)

# Same whitelist for list_recent_memories' optional type filter — Ada
# should never need to list style_profile rows since they are always
# in user_data, and listing analysis_insight is a specialized path
# (if ever needed, surface via a separate tool). Keeping parity with
# save_memory also simplifies the persona prompt.
_LISTABLE_TYPES: frozenset[str] = _MODEL_SAVABLE_TYPES

# Rendered provenance prefix per memory type. Keeps Ada's view of a
# retrieved memory structured enough that she can tell a user-typed
# goal from a model-saved accepted_suggestion without the server
# spelling out "authored_by=user" every line. Chosen to be terse so
# the prompt stays token-cheap.
#
# Format per line:
#   ``{prefix}{user_flag}: {summary}``
#
# where ``user_flag`` is " (user)" for user-typed rows and empty
# otherwise, because a model-written goal should not pretend to be
# user-declared intent.
_TYPE_PREFIX: dict[str, str] = {
    MemoryType.GOAL.value: "goal",
    MemoryType.USER_NOTE.value: "note",
    MemoryType.ACCEPTED_SUGGESTION.value: "tried",
    MemoryType.DISMISSED_SUGGESTION.value: "avoid",
    MemoryType.ANALYSIS_INSIGHT.value: "face",
    MemoryType.STYLE_PROFILE.value: "face",
}

# Memory types that pgvector returns but the search_memories tool
# must never surface — ``style_profile`` is always in the user_data
# system block, so including it again is duplicate context.
_SEARCH_EXCLUDED_TYPES: frozenset[str] = frozenset({MemoryType.STYLE_PROFILE.value})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SEARCH_DESCRIPTION = (
    "Semantic search over the authenticated user's memories. Returns the "
    "top matches by hybrid (similarity + recency + importance) score.\n\n"
    "Call when the user references something specific you do not have "
    "in front of you ('what did I say about bangs?', 'am I still going "
    "for the shorter cut?'). Do NOT call for greetings, one-word "
    "replies, or obviously unrelated topics. Do NOT iterate the same "
    "query. Never pass user_id — the server resolves it."
)

_LIST_RECENT_DESCRIPTION = (
    "Chronological list of the authenticated user's recent memories, "
    "newest first. Paginated by ``{created_at}|{id}`` cursor; the first "
    "call omits ``cursor``, subsequent calls pass the prior response's "
    "``next_cursor``.\n\n"
    "Use when the user asks for a direct list ('what are my goals?', "
    "'anything I've tried?'). Prefer this over ``search_memories`` when "
    "you do not have a specific query — it is cheaper and avoids the "
    "similarity threshold dropping recent items."
)

_SAVE_DESCRIPTION = (
    "Persist a new memory about the authenticated user. Writes under "
    "``authored_by='model'`` so the saved row never surfaces in the "
    "user's Goals/Notes UI — those tabs are user-authored only.\n\n"
    "When to save:\n"
    "  * goal: user states future intent in >5 words ('I want to grow "
    "my hair out this year').\n"
    "  * user_note: stable preference ('I prefer minimal jewelry').\n"
    "  * accepted_suggestion: user tried or is doing something ('I got "
    "the fringe, it's working').\n"
    "  * dismissed_suggestion: user explicitly rejects a suggestion "
    "('no, not cutting it short').\n\n"
    "Do NOT save: greetings, thanks, one-word replies, your own "
    "output, restatements of a memory you just retrieved, clearly "
    "ephemeral remarks. At most one save per turn. Dedup is automatic: "
    "exact and near-duplicate texts return ``saved=false`` with the "
    "dedup reason and you do NOT need to retry with different wording."
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": TOOL_NAME_SEARCH,
        "description": _SEARCH_DESCRIPTION,
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
                    "minimum": _SEARCH_MIN_LIMIT,
                    "maximum": _SEARCH_MAX_LIMIT,
                    "description": (
                        f"Maximum number of memories to return (default "
                        f"{_SEARCH_DEFAULT_LIMIT})."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": TOOL_NAME_LIST_RECENT,
        "description": _LIST_RECENT_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": sorted(_LISTABLE_TYPES),
                    "description": (
                        "Optional memory type filter. Omit to list across "
                        "all model/user-writable types."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "minimum": _LIST_MIN_LIMIT,
                    "maximum": _LIST_MAX_LIMIT,
                    "description": (
                        f"Page size (default {_LIST_DEFAULT_LIMIT})."
                    ),
                },
                "cursor": {
                    "type": "string",
                    "description": (
                        "Pagination cursor from a prior response's "
                        "``next_cursor``."
                    ),
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": TOOL_NAME_SAVE,
        "description": _SAVE_DESCRIPTION,
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": sorted(_MODEL_SAVABLE_TYPES),
                    "description": "Memory type (goal / user_note / accepted_suggestion / dismissed_suggestion).",
                },
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": _MAX_SAVE_TEXT_LENGTH,
                    "description": "The memory body, as prose.",
                },
            },
            "required": ["type", "text"],
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_manager(ctx: McpContext) -> MemoryManager:
    """Build a ``MemoryManager`` tied to the request context.

    Resolves the embedding adapter via ``app.api.deps`` so the tool
    module stays testable in isolation without forcing the service
    layer to pass adapters into every handler. Rebuilt per call — a
    ``MemoryManager`` is a thin wrapper around the repo and the
    adapter, so the allocation is cheap and the stateless-per-turn
    contract is easier to reason about than a lifetime cache on a
    frozen context.
    """
    from app.api.deps import get_embedding_adapter

    embedding: EmbeddingPort = get_embedding_adapter()
    return MemoryManager(
        advisor_repo=ctx.advisor_repo,
        embedding_adapter=embedding,
    )


def _format_memory_line(row: dict[str, Any]) -> str:
    """Render one memory row as a single structured line.

    Examples:
      * ``goal (user): grow my hair out``
      * ``tried: got the side-swept fringe``
      * ``avoid: short crop``
      * ``note (user): prefer minimal jewelry``

    Provenance is shown ONLY for user-authored rows — the ``(user)``
    marker lets Ada weight declared user intent over her own inferences.
    Rows with unknown type fall back to a generic ``memory:`` prefix so
    the handler never emits an unlabeled line.
    """
    kind = str(row.get("type", "")).strip()
    prefix = _TYPE_PREFIX.get(kind, "memory")
    user_flag = " (user)" if row.get("authored_by") == "user" else ""
    summary = summarize_memory_content(row.get("content") or {})
    # Flatten any embedded newlines so the block stays one-row-per-line.
    summary = (
        summary.replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    )
    return f"{prefix}{user_flag}: {summary}" if summary else ""


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    """Coerce ``value`` to an int and clamp into ``[lo, hi]`` with fallback."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_search(
    ctx: McpContext,
    *,
    query: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return the top semantically-matching memories as a text block.

    Returns ``{"content": [...], "is_error": False}`` — empty queries
    and empty matches are reportable outcomes, not envelope-level
    errors. ``style_profile`` rows are filtered out because they are
    always rendered into ``user_data`` and would be redundant here.
    """
    q_str = str(query).strip()
    if not q_str:
        return {
            "content": [{"type": "text", "text": "empty query"}],
            "is_error": False,
        }
    if len(q_str) > _MAX_QUERY_LENGTH:
        q_str = q_str[:_MAX_QUERY_LENGTH]

    n_limit = _clamp(
        limit if limit is not None else _SEARCH_DEFAULT_LIMIT,
        _SEARCH_MIN_LIMIT,
        _SEARCH_MAX_LIMIT,
        _SEARCH_DEFAULT_LIMIT,
    )

    manager = _get_manager(ctx)
    rows = await manager.get_relevant_memories(ctx.user_id, q_str, limit=n_limit)

    # ``MemoryManager.get_relevant_memories`` already drops
    # ``style_profile`` (it is always in the user_data block), so no
    # second filter is needed here.
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        line = _format_memory_line(row)
        if line:
            lines.append(line)

    text = "\n".join(lines) if lines else "no matches"
    return {"content": [{"type": "text", "text": text}], "is_error": False}


async def handle_list_recent(
    ctx: McpContext,
    *,
    type: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return a chronological page of memories with a cursor for paging."""
    type_filter: str | None = None
    if type is not None:
        type_str = str(type).strip()
        if type_str and type_str in _LISTABLE_TYPES:
            type_filter = type_str

    n_limit = _clamp(
        limit if limit is not None else _LIST_DEFAULT_LIMIT,
        _LIST_MIN_LIMIT,
        _LIST_MAX_LIMIT,
        _LIST_DEFAULT_LIMIT,
    )

    from app.db.async_helpers import run_sync

    fetch_limit = n_limit + 1
    try:
        rows = await run_sync(
            ctx.advisor_repo.get_memories_page,
            user_id=str(ctx.user_id),
            fetch_limit=fetch_limit,
            cursor=cursor,
            type_filter=type_filter,
        )
    except ValueError as exc:
        # Malformed cursor — surface as a tool error so the model can
        # recover by omitting the cursor on the retry.
        return {
            "content": [{"type": "text", "text": f"invalid cursor: {exc}"}],
            "is_error": True,
        }

    has_more = len(rows) > n_limit
    if has_more:
        rows = rows[:n_limit]

    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        line = _format_memory_line(row)
        if line:
            lines.append(line)

    next_cursor = (
        f"{rows[-1]['created_at']}|{rows[-1]['id']}" if has_more and rows else None
    )

    body = "\n".join(lines) if lines else "no memories"
    # Cursor is returned as a SEPARATE content block (not inlined into
    # the body text) so a memory whose text happens to contain the
    # literal substring ``cursor:`` cannot fool the model into parsing
    # the wrong token. Anthropic's tool_result shape accepts multiple
    # text blocks and they are concatenated for the model in order.
    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": body}]
    if next_cursor:
        content_blocks.append(
            {"type": "text", "text": f"next_cursor={next_cursor}"}
        )
    return {"content": content_blocks, "is_error": False}


async def handle_save(
    ctx: McpContext,
    *,
    type: str,
    text: str,
) -> dict[str, Any]:
    """Persist a model-authored memory.

    Return shape:
      * Success:      ``{"saved": true,  "id": "...", "type": "..."}``
      * Exact dupe:   ``{"saved": false, "dedup": "exact_content"}``
      * Semantic dupe:``{"saved": false, "dedup": "semantic_<score>"}``
      * Race dupe:    ``{"saved": false, "dedup": "race"}``
    Rendered as a single text block so Ada reads it in her tool_result.
    """
    type_str = str(type).strip()
    if type_str not in _MODEL_SAVABLE_TYPES:
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"invalid type: {type_str!r}. Must be one of "
                        f"{sorted(_MODEL_SAVABLE_TYPES)}"
                    ),
                }
            ],
            "is_error": True,
        }

    body = str(text).strip()
    if not body:
        return {
            "content": [{"type": "text", "text": "empty text"}],
            "is_error": True,
        }
    if len(body) > _MAX_SAVE_TEXT_LENGTH:
        body = body[:_MAX_SAVE_TEXT_LENGTH]

    manager = _get_manager(ctx)
    try:
        memory_enum = MemoryType(type_str)
    except ValueError:
        # Belt-and-suspenders — the whitelist above should have caught this.
        return {
            "content": [{"type": "text", "text": f"unknown type {type_str!r}"}],
            "is_error": True,
        }

    row = await manager.write_memory(
        ctx.user_id,
        memory_enum,
        {"text": body},
        authored_by="model",
    )

    dedup_reason = row.get("_dedup")
    if dedup_reason:
        text_line = f"saved=false, dedup={dedup_reason}"
    else:
        text_line = f"saved=true, type={type_str}, id={row.get('id', '')}"
    return {"content": [{"type": "text", "text": text_line}], "is_error": False}


# ---------------------------------------------------------------------------
# Registry export — plural pattern so one module ships three tools.
# ---------------------------------------------------------------------------

HANDLERS: dict[str, Any] = {
    TOOL_NAME_SEARCH: handle_search,
    TOOL_NAME_LIST_RECENT: handle_list_recent,
    TOOL_NAME_SAVE: handle_save,
}
