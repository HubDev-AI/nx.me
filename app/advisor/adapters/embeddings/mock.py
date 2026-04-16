"""Mock embedding adapter — deterministic unit vectors for testing.

Seeded from the input text so identical inputs produce identical vectors.
Length tracks `settings.EMBEDDING_DIMENSIONS` so tests stay in sync with
the DB column dimension.
"""

from __future__ import annotations

import hashlib
import random

from app.config import settings


class MockEmbeddingAdapter:
    """Returns a deterministic unit vector seeded from text."""

    async def compute_embedding(self, text: str) -> list[float]:
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(settings.EMBEDDING_DIMENSIONS)]
        # Normalize — pgvector cosine similarity NaNs on the zero vector.
        norm = sum(x * x for x in vec) ** 0.5
        return [x / norm for x in vec]
