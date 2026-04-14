"""Mock payment adapter — deterministic results for testing."""

from __future__ import annotations

import logging
from uuid import uuid4

from app.payment.ports import PriceInfo, WebhookEvent

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
            mode,
            user_id,
            session_id,
        )
        return f"https://checkout.stripe.com/mock/{session_id}"

    async def cancel_subscription(self, subscription_id: str) -> None:
        """No-op for mock."""
        logger.info("Mock cancel subscription: %s", subscription_id)

    async def get_price(self, price_id: str) -> PriceInfo:
        """Return a deterministic placeholder price for any ID."""
        return PriceInfo(price_id=price_id, amount_cents=999, currency="usd")

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> WebhookEvent:
        """Accept any signature in mock mode. Parse payload as JSON.

        H-1: The webhook handler accesses event.data["data"]["object"], matching
        the Stripe SDK's event dict structure. Ensure mock data has the same nesting.
        """
        import json

        raw: dict = json.loads(payload)
        # If the payload already has the nested Stripe structure, use as-is.
        # Otherwise, wrap it so event.data["data"]["object"] resolves correctly.
        if (
            "data" in raw
            and isinstance(raw.get("data"), dict)
            and "object" in raw["data"]
        ):
            data = raw
        else:
            # Wrap the raw payload so the handler's data["data"]["object"] path works
            data = {**raw, "data": {"object": raw}}
        return WebhookEvent(
            event_type=raw.get("type", ""),
            event_id=raw.get("id", ""),
            data=data,
        )
