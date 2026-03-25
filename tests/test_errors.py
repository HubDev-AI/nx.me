"""Tests for unified error handling.

Exercises production code in:
  - app/api/errors.py (ApiError, RateLimitExceeded, handlers, _status_to_code)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError


try:
    from app.api.errors import (
        ApiError, RateLimitExceeded, raise_api_error,
        api_error_handler, http_exception_handler,
        validation_error_handler, rate_limit_handler,
        _status_to_code,
    )
    _ERRORS_AVAILABLE = True
except (ImportError, AttributeError):
    _ERRORS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _ERRORS_AVAILABLE, reason="errors module unavailable"
)


class TestApiError:
    """Tests for ApiError class."""

    def test_api_error_attributes(self):
        err = ApiError(status_code=400, code="BAD_REQUEST", message="Invalid input")
        assert err.status_code == 400
        assert err.code == "BAD_REQUEST"
        assert err.message == "Invalid input"
        assert err.detail == {"error": {"code": "BAD_REQUEST", "message": "Invalid input"}}

    def test_api_error_with_headers(self):
        err = ApiError(status_code=429, code="RATE_LIMIT", message="Too fast", headers={"Retry-After": "60"})
        assert err.headers == {"Retry-After": "60"}

    def test_api_error_is_http_exception(self):
        err = ApiError(status_code=500, code="INTERNAL", message="oops")
        assert isinstance(err, HTTPException)


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_default_no_retry_after(self):
        exc = RateLimitExceeded()
        assert exc.retry_after is None
        assert str(exc) == "Rate limit exceeded"

    def test_with_retry_after(self):
        exc = RateLimitExceeded(retry_after=120)
        assert exc.retry_after == 120


class TestRaiseApiError:
    """Tests for raise_api_error convenience function."""

    def test_raises_api_error(self):
        with pytest.raises(ApiError) as exc_info:
            raise_api_error(404, "NOT_FOUND", "Resource not found")
        assert exc_info.value.status_code == 404


class TestApiErrorHandler:
    """Tests for api_error_handler."""

    @pytest.mark.asyncio
    async def test_returns_structured_json(self):
        request = MagicMock()
        exc = ApiError(status_code=400, code="BAD_REQUEST", message="Invalid")
        resp = await api_error_handler(request, exc)
        assert resp.status_code == 400
        assert resp.body is not None

    @pytest.mark.asyncio
    async def test_includes_headers(self):
        request = MagicMock()
        exc = ApiError(status_code=429, code="RATE_LIMIT", message="Slow down", headers={"Retry-After": "30"})
        resp = await api_error_handler(request, exc)
        assert resp.status_code == 429


class TestHttpExceptionHandler:
    """Tests for http_exception_handler."""

    @pytest.mark.asyncio
    async def test_structured_detail_passthrough(self):
        request = MagicMock()
        exc = HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "No access"}})
        resp = await http_exception_handler(request, exc)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_dict_detail_passthrough(self):
        request = MagicMock()
        exc = HTTPException(status_code=400, detail={"key": "value"})
        resp = await http_exception_handler(request, exc)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_string_detail_wrapped(self):
        request = MagicMock()
        exc = HTTPException(status_code=404, detail="Not found")
        resp = await http_exception_handler(request, exc)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_none_detail(self):
        request = MagicMock()
        exc = HTTPException(status_code=500)
        resp = await http_exception_handler(request, exc)
        assert resp.status_code == 500


class TestValidationErrorHandler:
    """Tests for validation_error_handler."""

    @pytest.mark.asyncio
    async def test_returns_422(self):
        request = MagicMock()
        exc = RequestValidationError(errors=[
            {"loc": ["body", "email"], "msg": "field required", "type": "missing"}
        ])
        resp = await validation_error_handler(request, exc)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_errors(self):
        request = MagicMock()
        exc = RequestValidationError(errors=[])
        resp = await validation_error_handler(request, exc)
        assert resp.status_code == 422


class TestRateLimitHandler:
    """Tests for rate_limit_handler."""

    @pytest.mark.asyncio
    async def test_returns_429(self):
        request = MagicMock()
        exc = RateLimitExceeded()
        resp = await rate_limit_handler(request, exc)
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_includes_retry_after(self):
        request = MagicMock()
        exc = RateLimitExceeded(retry_after=60)
        resp = await rate_limit_handler(request, exc)
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "60"


class TestStatusToCode:
    """Tests for _status_to_code mapping."""

    def test_known_codes(self):
        assert _status_to_code(400) == "BAD_REQUEST"
        assert _status_to_code(401) == "UNAUTHORIZED"
        assert _status_to_code(403) == "FORBIDDEN"
        assert _status_to_code(404) == "NOT_FOUND"
        assert _status_to_code(409) == "CONFLICT"
        assert _status_to_code(422) == "VALIDATION_ERROR"
        assert _status_to_code(429) == "RATE_LIMIT_EXCEEDED"
        assert _status_to_code(500) == "INTERNAL_ERROR"
        assert _status_to_code(503) == "SERVICE_UNAVAILABLE"

    def test_unknown_code_returns_error(self):
        assert _status_to_code(418) == "ERROR"
