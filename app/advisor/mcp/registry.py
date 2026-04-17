"""Tool registry — auto-discovers ``tools_*.py`` modules and dispatches by name.

Plan 2026-04-17-003 Unit 9. The registry is the central dispatch table
for Ada's tool surface. Each feature contributes a ``tools_<feature>.py``
module that exports:

    TOOL_SCHEMA: dict      # Anthropic-compatible {name, description, input_schema}
    async def handle(ctx: McpContext, **inputs) -> dict | list[dict]

At construction the registry walks its own package (``app.advisor.mcp``),
imports every module matching the ``tools_*.py`` naming convention, and
indexes its ``TOOL_SCHEMA["name"]`` to the handler. Adding a new feature
is a single file drop — no edits in this module, the adapter, or the
service layer.

Cross-user invariants (per-layer, see context.py):

* Layer 1 (frozen context): dispatcher passes the caller-provided context
  through unchanged; it cannot be mutated.
* Layer 2 (schema-gated args): ``dispatch`` filters ``raw_inputs`` against
  the tool's declared ``input_schema.properties`` and drops everything
  else. An LLM-hallucinated ``user_id`` / ``uid`` / ``account`` never
  reaches the handler — the schema MUST NOT declare any such key, which
  is separately asserted by the registry's own introspection test.
* Layer 3 (repo filter): every handler passes ``ctx.user_id`` to the
  repo. This registry cannot enforce that invariant statically, so it is
  a code-review gate + a dedicated test (see
  ``tests/test_advisor_tool_security.py``).
* Layer 4 (Supabase RLS): a belt-and-suspenders backstop on the tables
  we query. Not in this module.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
import time
from typing import Any, Awaitable, Callable

from app.advisor.mcp.context import McpContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Named constants — per ``feedback_no_hardcoded_urls`` / Unit 9 non-goals.
# ---------------------------------------------------------------------------

# Module naming convention for auto-discovery. Any file whose basename
# matches this prefix (and is not the registry / context / package init) is
# treated as a tool module and required to export the documented surface.
TOOL_MODULE_PREFIX = "tools_"

# Exported-symbol names every tool module must provide. A module can
# export EITHER the singular pair (``TOOL_SCHEMA`` + ``handle``) — the
# original single-tool convention — OR the plural pair (``TOOL_SCHEMAS``
# + ``HANDLERS``) when a feature wants to ship several related tools
# from one file. Mixing the two in the same module, or exporting
# neither pair, is a registration error — raised at construction time
# so a broken deploy fails fast instead of at first model call.
TOOL_SCHEMA_ATTR = "TOOL_SCHEMA"
TOOL_HANDLER_ATTR = "handle"
TOOL_SCHEMAS_ATTR = "TOOL_SCHEMAS"
TOOL_HANDLERS_ATTR = "HANDLERS"

# Result-block markers used when the dispatcher must fabricate a result on
# behalf of a failed handler (unknown name, exception, round-cap breach).
# Extracted as constants so tests can assert on them and ops can grep.
ERROR_CLASS_UNKNOWN_TOOL = "UnknownTool"
ERROR_CLASS_HANDLER_EXCEPTION = "HandlerException"
TOOL_ROUND_CAP_EXCEEDED_MARKER = "tool round cap exceeded"

# Metric keys for observability. One record per tool dispatch; operators
# can correlate with ``advisor.llm_call`` via ``user_id_hash`` +
# ``conversation_id``.
METRIC_TOOL_INVOKED = "advisor.tool_invoked"
METRIC_TOOL_STRIPPED_ARGS = "advisor.tool_stripped_args"
METRIC_TOOL_UNKNOWN = "advisor.tool_unknown"
METRIC_TOOL_ERROR = "advisor.tool_error"

# Anthropic content-block types. Handlers return these; the dispatcher
# normalizes to a list and validates shape before handing off.
CONTENT_BLOCK_TYPE_TEXT = "text"
CONTENT_BLOCK_TYPE_IMAGE = "image"

# Keys that must NEVER appear in any tool's declared input schema. The
# registry enforces the rule at construction time by refusing to register
# any schema whose ``input_schema.properties`` contains one of these (case-
# insensitive). Test ``test_tool_schemas_never_accept_user_id`` audits the
# live registry to catch drift.
FORBIDDEN_INPUT_KEY_FRAGMENTS: tuple[str, ...] = (
    "user_id",
    "userid",
    "uid",
    "account",
)


def _schema_properties(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a tool's declared input properties, or an empty dict."""
    input_schema = schema.get("input_schema") or {}
    properties = input_schema.get("properties") or {}
    return properties if isinstance(properties, dict) else {}


