"""Payment adapter port — Protocol for payment provider abstraction.

A-3: All external payment services accessed through this Protocol.
Concrete implementations: StripePaymentAdapter, MockPaymentAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PaymentFetchError(Exception):
    """Raised when the payment provider fails to satisfy a retrieve call.

    Wraps provider-specific errors (Stripe's ``StripeError``) and transport
    errors (timeouts) behind a single adapter-agnostic exception so callers
    don't need to import provider SDKs to handle failure modes.
    """


@dataclass(frozen=True)
class WebhookEvent:
    """Typed webhook event returned by construct_webhook_event."""

    event_type: str  # e.g. "checkout.session.completed"
    event_id: str  # provider event ID for idempotency
    data: dict  # the full event payload (provider-specific)
    created: int | None = None  # unix timestamp of event creation (for stale-event check)


@dataclass(frozen=True)
class PriceInfo:
    """Typed price metadata returned by get_price."""

    price_id: str
    amount_cents: int  # minor currency unit (e.g. cents)
    currency: str  # ISO 4217 lowercase, e.g. "usd"


@dataclass(frozen=True)
class PaymentIntentBundle:
    """Returned to client to bootstrap a Stripe Payment Sheet."""

    client_secret: str  # PaymentIntent client_secret
    ephemeral_key: str  # Stripe ephemeral key secret for the customer
    customer_id: str  # Stripe customer ID
    publishable_key: str  # publishable key (pass-through from settings)


@dataclass(frozen=True)
class SubscriptionSnapshot:
    """Typed subscription snapshot returned by retrieve_subscription.

    Fields mirror the subset of Stripe's Subscription object that the
    entitlement drift-protection path (R14b) consumes. Unix timestamps are
    used instead of datetimes so the adapter doesn't have to decide on a
    timezone representation — callers convert as needed.
    """

    id: str
    status: str  # Stripe status values (e.g. "active", "past_due", "canceled")
    current_period_start: int  # unix timestamp (seconds)
    current_period_end: int  # unix timestamp (seconds)
    cancel_at_period_end: bool
    customer_id: str
    cancel_at: int | None  # unix timestamp (seconds) or None


class PaymentPort(Protocol):
    """Port for payment provider interactions."""

    async def create_checkout_session(
        self,
        user_id: str,
        price_id: str,
        mode: str,
        success_url: str,
        cancel_url: str,
        metadata: dict | None = None,
    ) -> str:
        """Create a checkout session. Returns the checkout URL."""
        ...

    async def cancel_subscription(self, subscription_id: str) -> None:
        """Cancel subscription at period end."""
        ...

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> WebhookEvent:
        """Verify webhook signature and construct event object.

        Raises ValueError on invalid signature.
        """
        ...

    async def get_price(self, price_id: str) -> PriceInfo:
        """Fetch price metadata (amount + currency) for a Stripe price ID.

        Raises ``PaymentFetchError`` on retrieval failure (caller decides
        whether to skip the offering or propagate the error). Non-fetch
        shape errors (missing ``unit_amount`` on tiered/metered prices)
        still surface as ``ValueError`` — those are config-validation
        concerns, not transient provider failures.
        """
        ...

    async def create_payment_intent(
        self,
        user_id: str,
        price_id: str,
        metadata: dict | None = None,
    ) -> PaymentIntentBundle:
        """Create a PaymentIntent for the given price and the user's
        Stripe customer (creating the customer if absent, idempotent via
        metadata.user_id lookup).

        Returns the bundle needed to present a Stripe Payment Sheet.
        """
        ...

    async def retrieve_subscription(
        self,
        subscription_id: str,
        timeout: float | None = None,
    ) -> SubscriptionSnapshot:
        """Fetch a subscription snapshot for drift-protection (R14b).

        Raises ``PaymentFetchError`` on provider error or timeout. The
        adapter applies ``timeout`` as the SDK request timeout and
        ``timeout + STRIPE_RPC_TIMEOUT_SLACK_SECONDS`` as a belt-and-braces
        upper bound so a misbehaving SDK can't stall the caller past the
        webhook/entitlement budget. ``timeout=None`` defers to
        ``settings.STRIPE_RETRIEVE_SUBSCRIPTION_TIMEOUT_SECONDS``.
        """
        ...

    async def delete_customer(self, customer_id: str) -> None:
        """Delete a customer record at the payment provider.

        Idempotent: deleting an already-deleted customer (``resource_missing``
        at Stripe) is treated as success so callers can replay without
        tracking prior deletion state. Applies a ~3s timeout internally.
        """
        ...
