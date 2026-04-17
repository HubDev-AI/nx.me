"""Cross-user invariants and log-leak assertions for the advisor tool surface.

Plan 2026-04-17-003 Unit 9. These tests are the audit trail for the
four-layer isolation stack:

Layer 1 (frozen context): reassigning ``McpContext.user_id`` raises.
Layer 2 (schema-gated args): no registered tool schema declares
    ``user_id`` / ``uid`` / ``account`` etc.; the registry strips any
    such key the model hallucinates before the handler runs.
Layer 3 (repo filter): handlers pass ``ctx.user_id`` to the repo; a
    cross-user dispatch returns nothing for the caller's user even when
    another user has data.
Layer 4 (log-leak): tool_result image blocks are redacted in adapter
    DEBUG logs and the payload logger never emits base64 bytes or
    signed-URL fragments.

Each section names the layer it covers and cites the test that asserts
it so the report section of the implementation can reference a single
line.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.advisor.adapters.anthropic_adapter import _redact_image_sources
from app.advisor.mcp import McpContext, ToolRegistry
from app.advisor.mcp.registry import (
    FORBIDDEN_INPUT_KEY_FRAGMENTS,
    _schema_contains_forbidden_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_USER_A = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_USER_B = UUID("11111111-2222-3333-4444-555555555555")


def _ctx(user_id: UUID, repo: Any | None = None) -> McpContext:
    return McpContext(
        user_id=user_id,
        supabase=MagicMock(),
        advisor_repo=repo or MagicMock(),
        logger=logging.getLogger("test.security"),
    )


# ---------------------------------------------------------------------------
# Layer 1 — frozen context
# ---------------------------------------------------------------------------


def test_mcp_context_is_frozen():
    """Reassigning any field raises ``FrozenInstanceError``.

    Layer 1 of the isolation stack — if a handler or a future refactor
    could mutate ``user_id`` mid-turn, layer 3 (repo filter) would be
    meaningless. ``@dataclass(frozen=True)`` is enforced by the
    interpreter, not by convention.
    """
    ctx = _ctx(_USER_A)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.user_id = _USER_B  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.advisor_repo = MagicMock()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Layer 2 — no tool schema accepts a user_id-shaped key
# ---------------------------------------------------------------------------


def test_tool_schemas_never_accept_user_id():
    """Audit every registered schema for forbidden input keys.

    Layer 2: the registry builds a ``ToolRegistry`` per turn; every
    ``tools_<feature>.py`` module contributes one ``TOOL_SCHEMA``. This
    introspection test iterates the live list and asserts that none of
    ``user_id`` / ``uid`` / ``userid`` / ``account`` (any casing) appear
    in any ``input_schema.properties``. Adding a new tool module that
    violates the rule would fail this test the moment it lands.
    """
    registry = ToolRegistry(ctx=_ctx(_USER_A))
    for schema in registry.schemas():
        forbidden = _schema_contains_forbidden_key(schema)
        assert forbidden is None, (
            f"tool {schema['name']!r} declares forbidden input key "
            f"{forbidden!r} (matches one of {FORBIDDEN_INPUT_KEY_FRAGMENTS})"
        )


@pytest.mark.asyncio
async def test_dispatch_strips_hostile_keys_before_handler():
    """Registry filters ``raw_inputs`` against the declared schema.

    Layer 2b: an LLM that hallucinates ``user_id="USER_B"`` at call
    time never reaches the handler. The registry strips unknown keys
    BEFORE invoking the handler. This test builds a stub handler that
    captures everything it is called with and asserts that only the
    schema-declared ``limit`` survived.
    """
    captured: dict[str, Any] = {}

    async def _spy(ctx: McpContext, limit: int = 5) -> list[dict[str, Any]]:
        captured["ctx"] = ctx
        captured["limit"] = limit
        return [{"type": "text", "text": "ok"}]

    ctx = _ctx(_USER_A)
    registry = ToolRegistry(ctx=ctx)
    # Replace the get_recent_nudges handler with the spy; the schema is
    # unchanged so the filter rules still apply.
    registry._handlers["get_recent_nudges"] = _spy  # type: ignore[assignment]

    # The model tries to pass user_id. It MUST NOT reach the handler.
    await registry.dispatch(
        "get_recent_nudges",
        {"user_id": str(_USER_B), "limit": 3, "admin": True},
    )
    assert captured["limit"] == 3
    # No hostile keys survived — the handler's kwargs mirror the
    # schema exactly (ctx is positional-only by convention).
    assert captured["ctx"].user_id == _USER_A


# ---------------------------------------------------------------------------
# Layer 3 — repo filter uses ctx.user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_user_dispatch_scopes_repo_to_context_user():
    """A dispatch for user A never returns user B's data.

    Layer 3: handlers MUST pass ``ctx.user_id`` to the repo. If a
    handler forgets, this test catches it — the repo spy asserts that
    the user_id filter passed in is exactly the context's user, never
    any value the LLM tried to inject.
    """
    repo = MagicMock()
    captured_user_ids: list[str] = []

    def _spy_get_nudges(**kwargs: Any) -> list[dict[str, Any]]:
        captured_user_ids.append(str(kwargs.get("user_id")))
        return []  # Caller's user has no data; test invariant is the filter

    repo.get_recent_nudges_for_context = _spy_get_nudges
    registry = ToolRegistry(ctx=_ctx(_USER_A, repo=repo))
    await registry.dispatch(
        "get_recent_nudges",
        {"user_id": str(_USER_B), "limit": 2},
    )
    assert captured_user_ids == [str(_USER_A)]


# ---------------------------------------------------------------------------
# Layer 4 — redaction + log-leak invariants
# ---------------------------------------------------------------------------


_SUPABASE_SIGNED_URL = (
    "https://example.supabase.co/storage/v1/object/sign/images/path.jpg"
    "?token=abc.def.ghi&expires=1234567890"
)
_FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
_FAKE_B64 = base64.b64encode(_FAKE_JPEG_BYTES).decode("ascii")


def test_redact_image_sources_covers_tool_result_image_content():
    """The adapter's redaction walks image blocks inside tool_result content.

    Layer 4a: DEBUG log capture must never include base64 bytes. The
    payload logger serializes the messages array via ``_safe_serialize``,
    which deep-copies; the adapter's logger uses ``_redact_image_sources``
    to replace every image block's source before logging. This test
    fabricates a tool_result containing a base64 image and asserts that
    every base64 trace vanishes after redaction.
    """
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_1",
                    "content": [
                        {"type": "text", "text": "feature=glowup_analysis"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": _FAKE_B64,
                            },
                        },
                    ],
                }
            ],
        }
    ]
    redacted = _redact_image_sources(messages)
    serialized = json.dumps(redacted, default=str)
    assert _FAKE_B64 not in serialized
    assert "<redacted-image-source>" in serialized


def test_redact_image_sources_covers_top_level_image_block():
    """Pre-Unit-9 path: top-level image blocks still get redacted (back-compat)."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {
                    "type": "image",
                    "source": {"type": "url", "url": _SUPABASE_SIGNED_URL},
                },
            ],
        }
    ]
    redacted = _redact_image_sources(messages)
    serialized = json.dumps(redacted, default=str)
    assert _SUPABASE_SIGNED_URL not in serialized
    assert "<redacted-image-source>" in serialized


