"""Mock payment adapter — deterministic results for testing."""

from __future__ import annotations

import logging
from uuid import uuid4

from app.payment.ports import (
    PaymentFetchError,
    PaymentIntentBundle,
    PriceInfo,
    SubscriptionSnapshot,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


class MockPaymentAdapter:
    """Returns deterministic results. No Stripe calls."""

    def __init__(self) -> None:
        # In-memory store so tests can pre-populate a canonical response
        # for ``retrieve_subscription`` calls. Keeps the mock stateful
        # enough to exercise happy/miss branches without pulling in a
        # Stripe fixture.
        self._subscriptions: dict[str, SubscriptionSnapshot] = {}

    def set_subscription(self, snapshot: SubscriptionSnapshot) -> None:
        """Seed a snapshot retrievable via ``retrieve_subscription``.

        Intended for test setup. The caller keyed the snapshot by its own
        ``id`` so the adapter can look it up without additional bookkeeping.
        """
        self._subscriptions[snapshot.id] = snapshot

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

    async def create_payment_intent(
        self,
        user_id: str,
        price_id: str,
        metadata: dict | None = None,
    ) -> PaymentIntentBundle:
        """Return a deterministic PaymentIntent bundle. No Stripe calls."""
        logger.info(
            "Mock PaymentIntent created: user=%s, price=%s, metadata=%s",
            user_id,
            price_id,
            metadata,
        )
        return PaymentIntentBundle(
            client_secret=f"pi_mock_{user_id}_secret",
            ephemeral_key="ek_mock",
            customer_id=f"cus_mock_{user_id}",
            publishable_key="pk_test_mock",
        )

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

    async def retrieve_subscription(
        self,
        subscription_id: str,
        timeout: float = 3.0,
    ) -> SubscriptionSnapshot:
        """Return a seeded snapshot, or raise ``PaymentFetchError``.

        Callers use ``set_subscription`` to stage fixtures — unknown ids
        simulate Stripe's "not found" failure mode so tests can exercise
        the error branch without needing a real network round-trip.
        """
        snapshot = self._subscriptions.get(subscription_id)
        if snapshot is None:
            raise PaymentFetchError(f"mock has no subscription {subscription_id!r}")
        logger.info("Mock retrieve subscription: %s", subscription_id)
        return snapshot

    async def delete_customer(self, customer_id: str) -> None:
        """No-op for mock; always idempotent."""
        logger.info("Mock delete customer: %s", customer_id)
