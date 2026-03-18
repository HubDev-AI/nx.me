"""Mock LLM adapter — deterministic results for testing.

Returns canned responses. No Anthropic API calls. Zero vector for embeddings.
"""
from __future__ import annotations

import logging
from typing import Any

from app.advisor.models import LLMResponse

logger = logging.getLogger(__name__)

_MOCK_RESPONSE = "Yeah, that works for your face shape."
_MOCK_HAIKU_RESPONSE = "Keep it simple — your proportions do the work."
_MOCK_NUDGE_RESPONSE = "You've been making good progress. Next I'd look at the brows."


class MockLLMAdapter:
    """Returns deterministic responses. No network calls."""

    async def create_message(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        vision_content: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Return a canned response based on model."""
        if "haiku" in model.lower():
            content = _MOCK_HAIKU_RESPONSE
        else:
            content = _MOCK_RESPONSE

        logger.info(
            "Mock LLM: model=%s, messages=%d, max_tokens=%d",
            model,
            len(messages),
            max_tokens,
        )
        return LLMResponse(content=content, input_tokens=10, output_tokens=8)

    async def compute_embedding(self, text: str) -> list[float]:
        """Return zero vector (1536d) — no OpenAI calls."""
        logger.debug("Mock embedding for text length=%d", len(text))
        return [0.0] * 1536
