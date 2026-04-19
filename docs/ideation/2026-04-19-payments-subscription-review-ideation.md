---
date: 2026-04-19
topic: payments-subscription-review
focus: simplification, maintainability, test-key ergonomics, grandfathering-ready, single truth source
mode: repo-grounded
---

# Ideation: Payments / Subscription Review

## Grounding Context

### Codebase Context

**Stack:** Python 3.12 FastAPI + Supabase Postgres + ARQ worker + React Native Expo. Pre-launch.

**Backend payments surface:**
- `app/api/entitlement.py` — `GET /v1/entitlement`, `POST /credit-purchases[/intent]`, `POST|DELETE /subscriptions`
- `app/api/webhooks.py` — `POST /webhooks/stripe`, idempotent via `processed_webhook_events`
- `app/api/deps.py` — `get_payment_adapter()` selects Stripe vs Mock via `ADAPTER__PAYMENT_ADAPTER`
- `app/entitlement/service.py` — authoritative `EntitlementService` (AC-D1): `get_entitlement()`, `can_generate()`, `check()`, `has_feature()`
- `app/entitlement/tier_repo.py` — Redis 5-min TTL tier cache
- `app/entitlement/ledger.py` — credit balance from `credit_ledger` deltas
- `app/entitlement/usage_repo.py` — time-windowed/total usage counts
- `app/repositories/subscription_repo.py` — subs + webhook dedup + atomic RPC `handle_checkout_credit_atomic`
- `app/payment/ports.py` — `PaymentPort` Protocol
- `app/payment/adapters/{stripe_adapter,mock}.py` — Stripe SDK (lazy import) vs deterministic stub
- `app/constants/tiers.py` + `app/config/tiers.py` — tier IDs + seed
- `app/api/refund.py`, `app/generation/cost_tracker.py`, `app/services/limits.py`

**DB schema:**
- `subscriptions` (status IN active|cancelled|expired|past_due; billing_period_start/end; cancelled_at)
- `tiers` (generation_type, generation_limit, generation_period_seconds, stripe_price_id, advisor_nudges_*, max_concurrent_generations, credits_based, feature_advisor_chat, feature_visual_comparison)
- `credit_ledger` (trial_grant, purchase, reserve, commit, release, refund, adjustment) + `credit_reservations`
- `processed_webhook_events`, `users.tier_id`, `users.trial_analyses_remaining`

**Mobile surface:** `mobile/app/subscription.tsx`, `mobile/lib/entitlement.ts`, `mobile/lib/hooks/use-purchase-flow.ts`, `mobile/components/subscription/{PlanCard,CancelSubscriptionSheet,CreditPackGrid}.tsx`, `@stripe/stripe-react-native` PaymentSheet.

### Symptoms

1. Stripe keys blank. Mock adapter active. No test-mode onboarding.
2. Mobile displays "free tier" AND "subscription expired" simultaneously — `subscriptions.status` enum has `expired`/`past_due` but webhooks never produce them; `period_end` not cross-checked in `get_entitlement()`.
3. Tries-left NOT enforced. `users.trial_analyses_remaining` initialized once, never decremented. Gating goes through `usage_events` count instead. Two sources diverge.
4. CREDITS tier unlimited — only `balance > 0` check, no per-call cost match.
5. Ada correctly blocked (expected behavior, not a bug).
6. Price config split — credit packs in env vars, tier sub price in `tiers.stripe_price_id`.
7. Sync webhook handlers inside async endpoint (no `run_sync` wrapper).
8. No grandfathering primitive — `tiers.generation_limit` changes affect all users retroactively.

### Constraints

- Pre-launch, `feedback_pre_launch_destructive_ok` applies for schema rebuild, but **architecture must support post-launch grandfathering**.
- Gating centralized via `useCapabilities()` + `require_app_feature()`; entitlement through `EntitlementService`.
- `feedback_no_hardcoded_urls`, `feedback_no_env_fallbacks`, `feedback_guest_first_class`, `feedback_delete_account_scope` apply.
- **Another agent is fixing issues in parallel** — direction-setting and architectural ideas are safer than line-level edits while they work.
- User will obtain Stripe test key next — dev ergonomics for test mode are explicit scope.

### Past Learnings

