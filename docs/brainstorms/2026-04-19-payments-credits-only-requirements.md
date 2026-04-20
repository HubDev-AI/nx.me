---
date: 2026-04-19
topic: payments-credits-only
---

# Payments & Subscriptions: Credits-Only Engine

## Problem Frame

nxme.ai is pre-launch. The current payments/entitlement code has three visible bugs and broad maintainability debt:

1. Mobile shows "Free tier" and "subscription expired" simultaneously — `subscriptions.status` enum carries `expired`/`past_due` values that webhook handlers never produce, and `period_end` is not cross-checked at read time.
2. Tries-left is not enforced. `users.trial_analyses_remaining` initialises once but is never decremented; gating routes through `usage_events` count instead. Two truth sources diverge.
3. CREDITS tier is effectively unlimited — only `balance > 0` is checked, no per-call cost match.

Underlying cause: the domain is modelled as three parallel systems — tiers (`tiers` table + `tier_id`), trials (`users.trial_analyses_remaining`), and credits (`credit_ledger`). Each has its own counter and its own read path, so the sources of truth drift apart. Grandfathering is impossible today because tier configuration is mutated in place.

This brainstorm consolidates the three systems into a single credit ledger that is the source of truth for every billable action. Tiers remain as marketing labels on the paywall, but carry no quota logic. Pre-launch timing permits destructive schema changes, but a two-phase migration (additive first, destructive second — see R23) is still required to coexist with a concurrent bug-fix agent.

Referenced context: ideation doc at `docs/ideation/2026-04-19-payments-subscription-review-ideation.md`.

## Requirements

**Economy and accounting**

- R1. One credit ledger is the single source of truth for remaining entitlements. Every billable action reads and writes this ledger; no other counter enforces quota.
- R2. The internal unit of account is the **milli-credit** (integer). 1 glow-up generation = 100 milli-credits. 1 Ada/advisor message = 5 milli-credits (final ratio TBD in planning; constraint is that both glow-up and Ada costs are whole numbers of milli-credits). The `credit_ledger.delta` column and sum RPC remain INTEGER; no NUMERIC migration. User-facing display translates milli-credits into glow-ups and approximate Ada-message counts (see R3).
- R3. A user's displayed balance is `floor(milli_balance / plan_version.glowup_cost_milli)` glow-ups plus `floor(milli_balance / plan_version.ada_cost_milli)` approximate Ada messages — divisors come from the user's active plan_version row, not hardcoded. When `milli_balance < cost_of_next_action`, the action is atomically rejected before any state change, not partially debited. The milli-credit unit is never surfaced to users. Because glow-ups and Ada share one balance, the mobile UI must make the shared pool explicit (e.g., "You have X glow-ups OR ~Y Ada messages from a shared balance") — see Outstanding Questions for UX decision.
- R4. Every quota-consuming call performs an atomic reserve→commit/release cycle using the existing `credit_reservations` + `credit_ledger` primitive (per `app/migrations/0014_credit_ledger_rpcs.sql` and the advisory-lock variant `0019_credit_reserve_advisory_lock.sql`). Reserve debits milli-credits at job enqueue; commit finalises on success; release restores milli-credits on failure. The atomic reserve step is implemented as an RPC that acquires `pg_advisory_xact_lock(hashtext(user_id::text))` (same lock domain as 0019), then inside that lock: (1) SELECTs `users.locked_at` and `SUM(credit_ledger.delta)`, (2) rejects if `locked_at IS NOT NULL OR balance < p_amount_milli`, (3) INSERTs the reservation + ledger rows atomically. Balance is NEVER cached to `users`; ledger `SUM(delta)` remains the single source of truth (R1). REPLACE operations (R7/R11) and dispute-lock writes (`UPDATE users SET locked_at = now()`) acquire the SAME advisory lock, eliminating TOCTOU between reserve, REPLACE, and lock-set. The worker's `credit_commit_v2` RPC joins `users` and converts commit→release if `locked_at IS NOT NULL` at commit time. On lock-during-in-flight after fal.ai generation has completed, the worker marks the generation output as `dispute_review_quarantine` (hidden from user until dispute resolves) instead of double-loss. Failure mode for insufficient balance or locked account is a typed `InsufficientCredits` or `AccountLocked` error carrying the next-purchase or support URL.
- R4a. Ada is **ledger-gated**, not tier-gated. Any user — Free, Pro, grace, canceled, locked-by-dispute — may consume Ada if `milli_balance ≥ ada_cost` and no higher-level lock applies (see R-Dispute). The Free/Pro label does not gate Ada access; the ledger does. Mobile does not check tier label when displaying Ada availability.

**Paywall product shape (Tiers as marketing, credits as engine)**

