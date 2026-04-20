---
title: "feat: Payments & Subscriptions — Credits-Only Engine"
type: feat
status: active
date: 2026-04-19
deepened: 2026-04-19
origin: docs/brainstorms/2026-04-19-payments-credits-only-requirements.md
---

# feat: Payments & Subscriptions — Credits-Only Engine

## Overview

Collapse the three parallel billing systems (tiers, trial counters, credit ledger) into one credit-ledger source of truth denominated in milli-credits. Tiers become marketing labels derived from subscription lifecycle; quota gating is always ledger-based. Lands as a two-phase migration that coexists with a concurrent bug-fix agent working on `app/api/entitlement.py`, `app/api/webhooks.py`, `app/entitlement/service.py`.

## Problem Frame

Three visible bugs and broad maintainability debt (see origin: `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md`):

1. Mobile shows "Free tier" AND "subscription expired" simultaneously — `subscriptions.status` enum carries values webhook handlers never produce, and `period_end` is not cross-checked at read time.
2. Tries-left is not enforced — `users.trial_analyses_remaining` initialises once, never decrements.
3. CREDITS tier is effectively unlimited — only `balance > 0` check.

Root cause: three parallel truth sources (tiers table, trial counter, credit_ledger) drift apart. Grandfathering is impossible today because tier config is mutated in place. Pre-launch timing permits destructive schema changes but the concurrent bug-fix agent forces a safe-interleave Phase A + destructive Phase B split.

## Requirements Trace

- R1. One credit ledger is SoT.
- R2. Milli-credit integer unit; `credit_ledger.delta` stays INTEGER.
- R3. Display = `floor(balance / plan_version.glowup_cost_milli)` glow-ups + `floor(.../ada_cost_milli)` Ada messages. Divisors from user's active plan_version (or seeded `v1_free_default` for Free).
- R4. Atomic reserve→commit/release via advisory-lock'd RPC; rejects with typed `InsufficientCredits` or `AccountLocked`; never caches balance to users.
- R4a. Ada is ledger-gated, not tier-gated.
- R5. Free + Pro marketing labels derived from subscription lifecycle (R14a).
- R6. Free: signup_grant (one-time, fingerprint-bound R6a) + weekly_free_grant (idempotent per ISO-week).
- R6a. Device-fingerprint on signup uses HMAC-SHA256(server_secret, installation_uuid) for lookup + SHA256(per-row salt || uuid) for at-rest protection; 12-month TTL; survives delete_account (explicit exception).
- R7. Pro subscription REPLACES balance with monthly allotment on each period start.
- R7-Pack. Single $4.99/500-milli pack SKU; grants ADD to ledger via webhook only.
- R8. Partial UNIQUE index on `subscriptions(user_id) WHERE status='active'`.
- R9. Grace = `now() + 3 days` on `invoice.payment_failed`.
- R10. Label flips to Free when `grace_until < now()`; balance retained; Ada continues (R4a).
- R11. `invoice.payment_succeeded` during or after grace: REPLACE to monthly_allotment; pack credits preserved.
- R12. plan_versions freezes {price, monthly_allotment_milli, glowup_cost_milli, ada_cost_milli} per cohort.
- R13. Non-quota feature changes deploy globally.
- R14/14a. Single `EntitlementState` shape with typed `blocked_reason ∈ {insufficient_credits, subscription_locked_by_dispute, none}`.
- R14b. **DEFERRED TO v1.1 per scope review.** Pre-launch has no jitter signal; adding a 3-second live Stripe call on the hot `get_entitlement` path without empirical data is premature. Status is derived purely from `period_end` + `grace_until` + `locked_at` in v1. `last_authoritative_fetch_at` column and authoritative fetch branch land post-launch after telemetry justifies them. Origin R14b amended accordingly.
- R15. Refunds = compensating ledger entries (negative delta); self-refund deferred to v1.1.
- R-Dispute-1..4. Dispute lifecycle: created→lock, closed_won→unlock, closed_lost→compensate+stay-locked, funds_withdrawn→audit.
- R16. Guest ledger shape same as auth; 2× signup-grant cap on non-pack merge; `credit_pack_purchase` bypasses cap; merge-on-signup atomic.
- R17. Every new user-owned surface wired into delete_account + wipeLocalDeviceState (signup_grants_issued is the documented exception).
- R18. Webhook constraints: sig-verify before anything, 200 in <5s, idempotent by event_id, out-of-order tolerance via enqueued re-fetch (not inline), 72h ceiling.
- R19. `make stripe-dev` bootstrap.
- R22. `GET /v1/__debug/entitlement/{user_id}` with shared DEBUG_BEARER_TOKEN (secrets manager for staging) + env-gate refusing mount in prod.
- R23. Two-phase migration: Phase A additive-safe-interleave (0048–0052); Phase B destructive after writer+reader cutover AND bug-fix-agent merge.
- R24. Female-audience copy.

## Scope Boundaries

- Multiple Pro SKUs, multiple pack SKUs, annual billing — v1 excludes all.
- Rollover of unused allotment — NO.
- Per-preset glow-up pricing — NO.
- User-initiated self-refund — deferred to v1.1.
- Admin console for plan_versions — NO (direct DB write).
- Dunning email customization beyond Stripe Smart Retries — NO.
- Subscription pause / mid-period downgrade — NO.
- Full fraud-hold state machine — NO (minimal dispute-lock only).
- Staff-admin grant-credits / force-migrate UIs — NO (direct DB write).

### Deferred to Separate Tasks

- R20 dev-only `POST /__admin/entitlement/set` — v1.1 (direct DB writes + `stripe trigger` cover v1).
- R21 auto-recorded webhook fixture pipeline — v1.1 (hand-authored pytest fixtures cover v1).

## Context & Research

### Relevant Code and Patterns

- `app/api/entitlement.py` — current entitlement router (**READ-ONLY in Phase A**; flipped in Phase B after bug-fix-agent merge).
- `app/api/webhooks.py` — Stripe webhook router (**READ-ONLY in Phase A**; flipped in Phase B).
- `app/entitlement/service.py` — `EntitlementService` (**READ-ONLY in Phase A**; new `service_v2.py` added in parallel).
- `app/entitlement/ledger.py` — `CreditLedger.balance/reserve/release/commit/refund` (additive: new `reserve_action/commit/release/refund` methods for action-type RPCs).
- `app/payment/ports.py` + `app/payment/adapters/{stripe_adapter,mock}.py` — Port Protocol (additive: `retrieve_subscription`, `delete_customer`).
- `app/repositories/subscription_repo.py` — subs reads/writes + idempotency via `processed_webhook_events`.
- `app/generation/worker.py` `_fail_job` — reserve/commit/refund lifecycle (additive: switch to action-type RPC calls in Phase B).
- `app/migrations/0014_credit_ledger_rpcs.sql`, `0019_credit_reserve_advisory_lock.sql`, `0021_security_definer_search_path.sql`, `0029_credit_refund_rpc.sql` — existing RPC + lock + SECURITY DEFINER pattern.
- `app/migrations/0044_hard_delete_account.sql`, `0045_delete_account_cascade_completeness.sql` — CASCADE pattern (subscriptions + credit_ledger + credit_reservations already cascade — reusable).
- `app/db/guest.py` — `create_guest_user`, `resolve_guest_by_token` (reused; no new table).
- `app/api/auth.py::delete_account` — 8-step ordering (new surfaces wire in here).
- `mobile/lib/entitlement.ts` — API client types (rewritten in-place once Phase B lands).
- `mobile/lib/hooks/use-purchase-flow.ts` — PaymentSheet for packs; `Linking.openURL` for subscriptions (unchanged in scope).
- `mobile/lib/account-wipe.ts` — `wipeLocalDeviceState` (new SecureStore key wires in here).

### Institutional Learnings

- `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` — five invariants; registry pattern for new user-owned state.
- `docs/solutions/best-practices/partial-unique-index-for-republish-after-soft-delete-2026-04-19.md` — `CREATE UNIQUE INDEX ... WHERE status='active'` pattern.
- `docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md` — re-assert predicate at commit for CAS.
- `docs/solutions/best-practices/orphan-dlq-symmetry-2026-04-19.md` — pre-record-before-op for webhooks; race-free UPSERT via `on_conflict`.
- `docs/solutions/best-practices/blocking-auto-save-for-durable-share-urls-2026-04-19.md` — `raceWithTimeout` pattern for mobile post-checkout.

### External References

- Stripe CLI `stripe listen` session signing secret (distinct from dashboard secret).
- Stripe Smart Retries default window (~2–3 weeks, exceeds our 3-day grace).
- Stigg out-of-order fix: re-fetch authoritative from Stripe when payload suggests stale.
- Harry's atomic UPDATE RETURNING (deliberately NOT adopted — origin R4 preserves reserve→commit/release for fal.ai auto-refund).

## Key Technical Decisions

