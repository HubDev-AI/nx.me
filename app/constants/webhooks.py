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

# Unit 8b — credit-pack + dispute + refund event types.
EVT_PAYMENT_INTENT_SUCCEEDED = "payment_intent.succeeded"
EVT_CHARGE_REFUNDED = "charge.refunded"
EVT_CHARGE_DISPUTE_CREATED = "charge.dispute.created"
EVT_CHARGE_DISPUTE_UPDATED = "charge.dispute.updated"
EVT_CHARGE_DISPUTE_CLOSED = "charge.dispute.closed"
EVT_CHARGE_DISPUTE_FUNDS_WITHDRAWN = "charge.dispute.funds_withdrawn"

# Stripe dispute outcome status values (object.status on charge.dispute.closed).
DISPUTE_STATUS_WON = "won"
DISPUTE_STATUS_LOST = "lost"
# Stripe also emits 'warning_closed' / 'warning_needs_response' for
# pre-dispute inquiries (not formal chargebacks). Treat as won-equivalent
# (no lock, no compensation) — the account was never actually at risk.
DISPUTE_STATUS_WARNING_CLOSED = "warning_closed"
DISPUTE_STATUS_WARNING_NEEDS_RESPONSE = "warning_needs_response"

# Apply-dispute RPC status strings (must match the SQL CASE enum).
DISPUTE_EVENT_CREATED = "created"
DISPUTE_EVENT_CLOSED_WON = "closed_won"
DISPUTE_EVENT_CLOSED_LOST = "closed_lost"
DISPUTE_EVENT_FUNDS_WITHDRAWN = "funds_withdrawn"
