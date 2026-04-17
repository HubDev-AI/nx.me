"""Memory manager — pgvector read/write, embedding, hybrid retrieval.

Handles:
- Writing new memories (goal, user_note, analysis_insight, etc.)
- Retrieving relevant memories via pgvector + hybrid scoring
- Memory extraction from conversation turns (async, Haiku)
- Deduplication before storage
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.advisor._json_utils import strip_json_code_fence
from app.advisor.embedding_port import EmbeddingPort
from app.advisor.llm_port import LLMPort

from app.advisor.models import MemoryType
from app.advisor.nudge_policy import MODEL_HAIKU
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.advisor_repo import AdvisorRepository

logger = logging.getLogger(__name__)

# Hybrid score weights (spec Section 4.4)
_WEIGHT_SIMILARITY = 0.6
_WEIGHT_RECENCY = 0.3
_WEIGHT_IMPORTANCE = 0.1

# Similarity threshold: discard candidates below this
_MIN_SIMILARITY = 0.60

# Importance scores by memory type (spec Section 4.4)
_IMPORTANCE: dict[str, float] = {
    MemoryType.GOAL: 1.0,
    MemoryType.ACCEPTED_SUGGESTION: 0.9,
    MemoryType.ANALYSIS_INSIGHT: 0.8,
    MemoryType.USER_NOTE: 0.6,
    MemoryType.DISMISSED_SUGGESTION: 0.4,
}

# Deduplication: word-overlap threshold for same-type memories in last 7 days
_DEDUP_OVERLAP_THRESHOLD = 0.70

# pgvector candidate pool size
_CANDIDATE_LIMIT = 15


def _recency_score(created_at_str: str) -> float:
    """Compute recency score from ISO timestamp string (spec Section 4.4)."""
    try:
        created_at = datetime.fromisoformat(created_at_str)
    except (ValueError, TypeError):
        return 0.2

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    age_days = (now - created_at).total_seconds() / 86400

    if age_days < 1:
        return 1.0
    if age_days < 7:
        return 0.8
    if age_days < 30:
        return 0.5
    return 0.2


def _word_overlap(a: str, b: str) -> float:
    """Jaccard word overlap between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def summarize_memory_content(content: dict[str, Any]) -> str:
    """Convert memory content dict to a raw text fragment (no labels, no verbs).

    Used for both embedding computation and context assembly.
    """
    if not content:
        return ""

    # For analysis_insight: face_shape + symmetry + recommendations
    if "face_shape" in content:
        parts = [content["face_shape"], f"symmetry {content.get('symmetry_score', '')}"]
        recs = content.get("recommendations", [])
        if recs:
            parts.extend(recs[:3])
        return ", ".join(str(p) for p in parts if p)

    # For goal/note: use "text" or "description" field
    for key in ("text", "description", "note", "goal"):
        if key in content:
            return str(content[key])

    # Fallback: serialize known string values
    return " ".join(
        str(v) for v in content.values() if isinstance(v, (str, int, float))
    )