- R5. Two visible tiers: **Free** and **Pro**. These names appear on the paywall, in marketing copy, and in support communication. They carry no quota logic in the gating layer — gating is always ledger-based. The tier label is derived from subscription lifecycle state (R14a).
- R6. The Free tier grants credits via two mechanisms:
  - **Signup grant**: a one-time grant on first successful signup, credited as a ledger entry of type `signup_grant`. Value in milli-credits is a planning number (recommended: 300 milli = 3 glow-ups).
  - **Weekly regen**: a recurring grant of type `weekly_free_grant` issued every 7 days to every Free user (not to Pro users — Pro refill covers it), value TBD (recommended: 100 milli = 1 glow-up/week). Runs as an ARQ scheduled job. Grant is idempotent per `(user_id, ISO-week)` — re-running the job for the same user+week is a no-op.
  - Both grants land in `credit_ledger` like any other grant; R1's single-source-of-truth holds.
- R6a. The signup grant is **device-fingerprint-bound** to deter casual farming. Narrow scope: prevents naive same-device re-signup only. Does NOT prevent emulator, factory-reset, IDFA-reset, web-signup (card-web has no device signal), or device-transfer bypass. Those vectors are tolerated as CAC loss at pre-launch scale; revisit if observed abuse justifies.
  - **Signal**: installation-UUID generated on first native-app launch (not IDFA, not Android ID — avoids device-transfer false-positive). Web signups get no fingerprint (null); they are tolerated as unprotected.
  - **Lookup and storage**: two-level scheme. Primary lookup key is `deterministic_hash = HMAC-SHA256(server_secret, installation_uuid)` — indexed, deterministic, supports O(1) lookup at signup time. `server_secret` is a single, long-lived, high-entropy env var (not rotatable without rehashing the table). The stored value is `protected_hash = SHA256(salt || installation_uuid)` where `salt` is per-row 32-byte random, stored alongside — provides at-rest protection against rainbow-table compromise of the table backup. Lookup by `deterministic_hash`; signup-grant suppression uses the matched row without re-derivation. Per-row salt is at-rest-only (not used for dedup). Rejects rainbow-table attack on table dump; rejects DoS via full-scan lookup.
  - **TTL**: 12 months. Fingerprint entries older than 12 months are purged by a nightly ARQ job — after a year the device is presumed transferred/replaced.
  - **Storage**: `signup_grants_issued(fingerprint_hash BYTEA, salt BYTEA, issued_at TIMESTAMPTZ)` table. Survives `delete_account` — explicit exception to `feedback_delete_account_scope`, documented in Dependencies. GDPR-status of this record requires legal review before Phase A migration ships (see Outstanding Questions).
  - Re-signup on the same device within 12 months after delete: signup grant skipped, ledger entry `signup_grant_suppressed_by_fingerprint` written for audit. The user can still receive weekly_free_grant entries on the new account.
  - `weekly_free_grant` is not fingerprint-bound — grants only to existing accounts.
- R7. The Pro tier is subscription-only as the primary SKU. A successful subscription charge REPLACES the user's balance with the plan amount (in milli-credits) on each billing period start — use it or lose it, no rollover, no stacking. "Monthly allotment" is the canonical schema/code term. Pro users do not receive the weekly_free_grant (their refill is the monthly allotment).
- R7-Pack. A single one-time credit pack SKU is offered as a secondary paid option: $4.99 for N credits (N TBD in planning; recommended 500 milli = 5 glow-ups). Inherits the existing `create_payment_intent` flow at `app/payment/adapters/stripe_adapter.py:122-181` + the PaymentSheet integration in `mobile/lib/hooks/use-purchase-flow.ts`. Pack credits are granted EXCLUSIVELY via the server-side `payment_intent.succeeded` webhook handler (`app/api/webhooks.py:_handle_payment_intent_succeeded`) — client-side PaymentSheet completion is never trusted as authorization for a ledger write. All mandates from R18 apply (signature verify, idempotency, out-of-order tolerance). The pack is a direct ledger grant of type `credit_pack_purchase`. Purchased pack credits ADD to the ledger balance (one-time purchases are the one legitimate additive case); REPLACE operations (R7/R11) leave `credit_pack_purchase` ledger entries untouched. Packs are available to both Free and Pro users as an impulse-buyer on-ramp.
- R8. Only one Pro subscription can be live per user at a time (enforced by a partial UNIQUE index on `subscriptions(user_id) WHERE status='active'` per the existing `partial-unique-index-for-republish-after-soft-delete-2026-04-19` solution). Re-subscription after cancellation is supported and produces a fresh subscription row. No cooldown on resub because R7's REPLACE semantics eliminate the cancel→resub stacking exploit by construction (old balance is replaced, never additive).

**Payment failure and grace**

