"""Centralized logging configuration.

Single entry point so the API process and the ARQ worker emit logs at
the same effective level and format. Driven by
``settings.effective_log_level`` (DEBUG in development, INFO elsewhere
unless ``LOG_LEVEL`` overrides).

In development DEBUG mode this also raises advisor-specific loggers to
DEBUG explicitly so library noise (httpx, urllib3, supabase) does not
need to be turned up to follow the advisor flow.
"""

from __future__ import annotations

import logging
import re

from app.config import settings

_BIOMETRIC_PATTERN = re.compile(
    r"\b(mst_bin|undertone|region_anchors)\b\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_BIOMETRIC_REPLACEMENT = r"\1=[REDACTED]"


class BiometricFieldFilter(logging.Filter):
    """Rewrite biometric field values in log records at INFO and above.

    DEBUG records are left untouched so development tracing remains
    unobstructed.  DEBUG must not be enabled in production — enforced via
    :func:`app.config.Settings.effective_log_level`.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if record.levelno <= logging.DEBUG:
            return True
        record.msg = _BIOMETRIC_PATTERN.sub(_BIOMETRIC_REPLACEMENT, str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _BIOMETRIC_PATTERN.sub(_BIOMETRIC_REPLACEMENT, str(v))
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _BIOMETRIC_PATTERN.sub(_BIOMETRIC_REPLACEMENT, str(a))
                    for a in record.args
                )
        return True


_CONFIGURED = False

# Loggers we want chatty in dev DEBUG mode so the full advisor pipeline
# (service → context_builder → MCP registry → nudge scheduler →
# memory_manager → payload logger) is visible without flipping every
# library to DEBUG.
_ADVISOR_DEBUG_LOGGERS = (
    "app.advisor",
    "app.advisor.payload",
    "app.advisor.mcp",
    "app.advisor.nudge",
    "app.api.advisor",
)

# Library loggers that produce a lot of noise at DEBUG. Pin them to INFO
# even when the root is DEBUG so the advisor signal stays readable.
_NOISY_LIBRARY_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "asyncio",
    "anthropic._base_client",
)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"
_DATE_FORMAT = "%H:%M:%S"


def configure_logging() -> None:
    """Apply the project's logging configuration. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = settings.effective_log_level
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        force=True,
    )

    logging.root.addFilter(BiometricFieldFilter())

    if level == logging.DEBUG:
        for name in _ADVISOR_DEBUG_LOGGERS:
            logging.getLogger(name).setLevel(logging.DEBUG)
        for name in _NOISY_LIBRARY_LOGGERS:
            logging.getLogger(name).setLevel(logging.INFO)

    logging.getLogger(__name__).info(
        "Logging configured: level=%s advisor_payload_debug=%s",
        level_name,
        settings.advisor_debug_payload_enabled,
    )
    _CONFIGURED = True
