"""Tests for the embedding adapters (mock / ollama / openai).

Each adapter implements the EmbeddingPort Protocol. The mock adapter is
deterministic and self-contained; ollama + openai are tested via httpx
mocks so no real API calls fire.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings


# ---------------------------------------------------------------------------
# Mock embedding adapter
# ---------------------------------------------------------------------------


class TestMockEmbeddingAdapter:
    @pytest.mark.asyncio
    async def test_returns_unit_vector_of_configured_dim(self):
        from app.advisor.adapters.embeddings.mock import MockEmbeddingAdapter

        adapter = MockEmbeddingAdapter()
        vec = await adapter.compute_embedding("hello world")

        assert len(vec) == settings.EMBEDDING_DIMENSIONS
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-6, "expected unit-length vector"

    @pytest.mark.asyncio
    async def test_deterministic(self):
        from app.advisor.adapters.embeddings.mock import MockEmbeddingAdapter

        adapter = MockEmbeddingAdapter()
        v1 = await adapter.compute_embedding("identical text")
        v2 = await adapter.compute_embedding("identical text")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_different_text_produces_different_vector(self):
        from app.advisor.adapters.embeddings.mock import MockEmbeddingAdapter

        adapter = MockEmbeddingAdapter()
        v1 = await adapter.compute_embedding("apple")
        v2 = await adapter.compute_embedding("banana")
        assert v1 != v2


# ---------------------------------------------------------------------------
# Ollama embedding adapter
# ---------------------------------------------------------------------------


class TestOllamaEmbeddingAdapter:
    @pytest.mark.asyncio
    async def test_posts_to_correct_url_and_returns_embedding(self):
        from app.advisor.adapters.embeddings.ollama import OllamaEmbeddingAdapter

        expected_vec = [0.1] * settings.EMBEDDING_DIMENSIONS

        async def fake_post(self, url, json=None, **kwargs):
            assert url == "/api/embeddings"
            assert json["model"] == settings.OLLAMA_EMBEDDING_MODEL
            assert json["prompt"] == "hello"
            response = httpx.Response(200, json={"embedding": expected_vec})
            response._request = httpx.Request("POST", url)
            return response

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            adapter = OllamaEmbeddingAdapter()
            vec = await adapter.compute_embedding("hello")

        assert vec == expected_vec

    @pytest.mark.asyncio
    async def test_raises_when_dim_mismatches(self):
        from app.advisor.adapters.embeddings.ollama import OllamaEmbeddingAdapter

        async def fake_post(self, url, json=None, **kwargs):
            response = httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
            response._request = httpx.Request("POST", url)
            return response

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            adapter = OllamaEmbeddingAdapter()
            with pytest.raises(RuntimeError, match="EMBEDDING_DIMENSIONS"):
                await adapter.compute_embedding("hello")

    @pytest.mark.asyncio
    async def test_raises_clear_message_on_network_error(self):
        from app.advisor.adapters.embeddings.ollama import OllamaEmbeddingAdapter

        async def fake_post(self, url, json=None, **kwargs):
            raise httpx.ConnectError("refused")

        with patch.object(httpx.AsyncClient, "post", new=fake_post):
            adapter = OllamaEmbeddingAdapter()
            with pytest.raises(RuntimeError, match="Ollama embedding call failed"):
                await adapter.compute_embedding("hello")


# ---------------------------------------------------------------------------
# OpenAI embedding adapter
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddingAdapter:
    def test_init_fails_without_api_key(self):
        from app.advisor.adapters.embeddings.openai import OpenAIEmbeddingAdapter

        with patch("app.config.settings.OPENAI_API_KEY", ""):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                OpenAIEmbeddingAdapter()

    @pytest.mark.asyncio
    async def test_calls_openai_with_configured_dim(self):
        pytest.importorskip("openai")
        from app.advisor.adapters.embeddings.openai import OpenAIEmbeddingAdapter

        expected_vec = [0.2] * settings.EMBEDDING_DIMENSIONS
        with patch("app.config.settings.OPENAI_API_KEY", "sk-test"):
            adapter = OpenAIEmbeddingAdapter()

        fake_response = AsyncMock()
        fake_response.data = [type("Datum", (), {"embedding": expected_vec})()]

        adapter._client.embeddings.create = AsyncMock(return_value=fake_response)

        vec = await adapter.compute_embedding("hello")

        adapter._client.embeddings.create.assert_awaited_once_with(
            model=settings.ADVISOR_EMBEDDING_MODEL,
            input="hello",
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        assert vec == expected_vec
