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

from app.advisor.llm_port import LLMPort

from app.advisor.models import MemoryType
from app.advisor.nudge_policy import MODEL_HAIKU
from app.config import settings
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
    return " ".join(str(v) for v in content.values() if isinstance(v, (str, int, float)))


class MemoryManager:
    """Manages user memories with pgvector storage and hybrid retrieval."""

    def __init__(self, advisor_repo: AdvisorRepository, llm_adapter: LLMPort) -> None:
        self._repo = advisor_repo
        self._llm_adapter = llm_adapter

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def write_memory(
        self,
        user_id: UUID,
        memory_type: MemoryType,
        content: dict[str, Any],
    ) -> dict[str, Any]:
        """Write a new memory row with embedding. Returns the created row."""
        text = summarize_memory_content(content)
        embedding = await self._llm_adapter.compute_embedding(text)

        row = {
            "user_id": str(user_id),
            "type": memory_type.value,
            "content": content,
            "embedding": embedding,
        }

        created = self._repo.insert_memory(row)
        logger.info("Memory written: user=%s type=%s", user_id, memory_type)
        return created

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
        5. Return top ``limit`` results
        """
        if limit is None:
            limit = settings.ADVISOR_CONTEXT_MEMORY_LIMIT

        embedding = await self._llm_adapter.compute_embedding(query)

        candidates = self._repo.match_memories(str(user_id), embedding, _CANDIDATE_LIMIT)

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
            key = hashlib.md5(str(row.get("content", "")).encode()).hexdigest()
            if key not in seen:
                seen.add(key)
                results.append(row)
            if len(results) >= limit:
                break

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
            "Respond with JSON: {\"goals\": [...], \"accepted\": [...], "
            "\"dismissed\": [...], \"notes\": [...]}. "
            "Empty arrays if nothing to extract."
        )

        try:
            response = await self._llm_adapter.create_message(
                model=MODEL_HAIKU,
                system="Extract memory signals from the conversation. Return only valid JSON.",
                messages=[{"role": "user", "content": extraction_prompt}],
                max_tokens=300,
            )
            extracted = json.loads(response.content)
        except Exception as exc:  # includes json.JSONDecodeError and LLM errors
            logger.warning("Memory extraction failed: %s", exc)
            return

        # Fetch recent same-type memories for dedup check (last 7 days)
        recent_rows = self._repo.get_recent_memories(str(user_id), _seven_days_ago_iso())
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
            if _is_duplicate(acc_text, recent_by_type.get(MemoryType.ACCEPTED_SUGGESTION, [])):
                continue
            await self.write_memory(user_id, MemoryType.ACCEPTED_SUGGESTION, {"text": acc_text})

        for dis_text in extracted.get("dismissed", []):
            if _is_duplicate(dis_text, recent_by_type.get(MemoryType.DISMISSED_SUGGESTION, [])):
                continue
            await self.write_memory(user_id, MemoryType.DISMISSED_SUGGESTION, {"text": dis_text})

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
        image_id: str,
    ) -> None:
        """Write an analysis_insight memory after a face analysis completes."""
        # L-6: Verify image belongs to user before storing insight
        try:
            image_data = (
                self._repo._sb.table("images")
                .select("user_id")
                .eq("id", image_id)
                .maybe_single()
                .execute()
            )
            if image_data.data and image_data.data.get("user_id") != str(user_id):
                logger.warning("Image %s does not belong to user %s, skipping insight", image_id, user_id)
                return
        except Exception as exc:
            # A-8: Log and skip instead of proceeding with unverified data
            logger.warning(
                "Could not verify image ownership for %s — skipping insight storage: %s",
                image_id, exc,
            )
            return

        content: dict[str, Any] = {
            "face_shape": face_shape,
            "symmetry_score": symmetry_score,
            "recommendations": recommendations,
            "image_id": image_id,
        }
        await self.write_memory(user_id, MemoryType.ANALYSIS_INSIGHT, content)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_duplicate(text: str, recent_texts: list[str]) -> bool:
    """Return True if text overlaps >70% with any recent same-type memory."""
    for recent in recent_texts:
        if _word_overlap(text, recent) > _DEDUP_OVERLAP_THRESHOLD:
            return True
    return False


def _seven_days_ago_iso() -> str:
    """Return ISO timestamp for 7 days ago."""
    return (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()
