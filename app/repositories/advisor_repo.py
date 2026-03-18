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

    def update_conversation_summary(
        self, conversation_id: str, summary: str
    ) -> None:
        """Persist summary + summarised_at + updated_at on a conversation."""
        self._sb.table("advisor_conversations").update({
            "summary": summary,
            "summarised_at": datetime.now(tz=timezone.utc).isoformat(),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }).eq("id", conversation_id).execute()

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
            .order("created_at", asc=True)
            .execute()
        )
        return result.data or []

    def get_messages_page(
        self,
        conversation_id: str,
        fetch_limit: int,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of non-summarized messages (oldest first).

        Cursor format: ``{created_at}|{id}`` composite to avoid skipping
        records that share the same timestamp.
        """
        query = (
            self._sb.table("advisor_messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .is_("summarized_at", "null")
            .order("created_at", asc=True)
            .order("id", asc=True)
            .limit(fetch_limit)
        )
        if cursor:
            cursor_created_at, cursor_id = cursor.split("|", 1)
            query = query.or_(
                f"created_at.gt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.gt.{cursor_id})"
            )
        return query.execute().data or []

    def insert_message(
        self, conversation_id: str, role: str, content: str
    ) -> dict[str, Any]:
        """Insert a message row and return it."""
        result = (
            self._sb.table("advisor_messages")
            .insert({
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
            })
            .execute()
        )
        return (result.data or [{}])[0]

    def soft_delete_messages(self, conversation_id: str) -> None:
        """Mark all unsummarized messages as summarized (soft-delete after summarization).

        Sets summarized_at to now() on every message that has not already been
        summarized, preserving the rows for auditing and recovery.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        self._sb.table("advisor_messages").update({
            "summarized_at": now,
        }).eq("conversation_id", conversation_id).is_(
            "summarized_at", "null"
        ).execute()

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
            cursor_created_at, cursor_id = cursor.split("|", 1)
            # Rows before the cursor (newest-first): same created_at and id < cursor_id,
            # OR created_at < cursor_created_at
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        return query.execute().data or []

    def get_nudge_by_id(
        self, nudge_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """Fetch a single nudge, verifying ownership. Returns None if not found."""
        result = (
            self._sb.table("advisor_nudges")
            .select("id, read_at")
            .eq("id", nudge_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data or None

    def mark_nudge_read(self, nudge_id: str) -> None:
        """Set read_at to now on a nudge."""
        self._sb.table("advisor_nudges").update(
            {"read_at": datetime.now(tz=timezone.utc).isoformat()}
        ).eq("id", nudge_id).execute()

    def insert_nudge(self, nudge_data: dict[str, Any]) -> None:
        """Persist a new nudge row."""
        self._sb.table("advisor_nudges").insert(nudge_data).execute()

    def find_last_nudge(
        self, user_id: str, trigger: str
    ) -> dict[str, Any] | None:
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
            cursor_created_at, cursor_id = cursor.split("|", 1)
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        return query.execute().data or []

    def insert_memory(self, memory_data: dict[str, Any]) -> dict[str, Any]:
        """Insert a memory row (including embedding) and return it."""
        result = self._sb.table("user_memories").insert(memory_data).execute()
        return (result.data or [{}])[0]

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

    def get_recent_memories(
        self, user_id: str, since: str
    ) -> list[dict[str, Any]]:
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
        for row in (result.data or []):
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

    def get_latest_analysis_insight(
        self, user_id: str
    ) -> dict[str, Any] | None:
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

    # ------------------------------------------------------------------
    # Images / storage (vision context)
    # ------------------------------------------------------------------

    def get_cleared_images(
        self, user_id: str, limit: int = 2
    ) -> list[dict[str, Any]]:
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
