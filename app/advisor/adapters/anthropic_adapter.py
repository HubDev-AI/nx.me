"""Anthropic LLM adapter — real Claude API calls (chat only).

Uses claude-3-5-sonnet for chat and claude-3-haiku for memory extraction/nudges.
Lazy-imports anthropic SDK so tests don't require the package installed.

Embeddings are NOT handled here — pick an embedding backend separately via
`ADAPTER__EMBEDDING_ADAPTER` (openai | ollama | mock).
"""

from __future__ import annotations

import logging
from typing import Any

from app.advisor.models import LLMResponse
from app.config import settings

logger = logging.getLogger(__name__)


class AnthropicAdapter:
    """Real Anthropic adapter — calls Claude API for chat."""

    def __init__(self) -> None:
        import anthropic
        import httpx

        self._anthropic = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=httpx.Timeout(settings.ADVISOR_LLM_TIMEOUT_SECONDS),
            max_retries=settings.LLM_MAX_RETRIES,
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
        # Filter system messages out, normalize internal "advisor" role to
        # Claude's "assistant", and strip any extra fields (id, created_at,
        # etc.) that leak from DB rows — Anthropic rejects unknown keys.
        # `content` may be a string or a list of content blocks (vision);
        # pass through untouched.
        system_parts: list[str] = [system]
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role")
            if role == "system":
                system_parts.append(str(msg.get("content", "")))
                continue
            api_role = "user" if role == "user" else "assistant"
            api_messages.append({"role": api_role, "content": msg["content"]})

        combined_system = "\n\n".join(p for p in system_parts if p)

        # If vision_content provided, extend last user message
        if vision_content and api_messages:
            last = api_messages[-1]
            if last.get("role") == "user":
                text_content = last["content"]
                api_messages[-1] = {
                    "role": "user",
                    "content": [{"type": "text", "text": text_content}]
                    + vision_content,
                }

        response = await self._anthropic.messages.create(
            model=model,
            system=combined_system,
            messages=api_messages,
            max_tokens=max_tokens,
        )

        content = ""
        if response.content:
            content = (
                response.content[0].text
                if hasattr(response.content[0], "text")
                else str(response.content[0])
            )

        logger.debug(
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
