"""Payment adapter port — Protocol for payment provider abstraction.

A-3: All external payment services accessed through this Protocol.
Concrete implementations: StripePaymentAdapter, MockPaymentAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WebhookEvent:
    """Typed webhook event returned by construct_webhook_event."""

    event_type: str  # e.g. "checkout.session.completed"
    event_id: str  # provider event ID for idempotency
    data: dict  # the full event payload (provider-specific)


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
