"""Ollama embedding adapter — calls a local Ollama server.

POSTs to `{OLLAMA_BASE_URL}/api/embeddings` with the configured model.
Default model is `nomic-embed-text` (768-dim native), which matches the
DB column dimension set by migration 0020.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_OLLAMA_EMBEDDINGS_PATH = "/api/embeddings"


class OllamaEmbeddingAdapter:
    """Computes embeddings via a local Ollama server."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout=settings.ADVISOR_EMBEDDING_TIMEOUT_SECONDS,
        )

    async def compute_embedding(self, text: str) -> list[float]:
        """Compute a `settings.EMBEDDING_DIMENSIONS`-dim embedding via Ollama.

        Raises if the server is unreachable, returns a malformed payload, or
        emits a vector whose length differs from the configured dimension —
        better to fail loud than silently insert wrong-shape rows that the
        DB column will reject anyway.
        """
        try:
            response = await self._client.post(
                _OLLAMA_EMBEDDINGS_PATH,
                json={"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": text},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"Ollama embedding call failed: {exc}. Is Ollama running at "
                f"{settings.OLLAMA_BASE_URL}? Pull the model with "
                f"`ollama pull {settings.OLLAMA_EMBEDDING_MODEL}`."
            ) from exc

        payload: dict[str, Any] = response.json()
        embedding = payload.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError(
                f"Ollama returned unexpected payload (no 'embedding' list): {payload!r}"
            )

        if len(embedding) != settings.EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Ollama model {settings.OLLAMA_EMBEDDING_MODEL!r} returned "
                f"{len(embedding)}-dim vector but EMBEDDING_DIMENSIONS="
                f"{settings.EMBEDDING_DIMENSIONS}. Either change the model "
                f"or the EMBEDDING_DIMENSIONS setting (and re-run migration)."
            )

        return embedding
