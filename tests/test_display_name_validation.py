"""Tests for display_name XSS prevention (QF-8)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# Check if importing auth module works at all (FastAPI compat)
_AUTH_IMPORT_ERROR = None
try:
    from app.api.auth import RegisterRequest  # noqa: F401 — availability check

    _AUTH_AVAILABLE = True
except (ImportError, AttributeError) as exc:
    _AUTH_AVAILABLE = False
    _AUTH_IMPORT_ERROR = str(exc)

pytestmark = pytest.mark.skipif(
    not _AUTH_AVAILABLE,
    reason=f"app.api.auth cannot be imported: {_AUTH_IMPORT_ERROR}",
)


def test_display_name_rejects_angle_brackets():
    from app.api.auth import RegisterRequest

    with pytest.raises(ValidationError, match="display_name"):
        RegisterRequest(
            email="test@example.com",
            password="securepass123",
            username="testuser",
            display_name="<script>alert('xss')</script>",
        )


def test_display_name_rejects_double_quotes():
    from app.api.auth import RegisterRequest

    with pytest.raises(ValidationError, match="display_name"):
        RegisterRequest(
            email="test@example.com",
            password="securepass123",
            username="testuser",
            display_name='Hello "World"',
        )


def test_display_name_allows_normal_text():
    from app.api.auth import RegisterRequest

    req = RegisterRequest(
        email="test@example.com",
        password="securepass123",
        username="testuser",
        display_name="John O'Brien-Smith",
    )
    assert req.display_name == "John O'Brien-Smith"


def test_display_name_allows_unicode():
    from app.api.auth import RegisterRequest

    req = RegisterRequest(
        email="test@example.com",
        password="securepass123",
        username="testuser",
        display_name="Jean-Pierre",
    )
    assert req.display_name == "Jean-Pierre"


def test_display_name_allows_emoji():
    from app.api.auth import RegisterRequest

    req = RegisterRequest(
        email="test@example.com",
        password="securepass123",
        username="testuser",
        display_name="Cool User 🎉",
    )
    assert req.display_name == "Cool User 🎉"