- R9. When a Pro auto-renewal charge fails, the user enters a **grace** state for 3 days. `grace_until = now() + 3 days` at the moment the webhook `invoice.payment_failed` is processed (not relative to `period_end` — the billing-period boundary is already past at this point). During grace, existing credits remain consumable and the tier label stays Pro. Stripe Smart Retries run automatically.
- R10. If grace expires without a successful charge, the tier label flips to Free on the next `get_entitlement` call (derived from `grace_until < now()`). The current credit balance is retained — it does not zero out. Ada access continues per R4a because Ada is ledger-gated, not tier-gated. Only tier-label-sensitive UI (paywall copy, billing screen) changes.
- R11. A successful retry during grace or within Stripe's retry window after grace expiry fires `invoice.payment_succeeded`. On that event:
  - If the user's label is currently "grace": `grace_until` is cleared, label restores to Pro, monthly allotment is REPLACED per R7 (not added — "fresh allotment" means a ledger entry `monthly_allotment` that REPLACES the current balance with `plan_version.monthly_allotment_milli`, discarding any retained balance). No stacking possible.
  - If the user's label has already flipped to Free (grace expired): the subscription revives, label returns to Pro, monthly allotment is REPLACED per R7. `grace_until` stays cleared. Any pack-purchased credits (from `credit_pack_purchase` entries) are preserved — only monthly_allotment / weekly_free_grant / signup_grant entries are discarded at REPLACE time. Pack credits never expire and coexist with the monthly refill.

**Grandfathering (price + credit amount)**

- R12. Pro plan configuration is versioned. A plan version freezes **price, monthly allotment, glow-up cost, AND Ada cost** (all in milli-credits) per cohort. Changing any of those four creates a new plan version; existing subscribers remain bound to the plan version they originally subscribed to until they explicitly migrate. Schema: `plan_versions(id, version_num, price_usd_cents, monthly_allotment_milli, glowup_cost_milli, ada_cost_milli, created_at)` with `subscriptions.plan_version_id` FK.
- R13. Non-quota feature changes (new capabilities, UI changes, moderation rule tweaks) deploy globally on deploy — they are not grandfathered. The grandfathering guarantee is exactly: "price times effective monthly-message-and-glow-up purchasing-power stays constant for a locked cohort." If a change could increase how many credits a given action consumes, it must land as a new plan version, not a global deploy.

**Entitlement contract**

- R14. There is one authoritative entitlement shape returned by the backend. Mobile never derives status or balance from component parts; it renders whatever the single shape says. The shape includes: tier label (Free/Pro), remaining-glow-ups count (from R3 computation), approximate remaining-Ada-messages hint (from R3 computation), subscription status (active | grace | none | canceled | locked), period-end or grace-end timestamp where applicable, and a per-action `blocked_reason` field.
- R14a. `blocked_reason` is typed as a closed enum: `insufficient_credits | subscription_locked_by_dispute | none`. Mobile switches on this enum to render the right paywall CTA; it never infers a reason from combinations of other fields. Grace expiry does not block actions — per R4a and R10, Ada and billable actions remain ledger-gated even when the label has flipped to Free. `pro_feature_locked` is not in the enum (R4a removed Pro-only feature-tier-gating). The paywall CTA for grace-expired users is purchase-focused (no blocking reason), not support-focused.
- R14b. **Drift protection for derived status.** `get_entitlement` computes subscription status from `period_end`, `cancel_at`, `grace_until`, and `locked_at` timestamps. To tolerate out-of-order Stripe event delivery at period boundaries, `get_entitlement` applies a 1-hour sticky buffer: if `period_end < now() < period_end + 1 hour` AND `grace_until IS NULL` AND no authoritative-fetch has succeeded within the buffer (check `subscriptions.last_authoritative_fetch_at`), the function triggers an authoritative Stripe fetch with a 3-second timeout. `last_authoritative_fetch_at` is nullable and defaults to NULL; existing subscription rows at Phase A migration time are seeded to `last_authoritative_fetch_at = now()` so no immediate forced re-fetch fires on deploy. Implementation requires adding `retrieve_subscription(stripe_sub_id, timeout=3)` to `app/payment/ports.py::PaymentPort` and implementing it in both `stripe_adapter.py` (via `stripe.Subscription.retrieve(sub_id, timeout=3)` or equivalent `run_in_executor` + `asyncio.wait_for`) and `mock.py`. On successful fetch, refreshed timestamps are persisted to the subscriptions row AND `last_authoritative_fetch_at = now()` is set so subsequent calls within the same 1-hour buffer use the persisted data. On fetch failure, the function returns the last known-good status (active) and does NOT advance `last_authoritative_fetch_at`. Clock-skew note: the buffer uses app-server wall-clock throughout; container startup must NTP-sync (fail-fast if skew >30s against Stripe-reported timestamps in recent webhooks). Late-arriving webhook after buffer expiry: `grace_until` is written when the webhook eventually processes; retroactive-consumption during the buffer window is tolerated. Buffer revisited post-launch if telemetry shows a wider Stripe-delivery tail.

**Refunds**

- R15. Refunds are recorded as compensating ledger entries (negative `delta`), never as direct mutations of an existing row. A partial refund produces a partial compensating entry. Stripe-initiated refunds land via webhook (`charge.refunded`) and write the compensating entry. The existing `CreditLedger.refund` RPC (migration 0029) is the single primitive. User-initiated self-refund is **out of scope for v1** and deferred.

**Disputes and chargebacks**

