"""Chat-seeds service — Haiku-backed, Redis-cached, single-flight-locked.

Plan 2026-04-20-001 Unit 5.

Generates 3 conversation-starter seeds (label + text) for the composer
pre-fill UX.  Seeds are grounded on the user's latest completed glow-up
image via the same MCP image-fetch path used by the nudge scheduler.

Flow:
  1. No completed glow-up → return FALLBACK_SEEDS immediately.
  2. Cache hit → return cached seeds.
  3. Cooldown active (previous call within COOLDOWN_SECONDS) → fallback.
  4. Acquire lock (single-flight). Not acquired → sleep + re-check cache;
     still nothing → fallback.
  5. Lock acquired → set cooldown FIRST (prevents replay storm on parse
     failure), fetch images, call Haiku, validate, cache result.
  6. Any Redis hiccup / exception at any step → log + return fallback.
     Must not raise.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.advisor._json_utils import strip_json_code_fence
from app.advisor.chat_seed_fallback import FALLBACK_SEEDS
from app.advisor.chat_seed_prompt import build_chat_seeds_prompt
from app.advisor.models import ChatSeed, ChatSeedsResponse
from app.advisor.mcp.context import McpContext
from app.advisor.mcp.tools_glowup import _handle_get_latest_glowup
from app.advisor.mcp.tools_makeup import handle as _handle_get_latest_makeup
from app.advisor.payload_logger import log_llm_response
from app.advisor.persona import SOUL_MD
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.advisor_repo import AdvisorRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants — no magic strings/numbers
# ---------------------------------------------------------------------------

CACHE_KEY_FMT = "advisor:chat_seeds:{user_id}:{glowup_id}"
COOLDOWN_KEY_FMT = "advisor:chat_seeds:cooldown:{user_id}"
LOCK_KEY_FMT = "advisor:chat_seeds:lock:{user_id}:{glowup_id}"

COOLDOWN_VALUE = "1"
LOCK_VALUE = "1"

# Anthropic content-block type constants (mirrors nudge_scheduler).
_CONTENT_BLOCK_TYPE_IMAGE = "image"
_CONTENT_BLOCK_TYPE_TEXT = "text"

# Length caps (must match prompt output contract and test assertions).
LABEL_MAX = 24
TEXT_MAX = 140
SEEDS_COUNT = 3

# Max tokens for the Haiku seeds call.  Seeds are short structured JSON —
# 3 × (≤24 + ≤140) comfortably fits in 256 tokens with JSON overhead.
MAX_TOKENS_CHAT_SEEDS = 256

# Time to wait before re-checking cache when lock is held by another
# coroutine. The product of _LOCK_WAIT_SECONDS * _LOCK_WAIT_MAX_ATTEMPTS
# should comfortably cover typical Haiku latency (~2-3 s).
_LOCK_WAIT_SECONDS = 0.25
# Max attempts to poll the cache while another coroutine holds the lock.
# Bounded so a stuck holder cannot make the waiter block forever — after
# _LOCK_WAIT_MAX_ATTEMPTS misses the waiter gives up and returns fallback.
_LOCK_WAIT_MAX_ATTEMPTS = 20


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fallback() -> ChatSeedsResponse:
    """Return the static fallback response."""
    return ChatSeedsResponse(seeds=[ChatSeed(**s) for s in FALLBACK_SEEDS])


async def _fetch_vision_blocks(
    mcp_ctx: McpContext,
    source_type: str,
) -> list[dict[str, Any]]:
    """Fetch image blocks via the appropriate MCP handler.

    Dispatches to ``get_latest_makeup`` for makeup sessions, falls back
    to ``get_latest_glowup`` for all other source types.
    """
    if source_type == "makeup_session":
        payload = await _handle_get_latest_makeup(mcp_ctx)
    else:
        payload = await _handle_get_latest_glowup(mcp_ctx)
    inner = payload.get("content")
    blocks = inner if isinstance(inner, list) else []
    return [b for b in blocks if b.get("type") == _CONTENT_BLOCK_TYPE_IMAGE]


def _parse_seeds_json(raw: str) -> list[dict] | None:
    """Parse and validate the Haiku seeds JSON response.

    Returns a list of exactly SEEDS_COUNT dicts on success, None on any
    failure.  Validation:
      - Valid JSON after stripping code-fence.
      - Top-level key ``seeds`` is a list of exactly SEEDS_COUNT items.
      - Each item has ``label`` (str, ≤LABEL_MAX chars) and ``text``
        (str, ≤TEXT_MAX chars, ends with '?').
    """
    try:
        data = json.loads(strip_json_code_fence(raw))
    except (TypeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    seeds = data.get("seeds")
    if not isinstance(seeds, list) or len(seeds) != SEEDS_COUNT:
        return None

    validated: list[dict] = []
    for item in seeds:
        if not isinstance(item, dict):
            return None
        label = item.get("label")
        text = item.get("text")
        if not isinstance(label, str) or not label.strip():
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        label = label.strip()
        text = text.strip()
        if len(label) > LABEL_MAX or len(text) > TEXT_MAX:
            return None
        if not text.endswith("?"):
            return None
        validated.append({"label": label, "text": text})

    return validated


# ---------------------------------------------------------------------------
# Public service function
# ---------------------------------------------------------------------------


async def build_chat_seeds(
    user_id: str,
    supabase: Client,
    redis: aioredis.Redis,
    llm: Any,
) -> ChatSeedsResponse:
    """Generate (or serve cached) chat seeds for ``user_id``.

    Plan 2026-04-20-001 Unit 5.  See module docstring for the full flow.
    Never raises — any unhandled exception returns the fallback.
    """
    advisor_repo = AdvisorRepository(supabase)

    # ------------------------------------------------------------------
    # Step 1: no completed generation (glowup OR makeup) → fallback.
    # Use the polymorphic repo method to pick the most recent completed
    # job across both source_types (completed_at DESC, id DESC tie-break).
    # ------------------------------------------------------------------
    try:
        anchor_row = await run_sync(
            advisor_repo.get_latest_completed_job_with_images, user_id
        )
    except Exception:
        logger.warning(
            "chat_seeds: failed to resolve anchor job for user=%s — returning fallback",
            user_id,
            exc_info=True,
        )
        return _fallback()

    if anchor_row is None:
        logger.debug(
            "chat_seeds: no completed generation for user=%s — fallback", user_id
        )
        return _fallback()

    anchor_id = str(anchor_row.get("id") or "")
    anchor_source_type = str(anchor_row.get("source_type") or "glowup_analysis")

    cache_key = CACHE_KEY_FMT.format(user_id=user_id, glowup_id=anchor_id)
    cooldown_key = COOLDOWN_KEY_FMT.format(user_id=user_id)
    lock_key = LOCK_KEY_FMT.format(user_id=user_id, glowup_id=anchor_id)

    # ------------------------------------------------------------------
    # Step 2: cache hit
    # ------------------------------------------------------------------
    try:
        cached = await redis.get(cache_key)
    except Exception:
        logger.warning(
            "chat_seeds: redis.get(cache) failed — continuing", exc_info=True
        )
        cached = None

    if cached is not None:
        try:
            seeds_data = json.loads(cached)
            return ChatSeedsResponse(seeds=[ChatSeed(**s) for s in seeds_data])
        except Exception:
            logger.warning("chat_seeds: cache parse failed — continuing", exc_info=True)

    # ------------------------------------------------------------------
    # Step 3: cooldown active → fallback
    # ------------------------------------------------------------------
    try:
        cooldown_active = await redis.get(cooldown_key)
    except Exception:
        logger.warning(
            "chat_seeds: redis.get(cooldown) failed — continuing", exc_info=True
        )
        cooldown_active = None

    if cooldown_active is not None:
        # Cooldown alone does NOT guarantee a parse failure — a concurrent
        # single-flight holder sets the cooldown BEFORE calling Haiku, so
        # a waiter that reaches Step 3 between the holder's cooldown SET
        # and cache SET would incorrectly fall back. Poll the cache first
        # so the second caller reliably picks up the freshly-cached seeds.
        for _attempt in range(_LOCK_WAIT_MAX_ATTEMPTS):
            try:
                cached_during_cooldown = await redis.get(cache_key)
            except Exception:
                cached_during_cooldown = None
            if cached_during_cooldown is not None:
                try:
                    seeds_data = json.loads(cached_during_cooldown)
                    return ChatSeedsResponse(seeds=[ChatSeed(**s) for s in seeds_data])
                except Exception:
                    break
            await asyncio.sleep(_LOCK_WAIT_SECONDS)
        logger.debug("chat_seeds: cooldown active for user=%s — fallback", user_id)
        return _fallback()

    # ------------------------------------------------------------------
    # Step 4: attempt lock (single-flight)
    # ------------------------------------------------------------------
    lock_acquired = False
    try:
        lock_acquired = await redis.set(
            lock_key,
            LOCK_VALUE,
            nx=True,
            ex=settings.ADVISOR_CHAT_SEEDS_LOCK_TTL_SECONDS,
        )
    except Exception:
        logger.warning("chat_seeds: redis.set(lock) failed — continuing", exc_info=True)

    if not lock_acquired:
        # Another coroutine is generating. Poll the cache up to
        # _LOCK_WAIT_MAX_ATTEMPTS times so the second caller reliably
        # picks up the fresh seeds rather than falling back to the static
        # list while the first caller is still mid-Haiku.
        for _attempt in range(_LOCK_WAIT_MAX_ATTEMPTS):
            await asyncio.sleep(_LOCK_WAIT_SECONDS)
            try:
                cached_after_wait = await redis.get(cache_key)
            except Exception:
                cached_after_wait = None
            if cached_after_wait is None:
                continue
            try:
                seeds_data = json.loads(cached_after_wait)
                return ChatSeedsResponse(seeds=[ChatSeed(**s) for s in seeds_data])
            except Exception:
                # Cache parse failed — treat as unrecoverable for the
                # waiter; the holder already owns retry semantics.
                break
        return _fallback()

    # Lock acquired — run Haiku generation.
    try:
        return await _generate_seeds(
            user_id=user_id,
            anchor_id=anchor_id,
            anchor_source_type=anchor_source_type,
            supabase=supabase,
            redis=redis,
            llm=llm,
            advisor_repo=advisor_repo,
            cache_key=cache_key,
            cooldown_key=cooldown_key,
            lock_key=lock_key,
        )
    except Exception:
        logger.error(
            "chat_seeds: unexpected error in _generate_seeds for user=%s",
            user_id,
            exc_info=True,
        )
        # Release lock on unexpected failure.
        await _release_lock(redis, lock_key)
        return _fallback()


async def _generate_seeds(
    *,
    user_id: str,
    anchor_id: str,
    anchor_source_type: str,
    supabase: Client,
    redis: aioredis.Redis,
    llm: Any,
    advisor_repo: AdvisorRepository,
    cache_key: str,
    cooldown_key: str,
    lock_key: str,
) -> ChatSeedsResponse:
    """Inner generation path — called only when the lock is held.

    Sets cooldown FIRST, then fetches images + calls Haiku + validates.
    On success: cache result + release lock + return.
    On parse failure: cooldown stays set, cache not written, lock released,
    fallback returned.
    """
    # ------------------------------------------------------------------
    # Step 5: set cooldown BEFORE calling Haiku (prevents replay storm on
    # parse failure)
    # ------------------------------------------------------------------
    try:
        await redis.set(
            cooldown_key,
            COOLDOWN_VALUE,
            ex=settings.ADVISOR_CHAT_SEEDS_COOLDOWN_SECONDS,
        )
    except Exception:
        logger.warning(
            "chat_seeds: failed to set cooldown key — continuing", exc_info=True
        )

    # ------------------------------------------------------------------
    # Step 6: fetch image blocks via MCP handler
    # ------------------------------------------------------------------
    mcp_ctx = McpContext(
        user_id=UUID(user_id),
        supabase=supabase,
        advisor_repo=advisor_repo,
        logger=logger,
    )
    try:
        image_blocks = await _fetch_vision_blocks(mcp_ctx, anchor_source_type)
    except Exception:
        logger.warning(
            "chat_seeds: image fetch failed for user=%s — fallback",
            user_id,
            exc_info=True,
        )
        await _release_lock(redis, lock_key)
        return _fallback()

    if not image_blocks:
        logger.debug("chat_seeds: no image blocks for user=%s — fallback", user_id)
        await _release_lock(redis, lock_key)
        return _fallback()

    # ------------------------------------------------------------------
    # Step 7: fetch style_profile
    # ------------------------------------------------------------------
    try:
        profile_row = await run_sync(advisor_repo.get_style_profile, user_id)
        profile_content = (profile_row or {}).get("content") or None
    except Exception:
        logger.warning(
            "chat_seeds: failed to fetch style_profile for user=%s — continuing",
            user_id,
            exc_info=True,
        )
        profile_content = None

    # ------------------------------------------------------------------
    # Step 8: build prompt
    # ------------------------------------------------------------------
    prompt = build_chat_seeds_prompt(profile_content)

    # ------------------------------------------------------------------
    # Step 9: Haiku call
    # ------------------------------------------------------------------
    user_content: list[dict[str, Any]] = [
        {"type": _CONTENT_BLOCK_TYPE_TEXT, "text": prompt},
        *image_blocks,
    ]
    try:
        response = await llm.create_message(
            model=settings.ADVISOR_MODEL_HAIKU,
            system=SOUL_MD,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=MAX_TOKENS_CHAT_SEEDS,
        )
        log_llm_response(
            None,
            model=settings.ADVISOR_MODEL_HAIKU,
            user_id=user_id,
            conversation_id="-",
            response=response,
            purpose="chat_seeds",
        )
        raw = response.content.strip()
    except Exception:
        logger.error(
            "chat_seeds: Haiku call failed for user=%s", user_id, exc_info=True
        )
        await _release_lock(redis, lock_key)
        return _fallback()

    # ------------------------------------------------------------------
    # Step 10: parse + validate
    # ------------------------------------------------------------------
    validated = _parse_seeds_json(raw)
    if validated is None:
        logger.warning(
            "chat_seeds: parse failure for user=%s — fallback (cooldown set, cache not written)",
            user_id,
        )
        await _release_lock(redis, lock_key)
        return _fallback()

    # ------------------------------------------------------------------
    # Step 11: cache result + release lock
    # ------------------------------------------------------------------
    try:
        json_dump = json.dumps(validated)
        await redis.set(
            cache_key,
            json_dump,
            ex=settings.ADVISOR_CHAT_SEEDS_CACHE_TTL_SECONDS,
        )
    except Exception:
        logger.warning("chat_seeds: failed to write cache — continuing", exc_info=True)

    await _release_lock(redis, lock_key)

    return ChatSeedsResponse(seeds=[ChatSeed(**s) for s in validated])


async def _release_lock(redis: aioredis.Redis, lock_key: str) -> None:
    """Release the single-flight lock; errors are logged and suppressed.

    The lock already has a short TTL (``ADVISOR_CHAT_SEEDS_LOCK_TTL_SECONDS``)
    so failing to delete here only delays the next generation attempt by that
    TTL — never stalls it permanently.  Intentionally awaited (not fire-and-
    forget) so tests can assert lock state without pytest-asyncio teardown
    races.
    """
    try:
        await redis.delete(lock_key)
    except Exception:
        logger.debug(
            "chat_seeds: lock release failed for key=%s", lock_key, exc_info=True
        )
