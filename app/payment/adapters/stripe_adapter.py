"""Stripe payment adapter — real Stripe API calls.

Lazy-imports stripe SDK to avoid dependency when using MockPaymentAdapter.
PCI-DSS SAQ-A: No card data flows through this adapter — all card collection
via Stripe hosted payment sheet (mobile SDK).
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING

from postgrest.exceptions import APIError as PostgrestAPIError

from app.config import settings
from app.db.async_helpers import run_sync
from app.payment.ports import (
    PaymentFetchError,
    PaymentIntentBundle,
    PriceInfo,
    SubscriptionSnapshot,
    WebhookEvent,
)

# Supabase/PostgREST exceptions that the customer-id cache helpers treat as
# recoverable: the cache is advisory, not the source of truth. Stripe remains
# canonical — losing a cache read/write just means the next call re-does the
# search-or-create round trip. Scoped narrowly so genuine bugs (TypeError,
# AttributeError on malformed rows, etc.) still surface.
_CUSTOMER_ID_CACHE_RECOVERABLE = (PostgrestAPIError, ConnectionError, TimeoutError)

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=128)
def _retrieve_price_cached(price_id: str) -> PriceInfo:
    """Fetch and cache a Stripe price by ID. Module-level so the cache
    survives across adapter instances (one network call per price).

    Stripe prices are immutable; cache invalidation is not required.

    Raises ``PaymentFetchError`` on Stripe SDK failure so callers treat
    price retrieval failures through the same adapter-agnostic funnel as
    other fetches. Negative results (missing ``unit_amount``) still
    surface as ``ValueError`` — that's a price-shape problem, not a
    fetch failure, and belongs in the caller's config-validation path.
    """
    import stripe

    try:
        price = stripe.Price.retrieve(price_id)
    except stripe.StripeError as exc:
        logger.exception(
            "Stripe API error during Price.retrieve (%s): %s", price_id, exc
        )
        raise PaymentFetchError(
            f"Stripe Price.retrieve failed for {price_id}: {exc}"
        ) from exc

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

    def __init__(self, supabase_client: "Client | None" = None) -> None:
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET must be set for Stripe adapter")

        import stripe

        stripe.api_key = settings.STRIPE_API_KEY
        self._stripe = stripe
        # Optional: when supplied, `_get_or_create_customer` prefers the
        # cached `users.stripe_customer_id` column over `Customer.search`
        # and writes the id back on miss (lazy-write-back). When None, the
        # adapter falls back to pure Stripe calls — safe for contexts that
        # construct the adapter without DB access (e.g. one-shot scripts).
        self._supabase = supabase_client

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
            raise PaymentFetchError(
                f"Stripe Checkout.Session.create failed: {exc}"
            ) from exc

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
            raise PaymentFetchError(
                f"Stripe Subscription.modify failed for {subscription_id}: {exc}"
            ) from exc

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
            raise PaymentFetchError(
                f"Stripe PaymentIntent.create failed for user {user_id}: {exc}"
            ) from exc

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
        """Idempotent Stripe customer lookup with lazy-populated cache.

        Preference order (fastest first):
          1. ``users.stripe_customer_id`` column — O(1), zero Stripe calls.
          2. ``Customer.search(metadata.user_id:"...")`` fallback. Writes the
             column back on hit so subsequent calls skip straight to step 1.
          3. ``Customer.create(metadata.user_id=...)`` if nothing matches.
             Writes the column back.

        When constructed without a ``supabase_client`` the column steps are
        skipped and the adapter behaves like the legacy search/create path —
        a safety net for contexts (one-shot scripts, test harnesses) that
        don't have a DB handle.
        """
        loop = asyncio.get_running_loop()

        # Step 1: column-first lookup (zero Stripe calls on the hot path).
        cached_id = await self._read_cached_customer_id(user_id)
        if cached_id:
            return cached_id

        # Step 2: fallback to Stripe Customer.search, keyed on metadata.user_id.
        query = f'metadata["user_id"]:"{user_id}"'
        result = await loop.run_in_executor(
            None,
            lambda: self._stripe.Customer.search(query=query, limit=1),
        )
        existing = result.get("data") or []
        if existing:
            customer_id = existing[0]["id"]
            await self._write_cached_customer_id(user_id, customer_id)
            return customer_id

        # Step 3: create a new customer, stamping user_id into metadata for
        # future searches, and write the id back to the column.
        customer = await loop.run_in_executor(
            None,
            lambda: self._stripe.Customer.create(metadata={"user_id": user_id}),
        )
        customer_id = customer["id"]
        await self._write_cached_customer_id(user_id, customer_id)
        return customer_id

    async def _read_cached_customer_id(self, user_id: str) -> str | None:
        """Read ``users.stripe_customer_id`` for the given user.

        Returns None when the adapter has no supabase client, when the row
        is missing, or when the column is NULL. Failures are logged and
        swallowed — the caller falls back to the Stripe search path rather
        than bubbling an infra error up to the customer.
        """
        if self._supabase is None:
            return None

        try:
            result = await run_sync(
                lambda: (
                    self._supabase.table("users")
                    .select("stripe_customer_id")
                    .eq("id", user_id)
                    .maybe_single()
                    .execute()
                )
            )
        except _CUSTOMER_ID_CACHE_RECOVERABLE as exc:
            logger.warning(
                "Failed to read users.stripe_customer_id for %s: %s", user_id, exc
            )
            return None

        if not result or not result.data:
            return None
        cached = result.data.get("stripe_customer_id")
        return cached or None

    async def _write_cached_customer_id(self, user_id: str, customer_id: str) -> None:
        """Write ``users.stripe_customer_id`` for the given user.

        Best-effort — failures are logged and swallowed. The Stripe id is
        already the canonical source; losing the cache just means the next
        call will re-do the fallback search.
        """
        if self._supabase is None:
            return

        try:
            await run_sync(
                lambda: (
                    self._supabase.table("users")
                    .update({"stripe_customer_id": customer_id})
                    .eq("id", user_id)
                    .execute()
                )
            )
        except _CUSTOMER_ID_CACHE_RECOVERABLE as exc:
            logger.warning(
                "Failed to write users.stripe_customer_id for %s: %s", user_id, exc
            )

    async def retrieve_subscription(
        self,
        subscription_id: str,
        timeout: float | None = None,
    ) -> SubscriptionSnapshot:
        """Fetch a subscription snapshot from Stripe, bounded by ``timeout``.

        The Stripe SDK's ``request_timeout`` kwarg isn't always strict, so
        we layer ``asyncio.wait_for`` on top with a small slack upper
        bound as a belt-and-braces guard. Errors (SDK failures, socket
        timeouts, ``asyncio.TimeoutError``) all funnel into
        ``PaymentFetchError`` so callers don't need to import stripe to
        handle failure.

        ``timeout=None`` defers to
        ``settings.STRIPE_RETRIEVE_SUBSCRIPTION_TIMEOUT_SECONDS`` so every
        SDK call budget is discoverable via config rather than a hardcoded
        per-method literal.
        """
        effective_timeout = (
            timeout
            if timeout is not None
            else settings.STRIPE_RETRIEVE_SUBSCRIPTION_TIMEOUT_SECONDS
        )
        loop = asyncio.get_running_loop()
        upper_bound = effective_timeout + settings.STRIPE_RPC_TIMEOUT_SLACK_SECONDS

        try:
            sub = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(
                        self._stripe.Subscription.retrieve,
                        subscription_id,
                        request_timeout=effective_timeout,
                    ),
                ),
                timeout=upper_bound,
            )
        except asyncio.TimeoutError as exc:
            logger.warning(
                "Stripe Subscription.retrieve timed out after %.2fs for %s",
                upper_bound,
                subscription_id,
            )
            raise PaymentFetchError(
                f"timeout retrieving subscription {subscription_id}"
            ) from exc
        except self._stripe.StripeError as exc:
            logger.exception(
                "Stripe API error during Subscription.retrieve (%s): %s",
                subscription_id,
                exc,
            )
            raise PaymentFetchError(
                f"failed to retrieve subscription {subscription_id}: {exc}"
            ) from exc

        customer = sub.get("customer")
        if isinstance(customer, dict):
            customer_id = str(customer.get("id") or "")
        else:
            customer_id = str(customer or "")

        cancel_at_raw = sub.get("cancel_at")
        cancel_at = int(cancel_at_raw) if cancel_at_raw is not None else None

        return SubscriptionSnapshot(
            id=str(sub["id"]),
            status=str(sub["status"]),
            current_period_start=int(sub["current_period_start"]),
            current_period_end=int(sub["current_period_end"]),
            cancel_at_period_end=bool(sub.get("cancel_at_period_end", False)),
            customer_id=customer_id,
            cancel_at=cancel_at,
        )

    async def delete_customer(self, customer_id: str) -> None:
        """Delete a Stripe customer; idempotent on ``resource_missing``.

        The wider delete-account path (R17) must be tolerant of replays —
        if Stripe already has no record of the customer, the correct
        behaviour is "success, nothing to do". Any other Stripe error is
        logged and re-raised so the caller can decide whether to retry.
        """
        loop = asyncio.get_running_loop()

        try:
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(
                        self._stripe.Customer.delete,
                        customer_id,
                    ),
                ),
                timeout=settings.STRIPE_DELETE_CUSTOMER_TIMEOUT_SECONDS
                + settings.STRIPE_RPC_TIMEOUT_SLACK_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("Stripe Customer.delete timed out for %s", customer_id)
            raise PaymentFetchError(f"timeout deleting customer {customer_id}") from exc
        except self._stripe.InvalidRequestError as exc:
            # Stripe marks already-deleted customers as resource_missing.
            # Accept either the structured ``code`` attribute (preferred) or
            # the stringified message as a belt-and-braces fallback for
            # older stripe-python versions.
            code = getattr(exc, "code", None)
            if code == "resource_missing" or "resource_missing" in str(exc):
                logger.info(
                    "Stripe customer %s already deleted (resource_missing)",
                    customer_id,
                )
                return
            logger.exception(
                "Stripe API error during Customer.delete (%s): %s", customer_id, exc
            )
            raise PaymentFetchError(
                f"Stripe Customer.delete failed for {customer_id}: {exc}"
            ) from exc
        except self._stripe.StripeError as exc:
            logger.exception(
                "Stripe API error during Customer.delete (%s): %s", customer_id, exc
            )
            raise PaymentFetchError(
                f"Stripe Customer.delete failed for {customer_id}: {exc}"
            ) from exc

        logger.info("Stripe customer %s deleted", customer_id)

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