- R-Dispute-1. On `charge.dispute.created`, the user account is set to `locked_at = now()`. While `locked_at IS NOT NULL`, all billable actions are blocked with `blocked_reason = "subscription_locked_by_dispute"`. Paywall shows a contact-support message, not a purchase flow.
- R-Dispute-2. On `charge.dispute.closed` with outcome `won`, `locked_at` is cleared. The user regains normal access.
- R-Dispute-3. On `charge.dispute.closed` with outcome `lost`, `locked_at` stays set and a compensating ledger entry is written for the credits granted by the disputed charge (may produce negative balance — acceptable; the user is locked anyway). The account remains locked pending staff review. No automatic unlock.
- R-Dispute-4. `charge.dispute.funds_withdrawn` writes an internal audit log entry; no ledger or state change (the dispute-created handling already covered the user-facing lock).

**Guest users**

> **SUPERSEDED 2026-04-20** by `docs/brainstorms/2026-04-19-B-delete-guest-merge-plumbing-requirements.md`.
> The guest-merge pathway is deleted. New signups receive the flat
> `signup_grant` with no merge transfer from prior anonymous sessions. The
> 2× cap, pack-bypass, install-UUID binding, and guest ledger entries
> (`guest_merge_non_pack`, `guest_merge_truncated`) no longer exist.
> Weekly-free-grant applies to every non-Pro user (is_guest column dropped).

- R16. Guest users receive the same ledger shape as authenticated users, keyed by guest token, from the first billable action.
  - **Existing infrastructure**: the `app/db/guest.py` module already generates 256-bit tokens via `secrets.token_hex(32)` and stores them on `users.guest_session_token` with `is_guest = true`. Mobile SecureStore + `X-Guest-Token` header delivery already exists per `mobile/lib/guest-session.ts`. This brainstorm does NOT introduce a new `guest_tokens` table; it reuses existing primitives with the additions below.
  - **Session binding**: the existing `X-Guest-Token` header mechanism is the session binding (naturally ties token to the device's SecureStore). No cookie primitive — React Native has no first-class cookie jar. The token is delivered in one request header; tampering is detected by invalid-token rejection at merge time. 128-bit entropy (existing 256-bit exceeds) already makes cross-token substitution infeasible by enumeration.
  - **Merge-on-signup**: at signup, the client presents the guest token; server atomically (single transaction) (a) validates the token active via existing `resolve_guest_by_token`, (b) transfers ledger entries from guest-user-row → new-user-row with a CAP of 2× signup grant value for NON-pack entries (prevents ledger farming), (c) marks the guest user row as merged (add `merged_into_user_id UUID NULL` + `merged_at TIMESTAMPTZ NULL` columns to `users` rather than a new table), (d) writes the signup grant to the new user (subject to R6a fingerprint check).
  - **Weekly regen for guests**: guests do **NOT** receive `weekly_free_grant` entries — R6 is hereby clarified: weekly_free_grant applies to `is_guest = false` users only. The 2× cap is calibrated against signup-grant scale alone.
  - **Cap overflow**: if the guest non-pack ledger exceeds 2× signup grant, excess is discarded with an audit entry AND the mobile client is told about the truncation at merge-time (dedicated UI: "X credits will not transfer — reason Y") so the balance drop is not silent.
  - **Pack preservation**: `credit_pack_purchase` entries bypass the cap entirely — legitimate purchases transfer whole.
  - Guest-first-class applies to every paywall and credit surface.

**Delete-account wiring**

- R17. Every new user-owned surface introduced by this feature (Stripe customer id, ledger rows, subscription rows, any Redis keys for credit counters, any SecureStore keys on device caching balance) is registered with the account-delete hard-reset flow in the same change-set. Follows the registry pattern from `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md`.

**Webhook reliability**

- R18. Webhook handling satisfies these **constraints** (the specific mechanism — inline-with-idempotency-table vs outbox+async — is a planning decision):
  - **Signature verification is mandatory** and executes before any handler logic, before idempotency checks, before any DB read/write. HMAC-SHA256 via `stripe.Webhook.construct_event` on the raw request body (not the parsed JSON). Timestamp tolerance 300 seconds (Stripe default); events outside the tolerance return 400. Missing or invalid signature returns 400 with no state mutation. Re-verification is also required when an async worker picks up an event from a durable outbox (protects against DB-level event forgery between ingest and processing).
  - Handlers return 200 within 5 seconds. No external calls in the fast path other than signature verification itself.
  - Handlers are idempotent against Stripe's at-least-once delivery, keyed by `event_id` (existing `processed_webhook_events` primitive is acceptable).
  - Handlers tolerate out-of-order events by re-fetching canonical state from Stripe when the event payload alone cannot determine the correct action (e.g., `subscription.updated` before `subscription.created`). Re-fetches have a 3-second timeout and a circuit-breaker: on sustained Stripe-API failure, events requeue for retry rather than process with stale data. Re-fetch is triggered ONLY when the idempotency check or payload inspection suggests possible out-of-order — not on every event.
  - Events older than 72 hours on first-attempted processing are logged and discarded.
  - Handler pipeline must be resilient to the async-processor being down for up to 1 hour; Stripe retries compensate for longer outages.

**Dev and test ergonomics**

- R19. A single bootstrap path brings a local developer from empty `.env` to a working test-mode loop: starts `stripe listen --forward-to localhost:8000/webhooks/stripe`, writes the session signing secret to `app/.env`, seeds test products and prices matching the current plan_versions rows, and prints test cards for manual QA. Human never types a Stripe secret.
- R22. A debug endpoint `GET /v1/__debug/entitlement/{user_id}` returns the decision trace for any user's current entitlement (subscription row, recent ledger entries, recent webhook events, derivation path including R14b's drift-protection decision).
  - **Authentication**: requires a shared internal bearer token (env var `DEBUG_BEARER_TOKEN`, ≥256-bit random, stored in secrets manager not plain `.env` for staging) checked at request time, not startup-only. Rotation: on staff change + every 90 days scheduled.
  - **Redaction**: Stripe `customer_id` is OMITTED from the trace unless the env var `DEBUG_INCLUDE_CUSTOMER_ID == "true"` AND the request includes `?include_customer_id=true`. Single boolean env var, not a role-scoped token (no role-scoped-token infrastructure exists and the single-env-var pattern solves the same problem).
  - **Environment gate**: startup assertion refuses to mount the route when `APP_ENV == "prod"`. Additional runtime check on every request asserts `APP_ENV != "prod"` (defence in depth).
  - Dev and staging only. Logs every access (token hash + target user_id + requesting IP + timestamp) for post-hoc audit. Since the token is shared, the audit log identifies the token and the IP, not a specific caller identity.
