"""Stripe payment adapter — real Stripe API calls.

Lazy-imports stripe SDK to avoid dependency when using MockPaymentAdapter.
PCI-DSS SAQ-A: No card data flows through this adapter — all card collection
via Stripe hosted payment sheet (mobile SDK).
"""

from __future__ import annotations

import asyncio
import functools
import logging

from app.config import settings
from app.payment.ports import PaymentIntentBundle, PriceInfo, WebhookEvent

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=128)
def _retrieve_price_cached(price_id: str) -> PriceInfo:
    """Fetch and cache a Stripe price by ID. Module-level so the cache
    survives across adapter instances (one network call per price).

    Stripe prices are immutable; cache invalidation is not required.
    """
    import stripe

    price = stripe.Price.retrieve(price_id)
    unit_amount = price.get("unit_amount")
    if unit_amount is None:
        # Tiered or metered prices have no flat unit_amount and are not
        # supported for display in purchase_options.
        raise ValueError(
            f"Stripe price {price_id} has no flat unit_amount (tiered/metered?)"
        )
    return PriceInfo(
        price_id=price_id,
        amount_cents=int(unit_amount),
        currency=str(price["currency"]).lower(),
    )


class StripePaymentAdapter:
    """Real Stripe payment adapter."""

    def __init__(self) -> None:
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET must be set for Stripe adapter")

        import stripe

        stripe.api_key = settings.STRIPE_API_KEY
        self._stripe = stripe

    async def create_checkout_session(
        self,
        user_id: str,
        price_id: str,
        mode: str,
        success_url: str,
        cancel_url: str,
        metadata: dict | None = None,
    ) -> str:
        """Create a Stripe checkout session. Returns the checkout URL."""
        loop = asyncio.get_running_loop()

        session_metadata = {"user_id": user_id}
        if metadata:
            session_metadata.update(metadata)

        try:
            session = await loop.run_in_executor(
                None,
                lambda: self._stripe.checkout.Session.create(
                    line_items=[{"price": price_id, "quantity": 1}],
                    mode=mode,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    metadata=session_metadata,
                ),
            )
        except self._stripe.StripeError as exc:
            logger.exception(
                "Stripe API error during checkout session creation: %s", exc
            )
            raise

        logger.info(
            "Stripe checkout session created: mode=%s, user=%s",
            mode,
            user_id,
        )

        return session.url

    async def cancel_subscription(self, subscription_id: str) -> None:
        """Cancel subscription at period end via Stripe API."""
        loop = asyncio.get_running_loop()

        try:
            await loop.run_in_executor(
                None,
                lambda: self._stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                ),
            )
        except self._stripe.StripeError as exc:
            logger.exception("Stripe API error during subscription cancel: %s", exc)
            raise

        logger.info(
            "Stripe subscription %s set to cancel at period end", subscription_id
        )

    async def get_price(self, price_id: str) -> PriceInfo:
        """Fetch price metadata from Stripe (cached in-process)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _retrieve_price_cached, price_id)

    async def create_payment_intent(
        self,
        user_id: str,
        price_id: str,
        metadata: dict | None = None,
    ) -> PaymentIntentBundle:
        """Create a PaymentIntent + ephemeral key for Payment Sheet.

        Customer lookup is idempotent via `metadata.user_id` — existing
        customers are reused across calls. Price is resolved through the
        cached Price.retrieve helper so repeat calls for the same pack
        don't round-trip to Stripe.
        """
        loop = asyncio.get_running_loop()

        try:
            # Resolve amount + currency from the price (cached).
            price = await loop.run_in_executor(None, _retrieve_price_cached, price_id)

            customer_id = await self._get_or_create_customer(user_id)

            intent_metadata = {"user_id": user_id}
            if metadata:
                intent_metadata.update(metadata)

            intent = await loop.run_in_executor(
                None,
                lambda: self._stripe.PaymentIntent.create(
                    amount=price.amount_cents,
                    currency=price.currency,
                    customer=customer_id,
                    automatic_payment_methods={"enabled": True},
                    metadata=intent_metadata,
                ),
            )

            ephemeral = await loop.run_in_executor(
                None,
                lambda: self._stripe.EphemeralKey.create(
                    customer=customer_id,
                    stripe_version=self._stripe.api_version,
                ),
            )
        except self._stripe.StripeError as exc:
            logger.exception("Stripe API error during PaymentIntent creation: %s", exc)
            raise

        logger.info(
            "Stripe PaymentIntent created: user=%s, price=%s, intent=%s",
            user_id,
            price_id,
            intent.get("id"),
        )

        return PaymentIntentBundle(
            client_secret=intent["client_secret"],
            ephemeral_key=ephemeral["secret"],
            customer_id=customer_id,
            publishable_key=settings.STRIPE_PUBLISHABLE_KEY,
        )

    async def _get_or_create_customer(self, user_id: str) -> str:
        """Idempotent Stripe customer lookup keyed on `metadata.user_id`.

        No per-user `stripe_customer_id` table exists in v1; rate limits
        on `Customer.search` (~100/sec) are acceptable at current scale.
        If search misses, create a customer with the user_id stamped into
        metadata for future lookups.
        """
        loop = asyncio.get_running_loop()

        query = f'metadata["user_id"]:"{user_id}"'
        result = await loop.run_in_executor(
            None,
            lambda: self._stripe.Customer.search(query=query, limit=1),
        )
        existing = result.get("data") or []
        if existing:
            return existing[0]["id"]

        customer = await loop.run_in_executor(
            None,
            lambda: self._stripe.Customer.create(metadata={"user_id": user_id}),
        )
        return customer["id"]

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> WebhookEvent:
        """Verify Stripe webhook signature and return a typed WebhookEvent.

        Raises ValueError if signature is invalid.
        """
        try:
            event = self._stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
            return WebhookEvent(
                event_type=event["type"],
                event_id=event["id"],
                data=dict(event),
            )
        except self._stripe.SignatureVerificationError as exc:
            raise ValueError(f"Invalid Stripe webhook signature: {exc}") from exc