def _schema_contains_forbidden_key(schema: dict[str, Any]) -> str | None:
    """Return the first forbidden key found in ``schema.input_schema.properties``.

    Case-insensitive substring match against ``FORBIDDEN_INPUT_KEY_FRAGMENTS``.
    Returns ``None`` when the schema is clean. Used both during registration
    (hard failure) and by the introspection test (assert the whole registry
    is clean).
    """
    for key in _schema_properties(schema).keys():
        lowered = str(key).strip().lower()
        for fragment in FORBIDDEN_INPUT_KEY_FRAGMENTS:
            if fragment in lowered:
                return str(key)
    return None


def _filter_inputs(
    schema: dict[str, Any], raw_inputs: Any
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(accepted_inputs, stripped_keys)`` for a tool's raw LLM args.

    Keys not present in ``schema.input_schema.properties`` are dropped and
    reported in ``stripped_keys`` so the registry can emit a telemetry
    record. This is layer 2 of the cross-user lockdown — it runs BEFORE
    the handler even sees the input dict, so an LLM-hallucinated
    ``user_id`` is physically incapable of reaching any repository call.

    Non-dict inputs (``None``, a list, a bare string the model sometimes
    emits instead of an object) are treated as empty — the registry
    MUST never pass garbage through to a handler's ``**kwargs`` splat.
    """
    if not isinstance(raw_inputs, dict):
        return {}, []
    allowed_keys = set(_schema_properties(schema).keys())
    accepted: dict[str, Any] = {}
    stripped: list[str] = []
    for key, value in raw_inputs.items():
        if key in allowed_keys:
            accepted[key] = value
        else:
            stripped.append(str(key))
    return accepted, stripped


def _as_anthropic_result_content(
    handler_output: Any,
) -> list[dict[str, Any]]:
    """Normalize handler output into a valid Anthropic tool_result ``content`` list.

    Handlers may return a string, a single content-block dict, or a list of
    content-block dicts. Anything else is wrapped in a text block carrying
    ``repr()`` of the value so the dispatcher never emits a malformed
    tool_result (which Anthropic would reject on the next call).
    """
    if isinstance(handler_output, list):
        return [b for b in handler_output if isinstance(b, dict)]
    if isinstance(handler_output, dict):
        return [handler_output]
    return [{"type": CONTENT_BLOCK_TYPE_TEXT, "text": str(handler_output)}]


class ToolRegistry:
    """Registry of advisor tool handlers.

    Lifecycle:
      * Construct once per chat turn with a request-scoped ``McpContext``.
      * Pass ``registry.schemas()`` as the ``tools`` parameter to the
        Anthropic Messages API.
      * On each ``stop_reason == "tool_use"``, iterate the ``tool_use``
        blocks and call ``registry.dispatch(name, raw_inputs)`` for each,
        appending the return value as ``tool_result`` content.

    The registry instance is dropped after the turn ends, which also drops
    the captured context — stale references from a prior request cannot
    leak (layer 4 of the isolation stack).
    """

    def __init__(
        self,
        ctx: McpContext,
        *,
        package_name: str = __package__,
    ) -> None:
        self._ctx = ctx
        self._tools: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._discover(package_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schemas(self) -> list[dict[str, Any]]:
        """Return the list of TOOL_SCHEMA dicts for every registered tool.

        Sorted by tool name for deterministic prompt-cache behavior — the
        Anthropic ``tools`` array is part of the cached prefix, and
        shuffling would invalidate the cache on every turn.
        """
        return [dict(self._tools[name]) for name in sorted(self._tools)]

    def tool_names(self) -> list[str]:
        """Return the sorted list of registered tool names — used by tests."""
        return sorted(self._tools)

    async def dispatch(
        self,
        name: str,
        raw_inputs: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Run a tool by name and return Anthropic-shaped tool_result content.

        The caller (adapter) is responsible for wrapping the returned list
        in a ``{"type": "tool_result", "tool_use_id": <id>, "content": ...}``
        block and appending it to the next user message. This method
        handles only the registry-side concerns: argument filtering,
        handler invocation, exception → is_error translation, and
        telemetry.

        Errors never propagate — the dispatcher always returns a
        well-formed content list so the adapter can emit a tool_result and
        keep the loop going.
        """
        schema = self._tools.get(name)
        user_id_hash = _hash_for_log(self._ctx.user_id)

        if schema is None:
            self._ctx.logger.warning(
                "Advisor tool unknown: name=%s user=%s",
                name,
                user_id_hash,
                extra={
                    "metric": METRIC_TOOL_UNKNOWN,
                    "tool": str(name),
                    "user_id_hash": user_id_hash,
                    "error_class": ERROR_CLASS_UNKNOWN_TOOL,
                },
            )
            return [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": f"Unknown tool: {name}",
                }
            ]

        accepted, stripped = _filter_inputs(schema, raw_inputs)
        if stripped:
            self._ctx.logger.info(
                "Advisor tool stripped unknown args: tool=%s stripped=%s user=%s",
                name,
                stripped,
                user_id_hash,
                extra={
                    "metric": METRIC_TOOL_STRIPPED_ARGS,
                    "tool": str(name),
                    "user_id_hash": user_id_hash,
                    "stripped_keys": stripped,
                },
            )

        handler = self._handlers[name]
        start = time.monotonic()
        try:
            result = await handler(self._ctx, **accepted)
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._ctx.logger.warning(
                "Advisor tool handler error: tool=%s err=%s user=%s",
                name,
                exc,
                user_id_hash,
                exc_info=exc,
                extra={
                    "metric": METRIC_TOOL_ERROR,
                    "tool": str(name),
                    "user_id_hash": user_id_hash,
                    "duration_ms": duration_ms,
                    "error_class": type(exc).__name__ or ERROR_CLASS_HANDLER_EXCEPTION,
                },
            )
            return [
                {
                    "type": CONTENT_BLOCK_TYPE_TEXT,
                    "text": f"Tool '{name}' failed: {type(exc).__name__}",
                }
            ]

        duration_ms = int((time.monotonic() - start) * 1000)
        self._ctx.logger.info(
            "Advisor tool invoked: tool=%s duration_ms=%d user=%s",
            name,
            duration_ms,
            user_id_hash,
            extra={
                "metric": METRIC_TOOL_INVOKED,
                "tool": str(name),
                "user_id_hash": user_id_hash,
                "duration_ms": duration_ms,
            },
        )
        return _as_anthropic_result_content(result)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self, package_name: str) -> None:
        """Import every ``tools_*.py`` submodule and register its surface."""
        package = importlib.import_module(package_name)
        package_path = getattr(package, "__path__", None)
        if package_path is None:
            return

        seen_names: set[str] = set()
        for mod_info in pkgutil.iter_modules(package_path):
            if mod_info.ispkg:
                continue
            short_name = mod_info.name
            if not short_name.startswith(TOOL_MODULE_PREFIX):
                continue
            fq_name = f"{package_name}.{short_name}"
            module = importlib.import_module(fq_name)
            for schema, handler in _module_tool_pairs(module, fq_name):
                self._register(schema, handler, fq_name=fq_name, seen_names=seen_names)

    def _register(
        self,
        schema: dict[str, Any],
        handler: Callable[..., Awaitable[Any]],
        *,
        fq_name: str,
        seen_names: set[str],
    ) -> None:
        """Validate + register a single (schema, handler) pair."""
        if not isinstance(schema, dict) or "name" not in schema:
            raise RuntimeError(
                f"Tool module {fq_name!r}: TOOL_SCHEMA must be a dict "
                "with a 'name' key."
            )
        if not asyncio.iscoroutinefunction(handler):
            raise RuntimeError(f"Tool module {fq_name!r}: handle() must be async.")
        tool_name = str(schema["name"])
        if tool_name in seen_names:
            raise RuntimeError(
                f"Duplicate tool name {tool_name!r} while loading {fq_name!r}."
            )
        forbidden = _schema_contains_forbidden_key(schema)
        if forbidden is not None:
            raise RuntimeError(
                f"Tool module {fq_name!r}: TOOL_SCHEMA declares a "
                f"forbidden input key {forbidden!r}. Tools must never "
                "accept user_id / uid / account from the LLM."
            )
        seen_names.add(tool_name)
        self._tools[tool_name] = schema
        self._handlers[tool_name] = handler


