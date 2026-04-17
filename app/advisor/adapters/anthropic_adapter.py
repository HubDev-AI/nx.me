"""Anthropic LLM adapter — real Claude API calls (chat only).

Uses claude-3-5-sonnet for chat and claude-3-haiku for memory extraction/nudges.
Lazy-imports anthropic SDK so tests don't require the package installed.

Embeddings are NOT handled here — pick an embedding backend separately via
`ADAPTER__EMBEDDING_ADAPTER` (openai | ollama | mock).

Plan 2026-04-17-003 Unit 9 — tool-use loop:

When ``tools`` + ``tool_registry`` are supplied, the adapter issues the
first ``messages.create`` call with the tool schemas attached, inspects
``stop_reason``, dispatches every ``tool_use`` block through the
registry, appends the returned ``tool_result`` content to the message
list, and re-calls. The loop runs up to ``ADVISOR_MAX_TOOL_ROUNDS``
rounds; on cap exhaustion, any remaining tool_use blocks receive a
synthetic ``is_error=True`` tool_result with a round-cap marker so the
model can still finalize its text rather than leaving pending
tool_use blocks dangling.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from app.advisor.mcp.registry import TOOL_ROUND_CAP_EXCEEDED_MARKER
from app.advisor.models import LLMResponse
from app.config import settings

logger = logging.getLogger(__name__)

_REDACTED_IMAGE_SOURCE = "<redacted-image-source>"


def _redact_image_sources(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a deep-copied messages array with every image block's source
    replaced by a placeholder.

    Image sources are either ephemeral signed Supabase URLs or raw base64
    payloads. Neither belongs in a log stream if DEBUG ever gets shipped to
    a collector — the URLs can be replayed while they're live and the
    base64 blobs make the logs unreadable.

    Plan Unit 9 extension: the redaction now also walks ``tool_result``
    blocks, since the new tool surface returns image content inside tool
    results (not only inside the user message's top-level content list).
    """
    redacted = copy.deepcopy(messages)
    for msg in redacted:
        _redact_in_content(msg.get("content"))
    return redacted


