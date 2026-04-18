"""User repository — all supabase.table('users') and auth.admin queries in one place.

Follows the same pattern as TierRepository: constructor takes a Client,
methods are synchronous (callers use run_sync for async handlers).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import Client

from app.api.auth_helpers import normalize_username

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

    def check_username_availability(
        self, username: str, exclude_user_id: str | None = None
    ) -> dict:
        """Return { available: bool, reason?: str }.

        Checks (in order): active users, then active username_reservations.
        Normalizes via NFKC + ASCII-fold so homographs collide.
        """
        normalized = normalize_username(username)

        users_result = (
            self._sb.table("users")
            .select("id, username")
            .ilike("username", normalized)
            .execute()
        )
        for row in users_result.data or []:
            if exclude_user_id and row["id"] == exclude_user_id:
                continue
            return {"available": False, "reason": "taken"}

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        reservations_result = (
            self._sb.table("username_reservations")
            .select("username, reserved_until")
            .eq("username", normalized)
            .gt("reserved_until", now_iso)
            .execute()
        )
        if reservations_result.data:
            return {"available": False, "reason": "reserved"}

        return {"available": True}

    # Post-normalization, the old case-insensitive-only method is equivalent.
    # Keep the name as a thin alias so existing call sites don't break.
    check_username_available_ci = check_username_availability

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
        self._sb.table("users").update(
            {
                "username": new_username,
                "username_changed_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        ).eq("id", user_id).execute()

    def insert_username_reservation(
        self, username: str, reserved_until: datetime
    ) -> None:
        """UPSERT a normalized reservation row, extending the window on conflict.

        Stores the username already-normalized (NFKC + ASCII-fold lowercase).
        The DB CHECK constraint enforces lowercase at the storage layer.
        """
        (
            self._sb.table("username_reservations")
            .upsert(
                {
                    "username": normalize_username(username),
                    "reserved_until": reserved_until.isoformat(),
                },
                on_conflict="username",
            )
            .execute()
        )

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
