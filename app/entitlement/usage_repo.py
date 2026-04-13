"""Usage repository — rolling-window usage event queries.

A-5: usage_events table tracks all generation/nudge actions.
Used by EntitlementService to check time-window tier limits (daily/weekly/monthly).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)


class UsageRepository:
    """Query usage_events for rolling-window limit enforcement."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def count_in_window(self, user_id: UUID, action: str, window_seconds: int) -> int:
        """Count committed usage events for a user/action within a time window.

        Args:
            user_id: User UUID.
            action: Action type (e.g., 'generation', 'advisor_nudge').
            window_seconds: Rolling window in seconds (e.g., 86400 for daily).

        Returns:
            Number of committed events in the window.
        """
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()

        result = (
            self._sb.table("usage_events")
            .select("id", count="exact")
            .eq("user_id", str(user_id))
            .eq("action", action)
            .eq("status", "committed")
            .gte("created_at", cutoff)
            .execute()
        )

        return result.count if result.count is not None else 0

    def count_total(self, user_id: UUID, action: str) -> int:
        """Count all committed usage events for a user/action (lifetime)."""
        result = (
            self._sb.table("usage_events")
            .select("id", count="exact")
            .eq("user_id", str(user_id))
            .eq("action", action)
            .eq("status", "committed")
            .execute()
        )

        return result.count if result.count is not None else 0

    def earliest_in_window(
        self, user_id: UUID, action: str, window_seconds: int
    ) -> datetime | None:
        """Get the earliest committed event's created_at within a time window.

        Returns None if no events exist in the window.
        """
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=window_seconds)
        ).isoformat()

        result = (
            self._sb.table("usage_events")
            .select("created_at")
            .eq("user_id", str(user_id))
            .eq("action", action)
            .eq("status", "committed")
            .gte("created_at", cutoff)
            .order("created_at")
            .limit(1)
            .execute()
        )

        if result.data and result.data[0].get("created_at"):
            ts = datetime.fromisoformat(result.data[0]["created_at"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
        return None