def _redact_in_content(content: Any) -> None:
    """Walk a content list in place, redacting every image ``source`` field.

    Handles both the top-level image block shape and images nested inside
    ``tool_result`` blocks (whose ``content`` is itself a list of blocks).
    ``tool_use`` blocks never carry image data — their ``input`` is JSON —
    so they are left untouched.
    """
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "image":
            block["source"] = _REDACTED_IMAGE_SOURCE
            continue
        if block_type == "tool_result":
            _redact_in_content(block.get("content"))


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
        tools: list[dict[str, Any]] | None = None,
        tool_registry: Any | None = None,
    ) -> LLMResponse:
        """Send a conversation to Claude and return the response.

        The ``system`` parameter is passed as the Anthropic system prompt.
        ``messages`` is the conversation history (role/content pairs).
        ``vision_content`` is appended to the last user message as image blocks.
        ``tools`` + ``tool_registry`` (Plan Unit 9) enable the inline
        tool-use loop.
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

        # -------------------------------------------------------------
        # Single-shot path (no tool_registry): unchanged from pre-Unit-9.
        # -------------------------------------------------------------
        if not (tools and tool_registry is not None):
            return await self._single_call(
                model=model,
                combined_system=combined_system,
                api_messages=api_messages,
                max_tokens=max_tokens,
                tools=tools,
            )

        # -------------------------------------------------------------
        # Tool-use loop (Plan Unit 9).
        # -------------------------------------------------------------
        return await self._tool_use_loop(
            model=model,
            combined_system=combined_system,
            api_messages=api_messages,
            max_tokens=max_tokens,
            tools=tools,
            tool_registry=tool_registry,
        )

    async def _single_call(
        self,
        *,
        model: str,
        combined_system: str,
        api_messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
    ) -> LLMResponse:
        """One ``messages.create`` call with no tool-use choreography."""
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "Anthropic request: model=%s max_tokens=%d\nsystem=%s\nmessages=%s",
                model,
                max_tokens,
                combined_system,
                json.dumps(
                    _redact_image_sources(api_messages),
                    default=str,
                    ensure_ascii=False,
                ),
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "system": combined_system,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        response = await self._anthropic.messages.create(**kwargs)

        content = _extract_text_from_response(response)

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

    async def _tool_use_loop(
        self,
        *,
        model: str,
        combined_system: str,
        api_messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]],
        tool_registry: Any,
    ) -> LLMResponse:
        """Run the agentic tool-use loop until final text or round cap.

        Contract: the returned ``LLMResponse.content`` is the model's
        final text after all tool rounds. Input / output tokens are
        summed across all rounds — the service's token estimate
        logging should reflect the real cost, not the first call only.
        """
        max_rounds = max(1, int(settings.ADVISOR_MAX_TOOL_ROUNDS))
        rounds = 0
        total_input_tokens = 0
        total_output_tokens = 0

        messages = list(api_messages)

        while True:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "Anthropic tool-use request (round %d): model=%s "
                    "max_tokens=%d\nsystem=%s\nmessages=%s",
                    rounds,
                    model,
                    max_tokens,
                    combined_system,
                    json.dumps(
                        _redact_image_sources(messages),
                        default=str,
                        ensure_ascii=False,
                    ),
                )

            response = await self._anthropic.messages.create(
                model=model,
                system=combined_system,
                messages=messages,
                max_tokens=max_tokens,
                tools=tools,
            )
            total_input_tokens += int(getattr(response.usage, "input_tokens", 0))
            total_output_tokens += int(getattr(response.usage, "output_tokens", 0))

            stop_reason = getattr(response, "stop_reason", None)

            if stop_reason != "tool_use":
                return LLMResponse(
                    content=_extract_text_from_response(response),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

            # The model wants one or more tools. Record the assistant's
            # turn verbatim (including tool_use blocks — Anthropic needs
            # them on the next call so the tool_result IDs match).
            assistant_content = _response_content_as_plain(response.content)
            messages.append({"role": "assistant", "content": assistant_content})

            tool_use_blocks = [
                b for b in assistant_content if b.get("type") == "tool_use"
            ]

            # If stop_reason said tool_use but no actual tool_use blocks
            # survived (e.g. thinking-only content, or an SDK quirk),
            # submitting an empty user content array is a hard Anthropic
            # validation error. Treat this round as final and return the
            # text we already have — the assistant turn is already
            # recorded in ``messages`` for cache continuity.
            if not tool_use_blocks:
                return LLMResponse(
                    content=_extract_text_from_response(response),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

            tool_results: list[dict[str, Any]] = []
            if rounds + 1 >= max_rounds:
                # Cap will be hit by the NEXT call's results; if this
                # round's tool_use blocks execute, we still would need
                # another model call to let the model finalize. So we
                # stop here: every tool_use gets a round-cap error
                # tool_result, we send one final turn with no tools
                # available, and let the model produce the final text.
                for block in tool_use_blocks:
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.get("id", ""),
                            "content": TOOL_ROUND_CAP_EXCEEDED_MARKER,
                            "is_error": True,
                        }
                    )
                messages.append({"role": "user", "content": tool_results})
                # Final call with tools disabled — the model produces
                # final text from whatever context it has.
                final = await self._anthropic.messages.create(
                    model=model,
                    system=combined_system,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                total_input_tokens += int(getattr(final.usage, "input_tokens", 0))
                total_output_tokens += int(getattr(final.usage, "output_tokens", 0))
                return LLMResponse(
                    content=_extract_text_from_response(final),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                )

            # Normal round: dispatch every tool_use and append results.
            # ``dispatch`` returns {"content": [...], "is_error": bool};
            # we lift ``is_error`` onto the tool_result ENVELOPE (per
            # Anthropic's spec — it is an envelope field, not a nested
            # content-block field).
            for block in tool_use_blocks:
                name = str(block.get("name") or "")
                raw_input_candidate = block.get("input")
                raw_inputs = (
                    raw_input_candidate if isinstance(raw_input_candidate, dict) else {}
                )
                tool_use_id = block.get("id", "")
                result_payload = await tool_registry.dispatch(name, raw_inputs)
                result_envelope: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_payload.get("content", []),
                }
                if result_payload.get("is_error"):
                    result_envelope["is_error"] = True
                tool_results.append(result_envelope)
            messages.append({"role": "user", "content": tool_results})
            rounds += 1


def _extract_text_from_response(response: Any) -> str:
    """Pull the concatenated text blocks out of an Anthropic ``Message``."""
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", "") or ""
            if text:
                parts.append(text)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text") or ""
            if text:
                parts.append(str(text))
    if parts:
        return "\n".join(parts)
    # Fallback: legacy path that assumed first content block had .text.
    first = content[0]
    if hasattr(first, "text"):
        return str(first.text)
    return str(first)


def _response_content_as_plain(content: Any) -> list[dict[str, Any]]:
    """Convert the SDK response content (SDK objects) into plain dicts.

    Anthropic's async client returns typed objects for content blocks
    (``TextBlock``, ``ToolUseBlock``). The next ``messages.create`` call
    wants plain dicts. Walk the blocks and rebuild them block-by-block
    so the returned list is safe to embed in the next request.
    """
    if not isinstance(content, list):
        return []
    plain: list[dict[str, Any]] = []
    for block in content:
        if isinstance(block, dict):
            plain.append(block)
            continue
        block_type = getattr(block, "type", None)
        if block_type == "text":
            plain.append({"type": "text", "text": getattr(block, "text", "") or ""})
        elif block_type == "tool_use":
            plain.append(
                {
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {}) or {},
                }
            )
        elif block_type == "thinking":
            # Preserve thinking blocks so adaptive thinking keeps working
            # when tools are attached.
            plain.append(
                {
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", "") or "",
                }
            )
        else:
            # Unknown block type — skip rather than guess, so a new SDK
            # block kind doesn't leak unexpected fields back into the
            # request payload.
            continue
    return plain
