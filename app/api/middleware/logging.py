"""Request-logging middleware with sensitive-header scrubbing.

Logs method, path, status code, and latency for every request.  Headers
listed in ``_SCRUBBED_HEADERS`` are replaced with ``[REDACTED]`` in the
log line so secrets (Authorization tokens, device fingerprint UUIDs) do
not leak into application logs or log-aggregation pipelines.

Security review MEDIUM: X-Install-UUID is a device fingerprint; leaking
it in access logs creates a cross-session tracking vector.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Headers that must never appear verbatim in log output.
# Lower-cased to match Starlette's normalised header names.
_SCRUBBED_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "x-install-uuid",
    }
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log each request with latency; scrub sensitive headers."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000

        # Build a scrubbed header snapshot for the log line.
        scrubbed: dict[str, str] = {
            name: ("[REDACTED]" if name.lower() in _SCRUBBED_HEADERS else value)
            for name, value in request.headers.items()
        }

        logger.info(
            "HTTP %s %s → %d (%.1fms) headers=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            scrubbed,
        )
        return response
