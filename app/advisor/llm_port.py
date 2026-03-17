"""LLM adapter port (Protocol) — port/adapter pattern.

Consumers depend on LLMPort, not on any concrete adapter.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.advisor.models import LLMResponse


@runtime_checkable
class LLMPort(Protocol):
    """Port for LLM inference.

    Concrete implementations: AnthropicAdapter (production), MockLLMAdapter (testing).
    """

    async def create_message(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        vision_content: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and return the response."""
        ...