- **Deferred to v1.1:**
  - R20 (dev-only `POST /__admin/entitlement/set` endpoint for QA state injection) — direct DB writes + `stripe trigger` cover most scenarios at v1 scale.
  - R21 (auto-recorded webhook fixtures + replay harness) — manually authored pytest fixtures for the known scenarios (payment_failed, grace_expired, dispute_created, resub_cooldown) cover the regression goal without building a recording pipeline.

**Migration**

- R23. Migration lands as a **two-phase split** to coexist with the concurrent bug-fix agent:
  - **Phase A (additive, safe to interleave):**
    - Create: `plan_versions`, `signup_grants_issued(deterministic_hash BYTEA PRIMARY KEY, protected_hash BYTEA, salt BYTEA, issued_at TIMESTAMPTZ)` (fingerprint registry with 12-month TTL, survives delete, service-role-only access enforced by RLS `DENY ALL FOR anon, authenticated`), `users.locked_at`, `users.merged_into_user_id` + `users.merged_at` (guest-merge audit, no separate table — reuses existing `app/db/guest.py` primitives), `users.monthly_allotment_milli` (snapshot for fast reads), `subscriptions.plan_version_id`, `subscriptions.grace_until`, `subscriptions.last_authoritative_fetch_at` (nullable, seeded to NOW() for existing rows). Add `retrieve_subscription` method to `PaymentPort` (ports.py) + `StripePaymentAdapter` + `MockPaymentAdapter`.
    - Extend `credit_ledger.type` CHECK enum (DROP CONSTRAINT + ADD CONSTRAINT pattern — Postgres does not support ALTER CONSTRAINT on CHECK) with new types: `signup_grant`, `signup_grant_suppressed_by_fingerprint`, `weekly_free_grant`, `monthly_allotment`, `credit_pack_purchase`, `ada_message`, `dispute_compensation`, `retained_preserved` (audit entry on REPLACE).
    - **RPC signature migration**: ship parallel `_v2` RPCs (`credit_reserve_v2`, `credit_release_v2`, `credit_commit_v2`, `credit_refund_v2`) accepting `(p_user_id UUID, p_reservation_id UUID, p_action_type TEXT)` — NOT `p_amount_milli`. The RPC resolves cost server-side by looking up the user's active `plan_version_id` and reading `plan_versions.glowup_cost_milli` or `ada_cost_milli` keyed by `p_action_type`. Caller never supplies an amount. This prevents caller-controlled undercharge exploits and keeps the cost authoritative to `plan_versions`. All RPCs remain `SECURITY DEFINER` with `SET search_path = public` (consistent with `0021_security_definer_search_path.sql`). RPCs validate `auth.uid() = p_user_id` for user-authenticated callers; service-role callers bypass this check (service role already implies operator trust). SUM aggregates return BIGINT; `credit_ledger.delta` stays INTEGER per R2. Old RPCs remain available during Phase A for concurrent bug-fix-agent work; Phase B flips all call-sites to `_v2` and drops the old RPCs.
    - Starting migration number: 0048+ (current highest is 0047).
    - No drops in Phase A. Concurrent agent's fixes on existing tables are unaffected provided both workstreams reserve distinct migration number ranges (coordination protocol: Phase A reserves 0048–0052; concurrent agent takes 0053+ or vice-versa — decided in planning).
  - **Phase B (destructive, gated on read-path cutover AND writer cutover):** Before dropping `subscriptions.status` enum values, all writers that currently write these values must be flipped first: `app/api/webhooks.py:_handle_payment_failed` must write `grace_until` instead of `status='past_due'`; `_handle_subscription_deleted` must write `cancelled_at` instead of `status='expired'`. Once writers are cut over AND all readers use the new date-based derivation, drop: `tiers`, `users.tier_id`, `users.trial_analyses_remaining`, `usage_events`, the `subscriptions.status` enum values (`past_due`, `expired`), and the legacy `credit_reserve`/`credit_release`/`credit_commit`/`credit_refund` RPCs (all call-sites now use `_v2`). `credit_reservations` **stays** (see R4) — reserve→commit/release primitive preserved.
  - Dev seed data loss is accepted for Phase B. Phase B cannot merge until all read paths have been flipped to the new derivation (R14b) and all writer paths have been updated to write dates, not status strings. Phase A and Phase B may be split across multiple migration files in sequence.

