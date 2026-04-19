"""Webhook-processing constants.

All literal values used by the Stripe webhook handler live here so they
never appear as magic numbers or strings in application code.
"""

# Grace period granted when an invoice payment fails (R9).
GRACE_PERIOD_DAYS: int = 3

# Events older than this many hours are discarded on first receipt (R18).
WEBHOOK_EVENT_MAX_AGE_HOURS: int = 72

# Stripe event types handled by the subscription-lifecycle router.
EVT_CHECKOUT_SESSION_COMPLETED = "checkout.session.completed"
EVT_SUBSCRIPTION_CREATED = "customer.subscription.created"
EVT_SUBSCRIPTION_UPDATED = "customer.subscription.updated"
EVT_SUBSCRIPTION_DELETED = "customer.subscription.deleted"
EVT_INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"
EVT_INVOICE_PAYMENT_FAILED = "invoice.payment_failed"

# Payment-sheet flow discriminator (reused from entitlement module).
FLOW_PAYMENT_SHEET = "payment_sheet"
