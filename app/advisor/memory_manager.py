"""Memory manager — pgvector read/write + model-driven retrieval.

Handles:
- Writing new memories with embedding + dedup (exact content + semantic).
- Retrieving relevant memories via pgvector + hybrid scoring (called by
  the search_memories MCP tool; no longer auto-invoked every chat turn).
- Writing analysis_insight and style_profile rows from the face-analysis
  pipeline.

Post-refactor note (2026-04-18): the prior Haiku post-turn extraction
path was deleted. Memory writes now go through three explicit sources
— ``authored_by='user'`` (UI), ``authored_by='model'`` (Ada's
save_memory tool), ``authored_by='analysis'`` (face pipeline).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.advisor.embedding_port import EmbeddingPort
from app.advisor.models import MemoryType
from app.config import settings
from app.db.async_helpers import run_sync
from app.repositories.advisor_repo import AdvisorRepository
from app.utils.db_errors import is_unique_violation

logger = logging.getLogger(__name__)

# Hybrid score weights (retrieval re-ranker).
_WEIGHT_SIMILARITY = 0.6
_WEIGHT_RECENCY = 0.3
_WEIGHT_IMPORTANCE = 0.1

# Minimum cosine similarity for a candidate to qualify.
_MIN_SIMILARITY = 0.60

# Importance scores by memory type (retrieval ranker).
_IMPORTANCE: dict[str, float] = {
    MemoryType.GOAL: 1.0,
    MemoryType.ACCEPTED_SUGGESTION: 0.9,
    MemoryType.ANALYSIS_INSIGHT: 0.8,
    MemoryType.USER_NOTE: 0.6,
    MemoryType.DISMISSED_SUGGESTION: 0.4,
}

# pgvector candidate pool size for retrieval.
_CANDIDATE_LIMIT = 15

# Semantic-dedup threshold for write-time duplicate detection. A new
# memory whose cosine similarity against any existing same-type row of
# the same user meets or exceeds this floor is treated as a duplicate
# and skipped. 0.92 is high enough to catch paraphrases of the same
# intent ("grow my hair out" ≈ "growing my hair longer") while still
# accepting genuinely different items within a narrow topic.
_SEMANTIC_DEDUP_THRESHOLD = 0.92


# Write-path provenance. Callers MUST pass one of these values; the
# storage CHECK constraint (migration 0042) enforces it server-side.
VALID_AUTHORED_BY: frozenset[str] = frozenset({"user", "model", "analysis"})


def _recency_score(created_at_str: str) -> float:
    """Compute recency score from an ISO timestamp string."""
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
        embedding_adapter: EmbeddingPort,
    ) -> None:
        self._repo = advisor_repo
        self._embedding_adapter = embedding_adapter

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def write_memory(
        self,
        user_id: UUID,
        memory_type: MemoryType,
        content: dict[str, Any],
        authored_by: str,
    ) -> dict[str, Any]:
        """Write a new memory row with embedding. Returns the created row
        or the existing row on dedup hit.

        Dedup runs before the insert in two stages, cheapest first:
        1. Exact content fingerprint match against same-type rows of the
           same user in the last 30 days. SHA-256 over the serialized
           content. Skips the embedding call when a hit is found.
        2. Semantic similarity match — compute the embedding, run pgvector
           nearest-neighbor against same-user candidates, skip if any
           same-type match is above ``_SEMANTIC_DEDUP_THRESHOLD``.

        On dedup hit the existing row is returned annotated with
        ``_dedup: <reason>`` so callers (the save_memory tool) can
        surface the outcome to the model without a second lookup.

        Enforces ``ADVISOR_MEMORY_CAP``: if the user is at or above the
        cap, evict by authored_by priority before inserting (see
        ``_enforce_memory_cap``). Goals are never auto-evicted.
        """
        if authored_by not in VALID_AUTHORED_BY:
            raise ValueError(
                f"authored_by must be one of {sorted(VALID_AUTHORED_BY)!r}, "
                f"got {authored_by!r}"
            )

        # Stage 1: exact-content dedup. Cheap hash lookup, no network
        # call. Catches the "same user POSTs same goal twice" case
        # before we burn an embedding request. The canonical JSON
        # hash is stored alongside the row in ``content_hash`` so the
        # check is a single indexed query rather than a Python-side
        # scan, AND the partial unique index enforces the same
        # invariant atomically at the DB level (see migration 0042).
        content_hash = _content_fingerprint(content)
        existing_exact = await run_sync(
            self._repo.find_memory_by_content_hash,
            user_id=str(user_id),
            memory_type=memory_type.value,
            content_hash=content_hash,
        )
        if existing_exact is not None:
            logger.info(
                "Memory write deduped (exact): user=%s type=%s",
                user_id,
                memory_type,
            )
            return {**existing_exact, "_dedup": "exact_content"}

        text = summarize_memory_content(content)
        embedding = await self._embedding_adapter.compute_embedding(text)

        # Stage 2: semantic dedup. Find the nearest same-user neighbor
        # of the SAME TYPE and skip if similarity crosses the threshold.
        # We already have the embedding from the line above, so this
        # costs one extra pgvector round-trip.
        semantic_match = await run_sync(
            self._repo.find_semantic_duplicate,
            user_id=str(user_id),
            memory_type=memory_type.value,
            embedding=embedding,
            threshold=_SEMANTIC_DEDUP_THRESHOLD,
        )
        if semantic_match is not None:
            similarity = float(semantic_match.get("similarity", 0.0))
            logger.info(
                "Memory write deduped (semantic %.2f): user=%s type=%s",
                similarity,
                user_id,
                memory_type,
            )
            return {**semantic_match, "_dedup": f"semantic_{similarity:.2f}"}

        await run_sync(self._enforce_memory_cap, user_id)

        row = {
            "user_id": str(user_id),
            "type": memory_type.value,
            "content": content,
            "embedding": embedding,
            "authored_by": authored_by,
            "content_hash": content_hash,
        }

        # TOCTOU backstop: a concurrent writer could have inserted the
        # same (user_id, type, content_hash) between our dedup check
        # and this insert. The unique partial index in migration 0042
        # makes the race impossible at the DB level; on violation we
        # look up the winner and return it as a dedup hit.
        try:
            created = self._repo.insert_memory(row)
        except Exception as exc:
            if is_unique_violation(exc):
                winner = self._repo.find_memory_by_content_hash(
                    user_id=str(user_id),
                    memory_type=memory_type.value,
                    content_hash=content_hash,
                )
                if winner is not None:
                    logger.info(
                        "Memory write deduped (race): user=%s type=%s",
                        user_id,
                        memory_type,
                    )
                    return {**winner, "_dedup": "race"}
            raise
        logger.info(
            "Memory written: user=%s type=%s authored_by=%s",
            user_id,
            memory_type,
            authored_by,
        )
        return created

    def _enforce_memory_cap(self, user_id: UUID) -> None:
        """If user is at or above the cap, evict by authored_by priority.

        Eviction order (first class to find a victim wins):
          1. ``authored_by='model'`` — Ada's own saves go first; she can
             always re-save if the context still calls for it.
          2. ``authored_by='analysis'`` (except ``style_profile`` which
             is singleton-guarded by migration 0040).
          3. ``authored_by='user'`` — user-typed rows are last-resort.
             Even then, ``goal`` is protected and the eviction is skipped
             if every candidate is a goal.
        """
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

        # Try each priority tier in order. Goals are never evicted.
        eviction_priorities: list[dict[str, Any]] = [
            {"authored_by": "model", "exclude_types": (MemoryType.GOAL.value,)},
            {
                "authored_by": "analysis",
                "exclude_types": (
                    MemoryType.GOAL.value,
                    MemoryType.STYLE_PROFILE.value,
                ),
            },
            {"authored_by": "user", "exclude_types": (MemoryType.GOAL.value,)},
        ]
        for tier in eviction_priorities:
            try:
                evicted = self._repo.delete_oldest_memory_by_authored_by(
                    str(user_id),
                    authored_by=tier["authored_by"],
                    exclude_types=tier["exclude_types"],
                )
            except Exception:
                logger.warning(
                    "Memory eviction failed for user %s tier=%s",
                    user_id,
                    tier["authored_by"],
                    exc_info=True,
                )
                return
            if evicted:
                return

        # Every tier is empty of evictable rows — the user's memory is
        # entirely goals. Accept the overflow; goals represent declared
        # intent and the cap is a soft guard, not a hard invariant.
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

        Called only by the ``search_memories`` MCP tool. Not invoked
        automatically on chat turns — the model decides when a memory
        lookup is worth the cost.

        Steps:
        1. Compute query embedding.
        2. Fetch up to ``_CANDIDATE_LIMIT`` candidates via pgvector RPC.
        3. Re-rank with hybrid score (similarity + recency + importance).
        4. Deduplicate by content fingerprint.
        5. Excludes ``style_profile`` rows: those are always rendered
           into the chat turn's ``user_data`` system block, so surfacing
           them again via search would duplicate context.
        """
        if limit is None:
            limit = settings.ADVISOR_CONTEXT_MEMORY_LIMIT

        embedding = await self._embedding_adapter.compute_embedding(query)

        candidates = self._repo.match_memories(
            str(user_id), embedding, _CANDIDATE_LIMIT
        )

        scored: list[tuple[float, dict[str, Any]]] = []
        for row in candidates:
            if row.get("type") == MemoryType.STYLE_PROFILE.value:
                continue
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

        seen: set[str] = set()
        results: list[dict[str, Any]] = []
        for _, row in scored:
            key = _content_fingerprint(row.get("content", {}))
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
        """Delete a memory owned by user_id. Returns True if deleted."""
        deleted_rows = self._repo.delete_memory(str(memory_id), str(user_id))
        deleted = len(deleted_rows) > 0
        if deleted:
            logger.info("Memory deleted: user=%s memory=%s", user_id, memory_id)
        return deleted

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
        enqueued (see ``analyze_glowup`` → ``GlowupService.create_analysis``).
        The ``user_id`` passed here comes from the JWT claims, so no
        secondary lookup is required.
        """
        content: dict[str, Any] = {
            "face_shape": face_shape,
            "symmetry_score": symmetry_score,
            "recommendations": recommendations,
            "upload_id": upload_id,
        }
        content["summary"] = summarize_memory_content(content)
        await self.write_memory(
            user_id,
            MemoryType.ANALYSIS_INSIGHT,
            content,
            authored_by="analysis",
        )

    async def upsert_style_profile(
        self,
        user_id: UUID,
        face_shape: str | None,
        symmetry_score: float | None,
        recommendations: list[str] | None,
    ) -> dict[str, Any]:
        """Upsert the user's stable style_profile row.

        The profile is the current state (one row per user, enforced by
        the partial unique index in migration 0040); ``analysis_insight``
        rows remain the immutable per-event record.

        Merge semantics: on re-analysis, new fields overwrite existing
        ones and absent fields are preserved. ``last_updated_at`` is
        always refreshed. Prevents regression if a later analysis returns
        a thinner payload (e.g. the model omits ``recommendations``).

        Cap enforcement does NOT apply — the profile is a single row per
        user and must not be evictable.
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
            "authored_by": "analysis",
        }
        result = self._repo.upsert_style_profile(row)
        logger.info("Style profile upserted: user=%s", user_id)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_fingerprint(content: Any) -> str:
    """SHA-256 fingerprint of memory content for dedup.

    Canonicalizes via ``json.dumps(sort_keys=True, default=str)`` so two
    dicts with identical values but different key insertion order produce
    the same hash. Matters because Postgres JSONB does not preserve key
    order on round-trip; without canonicalization the write-side hash
    and any read-side hash could diverge.
    """
    canonical = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