- `account-delete-hard-reset-invariant-2026-04-18` — new user-owned surface (Stripe customer_id, entitlement counters) must wire into `delete_account` + `wipeLocalDeviceState`. Check ARQ `enqueue_job` return (`_job_id` dedup within 24h TTL). Redis `scan_iter`, not `KEYS`.
- `enumerate-before-cascade-with-cas-2026-04-19` — CAS pattern for cron sweeps racing user actions. Re-assert predicate at commit. Reason constants server-side only.
- `orphan-dlq-symmetry-2026-04-19` — pre-record-before-op for webhooks. DLQ shape rules. Cron stagger (03:45/04:00 UTC taken). `MAX_ATTEMPTS=5` with WARN. `record()` never raises. Race-free UPSERT via `on_conflict`.
- `blocking-auto-save-for-durable-share-urls-2026-04-19` — mobile post-checkout must block with `raceWithTimeout(confirmSubscription, CHECKOUT_CONFIRM_TIMEOUT_MS)`. Typed error class. No fire-and-forget.
- `partial-unique-index-for-republish-after-soft-delete-2026-04-19` — `CREATE UNIQUE INDEX ... WHERE status='active'` for one-live-sub-per-user. `is_unique_violation` helper at `app/utils/db_errors.py`.

### External Context

- **Stigg out-of-order fix** — if entity missing on incoming event, fetch authoritative from Stripe API before processing.
- **Garrett Dimon `pricing_version`** — integer column on account snapshotted at signup. Entitlement fallback: `active_subscription → pricing.free → default_free`.
- **Harry atomic UPDATE RETURNING** — `UPDATE credits SET remaining=remaining-1 WHERE remaining>0 RETURNING remaining`. Implicit row lock. NULL return = reject.
- **RevenueCat grace collapse** — consumer-app states reduce to `[free, trialing, active, grace, expired]` with `access_allowed` boolean.
- **Stripe CLI `stripe listen`** — forwards to localhost with a per-session webhook secret, distinct from dashboard secret. `sk_test_*` vs `sk_live_*`; CLI refuses live forwarding.
- **Stripe Entitlements API verdict** — boolean flags only, no quota counter, no real-time enforcement. Skip for "tries remaining." Custom table is correct.
- **Anti-patterns** — signature verify on parsed body, missing event_id dedup, sync heavy work in webhook.

## Ranked Ideas

### 1. Credits-Only Universe
**Description:** Burn the tiers/subs/trial split. One product: credits. "Free" = 5 trial credits granted on signup. "Pro subscription" = an auto-top-up SKU that refills N credits on a cadence. Every billable action (generation, Ada message) debits the ledger. Typed bucket kinds: `promo-expiring` vs `paid-perpetual`; consume expiring first. Grandfathering = immutable grant policy per bucket; A/B pricing = different grant rules.

**Rationale:** "Tries-left not enforced," "CREDITS unlimited," and "free+expired" all become impossible by construction — there is one counter (balance) and one code path. Mobile shows "you have N credits, action costs M." `tiers` table, `trial_analyses_remaining`, `usage_events`, and the tier-vs-quota branch collapse into `credit_ledger`. Ada-blocking, generation-gating, and any future paid feature share one primitive. Pre-launch timing is right — post-launch this is harder to reverse.

**Downsides:** Biggest mental-model shift for users (no "I'm on free tier"). Paywall UX rewrites — pricing page must sell credits not subscriptions. Requires explicit policy for advisor_nudges quota (same ledger or separate). Requires explicit policy for "auto-top-up payment failed" (grace-balance, blocked immediately, retry cadence). Post-launch hard to reverse.

**Confidence:** 70%
**Complexity:** Medium
**Status:** Explored (selected for brainstorm)

---

### 2. Derived Status + Grace Collapse
**Description:** Delete `subscriptions.status` enum. Replace with a SQL view (or `GENERATED ALWAYS AS`) deriving `trialing | active | grace | expired` from `period_end`, `cancel_at`, `grace_until`. `get_entitlement()` joins the view. Webhook handlers only write dates, never statuses.

**Rationale:** Kills "free + expired" display bug by construction — status cannot drift from reality. No cron to expire subs. No dead enum values. No transition-table logic. Works with any quota model.