@pytest.mark.asyncio
async def test_no_base64_or_signed_urls_leak_through_log_stream_end_to_end(
    caplog: pytest.LogCaptureFixture,
):
    """Full tool-use loop + payload logger — zero log records leak sensitive data.

    Layer 4b: the adversarial end-to-end test. Capture every log record
    emitted while:
      * the tool registry dispatches ``get_latest_generation`` (returns
        base64 image blocks from a fake Supabase stub)
      * the mock adapter runs the tool loop
      * the payload logger records the INFO (and optionally DEBUG) lines

    Then assert that no record contains the raw base64, no signed-URL
    fragments, and no ``/storage/v1/object/sign/`` path. Any single hit
    means a test fails and the leak is visible in CI, not in
    production.
    """
    from app.advisor.adapters.mock import MockLLMAdapter
    from app.advisor.payload_logger import log_llm_call

    # Stub repo returning fake image bytes — NO signed URL is ever
    # called; ``fetch_image_bytes`` returns bytes directly.
    repo = MagicMock()
    repo.get_latest_completed_job_with_images.return_value = {
        "id": "job_abc",
        "status": "completed",
        "source_type": "glowup_analysis",
        "created_at": "2026-04-17T00:00:00Z",
        "completed_at": "2026-04-17T00:01:00Z",
        "before_image_url": "raw-selfies/user_a/source.jpg",
        "after_image_url": "generated-images/user_a/after.jpg",
    }
    repo.fetch_image_bytes.return_value = _FAKE_JPEG_BYTES

    registry = ToolRegistry(ctx=_ctx(_USER_A, repo=repo))
    mock_llm = MockLLMAdapter()
    mock_llm.tool_use_script = [
        [{"name": "get_latest_generation", "input": {}}],
    ]

    with caplog.at_level(logging.DEBUG):
        # Pre-call log record (payload logger) — pre-Unit-9 usage.
        log_llm_call(
            None,
            model="claude-sonnet-4-6",
            user_id=_USER_A,
            conversation_id="conv_1",
            system="SOUL.md",
            messages=[{"role": "user", "content": "what did I look like?"}],
            vision_content=None,
            trimmed=False,
            dropped=0,
            tool_names=[s["name"] for s in registry.schemas()],
        )
        # Tool-use loop.
        await mock_llm.create_message(
            model="claude-sonnet-4-6",
            system="SOUL.md",
            messages=[{"role": "user", "content": "what did I look like?"}],
            max_tokens=256,
            tools=registry.schemas(),
            tool_registry=registry,
        )

    # Fingerprint prefix (enough to catch any accidental dump).
    b64_fingerprint = _FAKE_B64[:32]
    forbidden_substrings = (
        "/storage/v1/object/sign/",
        "?token=",
        b64_fingerprint,
    )
    # Merge message + every extra field into a single string per record
    # so substring checks catch leaks anywhere.
    for record in caplog.records:
        merged_parts: list[str] = [record.getMessage()]
        for key, value in record.__dict__.items():
            if key in {"args", "msg"}:
                continue
            try:
                merged_parts.append(json.dumps(value, default=str))
            except (TypeError, ValueError):
                merged_parts.append(repr(value))
        haystack = " ".join(merged_parts)
        for forbidden in forbidden_substrings:
            assert forbidden not in haystack, (
                f"log record leaked {forbidden!r}: {haystack[:400]}..."
            )