**Copy and audience**

- R24. All user-facing paywall copy, empty-states, and error messages targeting balance/subscription concerns are written for a majority-female audience. No male-coded or gender-neutral-by-default phrasing. Per `feedback_female_user_targeting`.

## Success Criteria

- The three visible bugs cannot recur by construction: "Free + expired" is not representable; tries-left is always the ledger sum; no tier encodes unlimited quota.
- A new developer goes from fresh clone to a working Stripe test-mode loop with one `make stripe-dev` invocation.
- A Pro plan price, monthly allotment, glow-up cost, or Ada cost can be changed without affecting any existing subscriber until they explicitly migrate.
- When a paid user's card fails, they retain access to unused credits for 3 days before the label flips; the `get_entitlement` drift-protection buffer (R14b) prevents mistaken "expired" display during Stripe event-delivery jitter.
- A Free user receives a signup grant and a weekly_free_grant grant automatically. Re-signup on the same device after `delete_account` does NOT re-issue the signup grant.
- A `dispute.created` webhook locks the user within 5 seconds; `dispute.closed_won` unlocks automatically; `dispute.closed_lost` holds the user in locked state pending staff review.
- A deleted account leaves no Stripe customer id, ledger row, subscription row, or device-cached balance behind, **except** the `signup_grants_issued` fingerprint record which is by design and documented in Dependencies.
- Mobile and backend agree on entitlement state across every billable surface: the single `EntitlementState` shape is the only contract; no client-side derivation of tier, balance, or `blocked_reason`.

## Scope Boundaries

- Multiple Pro SKUs (Pro Lite / Pro / Pro Max) are excluded from v1. Exactly one Pro tier with one plan version at launch.
- Multiple pack SKUs are excluded from v1. Exactly one pack SKU per R7-Pack at launch.
- Annual-billing Pro is excluded from v1.
- Rollover of unused monthly allotment credits is **not** a requirement. Each billing period resets.
- Feature-set freeze beyond quota costs is excluded. Non-quota feature changes deploy globally.
- Per-preset or per-intensity pricing differentiation for glow-ups is excluded. Every glow-up = `glowup_cost_milli`.
- An admin console for publishing new plan versions is excluded from v1; plan-version rows are created via migration or direct DB write.
- Dunning email cadence and copy (beyond Stripe Smart Retries defaults) are excluded from v1.
- "Subscription pausing" and "downgrade mid-period" UX flows are excluded from v1.
- User-initiated self-refund is excluded from v1.
- Dev admin-entitlement-set endpoint (former R20) and auto-recorded webhook fixture pipeline (former R21) are deferred to v1.1.
- Full fraud-hold state machine is excluded; minimal dispute-lock per R-Dispute-* is v1 scope.
- Staff-admin primitives (grant-credits-to-user, force-migrate-plan-version) are excluded from v1 UI; direct DB writes via planned helper scripts cover v1 support scenarios.

## Key Decisions

- **Tiers visible, credits invisible (engine)** — Marketing labels (Free/Pro) stay as derived-from-subscription. All quota logic is ledger-based. Tier label never gates actions; the ledger does.
- **Signup grant + weekly_free_grant for Free; no one-time packs in v1** — Signup grant (one-time, fingerprint-bound) gives day-1 product experience; weekly_free_grant creates a habit loop for non-converters. One cheap decision with two compounding effects on top-of-funnel health.
- **Ada is ledger-gated, not tier-gated** — Any user with sufficient milli-credits can send Ada messages. Resolves the two-truth-sources tension by construction. Pro is a refill rate, not a feature gate for Ada.
- **Milli-credit internal unit** — 1 glow-up = 100 milli, 1 Ada message = 5 milli. Integer math only; `credit_ledger.delta` stays INTEGER. User-facing display converts to glow-ups + approximate Ada messages.
- **Subscription + one pack SKU** — Pro subscription for predictable MRR; one-time pack SKU as the impulse-buyer on-ramp (captures intermediate willingness-to-pay without multi-SKU sophistication).
- **Grace + retain balance on payment fail** — Industry norm (RevenueCat model). Stripe Smart Retries handle retries.
- **REPLACE-not-ADD on every allotment event** — R7 monthly refill and R11 retry-success both REPLACE the balance with `plan_version.monthly_allotment_milli`. Pack purchases (R7-Pack) are the only ADD case. By construction, cancel→resub and fail-retry stacking exploits are impossible. No 30-day cooldown machinery needed.
- **Grandfather price + allotment + per-action costs** — A plan version freezes price, monthly allotment, glow-up cost, and Ada cost. New rates → new plan version. Non-quota feature changes still deploy globally.
- **Two-phase migration** — Phase A additive-only (safe to land concurrently with bug-fix agent); Phase B destructive, gated on read-path cutover.
- **Derive status from dates, with drift protection** — Subscription status derived from dates. `get_entitlement` applies a 1-hour sticky buffer past `period_end` with authoritative Stripe fetch to tolerate event-delivery jitter.
- **Reserve→commit/release primitive preserved** — Existing `credit_reservations` machinery stays; worker.py's auto-refund pattern works unchanged. Fal.ai business-cost leak on failure is a known tradeoff unaffected by this decision — tracked separately.
- **Dispute handling v1: lock on created, unlock on won, compensate on lost** — Minimal state addition (`users.locked_at`). Full fraud-hold modeling deferred.
- **Device-fingerprint on signup grant survives delete** — Explicit exception to `feedback_delete_account_scope` hard-reset-invariant. Prevents casual farming. Trade-off acknowledged.

