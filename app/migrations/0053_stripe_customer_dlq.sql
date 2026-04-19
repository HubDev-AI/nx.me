-- 0053: Stripe customer DLQ — rows for failed delete_customer calls, reconciled nightly.
CREATE TABLE IF NOT EXISTS stripe_customer_dlq (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    last_error TEXT,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_stripe_customer_dlq_drain ON stripe_customer_dlq (attempts, inserted_at);

ALTER TABLE stripe_customer_dlq ENABLE ROW LEVEL SECURITY;
CREATE POLICY stripe_customer_dlq_deny_all ON stripe_customer_dlq
    FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);
