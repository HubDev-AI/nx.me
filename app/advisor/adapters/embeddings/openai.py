"""OpenAI embedding adapter — calls text-embedding-3-small.

Supports configurable output dimension via the Matryoshka representation
(any value 1..1536 works for `text-embedding-3-small`). The dim is
sourced from `settings.EMBEDDING_DIMENSIONS` so the vector matches the
DB column size.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingAdapter:
    """Computes embeddings via OpenAI's embeddings API."""

    def __init__(self) -> None:
        # Validate config before importing the SDK so misconfigured
        # environments fail with the actionable message instead of
        # ModuleNotFoundError when the openai package isn't installed.
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is required when ADAPTER__EMBEDDING_ADAPTER=openai. "
                "Set it in .env or environment variables."
            )
        import openai

        self._client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.ADVISOR_EMBEDDING_TIMEOUT_SECONDS,
            max_retries=settings.EMBEDDING_MAX_RETRIES,
        )

    async def compute_embedding(self, text: str) -> list[float]:
        """Compute a `settings.EMBEDDING_DIMENSIONS`-dim embedding."""
        response = await self._client.embeddings.create(
            model=settings.ADVISOR_EMBEDDING_MODEL,
            input=text,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        return response.data[0].embedding
