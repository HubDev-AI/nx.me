"""Mock payment adapter — deterministic results for testing."""
from __future__ import annotations

import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


class MockPaymentAdapter:
    """Returns deterministic results. No Stripe calls."""

    async def create_checkout_session(
        self,
        user_id: str,
        price_id: str,
        mode: str,
        success_url: str,
        cancel_url: str,
        metadata: dict | None = None,
    ) -> str:
        """Return a fake checkout URL."""
        session_id = str(uuid4())
        logger.info(
            "Mock checkout session: mode=%s, user=%s, session=%s",
            mode, user_id, session_id,
        )
        return f"https://checkout.stripe.com/mock/{session_id}"

    async def cancel_subscription(self, subscription_id: str) -> None:
        """No-op for mock."""
        logger.info("Mock cancel subscription: %s", subscription_id)

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> dict:
        """Accept any signature in mock mode. Parse payload as JSON."""
        import json

        return json.loads(payload)
