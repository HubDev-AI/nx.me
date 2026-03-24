"""TikTok Login Kit v2 — server-side auth code exchange and user info retrieval.

Flow (native SDK):
1. Mobile app uses react-native-tiktok to authenticate with TikTok natively.
2. TikTok SDK returns an authorization code to the app.
3. Mobile sends the auth_code to POST /auth/tiktok-login.
4. This module exchanges the code for an access_token and fetches the user profile.

Refs:
- https://developers.tiktok.com/doc/login-kit-manage-user-access-tokens/
- https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info/
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
_TIKTOK_USER_INFO_FIELDS = "open_id,display_name,avatar_url"

_HTTPX_TIMEOUT = settings.TIKTOK_HTTPX_TIMEOUT_SECONDS


class TikTokAuthError(Exception):
    """Raised when TikTok API returns an error or unexpected response."""


@dataclass(frozen=True, slots=True)
class TikTokUserInfo:
    open_id: str
    display_name: str
    avatar_url: str


async def authenticate(
    code: str,
    code_verifier: str | None = None,
) -> tuple[str, TikTokUserInfo]:
    """Exchange auth code for access_token and fetch user profile in one call.

    Uses a single httpx client for connection reuse across both TikTok API calls.

    Returns (open_id, TikTokUserInfo).
    """
    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as client:
        access_token, open_id = await _exchange_code(client, code, code_verifier)
        user_info = await _fetch_user_info(client, access_token)
    return open_id, user_info


async def _exchange_code(
    client: httpx.AsyncClient,
    code: str,
    code_verifier: str | None,
) -> tuple[str, str]:
    """Exchange a native SDK authorization code for an access_token.

    Returns (access_token, open_id).
    """
    payload: dict[str, str] = {
        "client_key": settings.TIKTOK_CLIENT_KEY,
        "client_secret": settings.TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier

    resp = await client.post(TIKTOK_TOKEN_URL, data=payload)

    if resp.status_code != 200:
        logger.error("TikTok token exchange HTTP %s: %s", resp.status_code, resp.text)
        raise TikTokAuthError(f"Token exchange failed (HTTP {resp.status_code})")

    body = resp.json()

    # TikTok v2 API wraps the payload in a "data" key when successful.
    data = body if "access_token" in body else body.get("data", {})
    access_token = data.get("access_token")
    open_id = data.get("open_id")

    if not access_token or not open_id:
        error_desc = body.get("error_description") or body.get("message", "unknown")
        logger.error("TikTok token exchange missing fields: %s", body)
        raise TikTokAuthError(f"Token exchange error: {error_desc}")

    return access_token, open_id


async def _fetch_user_info(
    client: httpx.AsyncClient,
    access_token: str,
) -> TikTokUserInfo:
    """Fetch the user's basic profile from TikTok."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"fields": _TIKTOK_USER_INFO_FIELDS}

    resp = await client.get(TIKTOK_USER_INFO_URL, headers=headers, params=params)

    if resp.status_code != 200:
        logger.error("TikTok user info HTTP %s: %s", resp.status_code, resp.text)
        raise TikTokAuthError(f"User info request failed (HTTP {resp.status_code})")

    body = resp.json()
    user_data = body.get("data", {}).get("user", {})

    if not user_data.get("open_id"):
        logger.error("TikTok user info missing open_id: %s", body)
        raise TikTokAuthError("No open_id in user info response")

    return TikTokUserInfo(
        open_id=user_data["open_id"],
        display_name=user_data.get("display_name", ""),
        avatar_url=user_data.get("avatar_url", ""),
    )