## Dependencies / Assumptions

- Stripe test account is being obtained by the user this cycle.
- Stripe Smart Retries is acceptable as the default retry policy; no custom schedule.
- `@stripe/stripe-react-native` PaymentSheet remains the mobile checkout surface (`mobile/lib/hooks/use-purchase-flow.ts`).
- Fal.ai bills per API call regardless of success/failure — the reservation primitive (R4) protects the USER experience (auto-refund on provider error, preserved in `app/generation/worker.py` `_fail_job`); the BUSINESS absorbs the cost leak when fal.ai fails post-commit. This is a known cost-leak tradeoff, not an architectural bug, and is orthogonal to this feature. A separate fal.ai-reliability initiative may revisit later.
- **Two-phase migration (R23) resolves the concurrent-agent conflict by construction.** Phase A is additive only and can land any time; Phase B is gated on completion of read-path cutover in the same change-set and must not merge until the concurrent bug-fix work on `app/api/entitlement.py`, `app/api/webhooks.py`, or `app/entitlement/service.py` is merged.
- `useCapabilities()` (mobile) and `require_app_feature()` (backend) remain the gating module. The entitlement reshape plugs into the same seam.
- The existing `credit_ledger.delta` column stays INTEGER under the milli-credit scheme (R2). No NUMERIC migration.
- **Explicit exception to `feedback_delete_account_scope`:** the `signup_grants_issued(fingerprint_hash, issued_at)` table survives `delete_account` (R6a). Fingerprint hash is non-PII (derived from device signal, not linked to identity post-delete). This is the first and only hard-reset exception; any similar exception in the future requires an equivalent named justification.
- Stripe's Smart Retries default window (assumed ~2-3 weeks of retries total) extends beyond our 3-day grace. After day 3 the app flips label to Free but the subscription may still recover via Stripe retry; R11's "successful retry during or after grace restores Pro" handles that transition. Confirm Stripe's current retry schedule during planning; if it has changed, align the grace window or override Stripe's schedule explicitly.

## High-Level State Machine

Subscription lifecycle (no `trialing` state in v1 — Stripe product config is created without `trial_period_days`). All transitions derived from date columns + `locked_at`:

```
   none ─── subscribe ──▶ active
                            │
                            │◀──── renew_success ◀──┐
                            │                        │
                            ├── period_end + charge_fail ──▶ grace ──┐
                            │                                         │
                            │          ◀── retry_success ◀────────────┤
                            │                                         │
                            │       grace_end(3d) + no_success ──▶ expired
                            │                                         │
                            └── cancel_at_period_end ──▶ canceled ──▶ none

   [any state] ── dispute.created ──▶ locked
                  │
                  └── dispute.closed_won ──▶ [prior state restored]
                  └── dispute.closed_lost ──▶ remains locked (staff review)
```

Entitlement label and access:

| State | Label | Credits consumable (per R1/R4) | Ada accessible (R4a) |
|---|---|---|---|
| none | Free | Signup-grant + weekly-regen ledger balance | Yes if balance ≥ ada_cost |
| active | Pro | Monthly-allotment balance + any retained ledger | Yes if balance ≥ ada_cost |
| grace | Pro (banner: "update card") | Balance at grace entry, no new allotment | Yes if balance ≥ ada_cost |
| canceled (pre-period_end) | Pro (banner: "subscription ending") | Remaining balance | Yes if balance ≥ ada_cost |
| canceled (post-period_end) | Free | Remaining balance, weekly_free_grant resumes | Yes if balance ≥ ada_cost |
| expired | Free | Remaining balance (retained), weekly_free_grant resumes | Yes if balance ≥ ada_cost |
| locked | Free (banner: "contact support") | **Blocked** (`subscription_locked_by_dispute`) | Blocked |

Note: per R4a, Ada access follows the ledger, not the label. The "label" column here is purely for paywall-CTA display and marketing copy.

## Outstanding Questions

### Resolve Before Planning

