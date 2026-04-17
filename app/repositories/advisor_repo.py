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
            .select("id, trigger, content, read_at, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
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
            .select("id, trigger, content, read_at, created_at")
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
            .select("id, read_at")
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
        """Persist a new nudge row."""
        self._sb.table("advisor_nudges").insert(nudge_data).execute()

    def find_last_nudge(self, user_id: str, trigger: str) -> dict[str, Any] | None:
        """Return the most recent nudge for a user+trigger, or None."""
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

    def find_recent_nudges(
        self, user_id: str, trigger: str, since: str
    ) -> list[dict[str, Any]]:
        """Return nudges for user+trigger created after ``since`` (ISO timestamp).

        Used for cooldown / dedup checks.
        """
        result = (
            self._sb.table("advisor_nudges")
            .select("id")
            .eq("user_id", user_id)
            .eq("trigger", trigger)
            .gt("created_at", since)
            .limit(1)
            .execute()
        )
        return result.data or []

    def get_recent_nudges_for_context(
        self, user_id: str, limit: int, since_iso: str
    ) -> list[dict[str, Any]]:
        """Return the user's newest ``limit`` nudges created at/after ``since_iso``.

        Read-only helper used by the chat context builder (Plan
        2026-04-17-003 Unit 4). Does NOT mutate ``read_at`` — the chat
        surface must not change read state as a side effect of the model
        seeing a nudge. Returned rows carry ``content`` (the nudge body),
        ``trigger`` (lowercase identifier used as prefix in the system
        block), and ``created_at`` (ISO timestamp).

        Ordered newest-first so callers can emit them in recency order
        without re-sorting.
        """
        result = (
            self._sb.table("advisor_nudges")
            .select("content, trigger, created_at")
            .eq("user_id", user_id)
            .gte("created_at", since_iso)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_user_ids_with_nudge_since(
        self, since: str, trigger: str | None = None
    ) -> set[str]:
        """Batch version of ``find_recent_nudges`` — one query, any user.

        Returns the set of user IDs that have at least one nudge (optionally
        filtered by ``trigger``) created after ``since``. Callers use set
        membership to dedup eligibility scans in O(1) instead of N queries.
        """
        query = (
            self._sb.table("advisor_nudges").select("user_id").gt("created_at", since)
        )
        if trigger is not None:
            query = query.eq("trigger", trigger)
        result = query.execute()
        return {row["user_id"] for row in (result.data or [])}

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
    ) -> list[dict[str, Any]]:
        """Fetch a page of memories (newest first).

        Cursor format: ``{created_at}|{id}`` composite.
        """
        query = (
            self._sb.table("user_memories")
            .select("id, type, content, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(fetch_limit)
        )
        if type_filter is not None:
            query = query.eq("type", type_filter)
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

    def delete_oldest_memory_excluding_types(
        self, user_id: str, exclude_types: tuple[str, ...]
    ) -> list[dict[str, Any]]:
        """Delete the single oldest memory whose type is not in ``exclude_types``.

        Used to enforce the per-user memory cap without evicting user-declared
        intent (goals). Returns deleted rows (empty list if nothing to evict).
        """
        victim = (
            self._sb.table("user_memories")
            .select("id")
            .eq("user_id", user_id)
            .not_.in_("type", list(exclude_types))
            .order("created_at", desc=False)
            .order("id", desc=False)
            .limit(1)
            .execute()
        )
        victim_rows = victim.data or []
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

    def get_recent_memories(self, user_id: str, since: str) -> list[dict[str, Any]]:
        """Return memories created after ``since`` (ISO timestamp) for dedup."""
        result = (
            self._sb.table("user_memories")
            .select("type, content")
            .eq("user_id", user_id)
            .gte("created_at", since)
            .execute()
        )
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

    def get_all_insights_with_timestamps(self) -> list[dict[str, Any]]:
        """Fetch (user_id, created_at) for all analysis_insight rows.

        Used by nudge eligibility scans across all users.
        """
        result = (
            self._sb.table("user_memories")
            .select("user_id, created_at")
            .eq("type", "analysis_insight")
            .execute()
        )
        return result.data or []

    def count_insights_by_user(self) -> dict[str, int]:
        """Return a mapping of user_id → analysis_insight count for all users.

        Uses a COUNT query grouped by user_id to avoid fetching every row.
        """
        result = (
            self._sb.table("user_memories")
            .select("user_id", count="exact")
            .eq("type", "analysis_insight")
            .execute()
        )
        # PostgREST does not support GROUP BY directly; fall back to Python grouping
        # on the minimal (user_id-only) payload — significantly less data than
        # fetching created_at for every row.
        counts: dict[str, int] = {}
        for row in result.data or []:
            uid = row["user_id"]
            counts[uid] = counts.get(uid, 0) + 1
        return counts

    def get_all_goal_user_ids(self) -> set[str]:
        """Fetch distinct user IDs that have at least one goal memory.

        Used by the weekly check-in eligibility scan.
        """
        result = (
            self._sb.table("user_memories")
            .select("user_id")
            .eq("type", "goal")
            .execute()
        )
        return {row["user_id"] for row in (result.data or [])}

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

    def get_cleared_images(self, user_id: str, limit: int = 2) -> list[dict[str, Any]]:
        """Fetch the most recent cleared images for a user."""
        result = (
            self._sb.table("images")
            .select("id, storage_path")
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
