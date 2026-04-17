"""Shared JSON parsing helpers for advisor LLM responses.

Haiku occasionally wraps strict-JSON responses in a ``\u0060\u0060\u0060json ... \u0060\u0060\u0060``
markdown fence even when the prompt forbids markdown. The fence is
benign, but ``json.loads`` treats it as a parse error — which used to
silently drop every vision nudge (``_parse_vision_nudge_json``). This
module centralizes the fence-stripping pass so any strict-JSON caller
shares one implementation and one set of named constants.
"""

from __future__ import annotations

# Markdown code-fence markers. Named constants so callers never embed
# the literal backtick sequence inline (per ``feedback_no_hardcoded_urls``).
JSON_FENCE_OPEN = "```json"
JSON_FENCE_PLAIN = "```"


def strip_json_code_fence(raw: str) -> str:
    """Strip an optional ``\u0060\u0060\u0060json ... \u0060\u0060\u0060`` or ``\u0060\u0060\u0060 ... \u0060\u0060\u0060`` markdown fence.

    Pure string transform — no JSON parsing, no logging. Callers keep
    ownership of ``json.loads`` failure handling.
    """
    text = raw.strip()
    if not text.startswith(JSON_FENCE_PLAIN):
        return text
    if text.startswith(JSON_FENCE_OPEN):
        text = text[len(JSON_FENCE_OPEN) :]
    else:
        text = text[len(JSON_FENCE_PLAIN) :]
    text = text.lstrip("\r\n")
    if text.endswith(JSON_FENCE_PLAIN):
        text = text[: -len(JSON_FENCE_PLAIN)]
    return text.strip()
