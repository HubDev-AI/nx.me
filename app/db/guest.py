"""Guest user management for anonymous / pre-login flows.

When FEATURE_AUTH_REQUIRED is false, mobile calls POST /v1/guest to create
an ephemeral user row (is_guest=true) and receive a guest session token.
Subsequent requests send the token via the X-Guest-Token header. The token
is validated server-side by looking up the matching users row.

The fixed dev guest (00000000-...-0001) remains for legacy DEV_FEATURE_FOCUS
flows; new per-session guests get random UUIDs and guest_session_tokens.
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from supabase import Client

from app.constants.tiers import TIER_ID_TRIAL

logger = logging.getLogger(__name__)

# 64-hex-character tokens (256 bits of entropy). Matches the shape already
# used by guest_session_token throughout the codebase.
_GUEST_TOKEN_BYTES = 32
_GUEST_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")


def _generate_guest_token() -> str:
    """Generate a 64-hex-character guest session token."""
    return secrets.token_hex(_GUEST_TOKEN_BYTES)


def is_valid_guest_token_format(token: str) -> bool:
    """Cheap format check so callers skip DB lookup for garbage tokens."""
    return bool(_GUEST_TOKEN_RE.match(token))


def create_guest_user(supabase: Client) -> tuple[UUID, str]:
    """Create an ephemeral guest user row and return (user_id, token).

    The user is inserted with:
      - is_guest=true
      - guest_session_token=<64-hex>
      - username="guest-<short-id>" (must be unique; collision-resistant)
      - display_name="Guest"
      - email=None (guest users have no email)

    Returns (user_id, guest_token). Caller stores the token in SecureStore
    and sends it via X-Guest-Token on subsequent requests.
    """
    user_id = uuid4()
    token = _generate_guest_token()
    # Short suffix keeps username readable while collision-resistant enough
    # for the pre-launch scale (~10^10 combos).
    username_suffix = secrets.token_hex(6)  # 12 hex chars

    now = datetime.now(tz=timezone.utc).isoformat()

    user_row = {
        "id": str(user_id),
        "username": f"guest-{username_suffix}",
        "display_name": "Guest",
        "is_guest": True,
        "guest_session_token": token,
        "email_verified": False,
        "tier_id": TIER_ID_TRIAL,  # guests start on the free trial tier
        "created_at": now,
        "updated_at": now,
    }
    supabase.table("users").insert(user_row).execute()
    logger.info("Created guest user %s", user_id)
    return user_id, token


def resolve_guest_by_token(supabase: Client, token: str) -> UUID | None:
    """Look up the guest user_id for a given guest_session_token.

    Returns None if the token is not found or the matching user is not a
    guest (defensive — we only accept tokens for actual guest rows).
    """
    result = (
        supabase.table("users")
        .select("id, is_guest")
        .eq("guest_session_token", token)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        return None
    if not result.data.get("is_guest"):
        return None
    return UUID(result.data["id"])