**Downsides:** Still uses `subscriptions` table structure. Doesn't address tries-left enforcement. Postgres generated columns cannot reference `now()` directly — needs a view or trigger. Loses ability to "pin" status manually.

**Confidence:** 85%
**Complexity:** Low
**Status:** Unexplored

---

### 3. Event-Sourced Spine (`user_entitlement` Materialized Row)
**Description:** Append-only `entitlement_events` (`trial_granted`, `glowup_consumed`, `stripe_checkout_completed`, `stripe_sub_updated`, `admin_grant`, `refund`). `user_entitlement` is a reducer fold — `{tier, tries_remaining, period_resets_at, grandfather_plan_id, status, last_event_id}`. Every backend gate reads one row. Webhook inserts events; reducer runs async (ARQ) with DLQ. Mobile reads one endpoint.

**Rationale:** Maximum future leverage. Every billing question becomes "show me the event stream." Out-of-order Stripe events, refund audits, support debugging, grandfathering are all SELECT queries. Replay tests are trivial.

**Downsides:** Heaviest implementation. Two-table dance (events + materialized row). Reducer correctness must be bulletproof — a bug corrupts everyone. Likely overkill for pre-launch. Collides with concurrent bug-fix agent. `credit_ledger` already half-this.

**Confidence:** 55%
**Complexity:** High
**Status:** Unexplored

---

### 4. `pricing_version` Grandfathering Primitive
**Description:** Add `tiers.pricing_version INT` monotonic + `subscriptions.pricing_version_locked INT`. Tier changes are new rows with incremented version. Entitlement resolution reads the locked version's tier row. New signups take current version; existing subs keep theirs forever unless admin-migrated. Orthogonal to direction choice.

**Rationale:** User explicitly asked for quota-change safety. Dimon / Stigg published pattern. Pre-launch cost is one column + policy decision. Post-launch adding this needs a backfill; adding now is free. A/B pricing trivial. With Credits-Only (direction 1), this reshapes to per-ledger-grant policy.

**Downsides:** Adds a join per entitlement read. Admin UX for "publish new tier version" not in scope.

**Confidence:** 90%
**Complexity:** Low
**Status:** Unexplored

---

### 5. Atomic `UPDATE ... RETURNING`; Delete `credit_reservations`
**Description:** Replace reserve→commit→release dance with `UPDATE users SET credits = credits - :cost WHERE id = :uid AND credits >= :cost RETURNING credits`. NULL rowcount → `InsufficientCredits`. Job failure → compensating `UPDATE credits + :cost`. Kill `credit_reservations` + TTL sweeper + zombie cleanup.

**Rationale:** Harry's Engineering pattern. Row-level lock implicit. Eliminates TOCTOU race on tries-left (root cause of "not enforced" symptom). No two-phase janitor. `app/api/refund.py` logic collapses.

**Downsides:** Refund visible after job completion, not during (user sees credits drop, then refund). For paid external compute (fal.ai), confirm gating-before-spend already prevents failed-gate spend. Concurrent-limit Lua script stays separate.

**Confidence:** 80%
**Complexity:** Low-Medium
**Status:** Unexplored

---

### 6. Dev Loop Compound
**Description:** Four coordinated dev-env primitives:
- `make stripe-dev` — starts `stripe listen --forward-to localhost:8000/webhooks/stripe`, writes signing secret to `app/.env`, seeds test products/prices, prints test cards.
- `make entitle-me tries=0 tier=pro` — calls dev-only `POST /__admin/entitlement/set` (gated by `APP_ENV != "prod"` + feature flag) forcing a specific `EntitlementState`.
- Auto-record every dev/staging webhook to `tests/fixtures/stripe/`; pytest fixture replays by name and snapshot-asserts entitlement.
- `GET /v1/__debug/entitlement/:user_id` — full decision trace: subscription, ledger, events, path. Dev/staging only.

**Rationale:** User explicitly flagged test-key ergonomics. Every billing bug forever becomes a fixture + snapshot test. Orthogonal to architecture.

**Downsides:** Four small projects — ship incrementally. Auto-record needs PII strip (Stripe customer emails). Debug endpoint must be truly off in prod via startup assertion, not just "should be."

