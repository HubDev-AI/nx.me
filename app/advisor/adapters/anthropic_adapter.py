"""Anthropic LLM adapter — real Claude API calls.

Uses claude-3-5-sonnet for chat and claude-3-haiku for memory extraction/nudges.
Lazy-imports anthropic SDK so tests don't require the package installed.
"""
from __future__ import annotations

import logging
from typing import Any

from app.advisor.models import LLMResponse
from app.config import settings

logger = logging.getLogger(__name__)

# Embedding dimensions (fixed for text-embedding-3-small)
_EMBEDDING_DIMENSIONS = 1536


class AnthropicAdapter:
    """Real Anthropic adapter — calls Claude API and OpenAI embeddings."""

    def __init__(self) -> None:
        import anthropic
        import httpx
        import openai

        self._anthropic = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=httpx.Timeout(settings.ADVISOR_LLM_TIMEOUT_SECONDS),
        )
        # A-4: Fail fast if OPENAI_API_KEY missing — embeddings are required
        openai_key = settings.OPENAI_API_KEY
        if not openai_key:
            raise ValueError(
                "OPENAI_API_KEY is required for advisor embeddings. "
                "Set it in .env or environment variables."
            )
        self._openai = openai.AsyncOpenAI(
            api_key=openai_key,
            timeout=settings.ADVISOR_EMBEDDING_TIMEOUT_SECONDS,
        )

    async def create_message(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        vision_content: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send a conversation to Claude and return the response.

        The ``system`` parameter is passed as the Anthropic system prompt.
        ``messages`` is the conversation history (role/content pairs).
        ``vision_content`` is appended to the last user message as image blocks.
        """
        # Anthropic API: system is a top-level param, not a message role.
        # Filter out system messages from the messages list and collect them.
        system_parts: list[str] = [system]
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(str(msg.get("content", "")))
            else:
                api_messages.append(msg)

        combined_system = "\n\n".join(p for p in system_parts if p)

        # If vision_content provided, extend last user message
        if vision_content and api_messages:
            last = api_messages[-1]
            if last.get("role") == "user":
                text_content = last["content"]
                api_messages[-1] = {
                    "role": "user",
                    "content": [{"type": "text", "text": text_content}] + vision_content,
                }

        response = await self._anthropic.messages.create(
            model=model,
            system=combined_system,
            messages=api_messages,
            max_tokens=max_tokens,
        )

        content = ""
        if response.content:
            content = response.content[0].text if hasattr(response.content[0], "text") else str(response.content[0])

        logger.info(
            "Anthropic response: model=%s, input_tokens=%d, output_tokens=%d",
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def compute_embedding(self, text: str) -> list[float]:
        """Compute a 1536-dim text embedding via OpenAI text-embedding-3-small."""
        response = await self._openai.embeddings.create(
            model=settings.ADVISOR_EMBEDDING_MODEL,
            input=text,
            dimensions=_EMBEDDING_DIMENSIONS,
        )
        return response.data[0].embedding
