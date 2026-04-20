# Payments Runbook

Operational procedures for the NXME credits-only payments engine.
Covers local dev setup, incident response, key rotation, and monitoring.

---

## 1. Local dev setup

End-to-end Stripe test-mode loop from a clean checkout.

```bash
# 1. Clone and enter the repo.
git clone <repo-url> nxme.ai && cd nxme.ai

# 2. Copy env template and fill in required values.
cp app/.env.example app/.env
# Edit app/.env — at minimum set:
#   STRIPE_API_KEY=sk_test_...        (from Stripe dashboard → Developers → API keys)
#   STRIPE_PUBLISHABLE_KEY=pk_test_...
#   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
#   SECRET_KEY, ADMIN_API_KEY          (any 32-char random strings locally)
#   SIGNUP_FINGERPRINT_SERVER_SECRET   (any 32-char random string locally)

# 3. Start local Supabase + API.
make up

# 4. Seed Stripe Products + Prices (run once per test-mode Stripe project).
make stripe-bootstrap
# Copy the printed CREDIT_PACK_STRIPE_PRICE_ID=price_... into app/.env.
# The v1_pro plan_versions row now has its stripe_price_id populated in the DB.

# 5. Start the Stripe CLI webhook listener (separate terminal — Ctrl+C to stop).
make stripe-dev
# On startup the CLI prints a line like:
#   > Ready! Your webhook signing secret is whsec_abc123...
# Copy that whsec_... value into app/.env as STRIPE_WEBHOOK_SESSION_SECRET.
# (You can use it as STRIPE_WEBHOOK_SECRET for local testing.)

# 6. Test with Stripe test cards (any future expiry, any 3-digit CVC, any postal code):
#   4242 4242 4242 4242  — success
#   4000 0000 0000 9995  — decline: insufficient funds
#   4000 0025 0000 3155  — 3D Secure required
```

A new contributor should be able to complete steps 1-6 in under 15 minutes.

---

## 2. Pre-flight: active-subscription duplicate check

Before running any migration that adds a partial UNIQUE index on
`(user_id) WHERE status = 'active'` in `subscriptions`, verify no user
already has more than one active row (which would cause the migration to
fail with a duplicate-key error):

```sql
SELECT user_id, COUNT(*) AS active_count
FROM subscriptions
WHERE status = 'active'
GROUP BY user_id
HAVING COUNT(*) > 1;
```

If this returns rows: investigate the duplicates, cancel the extra
subscription via the Stripe dashboard, and update the DB row status to
`canceled` before proceeding with the migration.

---

## 3. Dispute simulation

Trigger a charge dispute and verify the user gets locked:

```bash
stripe trigger charge.dispute.created
```

Then assert in the DB:

```sql
SELECT id, locked_at
FROM users
WHERE locked_at IS NOT NULL
ORDER BY locked_at DESC
LIMIT 5;
```

`locked_at` must be populated for the user associated with the disputed
charge. If not, check the webhook handler logs for `charge.dispute.created`.

---

## 4. Grace test (invoice payment failure)

Trigger an invoice payment failure and verify a grace period is granted:

```bash
stripe trigger invoice.payment_failed
```

Then assert in the DB:

```sql
SELECT user_id, status, grace_until
FROM subscriptions
WHERE grace_until IS NOT NULL
ORDER BY grace_until DESC
LIMIT 5;
```

`grace_until` must be set approximately 3 days from `now()`. If not,
check the webhook handler logs for `invoice.payment_failed`.

---

## 5. Weekly free grant manual trigger

Run the ARQ weekly-free-grant task once outside its schedule (e.g. for
testing or a manual catchup):

```bash
# From the repo root with app/.env sourced:
make worker
# In a separate terminal:
set -a && . ./app/.env && set +a && \
  uv run python -c "
import asyncio
from app.workers.credits import run_weekly_free_grants
asyncio.run(run_weekly_free_grants())
"
```

Verify with:

```sql
SELECT user_id, amount_milli, reason, created_at
FROM credit_ledger
WHERE reason = 'weekly_free_grant'
ORDER BY created_at DESC
LIMIT 20;
```

### Pause / resume without a redeploy

The cron is gated by a DB kill-switch row in `app_kill_switches`. The
worker reads the flag at every fire — flipping it takes effect on the
next Monday 02:30 UTC tick (no restart needed).

```sql
-- Pause
UPDATE app_kill_switches
   SET enabled = FALSE,
       note = 'paused YYYY-MM-DD — <reason>',
       updated_at = now()
 WHERE key = 'weekly_free_grant';

-- Resume
UPDATE app_kill_switches
   SET enabled = TRUE,
       note = 'resumed YYYY-MM-DD',
       updated_at = now()
 WHERE key = 'weekly_free_grant';

-- Current state
SELECT key, enabled, note, updated_at
  FROM app_kill_switches
 WHERE key = 'weekly_free_grant';
```

