"""AdvisorService — orchestrates conversations, memories, nudges, and LLM calls.

Spec Section 5.3 message flow:
  1. require_feature("advisor_chat") — enforced at route layer
  2. Get/create active conversation
  3. Build context (Section 6)
  4. Call Claude Sonnet
  5. Save messages
  6. Extract memory signals (async, Haiku)
  7. Return response
"""
from __future__ import annotations

import asyncio
import logging
import re
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.advisor.llm_port import LLMPort

import redis.asyncio as aioredis

from app.advisor import content_filter
from app.advisor.context_builder import (
    build_context,
    build_user_data_block,
    has_visual_trigger,
)
from app.advisor.memory_manager import MemoryManager
from app.advisor.models import LLMResponse, MemoryType
from app.config import settings
from app.repositories.advisor_repo import AdvisorRepository

logger = logging.getLogger(__name__)

# Model identifiers — A-5: sourced from config to avoid duplication
_MODEL_SONNET = settings.ADVISOR_MODEL_SONNET

# Max tokens for chat response (keep concise per SOUL.md)
_MAX_TOKENS_CHAT = 256
_MAX_TOKENS_SUMMARY = 512

# SOUL.md loaded once at import time
_SOUL_MD_PATH = Path(__file__).parent / "SOUL.md"
try:
    _SOUL_MD: str = _SOUL_MD_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    raise RuntimeError(f"SOUL.md not found at {_SOUL_MD_PATH}. Advisor service cannot start.")

_background_tasks: weakref.WeakSet = weakref.WeakSet()


def _task_done(t: asyncio.Task) -> None:
    """Log errors from background tasks instead of letting them silently fail."""
    if t.cancelled():
        return
    exc = t.exception()
    if exc:
        logger.error("Background task failed: %s", exc, exc_info=exc)