def _module_tool_pairs(
    module: Any, fq_name: str
) -> list[tuple[dict[str, Any], Callable[..., Awaitable[Any]]]]:
    """Extract ``(schema, handler)`` pairs from a ``tools_*`` module.

    A module may export the singular pair (``TOOL_SCHEMA`` + ``handle``)
    or the plural pair (``TOOL_SCHEMAS`` + ``HANDLERS``). Mixing both
    forms, or exporting neither, is a registration error — the
    singular/plural choice is per-file, not per-tool.
    """
    singular_schema = getattr(module, TOOL_SCHEMA_ATTR, None)
    singular_handler = getattr(module, TOOL_HANDLER_ATTR, None)
    plural_schemas = getattr(module, TOOL_SCHEMAS_ATTR, None)
    plural_handlers = getattr(module, TOOL_HANDLERS_ATTR, None)

    has_singular = singular_schema is not None or singular_handler is not None
    has_plural = plural_schemas is not None or plural_handlers is not None

    if has_singular and has_plural:
        raise RuntimeError(
            f"Tool module {fq_name!r} exports both the singular "
            f"({TOOL_SCHEMA_ATTR}/{TOOL_HANDLER_ATTR}) and plural "
            f"({TOOL_SCHEMAS_ATTR}/{TOOL_HANDLERS_ATTR}) surfaces. "
            "Pick one."
        )

    if has_plural:
        if not isinstance(plural_schemas, list) or not plural_schemas:
            raise RuntimeError(
                f"Tool module {fq_name!r}: {TOOL_SCHEMAS_ATTR} must be a "
                "non-empty list of schema dicts."
            )
        if not isinstance(plural_handlers, dict) or not plural_handlers:
            raise RuntimeError(
                f"Tool module {fq_name!r}: {TOOL_HANDLERS_ATTR} must be a "
                "non-empty dict mapping tool_name → async handler."
            )
        pairs: list[tuple[dict[str, Any], Callable[..., Awaitable[Any]]]] = []
        for schema in plural_schemas:
            if not isinstance(schema, dict) or "name" not in schema:
                raise RuntimeError(
                    f"Tool module {fq_name!r}: every entry in "
                    f"{TOOL_SCHEMAS_ATTR} must be a dict with a 'name' key."
                )
            tool_name = str(schema["name"])
            handler = plural_handlers.get(tool_name)
            if handler is None:
                raise RuntimeError(
                    f"Tool module {fq_name!r}: {TOOL_HANDLERS_ATTR} is "
                    f"missing a handler for tool {tool_name!r}."
                )
            pairs.append((schema, handler))
        return pairs

    if singular_schema is None or singular_handler is None:
        raise RuntimeError(
            f"Tool module {fq_name!r} must export both "
            f"{TOOL_SCHEMA_ATTR} and {TOOL_HANDLER_ATTR}."
        )
    return [(singular_schema, singular_handler)]


def _hash_for_log(user_id: Any) -> str:
    """Short hash used in this module's log records.

    Defined here (not imported from ``payload_logger``) so the registry
    module stays importable in isolation — tests monkey-patch the logger
    and don't want to pull the entire payload-logger dependency in.
    """
    import hashlib

    return hashlib.sha256(str(user_id).encode()).hexdigest()[:12]
