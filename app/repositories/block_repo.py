"""Block repository — all queries for user blocking."""

from __future__ import annotations

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


class BlockRepository:
    """Encapsulates all DB queries for user blocking."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def block(self, blocker_id: str, blocked_id: str) -> dict[str, Any]:
        """Create a block relationship (idempotent via upsert)."""
        result = (
            self._sb.table("blocked_users")
            .upsert(
                {"blocker_id": blocker_id, "blocked_id": blocked_id},
                on_conflict="blocker_id,blocked_id",
            )
            .execute()
        )
        return (result.data or [{}])[0]

    def unblock(self, blocker_id: str, blocked_id: str) -> bool:
        """Remove a block relationship. Returns True if deleted."""
        result = (
            self._sb.table("blocked_users")
            .delete()
            .eq("blocker_id", blocker_id)
            .eq("blocked_id", blocked_id)
            .execute()
        )
        return len(result.data or []) > 0

    def get_blocked_ids(self, user_id: str) -> set[str]:
        """Get all user IDs blocked by this user."""
        result = (
            self._sb.table("blocked_users")
            .select("blocked_id")
            .eq("blocker_id", user_id)
            .execute()
        )
        return {r["blocked_id"] for r in (result.data or [])}

    def get_blocker_ids(self, user_id: str) -> set[str]:
        """Get all user IDs who have blocked this user."""
        result = (
            self._sb.table("blocked_users")
            .select("blocker_id")
            .eq("blocked_id", user_id)
            .execute()
        )
        return {r["blocker_id"] for r in (result.data or [])}

    def get_all_hidden_user_ids(self, user_id: str) -> set[str]:
        """Get all user IDs that should be hidden (blocked + blockers)."""
        return self.get_blocked_ids(user_id) | self.get_blocker_ids(user_id)

    def list_blocked(
        self,
        user_id: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[dict[str, Any]]:
        """Paginated list of blocked users with display names.

        Joins the users table via the blocked_id FK to include
        display_name and username for each blocked user.
        """
        fetch_limit = limit + 1
        query = (
            self._sb.table("blocked_users")
            .select(
                "id, blocked_id, created_at, "
                "blocked_user:users!blocked_users_blocked_id_fkey(display_name, username)"
            )
            .eq("blocker_id", user_id)
            .order("created_at", desc=True)
            .limit(fetch_limit)
        )
        if cursor:
            try:
                cursor_created_at, cursor_id = cursor.split("|", 1)
            except ValueError:
                raise ValueError(f"Malformed cursor: '{cursor}'")
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        return query.execute().data or []
