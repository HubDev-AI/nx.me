"""Mock LLM adapter — deterministic chat responses for testing.

Returns canned responses. No Anthropic API calls. Embeddings live in a
sibling adapter (`adapters/embeddings/mock.py`) so chat and embedding
mocks can be combined freely with real adapters.

Plan 2026-04-17-003 Unit 9 — the mock simulates the tool-use loop when
``tools`` + ``tool_registry`` are supplied. Callers can drive a specific
tool-use → tool_result → final-text sequence by setting
``MockLLMAdapter.tool_use_script`` — see the docstring on that attribute.
"""

from __future__ import annotations

import logging
from typing import Any

from app.advisor.mcp.registry import TOOL_ROUND_CAP_EXCEEDED_MARKER
from app.advisor.models import LLMResponse
from app.config import settings

logger = logging.getLogger(__name__)

_MOCK_RESPONSE = "Yeah, that works for your face shape."
_MOCK_HAIKU_RESPONSE = "Keep it simple — your proportions do the work."
_MOCK_NUDGE_RESPONSE = "You've been making good progress. Next I'd look at the brows."

# Prefixes/Ids used by the simulated tool-use loop. Extracted as named
# constants so tests can assert on them without duplicating magic strings.
MOCK_TOOL_USE_ID_PREFIX = "mocktu_"
MOCK_FINAL_TEXT_AFTER_TOOLS = "Based on what I just pulled in, that works for you."


class MockLLMAdapter:
    """Returns deterministic responses. No network calls.

    ``tool_use_script`` is a list-of-lists: each inner list is one model
    turn's tool_use blocks (dicts with ``name`` + ``input``). The mock
    emits the tools for that turn, the caller dispatches them, and on the
    next call the mock pops the next sub-list until the script is empty —
    at which point the mock emits the canned final text. This mirrors
    the real Anthropic adapter's ``stop_reason == "tool_use"`` loop
    exactly as far as the service layer is concerned.
    """

    def __init__(self) -> None:
        # Per-adapter script. Tests set this before calling create_message.
        # Outer list = rounds; inner list = tool_use blocks for that round.
        self.tool_use_script: list[list[dict[str, Any]]] = []
        # Response text the mock returns once the script is exhausted.
        # Exposed so tests can assert on the exact final message.
        self.final_response_text: str | None = None
        # Internal per-instance counter so sequential adapter calls step
        # through the script.
        self._script_cursor = 0
        # Captured kwargs from every create_message call — tests assert
        # that ``tools`` schemas were threaded through.
        self.calls: list[dict[str, Any]] = []

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
        """Return a canned response based on model.

        When ``tools`` + ``tool_registry`` are supplied, simulate the
        tool-use loop: dispatch the script's pending tool_use blocks,
        step the cursor, and recurse until the script is exhausted.
        """
        # Record every call for test introspection.
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": list(messages),
                "max_tokens": max_tokens,
                "vision_content": vision_content,
                "tools": tools,
                "tool_registry": tool_registry,
            }
        )

        if tools and tool_registry is not None and self.tool_use_script:
            return await self._simulate_tool_loop(
                model=model,
                tools=tools,
                tool_registry=tool_registry,
                messages=messages,
                max_tokens=max_tokens,
            )

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

    async def _simulate_tool_loop(
        self,
        *,
        model: str,
        tools: list[dict[str, Any]],
        tool_registry: Any,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> LLMResponse:
        """Walk the scripted tool rounds, dispatching each via the registry.

        Behaviour mirrors the real adapter:
        * For each round in ``tool_use_script`` (up to
          ``ADVISOR_MAX_TOOL_ROUNDS``), build the tool_use blocks, call
          ``tool_registry.dispatch`` for each, and track the returned
          tool_result content.
        * If the script has more rounds than the cap, the over-cap
          tool_use blocks receive ``TOOL_ROUND_CAP_EXCEEDED_MARKER``
          tool_results with ``is_error=True``.
        * After the loop, return the configured final text.
        """
        cap = max(1, int(settings.ADVISOR_MAX_TOOL_ROUNDS))
        script = self.tool_use_script
        total_rounds = len(script)
        rounds_to_run = min(cap, total_rounds)

        executed_results: list[list[dict[str, Any]]] = []
        self.tool_dispatch_log: list[tuple[str, dict[str, Any]]] = []

        for round_idx in range(rounds_to_run):
            round_blocks = script[round_idx]
            round_results: list[dict[str, Any]] = []
            for block_idx, tool_use in enumerate(round_blocks):
                name = str(tool_use.get("name") or "")
                raw_inputs = dict(tool_use.get("input") or {})
                self.tool_dispatch_log.append((name, raw_inputs))
                payload = await tool_registry.dispatch(name, raw_inputs)
                envelope: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": f"{MOCK_TOOL_USE_ID_PREFIX}{round_idx}_{block_idx}",
                    "content": payload.get("content", []),
                }
                if payload.get("is_error"):
                    envelope["is_error"] = True
                round_results.append(envelope)
            executed_results.append(round_results)

        # Over-cap rounds — synthesize round-cap errors so tests can
        # assert on the marker. The mock records these in
        # ``over_cap_tool_results`` for inspection; the real adapter
        # sends them back to the model inside the final user message.
        self.over_cap_tool_results: list[dict[str, Any]] = []
        for round_idx in range(rounds_to_run, total_rounds):
            for block_idx, tool_use in enumerate(script[round_idx]):
                self.over_cap_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": f"{MOCK_TOOL_USE_ID_PREFIX}capped_{round_idx}_{block_idx}",
                        "content": TOOL_ROUND_CAP_EXCEEDED_MARKER,
                        "is_error": True,
                    }
                )

        self.executed_tool_results = executed_results

        final_text = self.final_response_text
        if final_text is None:
            final_text = MOCK_FINAL_TEXT_AFTER_TOOLS
        return LLMResponse(content=final_text, input_tokens=10, output_tokens=8)