A missing row or DB lookup error is treated as **enabled** (fail-open) —
a forgotten seed must never silently skip a grant.

---

## 6. Fingerprint purge manual trigger

Run the nightly device-fingerprint purge worker once:

```bash
set -a && . ./app/.env && set +a && \
  uv run python -c "
import asyncio
from app.workers.fingerprint_purge import run_fingerprint_purge
asyncio.run(run_fingerprint_purge())
"
```

Verify that rows older than the retention window are removed from
`signup_grants_issued`.

---

## 7. DLQ reconciler manual trigger

Drain the Stripe customer DLQ (orphaned customer IDs that failed to
attach to a user row):

```bash
set -a && . ./app/.env && set +a && \
  uv run python -c "
import asyncio
from app.workers.stripe_customer_dlq import run_dlq_reconciler
asyncio.run(run_dlq_reconciler())
"
```

Check DLQ depth before and after:

```sql
SELECT COUNT(*), MAX(attempts), MAX(last_attempt_at)
FROM stripe_customer_dlq
WHERE resolved_at IS NULL;
```

---

## 8. DEBUG_BEARER_TOKEN rotation

**Status: TBD — deferred to Unit 14 (Supabase Vault integration).**

Rotation cadence: every 90 days and immediately on any staff change.

Planned procedure (once Unit 14 ships):
1. Generate a new 32-char+ random token.
2. Update the secret in Supabase Vault.
3. Redeploy the API (settings reload picks up the new value).
4. Verify the old token is rejected and the new token is accepted by
   the internal ops endpoints.

Until Unit 14 ships, `DEBUG_BEARER_TOKEN` is set directly in `app/.env`
(never committed). Treat it as a high-value secret — rotate on any
suspected compromise.

---

## 9. SIGNUP_FINGERPRINT_SERVER_SECRET rotation

The HMAC key used to derive `signup_grants_issued.deterministic_hash`
from the mobile installation UUID.

**Rotation format**: comma-separated `PRIMARY_SECRET,SECONDARY_SECRET`.
The secondary is optional. Lookups probe primary first, then secondary,
so existing hashes remain matchable while the background re-derivation
job rewrites them under the new primary.

**Procedure**:
1. Generate a new 256-bit (32-byte+) random value.
2. Set in `app/.env`:
   ```
   SIGNUP_FINGERPRINT_SERVER_SECRET=<new_primary>,<current_primary>
   ```
3. Redeploy the API.
4. Run the background re-derivation job to rewrite all existing hashes
   under the new primary.
5. Once re-derivation is complete, redeploy with:
   ```
   SIGNUP_FINGERPRINT_SERVER_SECRET=<new_primary>
   ```
   (drop the secondary).

Loss of this key invalidates the entire signup-grant dedup registry —
every device will be treated as new and receive the signup grant again.
Back up before rotation.

---

## 10. signup_grants_issued SURVIVES delete-account

`signup_grants_issued` is an **intentional exception** to the
hard-reset-invariant (every user-owned surface purged on account
deletion). Rows are keyed on `deterministic_hash` (derived from the
device fingerprint), not on `user_id`, so they survive user deletion
by design — this is the anti-abuse property.

**Rationale**: if a user creates an account, receives the signup grant,
deletes the account, then re-registers with the same device, the existing
hash row prevents a second signup grant. Without this exception the
signup-grant limit is trivially bypassed via delete-and-recreate.

**Legal sign-off**: retention of a one-way hash (no PII recoverable from
the hash alone) is reviewed as part of the NXME data-retention policy.
Document reference: [attach legal sign-off ticket URL here].

---

## 11. DLQ growth monitoring

Alert when:
- `SELECT COUNT(*) FROM stripe_customer_dlq WHERE resolved_at IS NULL`
  exceeds **50 unresolved rows** (indicates a systemic Stripe API failure
  or misconfiguration).
- Any row has `attempts >= 5` (max attempts; row will not be retried
  automatically — requires operator intervention).

Alert channel: PagerDuty / Slack #payments-alerts (configure per your
observability stack).

Manual inspection:
```sql
SELECT id, stripe_customer_id, attempts, last_error, last_attempt_at
FROM stripe_customer_dlq
WHERE resolved_at IS NULL
ORDER BY last_attempt_at DESC
LIMIT 20;
```

---

## 12. Webhook latency monitoring

Alert threshold: **p99 > 3000 ms** on `POST /v1/webhooks/stripe`.

Stripe retries failed webhooks up to 3 days. The webhook handler must
complete within 30 s (Stripe timeout) — the p99 alert gives headroom
before timeouts start.

Monitor via your APM / log aggregator. Key log line to search for:
```
POST /v1/webhooks/stripe  [latency_ms=...]
```

If latency spikes: check Supabase/Postgres connection pool saturation
and Redis availability. The handler does synchronous DB writes — a
pool bottleneck will cascade to webhook timeouts.

