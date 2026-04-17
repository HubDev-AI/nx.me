"""LLM adapter port (Protocol) — port/adapter pattern.

Consumers depend on LLMPort, not on any concrete adapter. Embeddings live
behind a separate `EmbeddingPort` so chat backends and embedding backends
can be selected independently.

Plan 2026-04-17-003 Unit 9: ``create_message`` accepts an optional
``tools`` parameter and an optional ``tool_registry``. When both are
supplied, the adapter runs the tool-use loop internally — dispatching
each ``tool_use`` block through the registry and submitting
``tool_result`` blocks until either the model emits final text or the
loop hits ``ADVISOR_MAX_TOOL_ROUNDS``. The returned ``LLMResponse`` is
still the final model text — the service layer is insulated from the
tool-use choreography.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.advisor.models import LLMResponse


@runtime_checkable
class LLMPort(Protocol):
    """Port for LLM chat inference.

    Concrete implementations: AnthropicAdapter (production), MockLLMAdapter (testing).
    """

    async def create_message(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        vision_content: list[dict[str, Any]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_registry: Any | None = None,
    ) -> LLMResponse:
        """Send messages to the LLM and return the response.

        ``tools`` carries Anthropic-compatible tool schemas (what
        ``ToolRegistry.schemas()`` returns). When ``tool_registry`` is
        also provided, the adapter runs the tool-use loop inline — the
        service layer sees only the final text and never interacts with
        the intermediate ``tool_use`` / ``tool_result`` exchange.
        """
        ...
