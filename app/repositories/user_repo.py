"""User repository — all supabase.table('users') and auth.admin queries in one place.

Follows the same pattern as TierRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

logger = logging.getLogger(__name__)


class UserRepository:
    """Encapsulates all DB and auth.admin calls related to the users table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Read — users table
    # ------------------------------------------------------------------

    def get_by_username(self, username: str) -> dict | None:
        """Fetch a non-deleted user by username, or None if not found."""
        result = (
            self._sb.table("users")
            .select("id, username, display_name, avatar_storage_key, created_at")
            .eq("username", username)
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        return result.data or None

    def check_username_availability(self, username: str) -> dict | None:
        """Return the row (including deleted_at / username_reserved_until) if username exists, else None."""
        result = (
            self._sb.table("users")
            .select("id, deleted_at, username_reserved_until")
            .eq("username", username)
            .execute()
        )
        return result.data[0] if result.data else None

    def check_username_taken(self, username: str, exclude_user_id: str | None = None) -> dict | None:
        """Return the row if username is taken by an active user other than exclude_user_id, else None."""
        result = (
            self._sb.table("users")
            .select("id")
            .eq("username", username)
            .maybe_single()
            .execute()
        )
        if not result.data:
            return None
        if exclude_user_id and result.data["id"] == exclude_user_id:
            return None
        return result.data

    def get_trial_analyses_remaining(self, user_id: str) -> int:
        """Return trial_analyses_remaining for the given user (0 if not found)."""
        result = (
            self._sb.table("users")
            .select("trial_analyses_remaining")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return result.data["trial_analyses_remaining"] if result.data else 0

    def get_by_username_for_card(self, username: str) -> dict | None:
        """Fetch user fields needed by the shareable card endpoint (includes deleted_at)."""
        result = (
            self._sb.table("users")
            .select("id, username, display_name, deleted_at")
            .eq("username", username)
            .maybe_single()
            .execute()
        )
        return result.data or None

    # ------------------------------------------------------------------
    # Write — users table
    # ------------------------------------------------------------------

    def insert(self, user_row: dict) -> None:
        """Insert a new user row."""
        self._sb.table("users").insert(user_row).execute()

    def upsert(self, user_row: dict, on_conflict: str = "id", ignore_duplicates: bool = False) -> None:
        """Upsert a user row."""
        self._sb.table("users").upsert(
            user_row,
            on_conflict=on_conflict,
            ignore_duplicates=ignore_duplicates,
        ).execute()

    def set_email_verified(self, user_id: str) -> None:
        """Mark a user's email as verified."""
        self._sb.table("users").update({"email_verified": True}).eq("id", user_id).execute()

    def update_profile(self, user_id: str, updates: dict) -> None:
        """Apply arbitrary field updates to a user row."""
        self._sb.table("users").update(updates).eq("id", user_id).execute()

    def soft_delete(self, user_id: str, now_utc: datetime, reserved_until: datetime) -> list[dict]:
        """Soft-delete a user row; returns the updated rows (empty if already deleted)."""
        result = (
            self._sb.table("users")
            .update(
                {
                    "deleted_at": now_utc.isoformat(),
                    "username_reserved_until": reserved_until.isoformat(),
                }
            )
            .eq("id", user_id)
            .is_("deleted_at", "null")
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # credit_reservations table (used during account deletion)
    # ------------------------------------------------------------------

    def get_active_reservations(self, user_id: str) -> list[dict]:
        """Return all active (status='reserved') credit reservations for a user."""
        result = (
            self._sb.table("credit_reservations")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "reserved")
            .execute()
        )
        return result.data or []

    # ------------------------------------------------------------------
    # auth.admin calls
    # ------------------------------------------------------------------

    def auth_create_user(self, email: str, password: str) -> object:
        """Create a Supabase auth user. Returns the auth API response."""
        return self._sb.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": False,
            }
        )

    def auth_delete_user(self, user_id: str) -> None:
        """Delete a Supabase auth user."""
        self._sb.auth.admin.delete_user(user_id)

    def auth_get_user(self, user_id: str) -> object:
        """Fetch a Supabase auth user by ID. Returns the auth API response."""
        return self._sb.auth.admin.get_user_by_id(user_id)

    def auth_sign_out(self, token: str) -> None:
        """Invalidate a session token server-side."""
        self._sb.auth.admin.sign_out(token)
