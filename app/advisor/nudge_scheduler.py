"""Nudge scheduler — thin orchestrator for advisor-initiated nudges.

Plan 2026-04-17-003 Unit 2: removed generic trigger functions and
eligibility cron. Only post_glowup vision-grounded path remains.

Plan 2026-04-20-001 Unit 3: simplified generate_nudge signature to
(ctx, user_id, job_id); rewrote parser for three-field contract
{body, next_step.{label, seed}}; added body_hash dedup.

Jobs:
  generate_nudge           — generate + save a single nudge via Haiku
  write_analysis_insight_job — persist analysis insight memory row
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.advisor._hashing import hash_user_id
from app.advisor._json_utils import strip_json_code_fence
from app.advisor.mcp.context import McpContext
from app.advisor.mcp.tools_glowup import _handle_get_latest_glowup
from app.advisor.mcp.tools_makeup import handle as _handle_get_latest_makeup
from app.advisor.payload_logger import log_llm_response
from app.advisor.persona import SOUL_MD
from app.db.async_helpers import run_sync
from app.repositories.advisor_repo import AdvisorRepository
from app.advisor.nudge_policy import MAX_TOKENS_NUDGE
from app.advisor.nudge_templates import build_vision_nudge_prompt
from app.api.deps import get_llm_adapter as _get_llm_adapter
from app.config import settings

logger = logging.getLogger(__name__)

# Anthropic content-block types — re-declared locally so this module has
# no structural dependency on registry / tool internals beyond the
# handler functions themselves.
CONTENT_BLOCK_TYPE_IMAGE = "image"
CONTENT_BLOCK_TYPE_TEXT = "text"

# Metric keys for observability (match memory_manager + service patterns).
METRIC_NUDGE_INVALID_JSON = "advisor.nudge_invalid_json"
METRIC_NUDGE_RAPID_RETRY_DEDUP = "advisor.nudge_rapid_retry_dedup"
METRIC_NUDGE_NO_PROFILE = "advisor.nudge_no_profile"
METRIC_NUDGE_PARSE_DROP = "advisor.nudge_parse_drop"
METRIC_NUDGE_DUPLICATE_BODY = "advisor.nudge_duplicate_body"

# Redis key template for the post_glowup rapid-retry dedup guard.
# Using a SETNX with a TTL keyed by (user_id, upload_id) — no schema
# creep on advisor_nudges.
_RAPID_RETRY_KEY_FMT = "advisor:nudge:post_glowup:{user_id}:{upload_id}"
_MAKEUP_THROTTLE_KEY_FMT = "advisor:nudge:post_makeup:{user_id}"
_RAPID_RETRY_VALUE = "1"
_SECONDS_PER_MINUTE = 60
_SECONDS_PER_DAY = 86_400

# Body dedup lookback window: drop nudges whose body_hash was seen within
# this many days to prevent repeating identical observations.
_BODY_DEDUP_DAYS = 30

# Schema length caps — mirror the VARCHAR(160)/(24)/(140) constraints added
# in migration 0062 and the advisor_nudges.body_hash column. Kept here so
# the JSON-parse validation and the DB constraint share a single source of
# truth (project rule: no magic numbers).
_NUDGE_BODY_MAX_LEN = 160
_NUDGE_NEXT_STEP_LABEL_MAX_LEN = 24
_NUDGE_NEXT_STEP_SEED_MAX_LEN = 140


# ---------------------------------------------------------------------------
# ARQ job: generate_nudge
# ---------------------------------------------------------------------------


async def generate_nudge(
    ctx: dict,
    user_id: str,
    job_id: str | None = None,
) -> None:
    """Generate and save a single nudge for a user.

    Plan 2026-04-20-001 Unit 3: simplified signature — trigger and insight
    args removed. Always runs the post_glowup vision-grounded path.

    Args:
        ctx:     ARQ worker context (supabase, redis injected at startup).
        user_id: UUID string of the target user.
        job_id:  Source job_id for the glow-up — used to resolve the
                 ``upload_id`` for rapid-retry dedup.
    """
    if not settings.ADVISOR_ENABLED:
        logger.debug(
            "Advisor disabled — skipping nudge for user=%s", hash_user_id(user_id)
        )
        return

    supabase: Client = ctx["supabase"]
    redis: aioredis.Redis = ctx["redis"]
    advisor_repo = AdvisorRepository(supabase)

    await _generate_vision_nudge(
        advisor_repo=advisor_repo,
        redis=redis,
        supabase=supabase,
        user_id=user_id,
        job_id=job_id,
    )


async def _generate_vision_nudge(
    *,
    advisor_repo: AdvisorRepository,
    redis: aioredis.Redis,
    supabase: Client,
    user_id: str,
    job_id: str | None,
) -> None:
    """Vision-grounded nudge flow (Plan 2026-04-20-001 Unit 3).

    1. Skip if no ``style_profile`` (no stable facts → no prompt).
    2. Rapid-retry dedup: if a second post_glowup for the same
       user+upload fires within ``ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES``,
       skip the second run.
    3. Fetch images via ``_handle_get_latest_glowup``.
    4. Build ``build_vision_nudge_prompt(profile, recent_nudges)``
       text, attach image blocks, call Haiku.
    5. Parse strict JSON ``{"body", "next_step": {"label", "seed"}}``.
       Validate lengths and seed-ends-with-? invariant. Drop on failure.
    6. Compute body_hash; drop if duplicate within 30 days.
    7. Insert nudge row with new three-field shape.
    """
    user_id_hash = hash_user_id(user_id)
    profile_row = await run_sync(advisor_repo.get_style_profile, user_id)
    profile_content = (profile_row or {}).get("content") or None
    if not profile_content:
        logger.info(
            "Vision nudge skipped — no style_profile for user=%s",
            user_id_hash,
            extra={"metric": METRIC_NUDGE_NO_PROFILE, "user_id_hash": user_id_hash},
        )
        return

    # Rapid-retry dedup
    if job_id:
        upload_id = await run_sync(_resolve_upload_id_for_job, supabase, job_id)
        if upload_id:
            rapid_ttl_minutes = settings.ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES
            if rapid_ttl_minutes > 0:
                key = _RAPID_RETRY_KEY_FMT.format(user_id=user_id, upload_id=upload_id)
                try:
                    ttl_seconds = rapid_ttl_minutes * _SECONDS_PER_MINUTE
                    accepted = await redis.set(
                        key, _RAPID_RETRY_VALUE, ex=ttl_seconds, nx=True
                    )
                except Exception as exc:
                    logger.warning(
                        "Rapid-retry SETNX failed for user=%s: %s — continuing",
                        user_id_hash,
                        exc,
                    )
                    accepted = True
                if not accepted:
                    logger.info(
                        "Vision nudge skipped — rapid_retry_dedup "
                        "(user=%s, upload_id=%s)",
                        user_id_hash,
                        upload_id,
                        extra={
                            "metric": METRIC_NUDGE_RAPID_RETRY_DEDUP,
                            "user_id_hash": user_id_hash,
                            "upload_id": upload_id,
                        },
                    )
                    return

    mcp_ctx = McpContext(
        user_id=UUID(user_id),
        supabase=supabase,
        advisor_repo=advisor_repo,
        logger=logger,
    )

    image_blocks = await _fetch_vision_blocks(mcp_ctx)
    if not image_blocks:
        logger.info(
            "Vision nudge skipped — no image blocks available (user=%s)",
            user_id_hash,
        )
        return

    recent_nudges = await run_sync(
        advisor_repo.get_recent_nudge_context,
        user_id,
        settings.ADVISOR_NUDGE_RECENT_CONTEXT_LIMIT,
    )
    prompt_text = build_vision_nudge_prompt(
        profile=profile_content, recent_nudges=recent_nudges
    )

    user_content: list[dict[str, Any]] = [
        {"type": CONTENT_BLOCK_TYPE_TEXT, "text": prompt_text},
        *image_blocks,
    ]

    llm = _get_llm_adapter()
    try:
        response = await llm.create_message(
            model=settings.ADVISOR_MODEL_HAIKU,
            system=SOUL_MD,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=MAX_TOKENS_NUDGE,
        )
        log_llm_response(
            None,
            model=settings.ADVISOR_MODEL_HAIKU,
            user_id=user_id,
            conversation_id="-",
            response=response,
            purpose="vision_nudge",
        )
        raw = response.content.strip()
    except Exception as exc:
        logger.error(
            "LLM call failed for vision nudge (user=%s): %s",
            user_id_hash,
            exc,
        )
        return

    parsed, parse_kind = _parse_nudge_json(raw)
    if parsed is None:
        logger.warning(
            "Vision nudge dropped — parse failure kind=%s (user=%s)",
            parse_kind,
            user_id_hash,
            extra={
                "metric": METRIC_NUDGE_PARSE_DROP,
                "kind": parse_kind,
                "user_id_hash": user_id_hash,
            },
        )
        return

    body: str = parsed["body"]
    next_step_label: str = parsed["next_step_label"]
    next_step_seed: str = parsed["next_step_seed"]

    # Body-hash dedup: drop if identical body seen in last 30 days.
    body_hash = hashlib.sha256(body.lower().encode()).hexdigest()
    since = datetime.now(tz=timezone.utc) - timedelta(days=_BODY_DEDUP_DAYS)
    try:
        is_dup = await run_sync(
            advisor_repo.find_duplicate_body, user_id, body_hash, since
        )
    except Exception as exc:
        logger.warning(
            "Body-hash dedup check failed for user=%s: %s — continuing",
            user_id_hash,
            exc,
        )
        is_dup = False

    if is_dup:
        logger.info(
            "Vision nudge dropped — duplicate body_hash within %d days (user=%s)",
            _BODY_DEDUP_DAYS,
            user_id_hash,
            extra={
                "metric": METRIC_NUDGE_DUPLICATE_BODY,
                "user_id_hash": user_id_hash,
            },
        )
        return

    try:
        advisor_repo.insert_nudge(
            {
                "user_id": user_id,
                "body": body,
                "next_step_label": next_step_label,
                "next_step_seed": next_step_seed,
                "body_hash": body_hash,
            }
        )
    except Exception as exc:
        logger.error("Failed to save vision nudge for user=%s: %s", user_id_hash, exc)
        return

    logger.info(
        "Vision nudge saved: user=%s next_step_label=%s",
        user_id_hash,
        next_step_label,
    )


def _resolve_upload_id_for_job(supabase: Client, job_id: str) -> str | None:
    """Resolve a job's source upload_id (for rapid-retry dedup).

    Chain: ``jobs.source_id`` → ``glowup_analyses.upload_id``. Returns
    ``None`` on any lookup failure — the caller falls through without
    dedup in that case (better to emit a potentially-duplicate nudge
    than to silently swallow the trigger).
    """
    from app.repositories.glowup_analysis_repo import GlowupAnalysisRepository
    from app.repositories.job_repo import JobRepository, SOURCE_TYPE_GLOWUP

    try:
        job = JobRepository(supabase).get_by_id(job_id)
    except Exception as exc:
        logger.debug("Failed to resolve job %s for rapid-retry dedup: %s", job_id, exc)
        return None
    if not job or job.get("source_type") != SOURCE_TYPE_GLOWUP:
        return None
    source_id = job.get("source_id")
    if not source_id:
        return None
    try:
        analysis = GlowupAnalysisRepository(supabase).get_by_id(str(source_id))
    except Exception as exc:
        logger.debug(
            "Failed to resolve analysis %s for rapid-retry dedup: %s", source_id, exc
        )
        return None
    if not analysis:
        return None
    upload_id = analysis.get("upload_id")
    return str(upload_id) if upload_id else None


def _content_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    inner = payload.get("content")
    return inner if isinstance(inner, list) else []


async def _fetch_vision_blocks(mcp_ctx: McpContext) -> list[dict[str, Any]]:
    """Fetch image blocks for the vision nudge via the MCP tool handlers.

    Plan 2026-04-20-001 Unit 3: post_analysis trigger removed; always
    calls ``_handle_get_latest_glowup``. The handler returns
    ``{"content": [...], "is_error": bool}``; we unwrap and keep only
    image blocks.
    """
    payload = await _handle_get_latest_glowup(mcp_ctx)
    blocks = _content_blocks(payload)
    return [b for b in blocks if b.get("type") == CONTENT_BLOCK_TYPE_IMAGE]


async def _fetch_makeup_vision_blocks(mcp_ctx: McpContext) -> list[dict[str, Any]]:
    """Fetch image blocks for the makeup nudge via the makeup MCP handler."""
    payload = await _handle_get_latest_makeup(mcp_ctx)
    blocks = _content_blocks(payload)
    return [b for b in blocks if b.get("type") == CONTENT_BLOCK_TYPE_IMAGE]


def _parse_nudge_json(raw: str) -> tuple[dict | None, str | None]:
    """Parse a strict JSON ``{"body", "next_step": {"label", "seed"}}`` response.

    Returns ``(parsed_dict, None)`` on success where parsed_dict has keys
    ``{"body", "next_step_label", "next_step_seed"}``.

    Returns ``(None, kind)`` on failure where kind is one of:
    ``"json" | "shape" | "length" | "seed_not_question"``.

    Validation:
    - Valid JSON after stripping code-fence.
    - Keys: ``body`` (str, non-empty), ``next_step`` (dict with ``label``
      str and ``seed`` str).
    - ``len(body) <= _NUDGE_BODY_MAX_LEN``.
    - ``len(next_step.label) <= _NUDGE_NEXT_STEP_LABEL_MAX_LEN``.
    - ``len(next_step.seed) <= _NUDGE_NEXT_STEP_SEED_MAX_LEN``.
    - ``next_step.seed.strip()`` must end with ``?``.
    """
    try:
        data = json.loads(strip_json_code_fence(raw))
    except (TypeError, ValueError):
        return None, "json"

    if not isinstance(data, dict):
        return None, "json"

    body = data.get("body")
    next_step = data.get("next_step")

    if not isinstance(body, str) or not body.strip():
        return None, "shape"
    if not isinstance(next_step, dict):
        return None, "shape"

    label = next_step.get("label")
    seed = next_step.get("seed")

    if not isinstance(label, str) or not label.strip():
        return None, "shape"
    if not isinstance(seed, str) or not seed.strip():
        return None, "shape"

    body = body.strip()
    label = label.strip()
    seed = seed.strip()

    if (
        len(body) > _NUDGE_BODY_MAX_LEN
        or len(label) > _NUDGE_NEXT_STEP_LABEL_MAX_LEN
        or len(seed) > _NUDGE_NEXT_STEP_SEED_MAX_LEN
    ):
        return None, "length"

    if not seed.endswith("?"):
        return None, "seed_not_question"

    return {"body": body, "next_step_label": label, "next_step_seed": seed}, None


# ---------------------------------------------------------------------------
# Memory manager builder (also used by write_analysis_insight_job)
# ---------------------------------------------------------------------------


async def _build_memory_manager(ctx: dict):
    """Construct a MemoryManager from worker context resources.

    Extracted so tests can patch this without standing up real Supabase/Redis.
    """
    from app.advisor.memory_manager import MemoryManager
    from app.api.deps import get_embedding_adapter

    supabase: Client = ctx["supabase"]
    return MemoryManager(
        advisor_repo=AdvisorRepository(supabase),
        embedding_adapter=get_embedding_adapter(),
    )


# ---------------------------------------------------------------------------
# ARQ job: write_analysis_insight_job
# ---------------------------------------------------------------------------


async def write_analysis_insight_job(
    ctx: dict,
    user_id: str,
    face_shape: str,
    symmetry_score: float,
    recommendations: list[str],
    upload_id: str,
) -> None:
    """Persist an `analysis_insight` memory row after a face analysis completes.

    Also upserts the user's stable ``style_profile`` row (Plan
    2026-04-17-003 Unit 7). The two writes are independent — a
    ``style_profile`` upsert failure must not prevent the
    ``analysis_insight`` row from being written (so the chat fallback
    path in ``_build_user_data`` still has a source), and an
    ``analysis_insight`` failure must not prevent the profile from
    being refreshed. Both are fire-and-forget relative to the API
    response.
    """
    if not settings.ADVISOR_ENABLED:
        return

    user_id_hash = hash_user_id(user_id)
    mm = None
    try:
        mm = await _build_memory_manager(ctx)
    except Exception:
        logger.warning(
            "Failed to build memory manager for user=%s — skipping both writes",
            user_id_hash,
            exc_info=True,
            extra={
                "metric": "advisor.analysis_insight_failure",
                "user_id_hash": user_id_hash,
            },
        )
        return

    try:
        await mm.write_analysis_insight(
            user_id=UUID(user_id),
            face_shape=face_shape,
            symmetry_score=symmetry_score,
            recommendations=recommendations,
            upload_id=upload_id,
        )
        logger.info("Analysis insight written for user=%s", user_id_hash)
    except Exception:
        logger.warning(
            "Failed to write analysis insight for user=%s",
            user_id_hash,
            exc_info=True,
            extra={
                "metric": "advisor.analysis_insight_failure",
                "user_id_hash": user_id_hash,
            },
        )

    # Independent try/except: profile upsert must not inherit or be
    # inherited by the insight write's failure. Matches the
    # fire-and-forget pattern used throughout nudge_scheduler.
    try:
        await mm.upsert_style_profile(
            user_id=UUID(user_id),
            face_shape=face_shape,
            symmetry_score=symmetry_score,
            recommendations=recommendations,
        )
        logger.info("Style profile upserted for user=%s", user_id_hash)
    except Exception:
        logger.warning(
            "Failed to upsert style profile for user=%s",
            user_id_hash,
            exc_info=True,
            extra={
                "metric": "advisor.style_profile_failure",
                "user_id_hash": user_id_hash,
            },
        )


# ---------------------------------------------------------------------------
# ARQ job: generate_nudge_makeup
# ---------------------------------------------------------------------------


async def generate_nudge_makeup(
    ctx: dict,
    user_id: str,
    job_id: str | None = None,
) -> None:
    """Generate and save a makeup-specific nudge for a user.

    Plan 2026-04-21-001 Unit 10. Mirrors ``generate_nudge`` but uses
    the makeup MCP handler (``get_latest_makeup``) for image fetch and
    applies a per-trigger 1/24h throttle keyed by user_id (no
    upload_id — makeup jobs do not chain through a glowup_analysis).

    Triggers fire independently: ``post_glowup`` and ``post_makeup``
    do not cross-throttle in v1.
    """
    if not settings.ADVISOR_ENABLED:
        logger.debug(
            "Advisor disabled — skipping makeup nudge for user=%s",
            hash_user_id(user_id),
        )
        return

    supabase: Client = ctx["supabase"]
    redis: aioredis.Redis = ctx["redis"]
    advisor_repo = AdvisorRepository(supabase)
    user_id_hash = hash_user_id(user_id)

    # Per-trigger 1/24h throttle
    throttle_key = _MAKEUP_THROTTLE_KEY_FMT.format(user_id=user_id)
    try:
        accepted = await redis.set(throttle_key, "1", ex=_SECONDS_PER_DAY, nx=True)
    except Exception as exc:
        logger.warning(
            "Makeup nudge throttle SETNX failed for user=%s: %s — continuing",
            user_id_hash,
            exc,
        )
        accepted = True

    if not accepted:
        logger.info(
            "Makeup nudge skipped — post_makeup throttle active (user=%s)",
            user_id_hash,
        )
        return

    profile_row = await run_sync(advisor_repo.get_style_profile, user_id)
    profile_content = (profile_row or {}).get("content") or None
    if not profile_content:
        logger.info(
            "Makeup nudge skipped — no style_profile for user=%s",
            user_id_hash,
            extra={"metric": METRIC_NUDGE_NO_PROFILE, "user_id_hash": user_id_hash},
        )
        return

    mcp_ctx = McpContext(
        user_id=UUID(user_id),
        supabase=supabase,
        advisor_repo=advisor_repo,
        logger=logger,
    )

    image_blocks = await _fetch_makeup_vision_blocks(mcp_ctx)
    if not image_blocks:
        logger.info(
            "Makeup nudge skipped — no image blocks available (user=%s)",
            user_id_hash,
        )
        return

    recent_nudges = await run_sync(
        advisor_repo.get_recent_nudge_context,
        user_id,
        settings.ADVISOR_NUDGE_RECENT_CONTEXT_LIMIT,
    )
    prompt_text = build_vision_nudge_prompt(
        profile=profile_content, recent_nudges=recent_nudges
    )

    user_content: list[dict[str, Any]] = [
        {"type": CONTENT_BLOCK_TYPE_TEXT, "text": prompt_text},
        *image_blocks,
    ]

    llm = _get_llm_adapter()
    try:
        response = await llm.create_message(
            model=settings.ADVISOR_MODEL_HAIKU,
            system=SOUL_MD,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=MAX_TOKENS_NUDGE,
        )
        log_llm_response(
            None,
            model=settings.ADVISOR_MODEL_HAIKU,
            user_id=user_id,
            conversation_id="-",
            response=response,
            purpose="makeup_nudge",
        )
        raw = response.content.strip()
    except Exception as exc:
        logger.error(
            "LLM call failed for makeup nudge (user=%s): %s",
            user_id_hash,
            exc,
        )
        return

    parsed, parse_kind = _parse_nudge_json(raw)
    if parsed is None:
        logger.warning(
            "Makeup nudge dropped — parse failure kind=%s (user=%s)",
            parse_kind,
            user_id_hash,
        )
        return

    body: str = parsed["body"]
    next_step_label: str = parsed["next_step_label"]
    next_step_seed: str = parsed["next_step_seed"]

    body_hash = hashlib.sha256(body.lower().encode()).hexdigest()
    since = datetime.now(timezone.utc) - timedelta(days=_BODY_DEDUP_DAYS)
    try:
        is_dup = await run_sync(
            advisor_repo.find_duplicate_body, user_id, body_hash, since
        )
    except Exception as exc:
        logger.warning(
            "Body-hash dedup check failed for user=%s: %s — continuing",
            user_id_hash,
            exc,
        )
        is_dup = False

    if is_dup:
        logger.info(
            "Makeup nudge dropped — duplicate body_hash within %d days (user=%s)",
            _BODY_DEDUP_DAYS,
            user_id_hash,
        )
        return

    try:
        advisor_repo.insert_nudge(
            {
                "user_id": user_id,
                "body": body,
                "next_step_label": next_step_label,
                "next_step_seed": next_step_seed,
                "body_hash": body_hash,
            }
        )
    except Exception as exc:
        logger.error("Failed to save makeup nudge for user=%s: %s", user_id_hash, exc)
        return

    logger.info(
        "Makeup nudge saved: user=%s next_step_label=%s",
        user_id_hash,
        next_step_label,
    )
