"""Advisor repository — all supabase queries for the advisor module in one place.

Covers tables: advisor_conversations, advisor_messages, advisor_nudges,
user_memories (pgvector), and images/storage for vision context.

Follows the same pattern as UserRepository: constructor takes a Client,
methods are synchronous unless they involve storage signed URLs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)

# Kept as a module-local constant to avoid importing the enum from
# ``app.advisor.models`` here — the repository sits below the advisor
# module in the dependency DAG and should not reach upward. The literal
# value matches ``MemoryType.STYLE_PROFILE.value``; a single-point
# cross-reference is enforced by
# ``tests/test_advisor_style_profile.py::test_repo_type_constant_matches_enum``.
STYLE_PROFILE_TYPE = "style_profile"

# ``jobs.source_type`` + ``jobs.status`` literals used by the glow-up
# lookup. Named constants rather than inline strings (project rule: no
# magic strings) so a rename of the canonical value is a single edit.
_SOURCE_TYPE_GLOWUP_ANALYSIS = "glowup_analysis"
_JOB_STATUS_COMPLETED = "completed"


class AdvisorRepository:
    """Encapsulates all DB queries for the advisor module."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def get_latest_conversation(self, user_id: str) -> dict[str, Any] | None:
        """Return the most recent conversation for a user, or None."""
        result = (
            self._sb.table("advisor_conversations")
            .select("id, updated_at, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def create_conversation(self, user_id: str) -> dict[str, Any]:
        """Create a new conversation and return the created row."""
        result = (
            self._sb.table("advisor_conversations")
            .insert({"user_id": user_id})
            .execute()
        )
        return (result.data or [{}])[0]

    def update_conversation_timestamp(self, conversation_id: str) -> None:
        """Touch updated_at on a conversation."""
        self._sb.table("advisor_conversations").update(
            {"updated_at": datetime.now(tz=timezone.utc).isoformat()}
        ).eq("id", conversation_id).execute()

    def update_conversation_summary(self, conversation_id: str, summary: str) -> None:
        """Persist summary + summarised_at + updated_at on a conversation."""
        self._sb.table("advisor_conversations").update(
            {
                "summary": summary,
                "summarised_at": datetime.now(tz=timezone.utc).isoformat(),
                "updated_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ).eq("id", conversation_id).execute()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Fetch all non-summarized messages for a conversation, oldest first."""
        result = (
            self._sb.table("advisor_messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .is_("summarized_at", "null")
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []

    def get_messages_page(
        self,
        conversation_id: str,
        fetch_limit: int,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of non-summarized messages.

        Reverse-chronological pagination — initial call (cursor=None)
        returns the NEWEST messages; subsequent calls with a cursor
        return messages OLDER than the cursor. Matches standard chat
        UX: the client sees the latest conversation on first open and
        scrolls up (onStartReached) to load older history.

        Rows are re-sorted to ascending (oldest → newest) before
        returning so callers can append them to a chat view without
        re-sorting.

        Cursor format: ``{created_at}|{id}`` composite, matching the
        nudges pagination cursor. The composite prevents skipping rows
        that share a timestamp.
        """
        query = (
            self._sb.table("advisor_messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .is_("summarized_at", "null")
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(fetch_limit)
        )
        if cursor:
            # A-7: Validate cursor format to return 400 on malformed input
            parts = cursor.split("|", 1)
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(
                    f"Malformed cursor: expected '{{created_at}}|{{id}}', got '{cursor}'"
                )
            cursor_created_at, cursor_id = parts
            # Reject characters that would break the PostgREST filter grammar —
            # commas, parentheses, or quotes inside a component smuggle filter
            # tokens into `or_()` (same injection shape as SQL).
            if any(ch in cursor_created_at + cursor_id for ch in ",()\"'"):
                raise ValueError(
                    f"Malformed cursor: illegal character in cursor components: '{cursor}'"
                )
            # Rows OLDER than the cursor (paging back in time):
            #   created_at < cursor, OR same created_at with id < cursor_id
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        rows = query.execute().data or []
        # DB returns newest-first; flip to ascending so callers render
        # oldest-at-top / newest-at-bottom without re-sorting.
        rows.reverse()
        return rows

    def insert_message(
        self, conversation_id: str, role: str, content: str
    ) -> dict[str, Any]:
        """Insert a message row and return it."""
        result = (
            self._sb.table("advisor_messages")
            .insert(
                {
                    "conversation_id": conversation_id,
                    "role": role,
                    "content": content,
                }
            )
            .execute()
        )
        return (result.data or [{}])[0]

    def soft_delete_messages(self, conversation_id: str) -> None:
        """Mark all unsummarized messages as summarized (soft-delete after summarization).

        Sets summarized_at to now() on every message that has not already been
        summarized, preserving the rows for auditing and recovery.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        self._sb.table("advisor_messages").update(
            {
                "summarized_at": now,
            }
        ).eq("conversation_id", conversation_id).is_("summarized_at", "null").execute()

    # ------------------------------------------------------------------
    # Nudges
    # ------------------------------------------------------------------

    def get_nudges(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch all nudges for a user, newest first."""
        result = (
            self._sb.table("advisor_nudges")
            .select("id, body, next_step_label, next_step_seed, read_at, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def get_recent_nudge_context(
        self, user_id: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return the newest N nudges for the "do not repeat" prompt block.

        Plan 2026-04-20-001 Unit 3. Returns
        ``[{"body": str, "next_step_label": str, "next_step_seed": str,
           "created_at": str}]`` newest-first. Does NOT touch ``read_at``
        — this is a pure read path.
        """
        result = (
            self._sb.table("advisor_nudges")
            .select("body, next_step_label, next_step_seed, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_nudges_page(
        self,
        user_id: str,
        fetch_limit: int,
        cursor: str | None = None,
        unread_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch a page of nudges (newest first).

        Cursor format: ``{created_at}|{id}`` composite.
        When ``unread_only`` is True, restricts to rows where read_at IS NULL.
        """
        query = (
            self._sb.table("advisor_nudges")
            .select("id, body, next_step_label, next_step_seed, read_at, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(fetch_limit)
        )
        if unread_only:
            query = query.is_("read_at", "null")
        if cursor:
            # A-7: Validate cursor format
            try:
                cursor_created_at, cursor_id = cursor.split("|", 1)
            except ValueError:
                raise ValueError(
                    f"Malformed cursor: expected '{{created_at}}|{{id}}', got '{cursor}'"
                )
            # Rows before the cursor (newest-first): same created_at and id < cursor_id,
            # OR created_at < cursor_created_at
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        return query.execute().data or []

    def get_nudge_by_id(self, nudge_id: str, user_id: str) -> dict[str, Any] | None:
        """Fetch a single nudge, verifying ownership. Returns None if not found."""
        result = (
            self._sb.table("advisor_nudges")
            .select("id, body, next_step_seed, read_at, created_at")
            .eq("id", nudge_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    def mark_nudge_read(self, nudge_id: str) -> None:
        """Set read_at to now on a nudge."""
        self._sb.table("advisor_nudges").update(
            {"read_at": datetime.now(tz=timezone.utc).isoformat()}
        ).eq("id", nudge_id).execute()

    def insert_nudge(self, nudge_data: dict[str, Any]) -> None:
        """Persist a new nudge row.

        Plan 2026-04-20-001 Unit 3. Expected keys:
        ``{user_id, body, next_step_label, next_step_seed, body_hash}``.
        Callers are responsible for the shape.
        """
        self._sb.table("advisor_nudges").insert(nudge_data).execute()

    def find_duplicate_body(
        self, user_id: str, body_hash: str, since: datetime
    ) -> bool:
        """Return True if a nudge with matching ``body_hash`` exists for this user
        with ``created_at >= since``.

        Plan 2026-04-20-001 Unit 3. Uses the non-unique index
        ``ix_advisor_nudges_user_body_hash (user_id, body_hash)``.
        """
        result = (
            self._sb.table("advisor_nudges")
            .select("id")
            .eq("user_id", user_id)
            .eq("body_hash", body_hash)
            .gte("created_at", since.isoformat())
            .limit(1)
            .execute()
        )
        return bool(result.data)

    def get_latest_completed_glowup_id(self, user_id: str) -> str | None:
        """Return the latest completed glowup job id for a user, or None.

        Plan 2026-04-20-001 Unit 3 (consumed by Unit 4 /next-step endpoint).
        Queries ``jobs`` with ``source_type='glowup_analysis'`` and
        ``status='completed'`` ordered by ``updated_at DESC LIMIT 1``.
        """
        result = (
            self._sb.table("jobs")
            .select("id")
            .eq("user_id", user_id)
            .eq("source_type", _SOURCE_TYPE_GLOWUP_ANALYSIS)
            .eq("status", _JOB_STATUS_COMPLETED)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        return str(rows[0]["id"])

    def get_recent_nudges_for_context(
        self, user_id: str, limit: int, since_iso: str
    ) -> list[dict[str, Any]]:
        """Return the user's newest ``limit`` nudges created at/after ``since_iso``.

        Read-only helper used by the chat context builder (Plan
        2026-04-17-003 Unit 4). Does NOT mutate ``read_at``. Returned rows
        carry ``body`` (the nudge body), ``next_step_label``,
        ``next_step_seed``, and ``created_at`` (ISO timestamp).

        Ordered newest-first so callers can emit them in recency order
        without re-sorting.
        """
        result = (
            self._sb.table("advisor_nudges")
            .select("body, next_step_label, next_step_seed, created_at")
            .eq("user_id", user_id)
            .gte("created_at", since_iso)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------

    def get_memories(
        self, user_id: str, type_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all memories for a user, newest first.

        If ``type_filter`` is given, restrict to that memory type.
        """
        query = (
            self._sb.table("user_memories")
            .select("id, type, content, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
        )
        if type_filter is not None:
            query = query.eq("type", type_filter)
        return query.execute().data or []

    def get_memories_page(
        self,
        user_id: str,
        fetch_limit: int,
        cursor: str | None = None,
        type_filter: str | None = None,
        authored_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of memories (newest first).

        Cursor format: ``{created_at}|{id}`` composite. ``authored_by``
        filters to a single provenance tier (the UI path passes
        ``'user'`` to hide model-written and analysis-written rows).

        ``authored_by`` is always in the projection even when not
        filtered on — the MCP tool renderer uses it to stamp user-
        authored rows with a ``(user)`` marker so Ada can weight
        declared intent over her own inferences.
        """
        query = (
            self._sb.table("user_memories")
            .select("id, type, content, created_at, authored_by")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(fetch_limit)
        )
        if type_filter is not None:
            query = query.eq("type", type_filter)
        if authored_by is not None:
            query = query.eq("authored_by", authored_by)
        if cursor:
            # A-7: Validate cursor format
            try:
                cursor_created_at, cursor_id = cursor.split("|", 1)
            except ValueError:
                raise ValueError(
                    f"Malformed cursor: expected '{{created_at}}|{{id}}', got '{cursor}'"
                )
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        return query.execute().data or []

    def insert_memory(self, memory_data: dict[str, Any]) -> dict[str, Any]:
        """Insert a memory row (including embedding) and return it."""
        result = self._sb.table("user_memories").insert(memory_data).execute()
        return (result.data or [{}])[0]

    def count_memories(self, user_id: str) -> int:
        """Return total memories for a user (spec §10 cap enforcement)."""
        result = (
            self._sb.table("user_memories")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        # supabase-py returns .count when count="exact"; fall back to len(data).
        count = getattr(result, "count", None)
        if count is None:
            count = len(result.data or [])
        return int(count)

    def delete_oldest_memory_by_authored_by(
        self,
        user_id: str,
        authored_by: str,
        exclude_types: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """Delete the single oldest memory of a given provenance tier.

        Used by ``MemoryManager._enforce_memory_cap`` to evict rows in
        priority order: ``model`` first, then ``analysis``, then ``user``.
        Returns deleted rows (empty list when the tier has nothing
        evictable — caller falls through to the next tier).
        """
        query = (
            self._sb.table("user_memories")
            .select("id")
            .eq("user_id", user_id)
            .eq("authored_by", authored_by)
            .order("created_at", desc=False)
            .order("id", desc=False)
            .limit(1)
        )
        if exclude_types:
            query = query.not_.in_("type", list(exclude_types))
        victim_rows = query.execute().data or []
        if not victim_rows:
            return []
        victim_id = victim_rows[0]["id"]
        deleted = (
            self._sb.table("user_memories")
            .delete()
            .eq("id", victim_id)
            .eq("user_id", user_id)
            .execute()
        )
        return deleted.data or []

    def find_memory_by_content_hash(
        self,
        *,
        user_id: str,
        memory_type: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        """Return an existing memory with a matching ``content_hash`` or ``None``.

        Indexed lookup via ``idx_user_memories_content_hash_unique``
        (migration 0042). The column is the app-computed canonical JSON
        hash — store and query sides compute it the same way to survive
        JSONB's unordered storage.
        """
        rows = (
            self._sb.table("user_memories")
            .select("id, type, content, created_at, authored_by, content_hash")
            .eq("user_id", user_id)
            .eq("type", memory_type)
            .eq("content_hash", content_hash)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    def find_semantic_duplicate(
        self,
        user_id: str,
        memory_type: str,
        embedding: list[float],
        threshold: float,
    ) -> dict[str, Any] | None:
        """Return the nearest same-type neighbor above ``threshold``, or ``None``.

        Calls the ``match_user_memories_by_type`` RPC (migration 0042)
        to fetch the single closest row of the same type for the user,
        then gates on cosine similarity. Returning ``None`` below the
        threshold lets the caller proceed with insertion.
        """
        result = self._sb.rpc(
            "match_user_memories_by_type",
            {
                "p_user_id": user_id,
                "p_embedding": embedding,
                "p_type": memory_type,
                "p_limit": 1,
            },
        ).execute()
        rows = result.data or []
        if not rows:
            return None
        top = rows[0]
        if float(top.get("similarity", 0.0)) >= threshold:
            return top
        return None

    def delete_memory(self, memory_id: str, user_id: str) -> list[dict[str, Any]]:
        """Delete a user-owned memory. Returns deleted rows (empty if not found)."""
        result = (
            self._sb.table("user_memories")
            .delete()
            .eq("id", memory_id)
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []

    def match_memories(
        self, user_id: str, embedding: list[float], limit: int
    ) -> list[dict[str, Any]]:
        """Run pgvector RPC to fetch the nearest memory candidates."""
        result = self._sb.rpc(
            "match_user_memories",
            {
                "p_user_id": user_id,
                "p_embedding": embedding,
                "p_limit": limit,
            },
        ).execute()
        return result.data or []

    def get_analysis_insights(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch analysis_insight memories for a user (used by service + nudge eligibility)."""
        result = (
            self._sb.table("user_memories")
            .select("user_id, created_at")
            .eq("user_id", user_id)
            .eq("type", "analysis_insight")
            .execute()
        )
        return result.data or []

    def get_latest_nudge_for_user(self, user_id: str) -> dict[str, Any] | None:
        """Return the most recent nudge (any trigger) for a user, or None."""
        result = (
            self._sb.table("advisor_nudges")
            .select("created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def count_analysis_insights(self, user_id: str) -> int:
        """Return the count of analysis_insight memories for a user."""
        result = (
            self._sb.table("user_memories")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("type", "analysis_insight")
            .execute()
        )
        return result.count or 0

    def get_latest_analysis_insight(self, user_id: str) -> dict[str, Any] | None:
        """Return the most recent analysis_insight content row, or None."""
        result = (
            self._sb.table("user_memories")
            .select("content, created_at")
            .eq("user_id", user_id)
            .eq("type", "analysis_insight")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_style_profile(self, user_id: str) -> dict[str, Any] | None:
        """Return the user's stable style_profile row (at most one), or None.

        Plan 2026-04-17-003 Unit 7. The partial unique index defined in
        migration 0040 guarantees that at most one row exists per user.
        Returns the ``content`` and ``created_at`` columns only — callers
        that need other columns should query directly.
        """
        result = (
            self._sb.table("user_memories")
            .select("content, created_at")
            .eq("user_id", user_id)
            .eq("type", STYLE_PROFILE_TYPE)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def upsert_style_profile(self, row: dict[str, Any]) -> dict[str, Any]:
        """Insert or update the user's style_profile row.

        Plan 2026-04-17-003 Unit 7. The partial unique index on
        ``user_memories(user_id) WHERE type='style_profile'`` cannot be
        referenced through PostgREST's ``on_conflict`` parameter because the
        parameter does not accept a WHERE clause. We use an explicit
        read-then-update-or-insert flow; the index still prevents race
        duplicates at the database level.

        ``row`` is expected to contain the same keys as ``insert_memory``
        (``user_id``, ``type``, ``content``, ``embedding``). Returns the
        persisted row.
        """
        user_id = row["user_id"]
        existing = (
            self._sb.table("user_memories")
            .select("id")
            .eq("user_id", user_id)
            .eq("type", STYLE_PROFILE_TYPE)
            .limit(1)
            .execute()
        )
        existing_rows = existing.data or []
        if existing_rows:
            row_id = existing_rows[0]["id"]
            updated = (
                self._sb.table("user_memories")
                .update(
                    {
                        "content": row["content"],
                        "embedding": row["embedding"],
                    }
                )
                .eq("id", row_id)
                .execute()
            )
            return (updated.data or [{}])[0]
        return self.insert_memory(row)

    # ------------------------------------------------------------------
    # Images / storage (vision context)
    # ------------------------------------------------------------------

    def get_latest_completed_job_with_images(
        self, user_id: str
    ) -> dict[str, Any] | None:
        """Return the user's most recent completed job that has BOTH URLs.

        Plan 2026-04-17-003 Unit 9. Used by the cross-feature
        ``get_latest_generation`` tool (polymorphic ``source_type``,
        treated uniformly by the advisor surface). Rows where either
        ``before_image_url`` or ``after_image_url`` is NULL are excluded —
        the advisor tool needs both to render the pair. Selects the
        polymorphic ``source_type`` alongside so the handler can surface
        ``feature="glowup" / "makeup"`` metadata without cross-table joins.
        """
        result = (
            self._sb.table("jobs")
            .select(
                "id, status, source_type, created_at, "
                "completed_at:updated_at, "
                "before_image_url, after_image_url"
            )
            .eq("user_id", user_id)
            .eq("status", "completed")
            .not_.is_("before_image_url", "null")
            .not_.is_("after_image_url", "null")
            .order("updated_at", desc=True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_latest_completed_glowup_with_images(
        self, user_id: str
    ) -> dict[str, Any] | None:
        """Return the user's most recent completed glow-up job with BOTH URLs.

        Plan 2026-04-17-003 Unit 2. Feature-specific sibling of
        ``get_latest_completed_job_with_images``: restricts
        ``source_type`` to ``glowup_analysis`` so the
        ``get_latest_glowup`` tool returns only glow-ups (not make-up
        sessions or any other polymorphic row that may land in ``jobs``
        later). Rows where either URL is NULL are excluded — the tool
        needs both images to render the pair.
        """
        result = (
            self._sb.table("jobs")
            .select(
                "id, status, source_type, created_at, "
                "completed_at:updated_at, "
                "before_image_url, after_image_url"
            )
            .eq("user_id", user_id)
            .eq("status", "completed")
            .eq("source_type", "glowup_analysis")
            .not_.is_("before_image_url", "null")
            .not_.is_("after_image_url", "null")
            .order("updated_at", desc=True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_latest_job_for_user(self, user_id: str) -> dict[str, Any] | None:
        """Return the user's most recent job regardless of status.

        Plan 2026-04-17-003 Unit 9 — backs the ``get_latest_job_status``
        tool. Returns status + timestamps + feature so the advisor can
        tell the user "your glow-up is still running" without exposing
        URLs.
        """
        result = (
            self._sb.table("jobs")
            .select("id, status, source_type, created_at, completed_at:updated_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def fetch_image_bytes(self, bucket: str, path: str) -> bytes:
        """Download raw bytes from a Supabase storage bucket.

        Plan 2026-04-17-003 Unit 9. Used by the vision-tool handlers to
        fetch the before/after images inline; the bytes are base64
        encoded into an Anthropic ``image`` content block by the caller.
        Signed URLs are NEVER generated on this path — the whole point of
        the Unit 9 rework is that no ephemeral URL enters the LLM
        payload or log stream.
        """
        return self._sb.storage.from_(bucket).download(path)

    def get_cleared_images(self, user_id: str, limit: int = 2) -> list[dict[str, Any]]:
        """Fetch the most recent cleared images for a user.

        The ``images`` table stores the path-within-bucket under
        ``storage_key`` (see migration 0001). There is no ``storage_path``
        column — selecting it raised 42703 and silently failed the
        post-glow-up nudge worker.
        """
        result = (
            self._sb.table("images")
            .select("id, storage_key")
            .eq("user_id", user_id)
            .eq("status", "cleared")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def create_signed_url(self, storage_path: str, expires_in: int) -> dict[str, Any]:
        """Create a signed URL for an image in storage."""
        return self._sb.storage.from_("images").create_signed_url(
            path=storage_path,
            expires_in=expires_in,
        )
