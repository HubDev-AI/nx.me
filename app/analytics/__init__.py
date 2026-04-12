"""Analytics package — event emission for NXME glow-up flows.

Import events directly from this package:
    from app.analytics import events
    events.glowup_upload_created(upload_id=..., user_id=..., face_detected=...)
"""

from app.analytics import events  # noqa: F401
