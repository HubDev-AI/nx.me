"""User repository — all supabase.table('users') and auth.admin queries in one place.

Follows the same pattern as TierRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging
from datetime import datetime

from supabase import Client

logger = logging.getLogger(__name__)


class UserRepository:
    """Encapsulates all DB and auth.admin calls related to the users table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ------------------------------------------------------------------
    # Read — users table
    # ------------------------------------------------------------------

    def get_profile_by_id(self, user_id: str) -> dict | None:
        """Fetch core profile fields for the authenticated user, or None if not found.

        ``face_mod_consent_at`` is included so the /users/me endpoint can
        hand the mobile ConsentProvider a source-of-truth value on boot —
        without it the client starts from ``hasConsent=null`` and silently
        lies its way into a 428 on the analyze call.
        """
        result = (
            self._sb.table("users")
            .select(
                "id, username, display_name, email, avatar_storage_key, "
                "username_changed_at, face_mod_consent_at"
            )
            .eq("id", user_id)
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def get_by_username(self, username: str) -> dict | None:
        """Fetch a non-deleted user by username, or None if not found."""
        result = (
            self._sb.table("users")
            .select(
                "id, username, display_name, avatar_storage_key, created_at, username_changed_at"
            )
            .eq("username", username)
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    def check_username_availability(self, username: str) -> dict | None:
        """Return the row (including deleted_at / username_reserved_until) if username exists, else None."""
        result = (
            self._sb.table("users")
            .select("id, deleted_at, username_reserved_until")
            .eq("username", username)
            .execute()
        )
        return result.data[0] if result.data else None

    def check_username_taken(
        self, username: str, exclude_user_id: str | None = None
    ) -> dict | None:
        """Return the row if username is taken by an active user other than exclude_user_id, else None."""
        result = (
            self._sb.table("users")
            .select("id")
            .eq("username", username)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        if exclude_user_id and result.data["id"] == exclude_user_id:
            return None
        return result.data

    def check_username_available_ci(
        self, username: str, exclude_user_id: str | None = None
    ) -> dict:
        """Check if a username is available (case-insensitive).

        Returns { available: bool, reason?: str }.
        Checks: active users, reserved usernames (deleted accounts within reservation window).
        """
        from datetime import timezone

        result = (
            self._sb.table("users")
            .select("id, deleted_at, username_reserved_until")
            .ilike("username", username)
            .execute()
        )

        if not result.data:
            return {"available": True}

        for row in result.data:
            if row.get("deleted_at") is None:
                if exclude_user_id and row["id"] == exclude_user_id:
                    continue
                return {"available": False, "reason": "taken"}

            reserved_until_str = row.get("username_reserved_until")
            if reserved_until_str:
                reserved_until = datetime.fromisoformat(reserved_until_str)
                if reserved_until.tzinfo is None:
                    reserved_until = reserved_until.replace(tzinfo=timezone.utc)
                if reserved_until > datetime.now(tz=timezone.utc):
                    return {"available": False, "reason": "reserved"}

        return {"available": True}

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

    def get_user_post_stats(self, user_id: str) -> dict:
        """Call the user_post_stats RPC to get post_count and total_reactions.

        Returns a dict with post_count and total_reactions (both default to 0).
        """
        result = self._sb.rpc("user_post_stats", {"p_user_id": user_id}).execute()
        rows = result.data or [{}]
        return rows[0] if rows else {}

    def get_by_username_for_card(self, username: str) -> dict | None:
        """Fetch user fields needed by the shareable card endpoint (includes deleted_at)."""
        result = (
            self._sb.table("users")
            .select("id, username, display_name, deleted_at")
            .eq("username", username)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data

    # ------------------------------------------------------------------
    # Write — users table
    # ------------------------------------------------------------------

    def insert(self, user_row: dict) -> None:
        """Insert a new user row."""
        self._sb.table("users").insert(user_row).execute()

    def upsert(
        self, user_row: dict, on_conflict: str = "id", ignore_duplicates: bool = False
    ) -> None:
        """Upsert a user row."""
        self._sb.table("users").upsert(
            user_row,
            on_conflict=on_conflict,
            ignore_duplicates=ignore_duplicates,
        ).execute()

    def set_email_verified(self, user_id: str) -> None:
        """Mark a user's email as verified."""
        self._sb.table("users").update({"email_verified": True}).eq(
            "id", user_id
        ).execute()

    def update_profile(self, user_id: str, updates: dict) -> None:
        """Apply arbitrary field updates to a user row."""
        self._sb.table("users").update(updates).eq("id", user_id).execute()

    def update_username(self, user_id: str, new_username: str) -> None:
        """Update username and set username_changed_at atomically."""
        from datetime import timezone

        self._sb.table("users").update(
            {
                "username": new_username,
                "username_changed_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ).eq("id", user_id).execute()

    def soft_delete(
        self, user_id: str, now_utc: datetime, reserved_until: datetime
    ) -> list[dict]:
        """Soft-delete a user row; returns the updated rows (empty if already deleted).

        Atomicity note (M-12): both ``deleted_at`` and ``username_reserved_until``
        are set in a single ``.update()`` call, so they are applied in the same
        database statement — no transaction wrapper needed.  The ``is_("deleted_at", "null")``
        guard ensures idempotency (a concurrent call sees zero rows).
        """
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
        """Create a Supabase auth user with auto-confirmed email.

        Using email_confirm=True so the user can sign in immediately
        after registration without needing to click a magic link
        (which doesn't work for mobile apps).
        """
        return self._sb.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
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

    # ------------------------------------------------------------------
    # TikTok identity lookup
    # ------------------------------------------------------------------

    def find_by_tiktok_open_id(self, open_id: str) -> dict | None:
        """Find a non-deleted user by their TikTok open_id, or None."""
        result = (
            self._sb.table("users")
            .select("id, username, display_name, email")
            .eq("tiktok_open_id", open_id)
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        return result.data
