"""Embedding adapter port (Protocol) — port/adapter pattern.

Decoupled from `LLMPort` so the advisor can pair any chat model with any
embedding backend (e.g. Anthropic chat + Ollama embeddings for local dev,
or Anthropic chat + OpenAI embeddings for production).

Concrete implementations: OpenAIEmbeddingAdapter, OllamaEmbeddingAdapter,
MockEmbeddingAdapter.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingPort(Protocol):
    """Port for text embedding inference."""

    async def compute_embedding(self, text: str) -> list[float]:
        """Compute a text embedding vector. Length must equal
        ``settings.EMBEDDING_DIMENSIONS`` (= the DB column dim).
        """
        ...
