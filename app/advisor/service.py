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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from supabase import Client

from app.advisor import content_filter
from app.advisor.context_builder import (
    build_context,
    build_user_data_block,
    has_visual_trigger,
)
from app.advisor.memory_manager import MemoryManager
from app.advisor.models import LLMResponse, MemoryType
from app.config import settings

logger = logging.getLogger(__name__)

# Model identifiers
_MODEL_SONNET = "claude-3-5-sonnet-20241022"
_MODEL_HAIKU = "claude-3-haiku-20240307"

# Max tokens for chat response (keep concise per SOUL.md)
_MAX_TOKENS_CHAT = 256
_MAX_TOKENS_SUMMARY = 512

# SOUL.md loaded once at import time
_SOUL_MD_PATH = Path(__file__).parent / "SOUL.md"
_SOUL_MD: str = _SOUL_MD_PATH.read_text(encoding="utf-8")


class AdvisorService:
    """Orchestrates all advisor functionality."""

    def __init__(
        self,
        supabase: Client,
        redis_client: aioredis.Redis,
        llm_adapter: Any,
    ) -> None:
        self._supabase = supabase
        self._redis = redis_client
        self._llm = llm_adapter
        self._memory_manager = MemoryManager(supabase=supabase, llm_adapter=llm_adapter)

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
        if len(history) >= settings.ADVISOR_CONVERSATION_SUMMARY_THRESHOLD:
            await self._summarize_conversation(conversation_id, history)
            history = self._load_conversation_history(conversation_id)

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
            messages=messages,
            vision_content=vision_content,
            recent_responses=recent_advisor_messages,
        )

        # Step 9: Persist messages
        user_msg_row = self._save_message(conversation_id, "user", message)
        advisor_msg_row = self._save_message(conversation_id, "advisor", advisor_response)

        # Update conversation updated_at
        self._supabase.table("advisor_conversations").update(
            {"updated_at": datetime.now(tz=timezone.utc).isoformat()}
        ).eq("id", conversation_id).execute()

        # Step 10: Async memory extraction (fire and forget)
        asyncio.create_task(
            self._memory_manager.extract_memories_from_turn(
                user_id=user_id,
                user_message=message,
                advisor_response=advisor_response,
            )
        )

        return advisor_msg_row

    async def _call_llm_with_check(
        self,
        messages: list[dict[str, Any]],
        vision_content: list[dict[str, Any]] | None,
        recent_responses: list[str],
    ) -> str:
        """Call LLM, apply post-generation check, retry once if needed (spec Section 11)."""
        # Determine model based on daily usage guard (spec Section 10)
        model = self._select_model()

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
                return content_filter.get_fallback_response()

            # Post-generation check (spec Section 11)
            hint = _post_check(text, recent_responses)
            if hint and attempt == 0:
                # Append instruction and retry
                messages = list(messages) + [
                    {"role": "user", "content": hint}
                ]
                continue

            return text

        return content_filter.get_fallback_response()

    def _select_model(self) -> str:
        """Select chat model (Sonnet normally, Haiku under high load guard).

        Spec Section 10: >50 messages/day → degrade to Haiku.
        For now, always Sonnet (daily count check left for future story).
        """
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

    # -----------------------------------------------------------------------
    # Nudges
    # -----------------------------------------------------------------------

    def get_nudges(self, user_id: UUID) -> list[dict[str, Any]]:
        """Return the nudge feed for a user (newest first)."""
        result = (
            self._supabase.table("advisor_nudges")
            .select("id, trigger, content, read_at, created_at")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    def mark_nudge_read(self, user_id: UUID, nudge_id: UUID) -> bool:
        """Mark a nudge as read. Returns True if found and updated."""
        # Verify ownership first
        existing = (
            self._supabase.table("advisor_nudges")
            .select("id, read_at")
            .eq("id", str(nudge_id))
            .eq("user_id", str(user_id))
            .maybe_single()
            .execute()
        )
        if not existing.data:
            return False

        if existing.data.get("read_at"):
            # Already read — idempotent success
            return True

        self._supabase.table("advisor_nudges").update(
            {"read_at": datetime.now(tz=timezone.utc).isoformat()}
        ).eq("id", str(nudge_id)).execute()

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
        result = (
            self._supabase.table("advisor_conversations")
            .select("id, updated_at, created_at")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        existing = (result.data or [None])[0]

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

        # Create new conversation
        new_conv = (
            self._supabase.table("advisor_conversations")
            .insert({"user_id": str(user_id)})
            .execute()
        )
        created = (new_conv.data or [{}])[0]
        logger.info("New conversation created: user=%s id=%s", user_id, created.get("id"))
        return created

    def _load_conversation_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """Load messages for a conversation (oldest first)."""
        result = (
            self._supabase.table("advisor_messages")
            .select("id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", asc=True)
            .execute()
        )
        return result.data or []

    def _save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        """Insert a message row and return it."""
        result = (
            self._supabase.table("advisor_messages")
            .insert({
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
            })
            .execute()
        )
        return (result.data or [{}])[0]

    def _build_user_data(self, user_id: UUID) -> str:
        """Build user data block from latest analysis insight."""
        result = (
            self._supabase.table("user_memories")
            .select("content, created_at")
            .eq("user_id", str(user_id))
            .eq("type", MemoryType.ANALYSIS_INSIGHT)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return ""

        content = rows[0].get("content", {})
        face_shape = content.get("face_shape")
        symmetry_score = content.get("symmetry_score")

        # Count total analyses
        count_result = (
            self._supabase.table("user_memories")
            .select("id", count="exact")
            .eq("user_id", str(user_id))
            .eq("type", MemoryType.ANALYSIS_INSIGHT)
            .execute()
        )
        analysis_count = count_result.count or 0

        from app.advisor.context_builder import build_user_data_block
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
            result = (
                self._supabase.table("images")
                .select("id, storage_path")
                .eq("user_id", str(user_id))
                .eq("status", "cleared")
                .order("created_at", desc=True)
                .limit(2)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None

            blocks: list[dict[str, Any]] = []
            for row in rows:
                try:
                    signed = self._supabase.storage.from_("images").create_signed_url(
                        path=row["storage_path"],
                        expires_in=settings.SIGNED_URL_EXPIRY_SECONDS,
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
                model=_MODEL_HAIKU,
                system="Summarise this conversation in 2-3 sentences, focusing on styling preferences and goals mentioned.",
                messages=[{"role": "user", "content": history_text}],
                max_tokens=_MAX_TOKENS_SUMMARY,
            )
            summary = response.content.strip()
        except Exception as exc:
            logger.warning("Conversation summarization failed: %s", exc)
            return

        # Store summary and truncate messages
        self._supabase.table("advisor_conversations").update({
            "summary": summary,
            "summarised_at": datetime.now(tz=timezone.utc).isoformat(),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }).eq("id", conversation_id).execute()

        # Delete all messages (fresh start after summary)
        self._supabase.table("advisor_messages").delete().eq(
            "conversation_id", conversation_id
        ).execute()

        logger.info("Conversation %s summarized and truncated", conversation_id)


# ---------------------------------------------------------------------------
# Post-generation check (spec Section 11)
# ---------------------------------------------------------------------------


def _post_check(response: str, recent_messages: list[str]) -> str | None:
    """Check response quality. Returns a regeneration hint, or None if OK."""
    if recent_messages:
        last_words = " ".join(recent_messages[-1].split()[:3]).lower()
        this_words = " ".join(response.split()[:3]).lower()
        if last_words and last_words == this_words:
            return "Start differently."

    sentence_count = (
        response.count(". ")
        + response.count("? ")
        + response.count("! ")
        + 1
    )
    if sentence_count > 3:
        return "Shorter. Say less."
    if sentence_count == 3:
        return "If you can say this in fewer words, do it."

    return None