- **Phase A is read-only on the shared trio.** `app/api/entitlement.py`, `app/api/webhooks.py`, `app/entitlement/service.py` are NOT edited in Phase A. New code lands as parallel modules (`app/entitlement/service_v2.py`, `app/api/entitlement_v2.py` mounted at `/v2/entitlement`, `app/api/webhooks_v2.py` if needed). Phase B does the shared-file flip after the bug-fix agent merges. This resolves the concurrent-agent collision by construction.
- **Phase B merge protocol for `_handle_payment_failed` + `_handle_subscription_deleted` + `_handle_payment_intent_succeeded`** (adversarial review P0). Before Phase B Unit 15 starts, sync with bug-fix agent to confirm which functions in the shared trio they touched. Phase B flip is explicit three-way merge: (1) start from post-bug-fix-agent-merge `dev` branch; (2) apply v2 writer semantics on top (grace_until instead of status='past_due'; cancelled_at instead of status='expired'); (3) preserve bug-fix agent's non-writer changes verbatim; (4) review per-function, not per-file. If bug-fix agent will touch `_handle_payment_failed` or `_handle_subscription_deleted` specifically, negotiate to freeze those two handlers in their PR and leave them to Unit 15.
- **Advisory-lock domain is `hashtextextended(user_id::text, 0)`** (adversarial review P2). 64-bit hash space eliminates user-count-scaling collision throughput cliffs that `hashtext`'s 32-bit space would cause at ≥10k users (birthday collision ≈ 1.16% at 10k, 69% at 100k). Apply uniformly to all `_v2` RPCs in Units 2, 3, 4, 10.
- **Free users reference a seeded `v1_free_default` plan_versions row** with `price_usd_cents=0, monthly_allotment_milli=0`. R3 divisors resolve via `COALESCE(subscriptions.plan_version_id, (SELECT id FROM plan_versions WHERE version_num='v1_free_default'))`. Uniform join shape; grandfathering applies to Free if Free-cost changes ever ship. Alternative — `users.plan_version_id` nullable column — rejected (extra null-handling, no upside).
- **Webhook architecture: inline + idempotency table** (not outbox). Fast path: verify-sig → event_id dedup check → switch on event_type → update subscription row / write ledger entry → record event. Under 5s hard budget (R18). **Out-of-order strategy: return HTTP 5xx** (scope review cut 2 + feasibility HIGH #1 resolution). Stripe's built-in exponential-backoff retry establishes eventual order. Dispute events additionally use CAS on `dispute_last_event_at` (security review CRITICAL fix). No ARQ retry worker in v1 — simpler, empirically-validated-by-Stripe, cuts ~1 module + ~30 lines + 1 test file. Outbox + ARQ retry deferred to v1.1 if empirical delivery tail widens.
- **RPCs ship as `_v2` parallel** (per R23 recommendation). `credit_reserve_v2(p_user_id, p_reservation_id, p_action_type)` looks up cost server-side from `plan_versions.{glowup_cost_milli|ada_cost_milli}`. Caller never supplies amount. Old RPCs stay available during Phase A; Phase B drops them.
- **REPLACE semantics: single net-delta entry with discarded amount in reference metadata** (scope review cut 3). `credit_apply_monthly_allotment_v2` issues ONE entry: `(+(monthly_allotment_milli - current_non_pack_balance), type='monthly_allotment', reference_id=plan_version_id, metadata={'discarded_milli': <prior_non_pack_balance>, 'plan_version_id': <uuid>})`. Audit reconstruction reads `metadata.discarded_milli`. `retained_preserved` enum value removed. Simpler queries; forensic goal preserved.
- **REPLACE non-pack balance computation EXCLUDES in-flight reservations and commit markers** (adversarial review P0 race fix). `current_non_pack_balance = SUM(delta) WHERE type NOT IN ('credit_pack_purchase', 'reserve', 'commit')`. Reserves are held-but-uncommitted; if the worker commits post-REPLACE, `credit_commit_v2` writes `(0, commit)` which does not affect balance (sum is already debited via the `reserve` entry). If the worker releases post-REPLACE, `(+reserved_amount, release)` refunds to the new balance. This prevents the "+3100 after renewal and release" exploit where a pre-renewal reserve bypassed the REPLACE.
- **Concrete numbers (plan_versions v1 row):** glowup_cost_milli=100, ada_cost_milli=5, monthly_allotment_milli=3000, price_usd_cents=999. Plus seeded Free default. Pack: 500 milli @ $4.99 (app-config key `CREDIT_PACK_V1`, not in plan_versions — packs are SKU-level not plan-level). Signup grant = 300 milli (3 glow-ups). Weekly free grant = 100 milli (1 glow-up). Numbers confirmed per user input.
- **DEBUG_BEARER_TOKEN via Supabase Vault for staging.** Plain-`.env` rejected. Rotation: scheduled every 90 days + on staff change. Env var injected at boot; runtime-fetched for header check (not startup-cached) so rotation propagates without redeploy.
- **`users.stripe_customer_id` column added in Phase A 0048.** Lazily populated on first `create_payment_intent` or `create_subscription` call (replaces current `Customer.search(metadata.user_id)` round-trip). Required for deterministic `delete_account` Stripe customer deletion.
- **Installation-UUID is mobile-generated.** First native-app launch writes `nxme_install_uuid` to SecureStore. Mobile sends `X-Install-UUID` header on `POST /auth/register`, `POST /auth/login`, `POST /auth/tiktok-login`. Backend writes to `signup_grants_issued` on first grant issuance. Web signups omit the header (tolerated unprotected per R6a).
- **Paywall CTA matrix = pure function in `mobile/lib/paywall-cta.ts`.** Keyed by `(tier, blocked_reason, has_grace)`. Unit-tested. UI switches on the returned `PaywallCTA` discriminated union.
- **Legal review is a hard gate on 0048 migration merge.** `signup_grants_issued` GDPR status must be signed off before 0048 ships. Tracked in Risk Analysis as blocking.

## Open Questions

### Resolved During Planning

- **plan_versions v1 numbers**: signup=300, weekly=100, monthly_allotment=3000, Pro=$9.99/mo, pack=500 @ $4.99, ada=5, glowup=100 (user-confirmed).
- **Webhook architecture**: inline + idempotency table with ARQ re-fetch-on-suspected-reorder branch. Outbox deferred.
- **RPC migration approach**: `_v2` parallel RPCs (origin R23 recommendation).
- **DEBUG_BEARER_TOKEN storage**: Supabase Vault for staging; env injection at boot.
- **Free-user plan_version resolution**: seeded `v1_free_default` row + `COALESCE` on subscription lookup.
- **Stripe customer_id persistence**: new `users.stripe_customer_id` column + lazy population (replaces metadata-search lookup).
- **Paywall CTA matrix location**: `mobile/lib/paywall-cta.ts` pure function, unit-tested.
- **Installation-UUID delivery**: mobile-generated, SecureStore, `X-Install-UUID` header on auth endpoints.
- **Monthly-allotment REPLACE audit**: single net-delta entry (`monthly_allotment`) with `metadata.discarded_milli` under one advisory lock; `SUM(delta)` for balance correctly excludes `type IN ('reserve','commit','credit_pack_purchase')` in the REPLACE computation to prevent in-flight-reserve race exploits (adversarial P0 fix).

### Deferred to Implementation

- Exact `raceWithTimeout` timeout constant for mobile checkout confirmation in subscription flow (`blocking-auto-save` solution suggests ~15–30s; final value decided alongside first real Stripe test run).
- The migration-specific SQL for dropping the `credit_ledger.type` CHECK constraint and re-adding with expanded enum — deferred to the writer of 0048 (trivial but touch requires live-schema verification).
- Exact text of R24 paywall copy — designer to supply female-targeted copy during Phase A Unit 12 implementation; placeholder strings acceptable until then.
- Whether Pro-grace paywall CTA should mention "your payment method will be retried" or simply "update card" — product+designer call during Unit 12.

### Deferred to v1.1 / Post-Launch

- Empirical Stripe event-delivery jitter measurement — tune R14b 1-hour buffer based on telemetry once ≥2 weeks of prod data exists.
- Admin workflow for force-migrating existing Pro users to a newer plan_version — `subscriptions.plan_version_id` stays mutable; UI deferred.
- Observability telemetry on pack-purchase volumetrics (guest 2× cap monitoring) — add dashboards post-launch.
- Webhook signing-secret rotation window handling — decide accept-multi-secret vs trust-ingest-only when first rotation is needed.
- Pack refund → negative-balance UX — compensating-delta clamp at current balance OR lock-for-review; decide before refund flow ships.
- Grandfathering disclosure copy on mobile billing screen — product call post-launch.

## Output Structure

New files created by this plan:

```
app/
  migrations/
    0048_payments_schema_phase_a.sql              (new — schema + partial UNIQUE + enum; NO legal gate)
    0049_credit_rpcs_v2.sql                       (new)
    0050_credit_grants_and_allotment_rpcs.sql     (new — includes merge_guest_ledger_v2)
    0051_dispute_and_delete_extension.sql         (new — apply_dispute_event CAS RPC)
    0052_signup_grants_issued.sql                 (new — LEGAL-GATED; split from 0048)
  entitlement/
    service_v2.py                                 (new — parallel to service.py)
    fingerprint.py                                (new — HMAC+salted hash helpers)
    dispute_service.py                            (new)
  api/
    entitlement_v2.py                             (new — /v2/entitlement)
    webhooks_v2.py                                (new — /v2/webhooks/stripe, 8a + 8b)
    debug_entitlement.py                          (new — /v1/__debug/entitlement/{user_id})
  payment/
    adapters/
      stripe_adapter.py                           (modify — add retrieve_subscription, delete_customer)
      mock.py                                     (modify — mirror port additions)
    ports.py                                      (modify — add methods)
  repositories/
    plan_version_repo.py                          (new)
    signup_grant_repo.py                          (new)
  scripts/
    backfill_stripe_customer_ids.py               (new — one-shot, run post-0048)
  workers/
    weekly_free_grant.py                          (new — ARQ scheduled)
    fingerprint_purge.py                          (new — nightly TTL sweep)
    purge_old_webhook_events.py                   (new — nightly payload-retention sweep)
  services/
    stripe_dev_bootstrap.py                       (new — make stripe-dev helper)
  middleware/
    logging.py                                    (modify — X-Install-UUID header scrub)
  features/
    (modify)                                      (register ENTITLEMENT_V2_ENABLED capability)

mobile/
  lib/
    install-uuid.ts                               (new — generate+persist on first launch)
    paywall-cta.ts                                (new — CTA matrix pure fn)
    entitlement_v2.ts                             (new — parallel to entitlement.ts during Phase A)

tests/
  test_plan_versions.py                           (new)
  test_credit_rpcs_v2.py                          (new)
  test_signup_grant_fingerprint.py                (new)
  test_monthly_allotment_replace.py               (new)
  test_weekly_free_grant_idempotency.py           (new)
  test_dispute_lifecycle.py                       (new)
  test_webhooks_v2_idempotency.py                 (new)
  test_webhooks_v2_out_of_order.py                (new)
  test_entitlement_v2_drift_buffer.py             (new)
  test_guest_merge_cap.py                         (new)
  test_debug_entitlement_endpoint.py              (new)
  test_delete_account_new_surfaces.py             (new)
  fixtures/stripe/                                (new — hand-authored webhook payloads)

Makefile                                          (modify — add stripe-dev target)
app/.env.example                                  (modify — new env vars)
mobile/.env.example                               (modify — new env vars)
docs/runbooks/payments.md                         (new — operator guide)
```

Phase B migration files (0053+ or later range) are not enumerated here; the bug-fix agent occupies 0053+, so Phase B uses the next free range at flip time.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

### Sequence — Pro monthly renewal (R7/R11, happy path)

```
Stripe                Webhook            subscription_repo     credit RPC
  │ invoice.payment_succeeded│
  ├──────────────────────────▶│ verify-sig
  │                           │ dedup check (event_id)
  │                           │ resolve user_id, plan_version_id
  │                           ├────────────────────────▶ UPDATE subscriptions
  │                           │                          SET billing_period_end = new_end,
  │                           │                              grace_until = NULL
  │                           │
  │                           ├───────────────────────────────────────▶ credit_apply_monthly_allotment_v2(
  │                           │                                            p_user_id, p_plan_version_id)
  │                           │                                         ├ advisory-lock(hashtextextended(user_id))
  │                           │                                         ├ SELECT SUM(delta) WHERE type NOT IN
  │                           │                                         │   ('credit_pack_purchase','reserve','commit')
  │                           │                                         ├ INSERT ledger (allotment - prior, monthly_allotment,
  │                           │                                         │                metadata.discarded_milli=prior)
  │                           │                                         └ COMMIT
  │                           │ record_webhook_event(event_id)
  │                           │ 200 OK  (total <5s)
```

### Sequence — out-of-order Stripe event (v1: 5xx + Stripe retry)

```
Stripe                Webhook
  │ subscription.updated (arrives before .created)│
  ├───────────────────────────────────▶│ verify-sig
  │                                    │ dedup check
  │                                    │ resolve subscription row → NOT FOUND
  │                                    │ (out-of-order detected)
  │ 500 Internal Server Error          │ (event_id NOT recorded)
  │◀───────────────────────────────────┤
  │ Stripe built-in exponential backoff                      │
  │ retries .updated → eventually after .created lands       │
  ├───────────────────────────────────▶│ subscription.created
  │                                    │ (apply, record event_id)
  │                                    │ 200 OK
  ├───────────────────────────────────▶│ subscription.updated retry
  │                                    │ (subscription row now exists; apply; 200 OK)
```

### Sequence — out-of-order dispute event (CAS on event_at)

```
Stripe                Webhook                    apply_dispute_event
  │ dispute.closed (t=10)  (arrives before dispute.created)
  ├───────────────────────▶│ verify-sig, dedup, resolve user_id
  │                        ├──────────────────▶  apply_dispute_event(user, evt_closed, t=10, 'closed_won')
  │                        │                    ├ advisory-lock
  │                        │                    ├ dispute_last_event_at IS NULL  → accept
  │                        │                    ├ locked_at = NULL (was NULL)
  │                        │                    ├ dispute_last_event_at=10, status=closed_won
  │                        │ 200 OK             │
  │                        │
  │ dispute.created (t=5)  (out-of-order late arrival)
  ├───────────────────────▶│
  │                        ├──────────────────▶  apply_dispute_event(user, evt_created, t=5, 'created')
  │                        │                    ├ advisory-lock
  │                        │                    ├ last_event_at=10 > t=5  → {applied:false}
  │                        │ 500 Server Error   │
  │                        │ (event NOT recorded)
  │ Stripe retries; eventual idempotent no-op once Stripe gives up (72h limit)
  │ Final state: closed_won (correct)
```

### State diagram — subscription lifecycle (all transitions are date/lock-derived; no status enum in v2)

```
       [no row]
          │ subscription.created
          ▼
       active ──invoice.payment_succeeded──▶ active (REPLACE allotment)
          │
          │ invoice.payment_failed         ┌──────────┐
          ├───────────────────────────────▶│  grace   │ (grace_until = now()+3d)
          │                                └────┬─────┘
          │           invoice.payment_succeeded │ grace_until < now()
          │◀────────────────────────────────────┤
          │                                     ▼
          │                              [label=Free, balance retained]
          │                              subscription.revives on later retry → REPLACE allotment
          │
          │ subscription.deleted / cancel_at_period_end then period_end<now
          ▼
       [label=Free, balance retained]

 [any] ─ charge.dispute.created ──▶ locked (users.locked_at=now())
          ├ dispute.closed_won  ──▶ unlock (locked_at=NULL)
          └ dispute.closed_lost ──▶ stays locked + compensating ledger entry
```

### Entitlement shape (v2 response)

```
EntitlementStateV2 {
  tier: "Free" | "Pro",
  remaining_glowups: int,              // floor(balance_milli / glowup_cost_milli)
  approx_remaining_ada: int,           // floor(balance_milli / ada_cost_milli)
  subscription_status: "active" | "grace" | "canceled" | "none" | "locked",
  period_end: ISO-datetime | null,
  grace_end: ISO-datetime | null,
  blocked_reason: "insufficient_credits" | "subscription_locked_by_dispute" | "none",
  plan_version_id: UUID,               // for display + grandfathering UI
  purchase_options: {
    pack: { price_id, amount_cents, currency, credits_milli },
    pro:  { price_id, amount_cents, currency, monthly_allotment_milli }
  } | null,
}
```

### Paywall CTA matrix (pure function in `mobile/lib/paywall-cta.ts`)

| tier | subscription_status | blocked_reason       | Primary CTA       | Secondary CTA |
|------|---------------------|---------------------|-------------------|---------------|
| Free | none / canceled     | insufficient_credits | Subscribe to Pro  | Buy pack      |
| Free | none                | none                | (no paywall; within balance) | — |
| Pro  | active              | insufficient_credits | Buy pack          | —             |
| Pro  | grace               | insufficient_credits | Update card       | Buy pack      |
| any  | locked              | subscription_locked_by_dispute | Contact support | — |
| Free | (post-grace-expiry) | insufficient_credits | Subscribe to Pro  | Buy pack      |

## Implementation Units

Units are grouped into Phase A (additive, safe to interleave with bug-fix agent) and Phase B (destructive, gated on bug-fix-agent merge). Phase A reserves migrations 0048–0052; concurrent bug-fix agent takes 0053+.

### Phase A — Additive (0048–0052)

- [ ] **Unit 1: Migration 0048 — schema additions + partial UNIQUE + plan_versions seed + stripe_customer_id backfill (NO fingerprint table)**

**Goal:** Create `plan_versions`, extend `users`/`subscriptions`, extend `credit_ledger.type` enum, partial UNIQUE index, seed v1 rows, backfill `stripe_customer_id` for existing users. `signup_grants_issued` split off to Unit 1b (0052) — see Dependencies for rationale.

**Requirements:** R7, R8, R12, R22, R23 Phase A.

**Dependencies:** Migration 0048 has NO legal blocker (fingerprint table moved to 0052).

**Files:**
- Create: `app/migrations/0048_payments_schema_phase_a.sql`
- Create: `app/scripts/backfill_stripe_customer_ids.py` (one-shot backfill script)
- Test: `tests/test_plan_versions.py`

**Approach:**
- `CREATE TABLE plan_versions (id UUID PK, version_num TEXT UNIQUE, price_usd_cents INT, monthly_allotment_milli INT, glowup_cost_milli INT NOT NULL, ada_cost_milli INT NOT NULL, stripe_price_id TEXT NULL, created_at TIMESTAMPTZ DEFAULT now())`. RLS deny-all (service-role only). `stripe_price_id` populated by `make stripe-dev` bootstrap (Unit 13).
- Seed two rows: `v1_free_default` (price=0, monthly=0, glowup=100, ada=5) and `v1_pro` (price=999, monthly=3000, glowup=100, ada=5).
- `ALTER TABLE users ADD COLUMN locked_at TIMESTAMPTZ, ADD COLUMN dispute_last_event_id TEXT NULL, ADD COLUMN dispute_last_event_at TIMESTAMPTZ NULL, ADD COLUMN dispute_last_status TEXT NULL, ADD COLUMN merged_into_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL, ADD COLUMN merged_at TIMESTAMPTZ NULL, ADD COLUMN stripe_customer_id TEXT NULL UNIQUE, ADD COLUMN guest_install_uuid_hash BYTEA NULL`. **NOTE: `users.monthly_allotment_milli` dropped from the plan per scope review (dead column — no reader; `plan_versions.monthly_allotment_milli` is the single source). `dispute_last_*` columns added for out-of-order dispute reconciliation (security review CRITICAL fix, Unit 4/8b). `guest_install_uuid_hash` populated on guest creation; required to match at merge time (security review HIGH fix, Unit 10).**
- `ALTER TABLE subscriptions ADD COLUMN plan_version_id UUID REFERENCES plan_versions(id), ADD COLUMN grace_until TIMESTAMPTZ NULL`. Seed existing rows with `plan_version_id = <v1_pro default>`. **NOTE: `last_authoritative_fetch_at` dropped — drift buffer deferred to v1.1 per scope review (R14b deferred).**
- `CREATE UNIQUE INDEX idx_subscriptions_one_active_per_user ON subscriptions(user_id) WHERE status='active'` (R8).
- `CREATE INDEX idx_users_locked_at_not_null ON users(locked_at) WHERE locked_at IS NOT NULL` (dispute-lock scan, moved from Unit 4).
- Extend `credit_ledger.type` CHECK: DROP CONSTRAINT + ADD CONSTRAINT with union of existing + new values: `signup_grant`, `signup_grant_suppressed_by_fingerprint`, `weekly_free_grant`, `monthly_allotment`, `credit_pack_purchase`, `ada_message`, `dispute_compensation`, `guest_merge_non_pack`, `guest_merge_truncated`. **`retained_preserved` removed** — single net-delta REPLACE with metadata instead.
- **One-shot Stripe customer backfill** (adversarial P1 fix): post-migration, run `app/scripts/backfill_stripe_customer_ids.py` which iterates all users, calls `Customer.search(metadata.user_id)` via the adapter, writes `stripe_customer_id` on hit. Skip users with no matching Stripe customer. Pre-seeds the column so webhook `charge.dispute.created` lookups are O(1) instead of falling back to `Customer.search` on the 5s fast path.
- Migration-runner wraps in its own transaction (per existing convention, see 0044 header).

**Patterns to follow:**
- `app/migrations/0044_hard_delete_account.sql` — RLS deny-all pattern; ALTER FK patterns; DOWN-is-destructive stanza.
- `app/migrations/0021_security_definer_search_path.sql` — SECURITY DEFINER + search_path pattern (future RPC migrations inherit).
- `docs/solutions/best-practices/partial-unique-index-for-republish-after-soft-delete-2026-04-19.md` — partial UNIQUE index for one-active-per-user.

**Test scenarios:**
- Happy path — schema apply succeeds on clean DB; all new tables/columns/indexes present; seed rows queryable.
- Happy path — `SELECT * FROM plan_versions WHERE version_num='v1_free_default'` returns row with glowup_cost_milli=100, ada_cost_milli=5.
- Edge case — rerunning the migration file is rejected by the migration runner (idempotency is runner-level, not script-level; script is not idempotent by design).
- Edge case — partial UNIQUE accepts one active + many cancelled subscriptions for the same user; rejects a second active.
- Error path — attempting to INSERT into `credit_ledger` with a type outside the new enum raises `check_violation`.
- Error path — attempting to INSERT `users.stripe_customer_id` duplicate across users raises `unique_violation`.

**Verification:**
- `make migrate` applies cleanly.
- `psql -c "\d+ plan_versions"` shows seeded rows.
- Existing subscription rows (if any exist in dev DB) have `plan_version_id` populated.
- `python -m app.scripts.backfill_stripe_customer_ids` completes without error; post-run, users with Stripe history have `stripe_customer_id` populated.

---

- [ ] **Unit 1b: Migration 0052 — `signup_grants_issued` table (legal-gated)**

**Goal:** Split the GDPR-reviewable fingerprint registry into a dedicated migration so 0048 can ship without the legal gate (feasibility review HIGH #2).

**Requirements:** R6a.

**Dependencies:** Legal sign-off on `signup_grants_issued` GDPR treatment (hard gate — see Risk Analysis). Unit 1.

**Files:**
- Create: `app/migrations/0052_signup_grants_issued.sql`

**Approach:**
- `CREATE TABLE signup_grants_issued (deterministic_hash BYTEA PRIMARY KEY, protected_hash BYTEA NOT NULL, salt BYTEA NOT NULL, issued_at TIMESTAMPTZ NOT NULL DEFAULT now())` + BTREE index on `issued_at` for TTL sweep. RLS deny-all.
- Runbook entry in `docs/runbooks/payments.md` documenting the SURVIVES-delete exception + `SIGNUP_FINGERPRINT_SERVER_SECRET` rotation procedure (see Unit 6).

**Test scenarios:**
- Happy path — table created; RLS rejects anon/authenticated access.
- Edge case — insert + dedup by `deterministic_hash` works.

**Verification:**
- `make migrate` applies after legal green-light.
- If legal returns blocking concerns, Phase A units 1, 2, 3, 5, 7, 8, 10–14 can still proceed. Only Units 6, 9 wait for 0052.

---

- [ ] **Unit 2: Migration 0049 — `_v2` credit RPCs (action-typed, advisory-locked)**

**Goal:** Ship parallel `_v2` RPCs that resolve cost server-side via `plan_versions` lookup; preserve advisory-lock domain from 0019.

**Requirements:** R4, R4a, R12, R23.

**Dependencies:** Unit 1.

**Files:**
- Create: `app/migrations/0049_credit_rpcs_v2.sql`
- Test: `tests/test_credit_rpcs_v2.py`

**Approach:**
- **Advisory-lock domain: `pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0))`** (adversarial P2 fix). 64-bit hash; negligible cross-user collision at ≥10k users.
- `credit_reserve_v2(p_user_id UUID, p_reservation_id UUID, p_action_type TEXT)` where `p_action_type ∈ {'glowup', 'ada_message'}`. Inside function: acquire 64-bit advisory lock; look up effective plan_version via `COALESCE(active-subscription.plan_version_id, v1_free_default.id)`; resolve cost column; SELECT `users.locked_at` + `SUM(credit_ledger.delta)`; reject with `AccountLocked` P0002 if locked; reject with `InsufficientCredits` P0001 if balance < cost; INSERT reservation (amount = cost, not 1) + ledger (-cost, type='reserve', reference_id=reservation_id).
- `credit_commit_v2(p_reservation_id UUID)`: acquire same lock (derive user_id from reservation row); if `users.locked_at IS NOT NULL`, convert commit→release (dispute-during-in-flight path, R4) — note: output-row quarantine (`dispute_review_quarantine`) is DEFERRED to v1.1 (adversarial P0 fix: R4 over-promised a column that doesn't exist in v1; credit refund via release is the v1 contract, user's generated image still visible); else insert `(+0, commit)` ledger row.
- `credit_release_v2(p_reservation_id UUID)`: acquire lock; flip status='released'; insert `(+reserved_amount, release)`.
- `credit_refund_v2(p_reservation_id UUID)`: flip status='released' from 'committed'; insert `(+reserved_amount, refund)`.
- All `SECURITY DEFINER SET search_path = public` per 0021 pattern. All validate `auth.uid() = p_user_id` for non-service-role callers; service role bypasses.
- Auto-update `credit_reservations.amount` to be cost-aware: reservations currently store `amount=1`. `_v2` stores actual cost in milli-credits. Legacy rows coexist (amount=1 is still valid).

**Patterns to follow:**
- `app/migrations/0014_credit_ledger_rpcs.sql` — RPC shape.
- `app/migrations/0019_credit_reserve_advisory_lock.sql` — advisory-lock domain.
- `app/migrations/0021_security_definer_search_path.sql` — search_path hardening.

**Test scenarios:**
- Happy path — `credit_reserve_v2(u, res, 'glowup')` on user with 3000 milli inserts ledger `-100`; balance drops to 2900.
- Happy path — `credit_commit_v2(res)` inserts `(0, commit)`; balance unchanged at 2900; reservation.status='committed'.
- Happy path — `credit_release_v2(res)` on reserved reservation inserts `(+100, release)`; balance restored to 3000.
- Happy path — `credit_refund_v2(res)` on committed reservation inserts `(+100, refund)`; balance 3000.
- Edge case — `credit_reserve_v2` for `ada_message` on user with balance=4 rejects `InsufficientCredits` (cost=5).
- Edge case — concurrent `credit_reserve_v2` for same user serialize via advisory lock; only as many succeed as balance permits.
- Error path — caller passes `p_action_type='unknown'` → SQL exception (no fallback to hardcoded cost).
- Error path — `credit_reserve_v2` on locked user (`users.locked_at IS NOT NULL`) rejects `AccountLocked`.
- Integration — `credit_commit_v2` during dispute-lock (locked_at set between reserve and commit) converts to release; no double-loss.
- Integration — Phase A leaves legacy `credit_reserve/release/commit/refund` callable; tests assert both coexist without type clashes.

**Verification:**
- `make migrate` applies.
- `tests/test_credit_rpcs_v2.py` passes end-to-end.
- Advisory-lock contention test: 10 concurrent `credit_reserve_v2` for a user with balance=300 milli → exactly 3 succeed (cost=100 each).

---

- [ ] **Unit 3: Migration 0050 — grant + allotment + pack RPCs (REPLACE audit)**

**Goal:** One-stop RPCs for signup_grant, weekly_free_grant, monthly_allotment (REPLACE with two-entry audit), credit_pack_purchase, dispute_compensation.

**Requirements:** R6, R7, R7-Pack, R11, R15, R-Dispute-3.

**Dependencies:** Unit 1, Unit 2.

**Files:**
- Create: `app/migrations/0050_credit_grants_and_allotment_rpcs.sql`
- Test: `tests/test_monthly_allotment_replace.py`, `tests/test_weekly_free_grant_idempotency.py`

**Approach:**
- `credit_apply_monthly_allotment_v2(p_user_id UUID, p_plan_version_id UUID)`: advisory-lock'd via `hashtextextended`; computes `current_non_pack_balance = SUM(delta) WHERE type NOT IN ('credit_pack_purchase', 'reserve', 'commit')` (adversarial P0 race fix — excludes in-flight reservations and commit markers so a mid-flight reserve doesn't get REPLACE'd away, and a subsequent release/commit doesn't credit the new allotment). Inserts ONE entry: `(delta = plan_versions.monthly_allotment_milli - current_non_pack_balance, type='monthly_allotment', reference_id=plan_version_id, metadata={'discarded_milli': <prior_non_pack_balance>, 'plan_version_id': <uuid>})`. Single-entry satisfies audit via `metadata.discarded_milli`. Idempotent guard: caller (webhook handler) dedup is via event_id in `processed_webhook_events`.
- `credit_apply_signup_grant_v2(p_user_id UUID, p_deterministic_hash BYTEA, p_protected_hash BYTEA, p_salt BYTEA, p_plan_version_id UUID)`: advisory-lock'd; checks `signup_grants_issued` for `p_deterministic_hash`; if exists, inserts `(+0, signup_grant_suppressed_by_fingerprint)` for audit and returns; else INSERT `signup_grants_issued` + `(+300, signup_grant)` ledger. Handles NULL fingerprint (web signup) — just grant + skip table insert.
- `credit_apply_weekly_free_grant_v2(p_user_id UUID, p_iso_week TEXT)`: advisory-lock'd; dedup via partial UNIQUE `(user_id, week_tag)` virtual — encoded as `reference_id = uuid5(namespace='weekly', name=user_id||iso_week)` and UNIQUE on that; ON CONFLICT DO NOTHING. Inserts `(+100, weekly_free_grant)`.
- `credit_apply_pack_purchase_v2(p_user_id UUID, p_event_id TEXT, p_credits_milli INT)`: advisory-lock'd; inserts `(+p_credits_milli, credit_pack_purchase, reference_id=event_id_as_uuid5)`. Outer dedup via `processed_webhook_events`.
- `credit_dispute_compensate_v2(p_user_id UUID, p_charge_id TEXT)`: looks up the ledger entry from original `charge.succeeded` (by Stripe charge_id stored in reference metadata); inserts compensating negative delta, type `dispute_compensation`. Acceptable negative balance per R-Dispute-3.

**Patterns to follow:**
- Unit 2's advisory-lock pattern.
- `docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md` — CAS on idempotent writes.

**Test scenarios:**
- Happy path — monthly-allotment on user with 2500 non-pack balance + 500 pack: after call, non-pack total = 3000 (REPLACE), pack total = 500, combined = 3500.
- Happy path — ledger post-REPLACE has one `monthly_allotment` entry with `delta=+500` (3000-2500) and `metadata.discarded_milli=2500`. Audit reconstruction via metadata.
- Happy path — signup_grant on fresh fingerprint: `signup_grants_issued` row inserted; balance += 300.
- Happy path — signup_grant with NULL fingerprint (web): balance += 300; no table insert.
- Edge case — signup_grant on user whose device has a matching `signup_grants_issued` row: ledger entry `signup_grant_suppressed_by_fingerprint` (+0); balance unchanged.
- Edge case — weekly_free_grant called twice for same (user, ISO-week): second call is no-op (ON CONFLICT DO NOTHING).
- Edge case — monthly_allotment on user with exactly 0 non-pack balance: single entry `(+3000, monthly_allotment, metadata.discarded_milli=0)`; balance lands at 3000 with no "phantom" second row.
- Adversarial race — user reserves 100 milli (in-flight), then renewal fires. `current_non_pack_balance` excludes `reserve` entries → REPLACE computes from pre-reserve baseline. Subsequent `credit_commit_v2` writes `(0, commit)` → final balance = allotment. Subsequent `credit_release_v2` (job failed) writes `(+100, release)` → final balance = allotment + 100 (the release refund to the new allotment — correct user-facing behaviour).
- Error path — `p_plan_version_id` points to non-existent row: RAISE EXCEPTION.
- Integration — run monthly_allotment while a concurrent `credit_reserve_v2` is in flight: advisory-lock serializes; no partial state.

**Verification:**
- `make migrate`.
- `tests/test_monthly_allotment_replace.py::test_audit_trail_has_both_entries` passes.
- `tests/test_weekly_free_grant_idempotency.py::test_same_week_is_noop` passes.

---

- [ ] **Unit 4: Migration 0051 — dispute state + delete-account extension + Stripe-customer-id cleanup**

**Goal:** RPCs for dispute lifecycle; extend `delete_account` SQL side (ON DELETE SET NULL for `users.merged_into_user_id`). Wire `stripe_customer_id` into the delete-account contract (app side in Unit 11).

**Requirements:** R-Dispute-1..4, R17.

**Dependencies:** Unit 1.

**Files:**
- Create: `app/migrations/0051_dispute_and_delete_extension.sql`
- Test: `tests/test_dispute_lifecycle.py`

**Approach:**
- **Dispute state is a CAS state machine on `(dispute_last_event_id, dispute_last_event_at, dispute_last_status)`** — security review CRITICAL fix for out-of-order events. Columns added in Unit 1.
- `apply_dispute_event(p_user_id UUID, p_event_id TEXT, p_event_at TIMESTAMPTZ, p_new_status TEXT)` where `p_new_status ∈ {'created', 'closed_won', 'closed_lost', 'funds_withdrawn'}`. Body:
  - Acquire `hashtextextended` advisory lock.
  - If `users.dispute_last_event_id = p_event_id` → idempotent no-op return.
  - If `users.dispute_last_event_at IS NOT NULL AND users.dispute_last_event_at > p_event_at` → out-of-order arrival; RETURN `{applied: false, reason: 'out_of_order'}` (caller enqueues Stripe API re-fetch of current dispute state).
  - Else: apply transition: `'created'` → set `locked_at = now()`; `'closed_won'` → set `locked_at = NULL`; `'closed_lost'` → keep `locked_at` set + caller writes compensating ledger; `'funds_withdrawn'` → audit only. UPDATE `users SET dispute_last_event_id, dispute_last_event_at, dispute_last_status`.
- Handler for out-of-order: the webhook handler (Unit 8) on `applied=false` does NOT enqueue a retry worker (scope cut — no retry worker). Instead it returns HTTP 5xx; Stripe retries with ordering that eventually resolves. The CAS on `dispute_last_event_at` guarantees the final state matches the latest event Stripe ever delivered.
- `clear_user_dispute_lock` / `set_user_dispute_lock` collapsed into `apply_dispute_event`; no separate entrypoints.
- `users.merged_into_user_id` FK already set to `ON DELETE SET NULL` in Unit 1 — verify SET NULL behaviour for guest-merge audit survives user delete (guest row dies, merged_into pointer on the survivor is cleared).
- `idx_users_locked_at_not_null` already created in Unit 1.

**Patterns to follow:**
- Unit 2/3 advisory-lock pattern.
- `app/migrations/0044_hard_delete_account.sql` — FK ON DELETE SET NULL pattern.

**Test scenarios:**
- Happy path — `apply_dispute_event(u, evt1, t1, 'created')` sets `locked_at`; subsequent `credit_reserve_v2` rejects `AccountLocked`.
- Happy path — `apply_dispute_event(u, evt2, t2, 'closed_won')` with t2 > t1 clears `locked_at`; `credit_reserve_v2` resumes.
- Edge case — same `apply_dispute_event(u, evt1, ...)` called twice: second returns idempotent no-op.
- Edge case — out-of-order: `apply_dispute_event(u, evt2, t2='closed_won')` arrives FIRST, then `apply_dispute_event(u, evt1, t1, 'created')` with t1 < t2. First call applies closed_won (locked_at cleared even though was already NULL); second call returns `{applied: false, reason: 'out_of_order'}` because dispute_last_event_at (t2) > t1. locked_at stays NULL. Final state = closed_won (correct).
- Edge case — out-of-order: `apply_dispute_event(u, evt1, t1='closed_lost')` arrives first, then `apply_dispute_event(u, evt0, t0, 'created')` with t0 < t1. First applies closed_lost; dispute_last_event_at=t1. Second returns out_of_order (t1 > t0). Net: user in closed_lost state — locked_at remains set from closed_lost being applied first. Correct (lost always locks).
- Edge case — `dispute_last_event_at` ties: identical timestamp + different event_ids → CAS rejects one (returns out_of_order); Stripe retries; eventually resolves.
- Integration — user deletion with `merged_into_user_id` pointing at them: FK fires ON DELETE SET NULL on the audit column of the survivor; DELETE succeeds.
- Integration — full lifecycle: created → closed_won → user regains access.
- Integration — full lifecycle: created → closed_lost → locked_at persists + compensating ledger entry visible in subsequent balance query.

**Verification:**
- `make migrate`.
- Dispute lifecycle test passes.

---

- [ ] **Unit 5: PaymentPort additions — `retrieve_subscription`, `delete_customer`**

**Goal:** Port + both adapters gain the new methods required by R14b drift-protection and R17 delete-account.

**Requirements:** R14b, R17.

**Dependencies:** None (independent of migrations).

**Files:**
- Modify: `app/payment/ports.py`
- Modify: `app/payment/adapters/stripe_adapter.py`
- Modify: `app/payment/adapters/mock.py`
- Test: `tests/test_payment_port_v2.py`

**Approach:**
- Add to `PaymentPort`:
  - `async def retrieve_subscription(self, subscription_id: str, timeout: float = 3.0) -> SubscriptionSnapshot` returning `{id, status, current_period_end, current_period_start, cancel_at_period_end, customer_id}`.
  - `async def delete_customer(self, customer_id: str) -> None` with 3s timeout.
- `StripePaymentAdapter.retrieve_subscription`: `await loop.run_in_executor(None, functools.partial(self._stripe.Subscription.retrieve, subscription_id, request_timeout=timeout))`. Wrap `StripeError` → `PaymentFetchError`. Apply `asyncio.wait_for(..., timeout=timeout+0.5)` as a belt-and-braces upper bound (stripe SDK's request_timeout isn't always strict).
- `StripePaymentAdapter.delete_customer`: `Customer.delete(customer_id)`. Treat `resource_missing` as success (idempotent).
- `MockPaymentAdapter`: returns deterministic stub matching an in-memory state (sub id → snapshot).
- `stripe_adapter._get_or_create_customer` rewrites to prefer `users.stripe_customer_id` lookup; falls back to `Customer.search` ONLY if column is NULL; writes back the column on create/find. (Lazy-population policy.)

**Patterns to follow:**
- Existing `create_payment_intent` for run_in_executor pattern.
- Existing `construct_webhook_event` for typed error wrapping.

**Test scenarios:**
- Happy path — `retrieve_subscription(mock_id)` returns a `SubscriptionSnapshot` with expected fields.
- Happy path — `delete_customer(mock_id)` succeeds; second call also succeeds (idempotent).
- Edge case — Stripe returns `resource_missing` on `delete_customer`: adapter treats as success.
- Error path — Stripe times out on retrieve (simulated): adapter raises `PaymentFetchError` within `timeout+0.5`.
- Integration — `_get_or_create_customer` on user with populated `stripe_customer_id`: zero Stripe calls; cached path.
- Integration — `_get_or_create_customer` on user with NULL column and matching metadata search: hits search, writes back column, returns id.

**Verification:**
- `make lint && make test`.
- Mock adapter round-trips.

---

- [ ] **Unit 6: `PlanVersionRepository` + `SignupGrantRepository` + fingerprint helpers**

**Goal:** Supabase repositories wrapping `plan_versions` + `signup_grants_issued` + HMAC+salted-hash helpers.

**Requirements:** R3, R6a, R12.

**Dependencies:** Unit 1.

**Files:**
- Create: `app/repositories/plan_version_repo.py`
- Create: `app/repositories/signup_grant_repo.py`
- Create: `app/entitlement/fingerprint.py`
- Modify: `app/config/__init__.py` (or equivalent settings module) — add `SIGNUP_FINGERPRINT_SERVER_SECRET`
- Modify: `app/.env.example` — document new env var (minimum 32-byte random hex)
- Test: `tests/test_signup_grant_fingerprint.py`, `tests/test_plan_version_repo.py`

**Approach:**
- `fingerprint.py`:
  - `compute_deterministic_hash(installation_uuid: str, server_secret: bytes) -> bytes` — `hmac.new(server_secret, installation_uuid.encode(), sha256).digest()`.
  - `compute_protected_hash(installation_uuid: str, salt: bytes) -> bytes` — `sha256(salt + installation_uuid.encode()).digest()`.
  - `generate_salt() -> bytes` — `secrets.token_bytes(32)`.
- **`SIGNUP_FINGERPRINT_SERVER_SECRET` rotation protocol** (security review HIGH fix). Env variable is a comma-separated list: `PRIMARY_SECRET,SECONDARY_SECRET` (secondary optional). Lookup checks the table with primary first, then secondary. Rotation procedure in `docs/runbooks/payments.md`: (1) deploy with `PRIMARY=new,SECONDARY=old` — both work; (2) background job re-derives every row's `deterministic_hash` under new secret and UPSERTs (old rows carry old hash; new-secret derivation writes a second row for the same device until migration completes — acceptable because an extra no-op check is preferable to a lookup miss); (3) once re-derivation complete, deploy with `PRIMARY=new,SECONDARY=`. No emergency rotation; planned rotations only. Secret rotation is an operator-initiated event, not automated.
- `PlanVersionRepository`:
  - `get_default_free_id() -> UUID` — cached in-process (plan_version rows are immutable once seeded).
  - `get_active_version_for_user(user_id: UUID) -> PlanVersionRow` — `COALESCE` logic: active-subscription → plan_version_id → default_free.
- `SignupGrantRepository`:
  - `exists(deterministic_hash: bytes) -> bool`.
  - `insert(deterministic_hash, protected_hash, salt)`.
  - `purge_older_than(cutoff: datetime) -> int` (used by nightly TTL sweep, Unit 9).
- `SIGNUP_FINGERPRINT_SERVER_SECRET` required; fail-fast on missing (per feedback_no_env_fallbacks).

**Patterns to follow:**
- `app/repositories/subscription_repo.py` — sync-Supabase repo shape.
- `app/db/guest.py` — `secrets` usage, regex validation.

**Test scenarios:**
- Happy path — `compute_deterministic_hash` is deterministic: same inputs → same output.
- Happy path — `compute_protected_hash` varies with salt: same uuid + different salt → different hash.
- Happy path — `PlanVersionRepository.get_active_version_for_user` on Pro user returns v1_pro.
- Happy path — same method on Free user (no subscription) returns v1_free_default.
- Edge case — `SIGNUP_FINGERPRINT_SERVER_SECRET` missing → ValueError at import / first call (no silent fallback).
- Edge case — `SignupGrantRepository.exists` with unknown hash returns False.
- Error path — `generate_salt()` returns 32 bytes; not all zeros; differs across calls.

**Verification:**
- `make lint && make test`.

---

- [ ] **Unit 7: `EntitlementServiceV2` + drift-protection buffer + `/v2/entitlement`**

**Goal:** Parallel entitlement service + parallel router mounted at `/v2/entitlement`. Read-only on `app/entitlement/service.py` and `app/api/entitlement.py`.

**Requirements:** R1, R3, R4a, R10, R14, R14a, R14b.

**Dependencies:** Unit 1, Unit 5, Unit 6.

**Files:**
- Create: `app/entitlement/service_v2.py`
- Create: `app/api/entitlement_v2.py`
- Create: `app/entitlement/models_v2.py` (EntitlementStateV2 dataclass + BlockedReason enum)
- Modify: `app/main.py` (mount new router under `/v2` prefix)
- Test: `tests/test_entitlement_v2_drift_buffer.py`

**Approach:**
- `EntitlementServiceV2.get_entitlement(user_id)`:
  1. Fetch user row (`locked_at`, `stripe_customer_id`).
  2. Fetch active subscription row (if any) — includes `grace_until`, `period_end`, `cancel_at`.
  3. Derive `subscription_status` from dates + `locked_at` (see state diagram). Pure date-derived; no authoritative Stripe fetch in v1 (R14b deferred to v1.1 per scope review).
  4. Resolve plan_version via `PlanVersionRepository.get_active_version_for_user`.
  5. Compute balance_milli via `sum_credit_balance` RPC.
  6. Compute `remaining_glowups = floor(balance_milli / plan.glowup_cost_milli)`, `approx_remaining_ada = floor(balance_milli / plan.ada_cost_milli)`.
  7. Compute `blocked_reason`: `subscription_locked_by_dispute` if locked_at else (the caller decides per-action whether `insufficient_credits` applies — shape doesn't bind action-level blocking except at the lock level).
  8. Build purchase_options from plan_version + `CREDIT_PACK_V1` app-config.
- `/v2/entitlement` returns `EntitlementStateV2`. Authenticated + guest-first-class via existing `get_user_or_guest`.
- **Register `ENTITLEMENT_V2_ENABLED` feature in backend capability registry** (feasibility review MODERATE fix). Add entry to `app/features/` (convention per `feedback_feature_gating_centralized`). Mobile `useCapabilities()` reads via existing capability plumbing. Flag defaults off; enabled per-env via admin config.

**Execution note:** Test-first for the drift-protection state machine (many branches; characterization coverage easier to write as failing tests first).

**Patterns to follow:**
- `app/entitlement/service.py` — service constructor shape.
- `app/db/async_helpers.py::run_sync` — sync-Supabase wrapping.

**Test scenarios:**
- Happy path — Pro user within billing period: status='active', tier='Pro', correct glowup count.
- Happy path — Free user (no subscription): status='none', tier='Free', plan_version=v1_free_default.
- Edge case — Pro user past `period_end` with `grace_until=NULL`: returns 'none'/'Free' (webhook is the authority; we render whatever latest webhook produced).
- Edge case — Pro user with `grace_until > now()`: status='grace', label='Pro', balance retained.
- Edge case — Pro user with `grace_until < now()` and `subscriptions.status='active'`: status='none'/'Free' (grace expired → label flip per R10).
- Edge case — user.locked_at set: status='locked'; blocked_reason='subscription_locked_by_dispute'; balance still exposed.
- Error path — user not found: 404.
- Error path — plan_version row missing (seed regression): 500 with clear log.
- Integration — `/v2/entitlement` with guest token returns shape; guest never receives weekly_free_grant entries (verified separately in Unit 9 test).
- Integration — `remaining_glowups` = `floor(balance_milli/100)` exactly; no off-by-one at 99/100/101 milli.
- Integration — `blocked_reason` enum rendering: matches typed string in response JSON.

**Verification:**
- `curl /v2/entitlement -H "Authorization: Bearer ..."` returns shape matching contract.
- `make lint && make test`.
- Phase A acceptance: `app/api/entitlement.py` and `app/entitlement/service.py` `git diff` shows **zero changes**.

---

- [ ] **Unit 8a: `webhooks_v2` — subscription lifecycle events**

**Goal:** New webhook router at `/v2/webhooks/stripe` handling subscription-lifecycle events (5 event types). Leaves `/webhooks/stripe` untouched for the bug-fix agent. Split from monolithic Unit 8 per scope review.

**Requirements:** R7, R9, R10, R11, R18.

**Dependencies:** Unit 2, Unit 3, Unit 5, Unit 6, Unit 7.

**Files:**
- Create: `app/api/webhooks_v2.py`
- Modify: `app/main.py` — mount router.
- Modify: `app/middleware/logging.py` (or equivalent) — add `X-Install-UUID` to header-scrub list alongside `Authorization` (security review MEDIUM fix).
- Test: `tests/test_webhooks_v2_subscription_idempotency.py`, `tests/test_webhooks_v2_subscription_ordering.py`

**Approach:**
- `POST /v2/webhooks/stripe`: **verify signature BEFORE any DB read/write** (security review; sig-verify happens before `event_id` dedup check); `event_id` dedup via `processed_webhook_events` (existing primitive; R18); route by `event_type`.
- Event routes (subscription lifecycle):
  - `checkout.session.completed` (subscription mode) → stamp `users.stripe_customer_id`; wait for `customer.subscription.created` to write the subscription row.
  - `customer.subscription.created` → UPSERT subscription row with `plan_version_id = <v1_pro>`, status='active', period dates. Call `credit_apply_monthly_allotment_v2`.
  - `customer.subscription.updated` → **If subscription row NOT FOUND: return HTTP 500** (scope review cut 2 + feasibility review HIGH #1 resolution). Stripe's built-in retry backoff handles out-of-order; no ARQ retry worker in v1. If found: update dates, cancel_at_period_end.
  - `invoice.payment_succeeded` (during grace) → if `subscriptions.grace_until IS NOT NULL` OR the user's label is currently Free (grace expired), clear `grace_until`, restore status='active', call `credit_apply_monthly_allotment_v2`.
  - `invoice.payment_failed` → `UPDATE subscriptions SET grace_until = now() + interval '3 days'` (NOT `status='past_due'` — writer lives in v2; legacy path untouched in Phase A).
  - `customer.subscription.deleted` → `UPDATE subscriptions SET cancelled_at = now(), status='cancelled'` (cancelled is the surviving enum value; `expired` is dropped in Phase B). No balance mutation.
- Events older than 72h on first attempt: log + 200 + skip (per R18).
- Handler fast path budget asserted via logging + metric: log `_webhook_latency_ms` per event; a separate test runs the full chain against the mock adapter and asserts <3000ms local (leaves headroom for prod 5s SLA).

**Test scenarios:**
- Happy path — `customer.subscription.created` creates subscription row + triggers monthly_allotment with single `monthly_allotment` entry carrying `metadata.discarded_milli`.
- Happy path — `invoice.payment_failed` sets `grace_until = now() + 3 days`; label unchanged.
- Happy path — `invoice.payment_succeeded` during grace clears `grace_until`, REPLACES allotment.
- Edge case — out-of-order `customer.subscription.updated` (subscription row NOT FOUND): returns 500; Stripe retries; second attempt after `.created` fires successfully.
- Edge case — duplicate event_id: second POST is no-op, returns 200 `{status:"already_processed"}`.
- Edge case — event older than 72h: logged, discarded, 200.
- Edge case — invalid signature: 400, no state mutation. Signature check fires BEFORE idempotency check.
- Edge case — `X-Install-UUID` header in request: middleware scrubs from access logs (assert log lines don't contain the UUID value).
- Error path — DB write fails mid-handler: event_id is NOT recorded; Stripe retry recomputes.
- Integration — webhook latency test: verify-sig + dedup + handler + record all fire in <3000ms local (mock adapter).
- Integration — Phase A acceptance: `app/api/webhooks.py` `git diff` shows **zero changes**.

**Verification:**
- `make test tests/test_webhooks_v2_subscription_*`.
- Manual: `stripe trigger invoice.payment_failed` against `/v2/webhooks/stripe` → grace_until populated.

---

- [ ] **Unit 8b: `webhooks_v2` — disputes + packs + refunds**

**Goal:** Same router; adds dispute + pack + refund event handlers. Lands independently from 8a for reviewable PR size.

**Requirements:** R7-Pack, R15, R-Dispute-1..4, R18.

**Dependencies:** Unit 4, Unit 5, Unit 6, Unit 8a.

**Files:**
- Modify: `app/api/webhooks_v2.py` — add handlers.
- Test: `tests/test_webhooks_v2_disputes.py`, `tests/test_webhooks_v2_packs.py`

**Approach:**
- Additional event routes:
  - `payment_intent.succeeded` with `metadata.type='credit_pack'` → `credit_apply_pack_purchase_v2(user_id, event_id, CREDIT_PACK_V1.credits_milli)`.
  - `charge.refunded` → compensating ledger entry via existing refund RPC (or new `credit_ledger.type='refund'` entry keyed on charge_id).
  - `charge.dispute.created|closed_won|closed_lost|funds_withdrawn` → derive `p_new_status` + `p_event_at = data.created` from payload; lookup `user_id` via `users.stripe_customer_id = payload.customer` (backfilled in Unit 1); call `apply_dispute_event(...)`. On `{applied: false, reason: 'out_of_order'}` → return HTTP 500 so Stripe retries.
  - `charge.dispute.closed` (outcome=lost) → after `apply_dispute_event`, write compensating ledger entry via `credit_dispute_compensate_v2(user_id, charge_id)`; `locked_at` stays set.

**Test scenarios:**
- Happy path — `payment_intent.succeeded` with credit_pack metadata ADDs 500 milli via `credit_apply_pack_purchase_v2`.
- Happy path — `charge.dispute.created` → `apply_dispute_event` sets `locked_at`; subsequent `credit_reserve_v2` rejects `AccountLocked`.
- Happy path — `charge.dispute.closed` (won) with higher timestamp → `apply_dispute_event` clears `locked_at`.
- Happy path — `charge.dispute.closed` (lost) → negative compensating entry; `locked_at` persists.
- Edge case — out-of-order dispute events: closed arrives before created → second `apply_dispute_event` returns `{applied:false, reason:'out_of_order'}` → handler returns 500; Stripe retries; order eventually resolves (tested).
- Edge case — user without `stripe_customer_id` (unpopulated edge) → falls back to `Customer.search(metadata.user_id)` via adapter; inline Stripe call; test asserts this path still fits <5s (relies on backfill in Unit 1 covering all prod users).
- Edge case — pack purchase duplicate event_id: second POST is idempotent (outer `processed_webhook_events` dedup).
- Integration — full dispute lifecycle: created → closed_won → user regains access; balance unchanged across lifecycle.
- Integration — full dispute lifecycle: created → closed_lost → locked_at persists + compensating entry visible; future `credit_reserve_v2` still rejects `AccountLocked`.

**Verification:**
- `make test tests/test_webhooks_v2_{disputes,packs}*`.
- Manual: `stripe trigger charge.dispute.created` → user.locked_at populated.

**Execution note:** Characterization coverage for the 10 event types across 8a + 8b before modifying any of them (pytest fixtures under `tests/fixtures/stripe/`).

**Patterns to follow (both 8a and 8b):**
- `app/api/webhooks.py` — existing sig-verify + dedup flow.
- `app/repositories/subscription_repo.py::record_webhook_event` — upsert-with-ignore_duplicates idempotency.
- `docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md` — re-assert at commit.

---

- [ ] **Unit 9: Signup grant on register + weekly_free_grant worker + fingerprint TTL sweep**

**Goal:** Wire the signup-grant RPC into the registration flow (three endpoints: `/auth/register`, `/auth/login`, `/auth/tiktok-login`); add ARQ scheduled weekly sweep; add ARQ nightly fingerprint purge.

**Requirements:** R6, R6a.

**Dependencies:** Unit 3, Unit 6.

**Files:**
- Modify: `app/api/auth.py` — inject fingerprint header; call signup_grant RPC at end of registration path.
- Create: `app/workers/weekly_free_grant.py` — ARQ task iterating `is_guest=false` users, calling `credit_apply_weekly_free_grant_v2(user_id, iso_week)`.
- Create: `app/workers/fingerprint_purge.py` — ARQ task purging `signup_grants_issued` rows older than 12 months.
- Modify: `app/workers/_registry.py` (or equivalent cron config) — register both tasks with staggered cron (use unused minutes 03:15 and 04:15 per `orphan-dlq-symmetry` cron-stagger guidance).
- Modify: `mobile/app/(auth)/register.tsx` (or the auth API client) — send `X-Install-UUID` header.
- Test: `tests/test_signup_grant_flow.py`, `tests/test_weekly_free_grant.py`, `tests/test_fingerprint_purge.py`

**Approach:**
- Accept `x-install-uuid: Annotated[str | None, Header()]` on `/auth/register`, `/auth/login`, `/auth/tiktok-login`.
- On successful account creation: compute `deterministic_hash` + `protected_hash` + `salt`; call `credit_apply_signup_grant_v2`. NULL `x-install-uuid` header (web) → call with NULLs (RPC grants +300 without table insert).
- Weekly worker: cron at `30 2 * * 1` (Monday 02:30 UTC — unused slot). Iterate non-guest users in pages; call RPC per user. Idempotent via `(user_id, iso_week)` unique reference.
- Fingerprint purge: cron at `15 3 * * *` (daily 03:15 UTC). `DELETE FROM signup_grants_issued WHERE issued_at < now() - interval '12 months'`.

**Patterns to follow:**
- `app/entitlement/trial_grantor.py` — idempotent grant shape.
- `app/workers/retention.py::reconcile_orphaned_users` — nightly sweep pattern.
- `docs/solutions/best-practices/orphan-dlq-symmetry-2026-04-19.md` — cron stagger rules.

**Test scenarios:**
- Happy path — `/auth/register` with `X-Install-UUID: <fresh>` → user has +300 milli; `signup_grants_issued` has row.
- Happy path — `/auth/register` second time on same device (after delete_account) with same `X-Install-UUID` → +0 milli; `signup_grant_suppressed_by_fingerprint` audit entry.
- Happy path — `/auth/register` with no `X-Install-UUID` (web) → +300 milli; no table row.
- Happy path — weekly worker grants +100 to Free user who hasn't received a grant for this ISO-week.
- Happy path — weekly worker is no-op for Pro user (filtered by `is_guest=false AND status!='active'` — simpler: only grant to users without active subscription).
- Edge case — weekly worker runs twice in same week: second run is no-op (ON CONFLICT DO NOTHING).
- Edge case — fingerprint purge deletes 12-month-old rows; retains fresh rows.
- Error path — `SIGNUP_FINGERPRINT_SERVER_SECRET` missing at call time: 500 + clear log.
- Integration — guest signs up without fingerprint header; weekly worker does not grant to the now-authenticated user until next Monday.

**Verification:**
- `make test`.
- Manual: `curl /auth/register -H 'X-Install-UUID: <...>'` twice; second call produces audit entry.

---

- [ ] **Unit 10: Guest merge-on-signup (2× cap + pack-bypass)** — SUPERSEDED 2026-04-20

> **SUPERSEDED** by the 2026-04-20 guest-removal PR (`feat/remove-guest-and-close-anon`).
> The guest-merge primitive is deleted outright. New signups get the flat
> `signup_grant` (Unit 9) with no carry-over from any anonymous session. The
> `merge_guest_ledger` RPC, `guest_install_uuid_hash` column, and
> `guest_merge_non_pack` / `guest_merge_truncated` ledger types have been
> dropped from the schema. `app/db/guest.py`, `app/repositories/guest_merge_repo.py`,
> the merge wiring in register/social_login/tiktok_login, and the mobile
> guest-session module are all gone.

**Goal:** Atomic merge of guest ledger into authenticated ledger at registration time.

**Requirements:** R16.

**Dependencies:** Unit 3, Unit 9.

**Files:**
- Modify: `app/api/auth.py` — at registration, if `guest_session_token` is present + valid, invoke merge RPC before signup_grant RPC.
- Modify: `app/migrations/0050_credit_grants_and_allotment_rpcs.sql` — add RPC `merge_guest_ledger_v2(p_guest_user_id, p_new_user_id, p_signup_grant_milli, p_install_uuid_hash BYTEA)` alongside the grant RPCs (migration slot 0052 is reserved for legal-gated `signup_grants_issued`).
- Modify: `app/db/guest.py::create_guest_user` — accept `X-Install-UUID` value from caller, write `guest_install_uuid_hash` at creation.
- Modify: `app/api/auth.py::create_guest` — read `X-Install-UUID` header, pass to `create_guest_user`.
- Modify: `mobile/lib/entitlement_v2.ts` or a merge-result type — expose truncation info to the client.
- Test: `tests/test_guest_merge_cap.py`, `tests/test_guest_merge_install_uuid_binding.py`

**Approach:**
- **Install-UUID binding** (security review HIGH fix — prevents pack drain via guest-token theft). Guest row gets a new column in Unit 1: `users.guest_install_uuid_hash BYTEA NULL` populated at guest creation from the device's `X-Install-UUID` header. Merge RPC requires `X-Install-UUID` to match the guest's recorded hash; mismatch → HTTP 403 + no merge. Guests created without a header (pre-header-rollout clients + web guests) accept any merge request — tolerated residual risk, narrow-scope. Covered by test.
- RPC acquires advisory locks on BOTH user ids via `hashtextextended` (ordered by uuid to prevent deadlock); selects guest non-pack balance + pack balance; computes `transfer_non_pack = min(non_pack, 2 * p_signup_grant_milli)`; computes `truncated = non_pack - transfer_non_pack`; inserts ledger entries on new user: `(+transfer_non_pack, guest_merge_non_pack)` + `(+pack_balance, credit_pack_purchase, reference_id=guest_merge_<uuid>)`; marks guest row `merged_into_user_id = p_new_user_id, merged_at = now()`; writes audit `(+0, guest_merge_truncated)` with `truncated` in reference metadata if > 0.
- `credit_ledger.type` enum already extended in Unit 1 to include `guest_merge_non_pack`, `guest_merge_truncated`.
- Response to client: `{credits_transferred, truncated_milli}` — mobile shows "X credits will not transfer" UI if `truncated > 0` (new mobile surface in `mobile/lib/guest-merge-notice.ts`).

**Patterns to follow:**
- Unit 2's advisory-lock pattern.
- `app/db/guest.py::resolve_guest_by_token` — token validation.

**Test scenarios:**
- Happy path — guest with 200 milli merges into new user; new user has +200 (below 2× cap of 600).
- Happy path — guest with 500 pack + 500 non-pack merges; new user gets +500 non-pack + +500 pack = +1000; no truncation.
- Happy path — guest with 700 non-pack + 0 pack merges; new user gets +600 (cap), truncated=100; audit entry present; response includes truncated.
- Edge case — guest with 0 balance: merge is no-op; guest row still marked merged.
- Edge case — merge is atomic: crash between steps leaves no partial state (tested by simulating a raised exception mid-RPC; balance unchanged).
- Edge case — install-UUID mismatch: guest created with install-UUID-A, merge attempted with install-UUID-B → HTTP 403; guest ledger NOT transferred; guest row NOT marked merged (security review HIGH coverage).
- Edge case — guest created without install-UUID header (pre-rollout client): `guest_install_uuid_hash IS NULL`; merge accepts any header (documented residual risk).
- Error path — invalid guest_session_token: 400; no merge.
- Error path — guest already merged (`merged_at IS NOT NULL`): 409.
- Integration — signup_grant runs AFTER merge; both grants land; signup_grant still respects fingerprint check.
- Integration — mobile surfaces truncated amount via dedicated toast/modal when > 0.
- Integration — theft attack simulation: attacker intercepts `guest_session_token` + attempts merge from different device → 403; victim's pack credits untouched.

**Verification:**
- `make test`.

---

- [ ] **Unit 11: Delete-account integration — Stripe customer delete + new surfaces + DLQ**

**Goal:** Wire every new user-owned surface into `delete_account` + `wipeLocalDeviceState` per `account-delete-hard-reset-invariant-2026-04-18` registry pattern.

**Requirements:** R17.

**Dependencies:** Unit 1, Unit 5.

**Files:**
- Modify: `app/api/auth.py::delete_account` — insert Stripe `delete_customer` call after auth-delete step; on failure write DLQ entry.
- Create: `app/repositories/stripe_customer_dlq.py` (or extend existing `orphaned_storage_repo` to a generic `orphaned_deletes` shape).
- Modify: `mobile/lib/account-wipe.ts` — no changes needed (existing loop over `SECURE_STORE_KEYS` covers the new `nxme_install_uuid` key added in Unit 14).
- Modify: `mobile/constants/config.ts` — add `nxme_install_uuid` to `SECURE_STORE_KEYS` so the `wipeLocalDeviceState` loop picks it up automatically.
- Test: `tests/test_delete_account_new_surfaces.py`

**Approach:**
- **Add new ordering step 1.5 — drain in-flight reservations** (adversarial review P2 gap). Before auth-delete, query `credit_reservations WHERE user_id=$1 AND status='reserved'`; call `credit_release_v2` on each. Step exists in current code but relies on `ledger.release` (v1 RPC); Phase B unit 17 flips to `_v2`. For Phase A, mirror the existing `release` loop using the new `_v2` RPC.
- **Add new ordering step 1.6 — drain scheduled ARQ jobs** (adversarial review P2 gap). Iterate known ARQ job prefixes for this user: `delete_account:{user_id}`, `weekly_free_grant:{user_id}`, any future per-user prefix. Call `arq_pool.job(_job_id).abort()` — best-effort; ignore errors. Not retry-safe, but the jobs themselves will 404-on-missing-user and log-warn gracefully.
- After `auth.admin.delete_user` succeeds (step 3 of the 8-step ordering), check `user.stripe_customer_id`; if non-NULL, call `payment.delete_customer(customer_id)` with 3s timeout; on failure, insert `(bucket='stripe_customer', key=customer_id, reason='delete_account_failed')` into the DLQ table and log WARNING. Do NOT fail the overall delete; the DLQ sweeper reconciles.
- **`processed_webhook_events` payload scrub** (adversarial review P2 gap). Event payloads contain Stripe `customer_id` + sometimes `email`. Add a nightly ARQ job `purge_old_webhook_events` that deletes events >30 days old (decision: webhook events carry no audit value past the 72h dedup window; 30 days is a safety margin). This isn't a per-user delete but it caps the PII retention window on this table. Document as a payment-ops hygiene task, not a delete-account step.
- Verify every new user-owned surface either CASCADEs (ledger entries, subscriptions, credit_reservations — already CASCADE per 0044), is columns on `users` (dies with row — locked_at, dispute_last_*, stripe_customer_id, merged_into_user_id, merged_at, guest_install_uuid_hash), or is the documented SURVIVES exception (`signup_grants_issued`).
- Redis: no new user-scoped keys introduced by this feature. Existing `scan_iter` for `concurrent:*` + `gen:user_daily:*` + `advisor_chat_rate:*` remains correct. `advisor_chat_rate:{user_id}` key-pattern verified via grep before claim (prerequisite of Unit 11 merge).
- Mobile: SecureStore key `nxme_install_uuid` is added to `SECURE_STORE_KEYS` registry so `wipeLocalDeviceState`'s existing `Object.values(SECURE_STORE_KEYS).map(deleteItem)` loop already covers it.
- Runbook: update `docs/runbooks/payments.md` with the signup_grants_issued SURVIVES exception + the Stripe DLQ sweeper contract + the webhook-events 30-day-purge job.

**Patterns to follow:**
- `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` — 8-step ordering; registry pattern; DLQ for retry-safe delete.
- `docs/solutions/best-practices/orphan-dlq-symmetry-2026-04-19.md` — pre-record-before-op for DLQ.

**Test scenarios:**
- Happy path — user with stripe_customer_id is deleted; Stripe delete_customer succeeds; no DLQ entry.
- Happy path — user without stripe_customer_id (never purchased): delete completes; no Stripe call.
- Edge case — Stripe delete_customer returns `resource_missing`: treated as success.
- Edge case — Stripe API times out: DLQ entry written; delete flow completes with 204; WARNING logged.
- Edge case — subscription row CASCADEs when users row deletes (already tested pre-feature; regression test re-validates with new columns).
- Edge case — `signup_grants_issued` row for this user's device SURVIVES delete (documented exception).
- Edge case — `users.merged_into_user_id` pointing at the deleted user: FK SET NULL fires; audit column on the survivor is cleared.
- Integration — post-delete, `/v2/entitlement` for a deleted user returns 404.
- Integration — mobile `wipeLocalDeviceState` removes `nxme_install_uuid` from SecureStore (verified by reading after wipe — returns null).

**Verification:**
- `make test`.
- Manual: `DELETE /auth/account` on a Pro user; Stripe dashboard shows customer deleted; `SELECT * FROM signup_grants_issued` for that device shows surviving row.

---

- [ ] **Unit 12: Mobile — `install-uuid.ts`, `paywall-cta.ts`, `entitlement_v2.ts`, paywall copy**

**Goal:** Mobile-side support for install-UUID, paywall CTA matrix, v2 entitlement type, female-targeted copy.

**Requirements:** R6a (mobile), R14/R14a (mobile), R24.

**Dependencies:** Unit 7 (backend shape), Unit 11 (SecureStore key).

**Files:**
- Create: `mobile/lib/install-uuid.ts`
- Create: `mobile/lib/paywall-cta.ts` (pure function + unit tests)
- Create: `mobile/lib/entitlement_v2.ts` (parallel to entitlement.ts; imports from `/v2/entitlement`)
- Modify: `mobile/constants/config.ts` — add `SECURE_STORE_KEYS.INSTALL_UUID = 'nxme_install_uuid'`.
- Modify: `mobile/lib/api.ts` (or auth helpers) — attach `X-Install-UUID` header on auth endpoints.
- Modify: `mobile/components/subscription/PaywallModal.tsx` + `CreditPackGrid.tsx` (or equivalent) — read from `paywall-cta.ts`.
- Test: `mobile/lib/__tests__/paywall-cta.test.ts`, `mobile/lib/__tests__/install-uuid.test.ts`

**Approach:**
- `install-uuid.ts`: `async function getOrCreateInstallUuid(): Promise<string>` — read `SECURE_STORE_KEYS.INSTALL_UUID`; if absent, `randomUUID()` + persist + return.
- `paywall-cta.ts`: pure function mapping `(tier, subscription_status, blocked_reason)` → `PaywallCTA = { primary: {label, action}, secondary?: {label, action} }`. Discriminated union (`type: 'subscribe' | 'buy_pack' | 'update_card' | 'contact_support'`).
- `entitlement_v2.ts`: types mirror `EntitlementStateV2`; `fetchEntitlementV2()` hits `/v2/entitlement`.
- Copy strings for female audience per R24 — dedicated copy file `mobile/copy/paywall.ts` — designer to supply final text during Unit 12 implementation; placeholders acceptable in plan.
- Screen wiring: Phase A — `PaywallModal` reads from `/v2/entitlement` when feature flag `ENTITLEMENT_V2_ENABLED=true`; falls back to `/v1/entitlement` otherwise. Flag flip to always-on lives in Phase B.

**Patterns to follow:**
- `mobile/lib/guest-session.ts` — SecureStore persistence.
- `docs/solutions/best-practices/blocking-auto-save-for-durable-share-urls-2026-04-19.md` — `raceWithTimeout` if mobile makes synchronous calls on paywall open.
- Project memory `feedback_female_user_targeting` — female copy invariant.
- Project memory `feedback_feature_gating_centralized` — `useCapabilities()` for feature flag.

**Test scenarios:**
- Happy path — first app launch generates UUID; second launch reads same UUID.
- Happy path — `paywall-cta.ts` for Free+insufficient_credits returns Subscribe primary / Pack secondary.
- Happy path — `paywall-cta.ts` for Pro+grace+insufficient returns Update-card primary / Pack secondary.
- Happy path — `paywall-cta.ts` for locked returns Contact-support with no secondary.
- Edge case — `paywall-cta.ts` for Free+none returns no-paywall sentinel.
- Edge case — UUID read fails (SecureStore error): regenerates; logs warning in dev.
- Integration — `wipeLocalDeviceState` removes UUID; next launch generates fresh UUID.
- Integration — copy strings pass `feedback_female_user_targeting` review (no beard/male-coded examples).

**Verification:**
- `cd mobile && npx expo lint`.
- `cd mobile && npx jest paywall-cta` — all matrix cells pass.

---

- [ ] **Unit 13: `make stripe-dev` + `.env` bootstrap + runbook**

**Goal:** Single command goes from empty `.env` to working Stripe test-mode loop with session signing secret + seeded test products/prices matching plan_versions.

**Requirements:** R19.

**Dependencies:** Unit 1 (plan_versions seeded).

**Files:**
- Create: `app/services/stripe_dev_bootstrap.py`
- Create: `docs/runbooks/payments.md`
- Modify: `Makefile` — add `stripe-dev` target.
- Modify: `app/.env.example` — add `DEBUG_BEARER_TOKEN`, `SIGNUP_FINGERPRINT_SERVER_SECRET`, `STRIPE_WEBHOOK_SESSION_SECRET` placeholders.
- Modify: `mobile/.env.example` — no new vars (install-UUID is mobile-generated).

**Approach:**
- Makefile target runs `stripe listen --forward-to localhost:8000/v2/webhooks/stripe --skip-verify` and pipes the session secret into a write to `app/.env` (append, not overwrite, with clear marker comments).
- Python bootstrap: for each `plan_versions` row, `Product.create` + `Price.create` via Stripe SDK; write the resulting `stripe_price_id` to `plan_versions` row (new nullable column OR held in app-config; decide in implementation — simplest: write back to plan_versions, add `stripe_price_id TEXT NULL` in Unit 1).
- Print test cards `4242 4242 4242 4242`, `4000 0000 0000 9995` (insufficient funds), `4000 0025 0000 3155` (3DS).
- Runbook covers: dispute simulation via `stripe trigger charge.dispute.created`, grace test (use `stripe listen` + local clock skip), weekly_free_grant manual trigger, fingerprint purge manual trigger, DEBUG_BEARER_TOKEN rotation procedure.

**Patterns to follow:**
- `docs/solutions/runtime-errors/make-nuke-missing-env-path-2026-04-19.md` — Make target error handling.

**Test scenarios:**
- Test expectation: none — `make stripe-dev` is an interactive dev tool; smoke-tested manually per runbook.

**Verification:**
- `make stripe-dev` on a fresh checkout produces working `.env` + seeded Stripe products.
- `docs/runbooks/payments.md` walks a new contributor end-to-end in <15 minutes.

---

- [ ] **Unit 14: `/v1/__debug/entitlement/{user_id}` with Vault-backed bearer token**

**Goal:** Dev + staging debug endpoint returning the full decision trace.

**Requirements:** R22.

**Dependencies:** Unit 7.

**Files:**
- Create: `app/api/debug_entitlement.py`
- Modify: `app/main.py` — conditional mount (`if settings.APP_ENV != 'prod'`).
- Modify: `app/config/__init__.py` — add `DEBUG_BEARER_TOKEN` (no fallback), `DEBUG_INCLUDE_CUSTOMER_ID` (default False).
- Test: `tests/test_debug_entitlement_endpoint.py`

**Approach:**
- Startup assertion in `main.py`: `if settings.APP_ENV == 'prod': do not include router`.
- Per-request check: `assert settings.APP_ENV != 'prod'`; return 404 otherwise (defence in depth).
- Bearer token check: `hmac.compare_digest(request.headers.get('X-Debug-Token', ''), settings.DEBUG_BEARER_TOKEN)`. Invalid → 401. Empty token env var → fail-fast at boot.
- **IP allowlist** (security review MEDIUM fix — blast-radius reduction). Env `DEBUG_ENDPOINT_IP_ALLOWLIST` = comma-separated CIDRs (operator LAN + office egress). Request is 403'd if `request.client.host` is outside the allowlist. Empty env var → empty list → all requests rejected (fail-closed). Documented in Risk table.
- **Per-IP request rate limit** (security review MEDIUM fix). Redis-backed: max 60 requests / 5 minutes per source IP, 429 with Retry-After. Reuses `app/services/rate_limiter.py` pattern.
- `customer_id` redaction: omit unless `DEBUG_INCLUDE_CUSTOMER_ID=true` AND `?include_customer_id=true` query param.
- Log every access: token hash (sha256 truncated) + target user_id + requesting IP + timestamp.
- Response shape: `{user, subscription_row, recent_ledger_entries (last 20), recent_webhook_events (last 10), derivation_path: [{step, result}]}`. Drift-buffer field removed (R14b deferred to v1.1).

**Patterns to follow:**
- Supabase Vault-backed env var pattern — staging deployment config loads `DEBUG_BEARER_TOKEN` from Vault at boot.
- `app/api/middleware/auth.py` — header extraction.

**Test scenarios:**
- Happy path — valid token + allowlisted IP returns full trace.
- Happy path — `?include_customer_id=true` with env flag on exposes customer_id.
- Edge case — `?include_customer_id=true` with env flag OFF still redacts.
- Edge case — request from non-allowlisted IP → 403 regardless of token validity.
- Edge case — empty `DEBUG_ENDPOINT_IP_ALLOWLIST` env → all requests 403 (fail-closed).
- Edge case — 61st request from same IP within 5 minutes → 429 with Retry-After.
- Error path — invalid token → 401.
- Error path — `APP_ENV=prod` at startup → route not mounted; request returns 404.
- Error path — missing `DEBUG_BEARER_TOKEN` at boot → startup crash.
- Integration — access log entry written per call (token hash + user_id + IP + timestamp).

**Verification:**
- `curl -H 'X-Debug-Token: <staging-token>' /v1/__debug/entitlement/<user-id>` returns trace.
- `curl` with wrong token returns 401.
- `APP_ENV=prod` CI test asserts route is not mounted.

---

### Phase A Checkpoint

- [ ] All Phase A units (1–14) merged to dev.
- [ ] `make format && make lint && make test` passes clean.
- [ ] `cd mobile && npx expo lint` passes clean.
- [ ] `git diff HEAD~<count> -- app/api/entitlement.py app/api/webhooks.py app/entitlement/service.py` shows **zero net changes** (the shared trio untouched — Phase A acceptance).
- [ ] Bug-fix agent has merged their work on the shared trio.
- [ ] Product + design have approved paywall copy per R24.
- [ ] Legal has signed off on `signup_grants_issued` GDPR treatment.

### Phase B — Destructive cutover (migrations 0053+ range assigned at flip time; see Risks)

- [ ] **Unit 15: Flip writers — webhook handlers write dates, not statuses**

**Goal:** Rewrite `app/api/webhooks.py::_handle_payment_failed` to write `grace_until` instead of `status='past_due'`; rewrite `_handle_subscription_deleted` to write `cancelled_at` instead of `status='expired'`. Drop /v2/webhooks/stripe mount (v2 behaviour folded into /webhooks/stripe); delete `app/api/webhooks_v2.py`.

**Requirements:** R23 Phase B.

**Dependencies:** Phase A checkpoint; bug-fix agent merged.

**Files:**
- Modify: `app/api/webhooks.py`
- Delete: `app/api/webhooks_v2.py` (or keep as alias; prefer delete for single-writer invariant)
- Modify: `app/main.py`
- Test: `tests/test_webhooks_writer_cutover.py`

**Approach:** Merge the `webhooks_v2.py` logic into `webhooks.py`; the legacy entry-points become the new entry-points; tests migrate from `test_webhooks_v2_*` to `test_webhooks_*`.

**Test scenarios:**
- Happy path — `invoice.payment_failed` writes `grace_until`, not `status='past_due'`.
- Happy path — `customer.subscription.deleted` writes `cancelled_at`, not `status='expired'`.
- Integration — end-to-end webhook events still satisfy idempotency + out-of-order + <5s budget.

**Verification:** `make test`; manual `stripe trigger` for each event type.

---

- [ ] **Unit 16: Flip readers — fold `service_v2.py` into `service.py`; retire `/v2` prefix**

**Goal:** Replace `EntitlementService` with the v2 implementation in place; update `app/api/entitlement.py` to return the v2 shape; delete `service_v2.py` and `entitlement_v2.py`; mobile switches to `/v1/entitlement` (now serving v2 shape).

**Requirements:** R23 Phase B.

**Dependencies:** Unit 15.

**Files:**
- Modify: `app/entitlement/service.py`
- Modify: `app/api/entitlement.py`
- Delete: `app/entitlement/service_v2.py`, `app/api/entitlement_v2.py`
- Modify: `mobile/lib/entitlement.ts` — adopt v2 shape in-place; delete `mobile/lib/entitlement_v2.ts`; delete the feature flag.
- Test: `tests/test_entitlement_reader_cutover.py`

**Approach:** `service.py` becomes the v2 implementation with the old type-aliases renamed. Mobile callsites that used the feature-flag branch now read unconditionally from `/v1/entitlement`.

**Test scenarios:**
- All existing `/v1/entitlement` tests pass with v2 shape.
- Integration — no mobile callsite still imports from `entitlement_v2.ts`.

**Verification:** `make test`; `cd mobile && npx expo lint`; grep confirms no orphan `_v2` imports.

---

- [ ] **Unit 17: Flip RPC callers — every `credit_reserve/release/commit/refund` call becomes `_v2`**

**Goal:** Update `app/entitlement/ledger.py` + `app/generation/worker.py::_fail_job` + `app/api/refund.py` + any other callers to use `_v2` RPCs with action types.

**Requirements:** R23 Phase B.

**Dependencies:** Unit 15, Unit 16.

**Files:**
- Modify: `app/entitlement/ledger.py` — swap all RPC names to `_v2`; accept `action_type` in `reserve()`.
- Modify: `app/generation/worker.py` — already uses `ledger.commit/release/refund` which are signature-compatible; no caller-side change beyond the `reserve` call site (which lives at the API layer, not the worker).
- Modify: `app/api/generation.py` (or wherever generation's `reserve` is called) — pass `action_type='glowup'`.
- Modify: `app/advisor/` (wherever Ada messages reserve credit) — pass `action_type='ada_message'`.
- Test: `tests/test_ledger_v2_call_sites.py`

**Approach:** Straight substitution; tests assert every call site supplies an action_type.

**Test scenarios:**
- Happy path — glowup generation path calls `credit_reserve_v2(..., 'glowup')`.
- Happy path — Ada message path calls `credit_reserve_v2(..., 'ada_message')`.
- Error path — any legacy call site missed → test fails (grep-based test).

**Verification:** `make test`; grep for `credit_reserve(` without `_v2` suffix returns zero non-migration results.

---

- [ ] **Unit 18: Drop legacy schema — `tiers`, `trial_analyses_remaining`, `usage_events`, status enum values, old RPCs**

**Goal:** Destructive migration dropping the three parallel systems.

**Requirements:** R23 Phase B.

**Dependencies:** Unit 15, Unit 16, Unit 17; concurrent bug-fix agent merged.

**Files:**
- Create: `app/migrations/0054_drop_legacy_payments.sql` (or whichever number is next free post-bug-fix-agent-merge).
- Delete: `app/constants/tiers.py` + `app/config/tiers.py` + `app/entitlement/tier_repo.py`.
- Modify: many callsites that import tier constants — replace with plan_version lookups.

**Approach:**
- DROP TABLE `tiers`, `usage_events`.
- ALTER TABLE `users` DROP COLUMN `tier_id`, DROP COLUMN `trial_analyses_remaining`.
- DROP the `status` CHECK values for `past_due` and `expired` via DROP+ADD pattern.
- DROP FUNCTION `credit_reserve`, `credit_release`, `credit_commit`, `credit_refund`, `handle_checkout_credit_atomic`.
- `credit_reservations` STAYS per R4 — the reserve→commit/release primitive is preserved.
- Existing `trial_analyses_remaining` callers must all be flipped to ledger reads before this migration runs.

**Test scenarios:**
- Happy path — migration applies cleanly; post-migration queries against dropped objects fail.
- Error path — migration rejected if any table still has `tier_id` column references (tested via schema introspection).

**Verification:** `make migrate` on seeded dev DB; no callers reference the dropped objects.

---

### Phase B Checkpoint

- [ ] All Phase B units (15–18) merged.
- [ ] Full verification loop passes (`make format && make lint && make test && cd mobile && npx expo lint`).
- [ ] Integration: end-to-end flow — new signup → signup grant → glow-up reserve → commit → monthly allotment REPLACE → dispute lock → unlock — all ledger-only; no references to tiers table; no references to trial_analyses_remaining.
- [ ] Operator runbook updated with post-cutover procedures.

## System-Wide Impact

- **Interaction graph:**
  - `EntitlementServiceV2` replaces tier-based gating; every route previously using `EntitlementService.check(user_id, action)` must adopt the v2 shape in Phase B.
  - Generation worker (`app/generation/worker.py::_fail_job`) relies on `ledger.release/commit/refund` being signature-compatible — Unit 17 validates.
  - `useCapabilities()` (mobile) reads from `/v1/entitlement`; switchover in Phase B is transparent if shape lands cleanly.
  - `require_app_feature()` (backend) is orthogonal — feature gating stays; quota gating replaces tier gating.
  - Concurrent-generation Lua counter (`concurrent:{user_id}` Redis key) is orthogonal and preserved.
- **Error propagation:**
  - `InsufficientCredits` (P0001) and `AccountLocked` (P0002) are the two new typed errors from `_v2` RPCs. API layer maps to HTTP 402 (`INSUFFICIENT_CREDITS`) and HTTP 423 (`ACCOUNT_LOCKED`) respectively. Mobile maps to paywall CTA matrix.
  - Webhook handler errors: transient → 5xx + Stripe retry; permanent → 200 + log + discard (R18 72h ceiling).
  - Out-of-order subscription events → HTTP 5xx → Stripe retry backoff handles recovery (no ARQ retry worker in v1 per scope review).
  - Out-of-order dispute events → CAS on `dispute_last_event_at` rejects older arrivals → HTTP 5xx → Stripe retry.
- **State lifecycle risks:**
  - REPLACE audit trail must be two-entry to preserve forensic reconstruction — if implemented as single net delta, a reviewer cannot distinguish "nothing happened" from "discarded 2500, granted 3000".
  - Dispute-lock during in-flight reserve is a double-loss hazard — mitigated by `credit_commit_v2` checking `locked_at` under the same advisory lock and converting commit→release if newly locked (per R4).
  - Out-of-order webhooks during busy billing-period boundary could race with `get_entitlement` drift buffer — buffer trusts authoritative fetch, so worst case is one user sees a briefly stale label (recovers within 1 hour).
- **API surface parity:**
  - `/v1/entitlement` (legacy) and `/v2/entitlement` (new) coexist during Phase A; mobile feature-flags between them. Phase B folds `/v2` back into `/v1`.
  - `/webhooks/stripe` (legacy) and `/v2/webhooks/stripe` (new) coexist; Stripe Dashboard endpoint config flips to `/v2` when ready; Phase B folds back.
- **Integration coverage:**
  - Full webhook-event → ledger-entry chain must be integration-tested per event type (`tests/fixtures/stripe/*.json` + `tests/test_webhooks_v2_*`). Mocks alone cannot prove idempotency or out-of-order behaviour.
  - Mobile PaymentSheet flow requires a real Stripe test key end-to-end once per phase to confirm server-side webhook → ledger → entitlement chain.
  - Dispute simulation via `stripe trigger charge.dispute.created` against /v2 adapter.
- **Unchanged invariants:**
  - `credit_reservations` table stays (R4); the reserve→commit/release primitive is not changed.
  - `processed_webhook_events` idempotency primitive is reused, not replaced.
  - `feedback_delete_account_scope` enforcement — every new surface wired into delete_account (signup_grants_issued is the documented exception).
  - Guest-first-class invariant (`feedback_guest_first_class`) — every new surface works for guests except account-mutation signup grants + merges.
  - Cursor-based pagination (`feedback_cursor_pagination`) — no new paginated endpoints.
  - Infinite-scroll UI (`feedback_infinite_scroll`) — no new list UIs.

## Risks & Dependencies

### Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Legal review on `signup_grants_issued` returns blocking concerns (GDPR Art. 4(5) pseudonymization + Art. 17 erasure)** | Medium | High (blocks all Phase A migration merges) | **Blocking gate — 0048 cannot merge without legal sign-off.** Bring the design to legal on day 1 of Phase A. If blocked, fallback options in ranked order: (a) shorter TTL (e.g., 6 months); (b) hash scheme change (drop HMAC, keep only salted hash + lookup-via-scan at signup — slower but rainbow-table-proof and no server secret); (c) drop fingerprinting entirely and accept CAC loss. Record resolution in `docs/runbooks/payments.md`. |
| **Concurrent bug-fix agent merges conflicting changes to the shared trio** | Medium | High (Phase B flip becomes ugly) | Phase A makes **zero changes** to shared trio (acceptance criterion). Sync before every Phase B unit merges. Rebase-resolve strategy: Phase B keeps our writer logic since writers must flip; reader flips are mechanical |
| **Stripe event-delivery jitter exceeds 1-hour R14b buffer** | Low | Medium (brief mislabel windows) | Emit `entitlement_drift_buffer_hit` metric post-launch; widen buffer if observed tail > 1h. Acceptance post-launch, not pre-launch |
| **Fingerprint false-negative (reinstall after 12 months) grants a second signup grant** | High (by design) | Low | Accepted — 12-month TTL is intentional. Monitor volumetrics post-launch |
| **Fingerprint false-positive (shared family device) blocks a legitimate new account's signup grant** | Low | Medium (CAC hit for that user) | Accepted at pre-launch scale. User still receives weekly_free_grant on the new account |
| **REPLACE on monthly renewal discards pack credits by accident (bug in query)** | Medium | High (angry paying customers) | `credit_apply_monthly_allotment_v2` RPC body EXCLUDES `type='credit_pack_purchase'` in the balance computation; integration test asserts pack entries survive REPLACE; code-reviewed with explicit adversarial-tester focus |
| **Out-of-order ARQ retry burns Stripe API rate limit** | Low | Low | 5-attempt WARN ceiling per `orphan-dlq-symmetry-2026-04-19` + circuit breaker already in `app/generation/cost_tracker.py` (reuse the pattern) |
| **Inline webhook handler exceeds 5s budget on busy host** | Low | High (Stripe resends + duplicate risk) | Latency metric + alert at 3s; inline handler must never call Stripe API (only `retrieve_subscription` is called, and only from ARQ). Monitored post-launch |
| **Phase B merge drops legacy rows before a caller is flipped** | Medium | High (prod crashes on missing column) | Unit 18 migration runs a "any caller still references tier_id?" grep test as a pre-check; Unit 17 validates every `credit_*` call has `_v2`; phased delivery with a 48h burn-in on Phase A before starting Phase B |
| **DEBUG_BEARER_TOKEN leakage in staging logs** | Medium | Medium | hmac.compare_digest check; log hash-truncated token only; 90-day rotation + staff-change rotation; Vault-backed storage |
| **Installation-UUID not sent by older mobile builds** | High | Low | Backend accepts NULL header (grants without fingerprint, per R6a web-signup rules). Covered by test |
| **Stripe customer DLQ grows unboundedly** | Low | Medium | Nightly reconciler calls `payment.delete_customer` on each DLQ row with 5-attempt WARN |
| **Mobile install-UUID regeneration on corruption double-grants** | Low | Low | If device generates a second UUID post-deletion, the device's original `deterministic_hash` is distinct, so a legitimate signup-grant fires. Monitored post-launch |
| **Guest merge cap incorrectly caps pack credits** | Low | Medium | RPC unit test exercises guest with 1000-milli pack: verifies pack pathway bypasses cap |
| **Guest-session-token theft drains victim pack credits at merge time** (security review HIGH) | Medium | High | Install-UUID binding: guest creation records `guest_install_uuid_hash`; merge rejects on mismatch with 403. Covered by test in Unit 10 |
| **Dispute event reordering locks user permanently** (security review CRITICAL) | Medium | High | CAS state machine on `dispute_last_event_at` (Unit 4); any out-of-order dispute event returns HTTP 5xx; Stripe retries establish correct final state |
| **`SIGNUP_FINGERPRINT_SERVER_SECRET` rotation silently disables abuse prevention** (security review HIGH) | Low | Medium | Rotation protocol in runbook: comma-separated primary+secondary env, background re-derive job, flip once complete. Planned rotations only. Documented in Unit 6 |
| **`X-Install-UUID` header leaked in access logs → table re-linking** (security review MEDIUM) | Medium | Medium | Add `X-Install-UUID` to logging middleware header-scrub list (Unit 8a). Verified via test |
| **DEBUG endpoint shared bearer + leak → read any user's ledger** (security review MEDIUM) | Low | High | IP allowlist (CIDR list env, fail-closed on empty) + per-IP 60-req/5min rate limit (Unit 14). 90-day + staff-change token rotation |
| **5s webhook budget slips on `charge.dispute.created` fallback Stripe Customer.search** (adversarial P1) | Low | High | One-shot `stripe_customer_id` backfill in Unit 1 pre-seeds the column for all existing users; eliminates the fallback-search path on the hot webhook path |
| **`processed_webhook_events` payload carries Stripe customer_id / email indefinitely** (adversarial P2) | Medium | Medium | Nightly `purge_old_webhook_events` ARQ job deletes events >30 days old; documented in Unit 11 |
| **In-flight credit reservation or ARQ job orphans a deleted account** (adversarial P2) | Low | Medium | Delete-account ordering adds step 1.5 (drain reservations via `credit_release_v2`) + step 1.6 (abort known ARQ job prefixes). Best-effort; downstream jobs 404-log-warn gracefully |

### Dependencies

- **Stripe test key** obtained this cycle (confirmed by user).
- **Supabase Vault access** for DEBUG_BEARER_TOKEN on staging (confirm with infra).
- **Bug-fix agent merge** is a prerequisite for Phase B; Phase A is independent.
- **Legal review** of signup_grants_issued GDPR posture is a prerequisite for **0052** merge only (Phase A feasibility review fix — 0048 no longer bundles the legal-gated table).
- **Designer-supplied female-targeted copy** for paywall CTA strings (Unit 12).
- **Existing infrastructure:** `processed_webhook_events` (R18), `credit_reservations` + advisory-lock pattern (R4), `guest_session_token` on users row (R16), CASCADE on subscriptions + credit_ledger + credit_reservations (R17), RLS deny-all pattern (Unit 1 applies), SECURE_STORE_KEYS registry (Unit 11).

### Migration-number collision protocol

The bug-fix agent holds 0053+; this plan holds 0048–0052. If the agent merges 0048 first (collision), the migration runner rejects; no race is silent. Resolution: both agents check `ls app/migrations/` before rebasing their PR, renumber to the next free slot, and update any file-number references (there are none in our plan — all dependencies are by object name, not file number). Announce slot changes in the shared chat before the rebase commit. Two-phase migration numbering for Phase B waits until bug-fix merges; Phase B takes the next free range at flip time.

## Phased Delivery

### Phase A — Additive landing (concurrent-safe)

Units 1 → 14. Order matters for schema dependencies: 1 before 2 before 3/4 before 5/6 before 7/8/9/10/11/12/13/14. Units 5, 6, 12, 13, 14 can land in parallel once their schema dependencies are in. Unit 11 waits for 1+5. 48-hour burn-in before Phase B starts — monitor webhook latency metric, fingerprint purge job, weekly_free_grant job, drift-buffer hit rate.

### Phase B — Destructive cutover (post bug-fix-agent merge)

Units 15 → 16 → 17 → 18 strictly in order. No overlap with Phase A. Landing cadence: one PR per unit, separate merges (atomic per flip).

## Documentation Plan

- `docs/runbooks/payments.md` — new. Covers:
  - `make stripe-dev` workflow.
  - Dispute simulation via `stripe trigger`.
  - Grace-expiry test procedure.
  - DEBUG_BEARER_TOKEN rotation.
  - Fingerprint purge manual trigger.
  - DLQ reconciler manual trigger.
  - Operator procedures for grandfathering (direct-DB plan_version assignment).
- `docs/solutions/best-practices/` — new solution docs after launch for any novel patterns that emerge (e.g., webhook-inline-with-enqueued-retry, if it proves robust).
- `app/.env.example` + `mobile/.env.example` updated inline with code changes.
- `CLAUDE.md` unchanged — the plan respects existing conventions.
- Project memory: add an entry confirming the `signup_grants_issued` exception to `feedback_delete_account_scope` post-merge (record in MEMORY.md via the auto-memory system).

## Operational / Rollout Notes

- **Feature flag** `ENTITLEMENT_V2_ENABLED` gates mobile's switch from `/v1` to `/v2` during Phase A. Default off; enabled in dev/staging for testing; flipped on in Phase B Unit 16.
- **Monitoring post-launch:**
  - Webhook handler latency p50/p95/p99 (alert at p99 > 3000ms).
  - Drift-buffer hit rate (alert if > 5% of entitlement reads).
  - Stripe DLQ growth (alert if > 10 entries pending).
  - Weekly_free_grant job duration (alert on failure).
  - Fingerprint table size (monitor growth vs 12-month TTL).
  - `credit_ledger` monthly totals vs Stripe-reported revenue (reconciliation).
- **Rollback procedure for Phase A:** revert the PR — migrations roll forward only (no DOWN), but adding columns and tables is benign. If Unit 7/8/12/14 need to come out, disable feature flag first, then revert.
- **Rollback procedure for Phase B:** Phase B drops legacy; rollback means re-creating `tiers` + `trial_analyses_remaining` + `usage_events` from backup. Pre-launch timing means acceptable; post-launch this would require a data migration. Do NOT start Phase B unless confident.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-19-payments-credits-only-requirements.md](../brainstorms/2026-04-19-payments-credits-only-requirements.md)
- **Ideation:** [docs/ideation/2026-04-19-payments-subscription-review-ideation.md](../ideation/2026-04-19-payments-subscription-review-ideation.md)
- **Code anchors:**
  - `app/api/entitlement.py`
  - `app/api/webhooks.py`
  - `app/entitlement/service.py`
  - `app/entitlement/ledger.py`
  - `app/payment/ports.py`, `app/payment/adapters/stripe_adapter.py`
  - `app/generation/worker.py::_fail_job`
  - `app/repositories/subscription_repo.py`
  - `app/migrations/0014_credit_ledger_rpcs.sql`, `0019_credit_reserve_advisory_lock.sql`, `0021_security_definer_search_path.sql`, `0029_credit_refund_rpc.sql`, `0044_hard_delete_account.sql`, `0045_delete_account_cascade_completeness.sql`
  - `app/db/guest.py`
  - `app/api/auth.py::delete_account`
  - `mobile/lib/entitlement.ts`, `mobile/lib/hooks/use-purchase-flow.ts`, `mobile/lib/account-wipe.ts`, `mobile/constants/config.ts`
- **Institutional learnings:**
  - `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md`
  - `docs/solutions/best-practices/partial-unique-index-for-republish-after-soft-delete-2026-04-19.md`
  - `docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md`
  - `docs/solutions/best-practices/orphan-dlq-symmetry-2026-04-19.md`
  - `docs/solutions/best-practices/blocking-auto-save-for-durable-share-urls-2026-04-19.md`
- **External references:**
  - Stripe CLI `stripe listen` session signing secret.
  - Stripe Smart Retries default window.
  - Stigg out-of-order event-re-fetch pattern.
  - Harry's Engineering atomic UPDATE RETURNING (considered, rejected — preserves reserve/commit/release for fal.ai auto-refund).
- **Project memory:** `feedback_pre_launch_destructive_ok`, `feedback_delete_account_scope`, `feedback_feature_gating_centralized`, `feedback_female_user_targeting`, `feedback_guest_first_class`, `feedback_no_env_fallbacks`, `feedback_no_hardcoded_urls`, `feedback_verify_before_claiming_fixed`.