---

## 13. Monthly reconciliation

Verify `credit_ledger` totals match Stripe revenue.

```sql
-- Total credits purchased this calendar month
SELECT
  DATE_TRUNC('month', created_at) AS month,
  reason,
  SUM(amount_milli) AS total_milli
FROM credit_ledger
WHERE created_at >= DATE_TRUNC('month', now())
  AND amount_milli > 0
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

Cross-reference with Stripe Dashboard → Reports → Revenue. Discrepancies
indicate missed or duplicate webhook deliveries. Investigate the
`stripe_webhook_events` dedup table for gaps.

Perform this check on the 1st business day of each month.

---

## 10. Delete-account ordering with payments (Unit 11)

The `DELETE /auth/account` handler runs these payment-related steps in strict order:

| Step | When | Action |
|------|------|--------|
| **1.5** | Before auth-delete | Drain in-flight `credit_reservations` via `credit_release` RPC (best-effort per row; enumeration failure is logged + skipped) |
| **1.6** | Before auth-delete | Abort known per-user ARQ jobs (`delete_account:{uid}`, `weekly_free_grant:{uid}`) — best-effort |
| **3.5** | After auth-delete, before users-row DELETE | Call `PaymentPort.delete_customer(stripe_customer_id)` with ~3 s timeout; on any failure write to `stripe_customer_dlq` and continue |

**Invariants:**
- Steps 1.5 and 1.6 are always best-effort: a failure in either step does **not** abort the delete.
- Step 3.5 is best-effort **after** the Supabase auth identity is gone — the overall delete returns 204 regardless of the Stripe outcome.
- Users without a `stripe_customer_id` skip step 3.5 entirely.

**Retry path:** If step 3.5 fails, the `stripe_customer_dlq_reconciler` cron retries nightly at 04:00 UTC (see section 11 below).

---

## 11. Stripe customer DLQ sweeper

**Worker:** `app/workers/stripe_customer_dlq_reconciler.py`
**Cron:** daily 04:00 UTC
**Table:** `stripe_customer_dlq`

### What it does

Iterates up to 100 DLQ rows ordered by `(attempts ASC, inserted_at ASC)` and calls `PaymentPort.delete_customer` for each:
- **success** → deletes the row
- **`resource_missing`** → treats as success (customer already gone) → deletes the row
- **any other failure** → increments `attempts`; emits `WARNING` when `attempts > 5`

### Inspect the table

```sql
-- View all pending DLQ rows
SELECT customer_id, reason, attempts, last_error, inserted_at, updated_at
FROM stripe_customer_dlq
ORDER BY attempts DESC, inserted_at;

-- Count rows above the warning threshold (attempts > 5)
SELECT count(*) FROM stripe_customer_dlq WHERE attempts > 5;
```

### Manual drain (one-off)

```python
# Run from a Python shell with app environment loaded
import asyncio
from app.db.client import get_supabase_service
from app.repositories.stripe_customer_dlq import StripeCustomerDLQRepository
from app.payment.adapters.stripe_adapter import StripePaymentAdapter

async def drain():
    sb = get_supabase_service()
    repo = StripeCustomerDLQRepository(sb)
    payment = StripePaymentAdapter()
    for row in repo.list_drainable(100):
        cid = row["customer_id"]
        try:
            await payment.delete_customer(cid)
            repo.delete(cid)
            print(f"deleted {cid}")
        except Exception as e:
            print(f"FAILED {cid}: {e}")

asyncio.run(drain())
```

### Escalation

If rows stay above `attempts > 5` after multiple days: the Stripe customer may have been detached from its account in the Stripe dashboard, or the API key may lack permission. Investigate via `last_error` column and the Stripe dashboard.

---

## 12. processed_webhook_events 30-day purge

**Worker:** `app/workers/purge_old_webhook_events.py`
**Cron:** daily 03:45 UTC
**Table:** `processed_webhook_events`

### Purpose

Stripe webhook idempotency keys are kept in `processed_webhook_events` to deduplicate replay attempts within the delivery window. Rows older than **30 days** are outside any reasonable Stripe retry window and constitute unnecessary PII/event retention.

The worker issues a single `DELETE ... WHERE inserted_at < now() - 30 days` — the `inserted_at` index from migration 0001 makes this index-driven with no sequential scan.

### Retention constant

```python
# app/workers/purge_old_webhook_events.py
_WEBHOOK_EVENT_RETENTION_DAYS = 30
```

Changing this value requires only a code edit + redeploy (no migration). If Stripe extends its retry window beyond 30 days, increase accordingly.

### Verify purge ran

```sql
-- Confirm no rows older than 30 days remain
SELECT count(*) FROM processed_webhook_events
WHERE inserted_at < now() - interval '30 days';
-- Expected: 0 after nightly purge completes
```