- [Affects R2, R6, R7, R12] [User decision] Concrete numbers, in milli-credits where applicable:
  - Signup grant (recommendation: 300 milli = 3 glow-ups)
  - Weekly free regen (recommendation: 100 milli = 1 glow-up/week)
  - Pro monthly allotment (recommendation: 3000 milli = 30 glow-ups/month)
  - Pro monthly price (recommendation: $9.99/mo)
  - Ada cost per message (recommendation: 5 milli ≈ 600 messages/month on Pro)
  - Glow-up cost (anchor: 100 milli per generation)
  These must land in the Phase A migration's first `plan_versions` row and the corresponding Stripe Product/Price objects.

### Deferred to Planning

- [Affects R18] [Technical] Webhook outbox vs inline-with-idempotency-table. The constraints in R18 are satisfied by either; pick during planning once handler scope is enumerated.
- [Affects R6a] [Legal] Review `signup_grants_issued` design with legal before Phase A migration ships. Record characteristics: salted SHA-256 of installation-UUID (not IDFA/Android ID), 12-month TTL, survives `delete_account` for abuse-prevention. GDPR Art. 4(5) pseudonymization analysis + Art. 17 right-to-erasure response procedure required.
- [Affects R23 Phase A] [Technical] RPC signature migration approach: modify credit_reserve/release/commit/refund in place (requires atomic swap of all call sites + tests) vs. ship `_v2` parallel RPCs and flip call sites in Phase B (more files, cleaner rollback).
- [Affects R14b] [Needs research] Stripe event-delivery jitter empirical distribution. If observed >1h tail, widen R14b buffer.
- [Affects R12] [Technical] Admin workflow for force-migrating existing Pro users to a newer plan version. Not in v1 UI; the Phase B migration should leave `subscriptions.plan_version_id` mutable so a future direct-DB migration is possible.
- [Affects R16] [Needs research] Existing guest-token mechanism inventory — does `mobile/lib` already generate guest tokens via a known-entropy scheme, or does this require new token generation primitives?
- [Affects R3] [UX] Unified-currency display vs separate-pool framing. The mobile balance display must make the shared-pool nature explicit; designer decides final copy.
- [Affects R3] [Technical] Free users have no active subscription row, so `plan_version.glowup_cost_milli / ada_cost_milli` divisors must come from a default/v1 `plan_versions` row. Planning to confirm the resolution: either Free users reference the current `plan_versions.version_num = 'v1_free_default'`, or divisors fall back to app-config constants when no subscription row exists. Pick during planning.
- [Affects R7/R11] [UX] R7 REPLACE may punish light Pro users who consume <50% of allotment — they see 'credits disappeared' at every renewal. Mitigation options: (a) UI cue "X unused credits will refresh on {date}", (b) bounded rollover up to 1× (cap at 2× allotment). Planning decides with designer input.
- [Affects R7-Pack + R14a] [Product] Paywall CTA ordering is a matrix: (Free + insufficient) = Pro primary + pack secondary; (Pro-active + insufficient) = pack primary; (Pro-grace + insufficient) = update-card primary + pack secondary. Encode in mobile paywall component.
- [Affects R18] [Technical] Webhook signing-secret rotation: Stripe supports multiple active secrets during rotation. Planning decides between (a) trust ingest-time verification and drop re-verification at worker pickup (accept the DB-forgery risk), or (b) rotation-aware verifier that accepts multiple secrets during a transition window.
- [Affects R7-Pack + R15] [Product] Pack refund on fully-consumed pack produces negative balance that silently paywalls until balance > 0. Options: (a) cap compensating delta at current balance, (b) lock user for staff review, (c) allow negative + surface "refund in progress" UI. Decision needed before refund flow ships.
- [Affects R16] [Observability] `credit_pack_purchase` bypasses the 2× guest merge cap. A legitimate guest who stacks packs + survives merge is fine, but volumetric telemetry (guest purchases $X across Y packs) helps catch abuse post-launch.
- [Affects R17] [Technical] Enumerate every new user-owned surface introduced by this feature and wire into `delete_account` + `wipeLocalDeviceState` per `account-delete-hard-reset-invariant-2026-04-18` registry pattern. Known list: `users.locked_at`, `users.monthly_allotment_milli`, `subscriptions.plan_version_id / grace_until / last_authoritative_fetch_at`, `guest_tokens` (scoped to session), new ledger-entry types. `signup_grants_issued` is the one SURVIVES exception (documented).
- [Affects R22] [Technical] `DEBUG_BEARER_TOKEN` scheme: how is the token generated, rotated, and scoped? Pick during planning.
- [Affects R13] [Product] The grandfathering guarantee is narrower than it reads — it covers price + monthly allotment + glow-up cost + Ada cost but not success rate, moderation strictness, or model quality. Decide whether to document this limitation in user-facing copy or keep it silent. If user-facing, mobile billing screen needs a corresponding disclosure.

## Next Steps

→ Resume `/ce:brainstorm` to agree concrete numbers (R2/R3) if required, or note them as a planning-time product decision.
→ Then `/ce:plan` for structured implementation planning, phased per the concurrent-agent coordination constraint in Dependencies.