class AdvisorService:
    """Orchestrates all advisor functionality."""

    def __init__(
        self,
        advisor_repo: AdvisorRepository,
        redis_client: aioredis.Redis,
        llm_adapter: LLMPort,
    ) -> None:
        self._repo = advisor_repo
        self._redis = redis_client
        self._llm = llm_adapter
        self._memory_manager = MemoryManager(advisor_repo=advisor_repo, llm_adapter=llm_adapter)

    # -----------------------------------------------------------------------
    # Chat
    # -----------------------------------------------------------------------

    async def send_message(
        self,
        user_id: UUID,
        raw_message: str,
    ) -> dict[str, Any]:
        """Process a chat message and return the advisor response.

        Full flow per spec Section 5.3.
        """
        # Step 1: Sanitize input + rate limit
        try:
            message = content_filter.sanitize_input(raw_message)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        await content_filter.check_rate_limit(str(user_id), self._redis)

        # Step 2: Get/create active conversation
        conversation = self._get_or_create_conversation(user_id)
        conversation_id = conversation["id"]

        # Step 3: Load conversation history
        history = self._load_conversation_history(conversation_id)

        # Auto-summarize if threshold reached (spec Section 5.2)
        # L-7: Guard against double-trigger — skip if recently summarized
        # A-1: Redis distributed lock prevents race condition on concurrent messages
        if len(history) >= settings.ADVISOR_CONVERSATION_SUMMARY_THRESHOLD:
            should_summarize = True
            summarized_at_str = conversation.get("summarized_at")
            if summarized_at_str:
                try:
                    last_summary = datetime.fromisoformat(summarized_at_str)
                    if last_summary.tzinfo is None:
                        last_summary = last_summary.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - last_summary < timedelta(minutes=5):
                        should_summarize = False
                except (ValueError, TypeError):
                    pass
            if should_summarize:
                lock_key = f"advisor:summarize_lock:{conversation_id}"
                # Acquire a 60s lock — if another request is already summarizing, skip
                acquired = await self._redis.set(lock_key, "1", nx=True, ex=60)
                if acquired:
                    try:
                        # A-17: Timeout on summarization to avoid blocking response
                        await asyncio.wait_for(
                            self._summarize_conversation(conversation_id, history),
                            timeout=10.0,
                        )
                        history = self._load_conversation_history(conversation_id)
                    except asyncio.TimeoutError:
                        logger.warning("Summarization timed out for conversation %s", conversation_id)
                    finally:
                        await self._redis.delete(lock_key)

        # Step 4: Retrieve relevant memories
        memories = await self._memory_manager.get_relevant_memories(user_id, message)

        # Step 5: Build user data block from latest analysis
        user_data_block = self._build_user_data(user_id)

        # Step 6: Check for visual context triggers
        vision_content: list[dict[str, Any]] | None = None
        if has_visual_trigger(message):
            vision_content = self._fetch_vision_content(user_id)

        # Step 7: Build LLM context
        messages = build_context(
            soul_md=_SOUL_MD,
            user_data=user_data_block,
            memories=memories,
            conversation=history,
            message=message,
        )

        # Step 8: Call LLM (with post-generation check + one retry)
        recent_advisor_messages = [
            m["content"] for m in history if m.get("role") == "advisor"
        ]
        advisor_response = await self._call_llm_with_check(
            user_id=user_id,
            messages=messages,
            vision_content=vision_content,
            recent_responses=recent_advisor_messages,
        )

        # Step 9: Persist messages
        self._save_message(conversation_id, "user", message)
        advisor_msg_row = self._save_message(conversation_id, "advisor", advisor_response)

        # Update conversation updated_at
        self._repo.update_conversation_timestamp(conversation_id)

        # Step 10: Async memory extraction (fire and forget, L-5 / M-6)
        # No explicit retry — extraction will naturally re-trigger on next message.
        # A-9: Structured error logging with extraction failure counter
        async def _extract_with_logging() -> None:
            try:
                await self._memory_manager.extract_memories_from_turn(
                    user_id=user_id,
                    user_message=message,
                    advisor_response=advisor_response,
                )
            except Exception:
                logger.warning(
                    "Memory extraction failed for user %s. Will retry on next message.",
                    str(user_id),
                    exc_info=True,
                    extra={"metric": "advisor.memory_extraction_failure", "user_id": str(user_id)},
                )

        task = asyncio.create_task(_extract_with_logging())
        task.add_done_callback(_task_done)
        _background_tasks.add(task)

        return advisor_msg_row

    async def _call_llm_with_check(
        self,
        user_id: UUID,
        messages: list[dict[str, Any]],
        vision_content: list[dict[str, Any]] | None,
        recent_responses: list[str],
    ) -> str:
        """Call LLM, apply post-generation check, retry once if needed (spec Section 11)."""
        # Determine model based on daily usage guard (spec Section 10)
        model = await self._select_model(str(user_id))

        for attempt in range(2):
            response: LLMResponse = await self._llm.create_message(
                model=model,
                system=_SOUL_MD,
                messages=[m for m in messages if m.get("role") != "system"],
                max_tokens=_MAX_TOKENS_CHAT,
                vision_content=vision_content,
            )
            text = response.content.strip()

            # Check C-2 violations
            if content_filter.scan_output(text):
                logger.warning("C-2 violation in LLM output (attempt %d)", attempt + 1)
                if attempt == 0:
                    continue
                return content_filter.get_fallback_response("c2_violation")

            # Post-generation check (spec Section 11)
            hint = _post_check(text, recent_responses)
            if hint and attempt == 0:
                # Append instruction and retry
                messages = list(messages) + [
                    {"role": "user", "content": hint}
                ]
                continue

            return text

        return content_filter.get_fallback_response("c2_violation")

    async def _select_model(self, user_id: str) -> str:
        """Select chat model — Sonnet normally, Haiku if daily threshold exceeded.

        Spec Section 10: >50 messages/day → degrade to Haiku to cap costs.
        """
        from datetime import datetime, timezone
        daily_key = f"advisor_daily_msgs:{user_id}:{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}"
        count = int(await self._redis.get(daily_key) or 0)
        if count > settings.ADVISOR_DEGRADATION_THRESHOLD:
            logger.info("User %s exceeded daily threshold (%d > %d) — using Haiku",
                         user_id, count, settings.ADVISOR_DEGRADATION_THRESHOLD)
            return settings.ADVISOR_MODEL_HAIKU
        return _MODEL_SONNET

    # -----------------------------------------------------------------------
    # Conversation history
    # -----------------------------------------------------------------------

    def get_conversation_history(self, user_id: UUID) -> dict[str, Any]:
        """Return the active conversation and its messages."""
        conversation = self._get_or_create_conversation(user_id)
        messages = self._load_conversation_history(conversation["id"])
        return {
            "conversation_id": conversation["id"],
            "messages": [
                {
                    "id": m.get("id", ""),
                    "role": m.get("role", ""),
                    "content": m.get("content", ""),
                    "created_at": m.get("created_at", ""),
                }
                for m in messages
            ],
        }

    def get_conversation_history_page(
        self,
        user_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Return a paginated page of conversation messages."""
        conversation = self._get_or_create_conversation(user_id)
        fetch_limit = limit + 1
        rows = self._repo.get_messages_page(
            conversation_id=conversation["id"],
            fetch_limit=fetch_limit,
            cursor=cursor,
        )
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        # L-8: Cursor format: {created_at}|{id}
        # Assumes (created_at, id) is unique. The id tiebreaker prevents skipped records
        # when multiple messages share the same created_at timestamp.
        next_cursor = (
            f"{rows[-1]['created_at']}|{rows[-1]['id']}"
            if has_more and rows
            else None
        )
        return {
            "conversation_id": conversation["id"],
            "messages": [
                {
                    "id": m.get("id", ""),
                    "role": m.get("role", ""),
                    "content": m.get("content", ""),
                    "created_at": m.get("created_at", ""),
                }
                for m in rows
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    # -----------------------------------------------------------------------
    # Nudges
    # -----------------------------------------------------------------------

    def get_nudges(self, user_id: UUID) -> list[dict[str, Any]]:
        """Return the nudge feed for a user (newest first)."""
        return self._repo.get_nudges(str(user_id))

    def get_nudges_page(
        self,
        user_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        """Return a paginated page of nudges."""
        fetch_limit = limit + 1
        rows = self._repo.get_nudges_page(
            user_id=str(user_id),
            fetch_limit=fetch_limit,
            cursor=cursor,
            unread_only=unread_only,
        )
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        next_cursor = (
            f"{rows[-1]['created_at']}|{rows[-1]['id']}"
            if has_more and rows
            else None
        )
        return {
            "nudges": rows,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def mark_nudge_read(self, user_id: UUID, nudge_id: UUID) -> bool:
        """Mark a nudge as read. Returns True if found and updated."""
        existing = self._repo.get_nudge_by_id(str(nudge_id), str(user_id))
        if not existing:
            return False

        if existing.get("read_at"):
            # Already read — idempotent success
            return True

        self._repo.mark_nudge_read(str(nudge_id))
        logger.info("Nudge %s marked read for user %s", nudge_id, user_id)
        return True

    # -----------------------------------------------------------------------
    # Memories (public API — delegates to MemoryManager)
    # -----------------------------------------------------------------------

    async def add_memory(
        self,
        user_id: UUID,
        memory_type: MemoryType,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """Add a user-authored memory (goal or note)."""
        return await self._memory_manager.write_memory(user_id, memory_type, content)

    def list_memories(self, user_id: UUID) -> list[dict[str, Any]]:
        """List all memories for a user."""
        return self._memory_manager.list_memories(user_id)

    def list_memories_page(
        self,
        user_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Return a paginated page of memories."""
        fetch_limit = limit + 1
        rows = self._repo.get_memories_page(
            user_id=str(user_id),
            fetch_limit=fetch_limit,
            cursor=cursor,
        )
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        next_cursor = (
            f"{rows[-1]['created_at']}|{rows[-1]['id']}"
            if has_more and rows
            else None
        )
        return {
            "memories": rows,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    def delete_memory(self, user_id: UUID, memory_id: UUID) -> bool:
        """Delete a user-owned memory."""
        return self._memory_manager.delete_memory(user_id, memory_id)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_or_create_conversation(self, user_id: UUID) -> dict[str, Any]:
        """Return the active conversation or create a new one.

        Rules (spec Section 5.2):
        - One active conversation per user
        - Auto-new after ADVISOR_CONVERSATION_INACTIVE_DAYS days inactive
        """
        existing = self._repo.get_latest_conversation(str(user_id))

        if existing:
            # Check if inactive
            updated_at_str = existing.get("updated_at") or existing.get("created_at", "")
            try:
                updated_at = datetime.fromisoformat(updated_at_str)
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                updated_at = datetime.now(tz=timezone.utc)

            cutoff = datetime.now(tz=timezone.utc) - timedelta(
                days=settings.ADVISOR_CONVERSATION_INACTIVE_DAYS
            )
            if updated_at >= cutoff:
                return existing

        # A-2: Create new conversation. Note: Supabase JS/Python client does not
        # support multi-statement transactions. If the subsequent message INSERT fails,
        # the orphaned conversation row is harmless (no messages = empty, will be
        # reused or replaced on next inactive-days check). A true fix requires an
        # RPC function wrapping both INSERTs in a single PostgreSQL transaction.
        created = self._repo.create_conversation(str(user_id))
        logger.info("New conversation created: user=%s id=%s", user_id, created.get("id"))
        return created

    def _load_conversation_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Load messages for a conversation (oldest first)."""
        return self._repo.get_messages(conversation_id)

    def _save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        """Insert a message row and return it."""
        return self._repo.insert_message(conversation_id, role, content)

    def _build_user_data(self, user_id: UUID) -> str:
        """Build user data block from latest analysis insight."""
        latest = self._repo.get_latest_analysis_insight(str(user_id))
        if not latest:
            return ""

        content = latest.get("content", {})
        face_shape = content.get("face_shape")
        symmetry_score = content.get("symmetry_score")
        analysis_count = self._repo.count_analysis_insights(str(user_id))

        return build_user_data_block(
            face_shape=face_shape,
            symmetry_score=symmetry_score,
            analysis_count=analysis_count,
        )

    def _fetch_vision_content(self, user_id: UUID) -> list[dict[str, Any]] | None:
        """Fetch recent signed image URLs for visual context (spec Section 6.4).

        Returns Anthropic vision content blocks, or None if no images.
        """
        try:
            rows = self._repo.get_cleared_images(str(user_id), limit=2)
            if not rows:
                return None

            blocks: list[dict[str, Any]] = []
            for row in rows:
                try:
                    signed = self._repo.create_signed_url(
                        row["storage_path"],
                        settings.SIGNED_URL_EXPIRY_SECONDS,
                    )
                    url = signed.get("signedURL") or signed.get("signedUrl", "")
                    if url:
                        blocks.append({
                            "type": "image",
                            "source": {"type": "url", "url": url},
                        })
                except Exception as exc:
                    logger.warning("Failed to create signed URL for image %s: %s", row["id"], exc)

            return blocks if blocks else None
        except Exception as exc:
            logger.warning("Failed to fetch vision content for user %s: %s", user_id, exc)
            return None

    async def _summarize_conversation(
        self,
        conversation_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        """Summarize and truncate the conversation (spec Section 5.2).

        Uses Haiku. In mock mode, the mock adapter returns a short canned response.
        After summarization, deletes old messages and stores summary on the conversation.
        """
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in history
        )
        try:
            response = await self._llm.create_message(
                model=settings.ADVISOR_MODEL_HAIKU,
                system=(
                    "Summarise this conversation in 2-3 sentences, "
                    "focusing on styling preferences and goals mentioned."
                ),
                messages=[{"role": "user", "content": history_text}],
                max_tokens=_MAX_TOKENS_SUMMARY,
            )
            summary = response.content.strip()
        except Exception as exc:
            logger.warning("Conversation summarization failed: %s", exc)
            return

        # Store summary and truncate messages
        self._repo.update_conversation_summary(conversation_id, summary)

        # Soft-delete messages (mark summarized_at instead of hard-delete)
        self._repo.soft_delete_messages(conversation_id)

        logger.info("Conversation %s summarized and truncated", conversation_id)


# ---------------------------------------------------------------------------
# Post-generation check (spec Section 11)
# ---------------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    """Return the first sentence of text (split on .!?) lowercased and stripped."""
    parts = re.split(r"[.!?]", text.strip())
    first = parts[0].strip().lower() if parts else ""
    return first


def _post_check(response: str, recent_messages: list[str]) -> str | None:
    """Check response quality. Returns a regeneration hint, or None if OK."""
    if recent_messages:  # L-4: Guard — skip repetition check when no prior messages
        last_sentence = _first_sentence(recent_messages[-1])
        this_sentence = _first_sentence(response)
        if last_sentence and last_sentence == this_sentence:
            return "Start differently."

    sentence_count = len(re.split(r'(?<=[.!?])\s+', response.strip()))
    if sentence_count > 3:
        return "Shorter. Say less."
    if sentence_count == 3:
        return "If you can say this in fewer words, do it."

    return None
