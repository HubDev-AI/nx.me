"""Sentry ``before_send`` hook — strips biometric fields from error events.

Biometric fields (mst_bin, undertone, region_anchors) must not appear in
Sentry crash reports.  This hook scrubs them from three carriers:

  1. ``event["extra"]`` — arbitrary key/value dict attached to the event.
  2. ``event["breadcrumbs"][*]["data"]`` — per-breadcrumb structured data.
  3. Frame-local variables — ``event["exception"]["values"][*]
       ["stacktrace"]["frames"][*]["vars"]``.

Register this once at process startup:

    import sentry_sdk
    from app.observability.sentry_before_send import before_send
    sentry_sdk.init(dsn=..., before_send=before_send)
"""

from __future__ import annotations

from typing import Any

_BIOMETRIC_KEYS: frozenset[str] = frozenset({"mst_bin", "undertone", "region_anchors"})
_REDACTED = "[REDACTED]"


def _scrub_dict(d: dict[str, Any]) -> None:
    """In-place: replace values for biometric keys with _REDACTED (recursive)."""
    for key, value in d.items():
        if key in _BIOMETRIC_KEYS:
            d[key] = _REDACTED
        elif isinstance(value, dict):
            _scrub_dict(value)


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Strip biometric fields from a Sentry event before it is transmitted."""
    # 1. event["extra"]
    extra = event.get("extra")
    if isinstance(extra, dict):
        _scrub_dict(extra)

    # 2. event["breadcrumbs"][*]["data"]
    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        values = breadcrumbs.get("values", [])
    elif isinstance(breadcrumbs, list):
        values = breadcrumbs
    else:
        values = []
    for crumb in values:
        if isinstance(crumb, dict):
            data = crumb.get("data")
            if isinstance(data, dict):
                _scrub_dict(data)

    # 3. Frame-local vars
    exception = event.get("exception")
    if isinstance(exception, dict):
        for exc_val in exception.get("values", []):
            if not isinstance(exc_val, dict):
                continue
            stacktrace = exc_val.get("stacktrace")
            if not isinstance(stacktrace, dict):
                continue
            for frame in stacktrace.get("frames", []):
                if not isinstance(frame, dict):
                    continue
                frame_vars = frame.get("vars")
                if isinstance(frame_vars, dict):
                    _scrub_dict(frame_vars)

    return event
