"""Unified API error handling.

All API errors return: {"error": {"code": "...", "message": "..."}}
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    """Structured API error with code, message, and optional details."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        details: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        error_body: dict = {"code": code, "message": message}
        if details is not None:
            error_body["details"] = details
        super().__init__(
            status_code=status_code,
            detail={"error": error_body},
            headers=headers,
        )


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded.

    Replaces ValueError("RATE_LIMIT_EXCEEDED") for clearer semantics.
    """

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded")


def raise_api_error(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    details: dict | None = None,
) -> None:
    """Convenience function to raise a structured API error."""
    raise ApiError(status_code=status_code, code=code, message=message, headers=headers, details=details)


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Handle ApiError — return structured error response."""
    error_body: dict = {"code": exc.code, "message": exc.message}
    if exc.details is not None:
        error_body["details"] = exc.details
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_body},
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle standard HTTPException — normalize to structured format."""
    # If detail is already structured (dict with "error" key), pass through
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=getattr(exc, "headers", None),
        )

    # If detail is a dict with other nested structure, pass through as-is
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=getattr(exc, "headers", None),
        )

    # String detail — wrap in standard format
    code = _status_to_code(exc.status_code)
    message = str(exc.detail) if exc.detail else "An error occurred"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message}},
        headers=getattr(exc, "headers", None),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle Pydantic validation errors — return structured format."""
    errors = exc.errors()
    # Build a human-readable message from the first error
    if errors:
        first = errors[0]
        loc = " → ".join(str(loc) for loc in first.get("loc", []))
        msg = first.get("msg", "Validation error")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "Validation error"

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "details": errors,
            }
        },
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Handle RateLimitExceeded — return 429 with optional Retry-After."""
    headers = {}
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"}},
        headers=headers or None,
    )


def _status_to_code(status_code: int) -> str:
    """Map HTTP status code to a default error code."""
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "ERROR")
