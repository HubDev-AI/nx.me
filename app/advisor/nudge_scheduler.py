"""Nudge scheduler — thin orchestrator for advisor-initiated nudges.

Plan 2026-04-17-003 Unit 2: removed generic trigger functions and
eligibility cron. Only post_glowup vision-grounded path remains.

Jobs:
  generate_nudge           — generate + save a single nudge via Haiku
  write_analysis_insight_job — persist analysis insight memory row
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.advisor._hashing import hash_user_id
from app.advisor._json_utils import strip_json_code_fence
from app.advisor.mcp.context import McpContext
from app.advisor.mcp.tools_glowup import (
    _handle_get_latest_glowup,
    _handle_get_latest_photo,
)
from app.advisor.persona import SOUL_MD
from app.db.async_helpers import run_sync
from app.repositories.advisor_repo import AdvisorRepository
from app.advisor.nudge_policy import (
    MAX_TOKENS_NUDGE,
    TRIGGER_POST_GLOWUP,
)
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

# Redis key template for the post_glowup rapid-retry dedup guard.
# Using a SETNX with a TTL keyed by (user_id, upload_id) — no schema
# creep on advisor_nudges.
_RAPID_RETRY_KEY_FMT = "advisor:nudge:post_glowup:{user_id}:{upload_id}"
_RAPID_RETRY_VALUE = "1"
_SECONDS_PER_MINUTE = 60


# ---------------------------------------------------------------------------
# ARQ job: generate_nudge
# ---------------------------------------------------------------------------


async def generate_nudge(
    ctx: dict,
    user_id: str,
    trigger: str,
    insight: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> None:
    """Generate and save a single nudge for a user.

    Plan 2026-04-17-003 Unit 2: only the post_glowup vision-grounded
    path remains. All generic triggers have been removed.

    Args:
        ctx:     ARQ worker context (supabase, redis injected at startup).
        user_id: UUID string of the target user.
        trigger: Must be TRIGGER_POST_GLOWUP.
        insight: Legacy kwarg — unused, kept for wire compatibility.
        job_id:  Source job_id for ``post_glowup`` — used to resolve
                 the ``upload_id`` for rapid-retry dedup.
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
        trigger=trigger,
        job_id=job_id,
    )