**Confidence:** 90%
**Complexity:** Low each, Medium bundled
**Status:** Unexplored

---

### 7. `authoritative_sync(stripe_id)` + Webhook Outbox
**Description:** Two paired pieces. Webhook writes raw event to `webhook_outbox(id, event_id UNIQUE, payload, received_at, processed_at)` and returns 200. ARQ worker drains. Each handler's first step calls `authoritative_sync(stripe_id)` — fetch canonical state from Stripe API and fold into our state, not relying on event payload. Stigg out-of-order fix generalized.

**Rationale:** Fixes sync-in-async blocking. Fixes out-of-order by construction. Admin "fix this user" = call the same helper. Inherits DLQ + retry + pre-record-before-op patterns from `docs/solutions/`.

**Downsides:** Extra Stripe API calls per event (rate limits). Needs `ALLOWED_CRON_MINUTES` stagger (03:45/04:00 taken). Under direction 3 this folds into the reducer; under 1 or 2, standalone. Retry budget matches Stripe's (5 attempts, WARN on ceiling).

**Confidence:** 75%
**Complexity:** Medium
**Status:** Unexplored

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| A1 | Single Entitlement Snapshot Endpoint | Subsumed by wire contract implicit in all directions. |
| A3 | `EntitlementState` wire contract | Absorbed into all three directions — every survivor implies one shape. |
| A4 | Trigger-materialized JSONB column | Duplicates survivor 3 with worse tooling. |
| A5 | JSONB bag on `users.entitlements` | Same as A4; untyped. |
| A6 | Warranty-card analogy | Same shape as survivor 3 materialized row. |
| B1 | Stripe-as-source-of-truth JSONB | Tension with `pricing_version` grandfathering. Parts kept in survivor 7. |
| B2 | Stripe IS the database / replay | Same as B1. |
| B3 | Only store `stripe_customer_id` | Provocation — Stripe not designed as primary DB. |
| B4 | No webhooks, pull-only | Provocation — polling cost prohibitive. |
| C1 | Derived from events | Duplicates survivor 3. |
| C2 | Pure-function webhook UPSERT | Partially adopted in survivor 7. |
| C4 | Subscriptions as ledger | Duplicates survivor 3. |
| D2 | Show cost-to-next-action | Absorbed into survivor 1 (credits-only implies this UX). |
| D3 | No free tier, trial credits only | Absorbed into survivor 1. |
| D5 | Airline-miles policy-versioned buckets | Same primitive as survivor 4 at ledger grain. |
| E1, E3, E4 | plan_version / snapshot / YAML variants | Duplicate survivor 4; picked simplest form. |
| F1, F3 | Reserve-commit / ticket-reservation | Duplicate/mutex with survivor 5; picked atomic. |
| G1 | Webhook outbox alone | Absorbed into survivor 7. |
| H1 | `make stripe-dev` alone | Absorbed into survivor 6. |
| I1 | Manual fixture pack | Duplicates survivor 6 auto-record. |
| J1, J3, J4, J5 | State-machine variants, F2P regen, period-end cron | Duplicates of survivor 2 (derive-from-dates). |
| K1 | Token bucket primitive | Direction-dependent; re-surface in brainstorm. |
| M1 | Adapter consolidation | Absorbed into survivor 6 (user-scoped stronger than process flag). |
| N1/N2 | Price catalog | Direction-dependent follow-on. |
| O1 | Features-ARE-tiers unification | Orthogonal cleanup; repo memory already enforces. Next-steps. |
| P1 | Debug dump endpoint | Absorbed into survivor 6. |
| Q1 | Guest shadow subscriptions | Secondary; handle when wiring guest into winning architecture. |
| S1 | Mobile-thin `can_i(action)` | Orthogonal ergonomic; implied by any direction. |
| T1 | Refunds on happy path | Provocation — if survivor 5 lands, compensating UPDATE is already happy path. |
| U1 | Hand-managed JSON file | Pure provocation. |

## Collision Notes

Another agent is fixing issues concurrently. Survivors 2, 5, 7 are bug-shaped (potential conflicts). Survivors 1, 3, 4, 6 are architectural (plan-first-safe). Recommendation: sync with other agent before implementing 2/5/7; use 1/3/4 as direction-setting conversation; begin 6 independently.