class MemoryManager:
    """Manages user memories with pgvector storage and hybrid retrieval."""

    def __init__(
        self,
        advisor_repo: AdvisorRepository,
        llm_adapter: LLMPort,
        embedding_adapter: EmbeddingPort,
    ) -> None:
        self._repo = advisor_repo
        self._llm_adapter = llm_adapter
        self._embedding_adapter = embedding_adapter

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def write_memory(
        self,
        user_id: UUID,
        memory_type: MemoryType,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """Write a new memory row with embedding. Returns the created row.

        Enforces `ADVISOR_MEMORY_CAP` per spec §10: if the user is already at or
        above the cap, evict the oldest non-goal memory before inserting. Goals
        are never auto-evicted — if the user hits the cap with goals only, the
        write still proceeds (overflow logged; intent is preserved).

        Soft-cap race: under concurrent extractions for the same user at the
        boundary, two writes may each pass the count check and each evict one
        row — final count can exceed the cap by one. Acceptable trade-off:
        the cap is a bound on unbounded growth, not a hard invariant, and
        real extraction volume is a few rows per turn.
        """
        await run_sync(self._enforce_memory_cap, user_id)

        text = summarize_memory_content(content)
        embedding = await self._embedding_adapter.compute_embedding(text)

        row = {
            "user_id": str(user_id),
            "type": memory_type.value,
            "content": content,
            "embedding": embedding,
        }

        created = self._repo.insert_memory(row)
        logger.info("Memory written: user=%s type=%s", user_id, memory_type)
        return created

    def _enforce_memory_cap(self, user_id: UUID) -> None:
        """If user is at or above the cap, delete the oldest non-goal memory."""
        cap = settings.ADVISOR_MEMORY_CAP
        try:
            count = self._repo.count_memories(str(user_id))
        except Exception:
            logger.warning(
                "Memory count failed for user %s — skipping cap check",
                user_id,
                exc_info=True,
            )
            return

        if count < cap:
            return

        try:
            evicted = self._repo.delete_oldest_memory_excluding_types(
                str(user_id), exclude_types=(MemoryType.GOAL.value,)
            )
        except Exception:
            logger.warning(
                "Memory eviction failed for user %s",
                user_id,
                exc_info=True,
            )
            return

        if not evicted:
            logger.warning(
                "Memory cap reached with goals only for user %s — accepting overflow",
                user_id,
                extra={
                    "metric": "advisor.memory_cap_goal_only",
                    "user_id": str(user_id),
                    "count": count,
                },
            )

    async def get_relevant_memories(
        self,
        user_id: UUID,
        query: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top-k memories relevant to ``query`` via hybrid scoring.

        Steps:
        1. Compute query embedding
        2. Fetch _CANDIDATE_LIMIT candidates via pgvector RPC
        3. Re-rank with hybrid score (similarity + recency + importance)
        4. Deduplicate by content
        5. Pin the user's latest ``analysis_insight`` at position 0 when
           the hybrid-scored dedup pass did not already include it.
        6. Return top ``limit`` results
        """
        if limit is None:
            limit = settings.ADVISOR_CONTEXT_MEMORY_LIMIT

        embedding = await self._embedding_adapter.compute_embedding(query)

        candidates = self._repo.match_memories(
            str(user_id), embedding, _CANDIDATE_LIMIT
        )

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in candidates:
            similarity = float(row.get("similarity", 0.0))
            if similarity < _MIN_SIMILARITY:
                continue

            recency = _recency_score(row.get("created_at", ""))
            importance = _IMPORTANCE.get(row.get("type", ""), 0.5)
            score = (
                _WEIGHT_SIMILARITY * similarity
                + _WEIGHT_RECENCY * recency
                + _WEIGHT_IMPORTANCE * importance
            )
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Deduplicate by content fingerprint
        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for _, row in scored:
            # M-4: Use SHA-256 instead of MD5 for content dedup fingerprint
            key = _content_fingerprint(row.get("content", ""))
            if key not in seen:
                seen.add(key)
                results.append(row)
            if len(results) >= limit:
                break

        # Always pin the latest analysis_insight — the 0.60 similarity floor
        # can silently drop it for one-noun style queries like "hairstyle",
        # but it is the single most load-bearing memory for style advice.
        latest_insight = self._repo.get_latest_analysis_insight(str(user_id))
        if latest_insight is not None:
            insight_key = _content_fingerprint(latest_insight.get("content", ""))
            if insight_key not in seen:
                pinned = {
                    "type": MemoryType.ANALYSIS_INSIGHT.value,
                    **latest_insight,
                }
                results.insert(0, pinned)
                # Enforce the limit by dropping the last scored item so the
                # pinned row takes its slot.
                if len(results) > limit:
                    results = results[:limit]

        return results

    def list_memories(self, user_id: UUID) -> list[dict[str, Any]]:
        """List all memories for a user (unfiltered, for the /memories endpoint)."""
        return self._repo.get_memories(str(user_id))

    def delete_memory(self, user_id: UUID, memory_id: UUID) -> bool:
        """Delete a memory owned by user_id. Returns True if deleted, False if not found."""
        deleted_rows = self._repo.delete_memory(str(memory_id), str(user_id))
        deleted = len(deleted_rows) > 0
        if deleted:
            logger.info("Memory deleted: user=%s memory=%s", user_id, memory_id)
        return deleted

    async def extract_memories_from_turn(
        self,
        user_id: UUID,
        user_message: str,
        advisor_response: str,
    ) -> None:
        """Extract and store memory signals from a conversation turn (async, Haiku).

        Extracts: goals, accepted suggestions, dismissed suggestions, notes.
        Validates and deduplicates before storage.
        """
        # Build extraction prompt for Haiku
        extraction_prompt = (
            f"User said: {user_message}\n\n"
            f"Advisor replied: {advisor_response}\n\n"
            "Extract any: goals (future intent >5 words), "
            "accepted suggestions (user confirmed trying/doing something), "
            "dismissed suggestions (user rejected), "
            "or notes. "
            'Respond with JSON: {"goals": [...], "accepted": [...], '
            '"dismissed": [...], "notes": [...]}. '
            "Empty arrays if nothing to extract."
        )

        try:
            response = await self._llm_adapter.create_message(
                model=MODEL_HAIKU,
                system="Extract memory signals from the conversation. Return only valid JSON.",
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=300,
            )
            from app.advisor.payload_logger import log_llm_response

            log_llm_response(
                None,
                model=MODEL_HAIKU,
                user_id=user_id,
                conversation_id="-",
                response=response,
                purpose="memory_extract",
            )
            extracted = json.loads(strip_json_code_fence(response.content))
        except Exception as exc:  # includes json.JSONDecodeError and LLM errors
            logger.warning("Memory extraction failed: %s", exc)
            return

        # Fetch recent same-type memories for dedup check (last 7 days)
        recent_rows = self._repo.get_recent_memories(
            str(user_id), _seven_days_ago_iso()
        )
        recent_by_type: dict[str, list[str]] = {}
        for row in recent_rows:
            t = row["type"]
            text = summarize_memory_content(row.get("content", {}))
            recent_by_type.setdefault(t, []).append(text)

        # Process each category
        for goal_text in extracted.get("goals", []):
            words = goal_text.split()
            if len(words) < 5:
                continue
            if _is_duplicate(goal_text, recent_by_type.get(MemoryType.GOAL, [])):
                continue
            await self.write_memory(user_id, MemoryType.GOAL, {"text": goal_text})

        for acc_text in extracted.get("accepted", []):
            markers = ("tried", "did", "got", "went", "bought", "used", "wore", "cut")
            if not any(m in acc_text.lower() for m in markers):
                continue
            if _is_duplicate(
                acc_text, recent_by_type.get(MemoryType.ACCEPTED_SUGGESTION, [])
            ):
                continue
            await self.write_memory(
                user_id, MemoryType.ACCEPTED_SUGGESTION, {"text": acc_text}
            )

        for dis_text in extracted.get("dismissed", []):
            if _is_duplicate(
                dis_text, recent_by_type.get(MemoryType.DISMISSED_SUGGESTION, [])
            ):
                continue
            await self.write_memory(
                user_id, MemoryType.DISMISSED_SUGGESTION, {"text": dis_text}
            )

        for note_text in extracted.get("notes", []):
            if _is_duplicate(note_text, recent_by_type.get(MemoryType.USER_NOTE, [])):
                continue
            await self.write_memory(user_id, MemoryType.USER_NOTE, {"text": note_text})

        # A-18: Note — async extraction is fire-and-forget (create_task in service.py).
        # Out-of-order dedup may miss concurrent extractions for the same turn.
        # Accepted trade-off: duplicate memories are low-impact and naturally
        # deduplicated by the hybrid retrieval scoring.

    async def write_analysis_insight(
        self,
        user_id: UUID,
        face_shape: str,
        symmetry_score: float,
        recommendations: list[str],
        upload_id: str,
    ) -> None:
        """Write an analysis_insight memory after a face analysis completes.

        Upload ownership is verified at the API gate before this job is
        enqueued (see `analyze_glowup` → `GlowupService.create_analysis`,
        which calls `UploadRepository.get_by_id_for_owner_check`). The
        `user_id` passed here comes from the JWT claims, so no secondary
        lookup is required — doing one would cross the upload/image schema
        boundary (uploads.id is not an images.id; see migrations 0001 and
        0034).
        """
        content: dict[str, Any] = {
            "face_shape": face_shape,
            "symmetry_score": symmetry_score,
            "recommendations": recommendations,
            "upload_id": upload_id,
        }
        content["summary"] = summarize_memory_content(content)
        await self.write_memory(user_id, MemoryType.ANALYSIS_INSIGHT, content)

    async def upsert_style_profile(
        self,
        user_id: UUID,
        face_shape: str | None,
        symmetry_score: float | None,
        recommendations: list[str] | None,
    ) -> dict[str, Any]:
        """Upsert the user's stable style_profile row.

        Plan 2026-04-17-003 Unit 7. The profile is the current state
        (one row per user, enforced by the partial unique index in
        migration 0040); ``analysis_insight`` rows remain the immutable
        per-event record.

        Merge semantics: on re-analysis, new fields overwrite existing
        ones and absent fields are preserved. ``last_updated_at`` is
        always refreshed from ``datetime.now(tz=timezone.utc)``. Prevents
        regression if a later analysis returns a thinner payload (e.g.
        the model omits ``recommendations``).

        Cap enforcement does NOT apply — the profile is a single row
        per user and must not be evictable; the cap only governs the
        unbounded extraction types.
        """
        existing = self._repo.get_style_profile(str(user_id))
        merged: dict[str, Any] = dict(existing.get("content", {})) if existing else {}

        if face_shape is not None:
            merged["face_shape"] = face_shape
        if symmetry_score is not None:
            merged["symmetry_score"] = symmetry_score
        if recommendations is not None:
            merged["recommendations"] = recommendations
        merged["last_updated_at"] = datetime.now(tz=timezone.utc).isoformat()

        text = summarize_memory_content(merged)
        embedding = await self._embedding_adapter.compute_embedding(text)

        row = {
            "user_id": str(user_id),
            "type": MemoryType.STYLE_PROFILE.value,
            "content": merged,
            "embedding": embedding,
        }
        result = self._repo.upsert_style_profile(row)
        logger.info("Style profile upserted: user=%s", user_id)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_fingerprint(content: Any) -> str:
    """SHA-256 fingerprint of memory content for dedup + pin matching."""
    return hashlib.sha256(str(content).encode()).hexdigest()


def _is_duplicate(text: str, recent_texts: list[str]) -> bool:
    """Return True if text overlaps >70% with any recent same-type memory."""
    for recent in recent_texts:
        if _word_overlap(text, recent) > _DEDUP_OVERLAP_THRESHOLD:
            return True
    return False


def _seven_days_ago_iso() -> str:
    """Return ISO timestamp for 7 days ago."""
    return (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()