async def _generate_vision_nudge(
    *,
    advisor_repo: AdvisorRepository,
    redis: aioredis.Redis,
    supabase: Client,
    user_id: str,
    trigger: str,
    job_id: str | None,
) -> None:
    """Vision-grounded nudge flow (Plan 2026-04-17-003 Unit 8).

    1. Skip if no ``style_profile`` (no stable facts → no prompt).
    2. Rapid-retry dedup for ``post_glowup``: if a second
       ``post_glowup`` for the same user+upload fires within
       ``ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES``, skip the second run.
    3. Fetch images via the MCP tool handlers
       (``_handle_get_latest_glowup`` / ``_handle_get_latest_photo``) —
       same in-process code path Ada chat uses. Error text blocks from
       the handler are filtered out; only image blocks reach the model.
    4. Build ``build_vision_nudge_prompt(profile, recent_nudges)``
       text, attach image blocks in the user message's ``content`` list,
       call Haiku.
    5. Parse strict JSON ``{"body", "observation_tag"}``. Drop on
       parse failure.
    """
    user_id_hash = hash_user_id(user_id)
    profile_row = await run_sync(advisor_repo.get_style_profile, user_id)
    profile_content = (profile_row or {}).get("content") or None
    if not profile_content:
        logger.info(
            "Vision nudge skipped — no style_profile for user=%s (trigger=%s)",
            user_id_hash,
            trigger,
            extra={"metric": METRIC_NUDGE_NO_PROFILE, "user_id_hash": user_id_hash},
        )
        return

    # Rapid-retry dedup — only applies to post_glowup; post_analysis
    # predates any generation and runs at most once per analysis event.
    if trigger == TRIGGER_POST_GLOWUP and job_id:
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
                    # Redis hiccup → fall through rather than block the
                    # nudge; the model still has its own dedup via
                    # recent_nudges context.
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

    # Build the per-turn MCP context in the same shape the chat path
    # uses. The worker resolves the user from its own ctx, never from
    # any model-provided input — cross-user leakage is impossible
    # because the worker-built context's ``user_id`` is the only
    # identity the handlers see.
    mcp_ctx = McpContext(
        user_id=UUID(user_id),
        supabase=supabase,
        advisor_repo=advisor_repo,
        logger=logger,
    )

    image_blocks = await _fetch_vision_blocks(mcp_ctx, trigger)
    # The prompt handles the degenerate 1-image case gracefully; we
    # still emit the nudge when only one image is available
    # (post_analysis pre-generation). Zero image blocks means the
    # handler returned only error text — skip to avoid feeding the
    # model an image-shaped prompt with no image.
    if not image_blocks:
        logger.info(
            "Vision nudge skipped — no image blocks available (user=%s, trigger=%s)",
            user_id_hash,
            trigger,
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
        from app.advisor.payload_logger import log_llm_response

        log_llm_response(
            None,
            model=settings.ADVISOR_MODEL_HAIKU,
            user_id=user_id,
            conversation_id="-",
            response=response,
            purpose=f"vision_nudge:{trigger}",
        )
        raw = response.content.strip()
    except Exception as exc:
        logger.error(
            "LLM call failed for vision nudge (user=%s, trigger=%s): %s",
            user_id_hash,
            trigger,
            exc,
        )
        return

    parsed = _parse_vision_nudge_json(raw)
    if parsed is None:
        logger.warning(
            "Vision nudge dropped — malformed JSON (user=%s, trigger=%s)",
            user_id_hash,
            trigger,
            extra={
                "metric": METRIC_NUDGE_INVALID_JSON,
                "user_id_hash": user_id_hash,
                "trigger": trigger,
            },
        )
        return

    body, observation_tag = parsed

    try:
        advisor_repo.insert_nudge(
            {
                "user_id": user_id,
                "trigger": trigger,
                "content": body,
                "observation_tag": observation_tag,
            }
        )
    except Exception as exc:
        logger.error("Failed to save vision nudge for user=%s: %s", user_id_hash, exc)
        return

    logger.info(
        "Vision nudge saved: user=%s trigger=%s observation_tag=%s",
        user_id_hash,
        trigger,
        observation_tag,
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


async def _fetch_vision_blocks(
    mcp_ctx: McpContext, trigger: str
) -> list[dict[str, Any]]:
    """Fetch image blocks for the vision nudge via the MCP tool handlers.

    Plan 2026-04-17-003 Unit 8 Dependency on Unit 2/9: nudge generation
    shares the exact same image-fetch code path as Ada chat. For
    ``post_glowup`` we call ``get_latest_glowup``; for ``post_analysis``
    (which can fire before any generation exists) we call
    ``get_latest_glowup`` first and fall back to ``get_latest_photo``
    when no glow-up is available yet.

    The handlers now return ``{"content": [...], "is_error": bool}``
    (envelope-shaped payload). We unwrap ``content`` and keep only the
    image blocks; error payloads naturally drop to zero image blocks
    and trigger the fallback or skip path.
    """

    def _content(payload: dict[str, Any]) -> list[dict[str, Any]]:
        inner = payload.get("content")
        return inner if isinstance(inner, list) else []

    if trigger == TRIGGER_POST_GLOWUP:
        payload = await _handle_get_latest_glowup(mcp_ctx)
        blocks = _content(payload)
    else:
        # post_analysis: prefer the glow-up if one exists (user may
        # have completed one already), otherwise fall back to the
        # most recent source photo.
        payload = await _handle_get_latest_glowup(mcp_ctx)
        blocks = _content(payload)
        if not any(b.get("type") == CONTENT_BLOCK_TYPE_IMAGE for b in blocks):
            payload = await _handle_get_latest_photo(mcp_ctx)
            blocks = _content(payload)

    return [b for b in blocks if b.get("type") == CONTENT_BLOCK_TYPE_IMAGE]


def _parse_vision_nudge_json(raw: str) -> tuple[str, str] | None:
    """Parse a strict JSON ``{"body", "observation_tag"}`` response.

    Returns ``(body, observation_tag)`` when both fields are non-empty
    strings; returns ``None`` on any parse or shape failure. Dropping
    on failure is preferred to retrying — a malformed response from
    Haiku is usually a token-budget accident, not a retryable error.
    """
    try:
        data = json.loads(strip_json_code_fence(raw))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    body = data.get("body")
    observation_tag = data.get("observation_tag")
    if not isinstance(body, str) or not body.strip():
        return None
    if not isinstance(observation_tag, str) or not observation_tag.strip():
        return None
    return body.strip(), observation_tag.strip()


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
