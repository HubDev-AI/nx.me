"""Anthropic adapter redacts image sources from its DEBUG log payload.

Signed image URLs (and raw base64 blobs) must not end up in logs that
could get shipped off-host. The helper replaces every image block's
`source` with a placeholder and leaves everything else intact.
"""

from __future__ import annotations

from app.advisor.adapters.anthropic_adapter import (
    _REDACTED_IMAGE_SOURCE,
    _redact_image_sources,
)


def test_redacts_signed_url_image_blocks():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look at this"},
                {
                    "type": "image",
                    "source": {
                        "type": "url",
                        "url": "https://signed.example/a?sig=secret",
                    },
                },
            ],
        }
    ]

    out = _redact_image_sources(messages)

    assert out[0]["content"][0] == {"type": "text", "text": "look at this"}
    assert out[0]["content"][1]["source"] == _REDACTED_IMAGE_SOURCE
    # Original must not be mutated.
    assert messages[0]["content"][1]["source"]["url"].startswith("https://")


def test_redacts_base64_image_blocks():
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": "AAAA" * 100,
                    },
                },
            ],
        }
    ]

    out = _redact_image_sources(messages)
    assert out[0]["content"][0]["source"] == _REDACTED_IMAGE_SOURCE


def test_text_only_messages_pass_through_unchanged():
    messages = [
        {"role": "user", "content": "plain text"},
        {"role": "assistant", "content": "reply"},
    ]

    out = _redact_image_sources(messages)
    assert out == messages
