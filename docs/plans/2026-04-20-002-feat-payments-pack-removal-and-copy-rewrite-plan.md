---
title: "feat(payments): pack SKU removal + \"unlimited\" copy rewrite + weekly-regen flag gating"
type: feat
status: active
date: 2026-04-20
origin: docs/brainstorms/2026-04-19-payments-credits-only-requirements.md
supersedes-in: docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md
---

# feat(payments): pack SKU removal + Pro cap copy + weekly-regen flag gating

## Overview

Three coupled cleanups that ship as one PR sequence because they share surfaces (paywall, constants, capabilities):

1. **Pack rip** — delete the credit pack SKU from every surface (DB, backend, mobile, tests).
2. **Unlimited copy rip** — replace every user-facing "unlimited" string with the concrete Pro cap (30 glow-ups/mo + ~200 Ada msgs shared pool, $9.99/mo). Promote the numbers to constants + a `plan_versions` row. Add a CI grep gate so "unlimited" cannot regress.
3. **Weekly-regen flag gating** — surface the existing `app_kill_switches.weekly_free_grant` kill-switch through the capabilities module so mobile can conditionally render the "+ 1 free glow-up every week" line.
4. **Plan doc sync** — retro-update `docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md` so its unit list matches reality (pack units deleted, new copy + capabilities units added).

Pre-launch destructive policy (napkin #3) applies: deletions happen in place, no deprecation shims, no legacy RPCs or enum values left behind.

## Problem Frame

- The credits-only brainstorm shipped with a `credit_pack_purchase` SKU as a secondary paid option. Product direction changed 2026-04-20 — Pro subscription is the only paid SKU at launch. Pack code still lives across ~10 files (migrations, webhook branch, mobile components, tests, constants).
- Mobile calls Pro "Unlimited" in three places despite R7's REPLACE semantic (3000 milli = 30 glow-ups/mo). `app/services/limits.py:11` also carries a legacy `UNLIMITED = "unlimited"` tier-enum residue from the pre-credits-only design.
- `ADA_COST_MILLI = 5` from the original brainstorm was underwater on Claude inference cost (~600 msgs/mo × $0.02 > $9.99). Revised to `15` (~200 msgs/mo, ~50% gross margin at a realistic 20-gen + 60-Ada mix).
- `app_kill_switches.weekly_free_grant` already exists (migration 0057 + `app/runtime_flags.py` + `scripts/kill-switch.sh`). When the cron is paused, the UI still promises "+1/week" — false promise.

## Requirements Trace

Origin: `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md`

- **R-Pack-Removal** — delete the pack SKU; no legacy enum value, no dormant code.
- **R-Pro-Copy** — ban "unlimited"; name constants; enforce via CI grep.
- **R-Weekly-Regen-Flag-Gated** — conditional copy via capabilities module.
- Locked numbers (resolved Outstanding Question, 2026-04-20):
  - `SIGNUP_GRANT_MILLI = 300` (3 glow-ups) — already live.
  - `WEEKLY_FREE_GRANT_MILLI = 100` — already live.
  - `MONTHLY_ALLOTMENT_MILLI = 3000` (30 glow-ups/mo).
  - `GLOWUP_COST_MILLI = 100`.
  - `ADA_COST_MILLI = 15` (revised from 5).
  - `PRO_MONTHLY_PRICE_USD = "$9.99"`.

## Scope Boundaries

- Pack SKU will not be reintroduced in v1. Any re-add is a fresh requirement + plan.
- Rollover of unused monthly allotment — NO (baseline R7 REPLACE stands).
- The mobile "next refill on {date}" empty-state CTA is in scope as the replacement for the pack CTA in the pack-slot matrix.
- Grandfathering (R12) is unchanged: changing `ADA_COST_MILLI` creates a new `plan_versions` row; existing subscribers stay bound to their original row.
- `R22` debug endpoint and R21 fixture pipeline — out of scope.

## Units

Land in the order below. Each unit is one PR. No batching across units (each has its own verification surface).

### Unit 1 — Pack SKU removal

**Files touched:**

Backend:
- `app/api/webhooks.py` — remove the pack branch from `_handle_payment_intent_succeeded` and any sibling pack handlers (search for `credit_pack_purchase`, `call_credit_apply_pack_purchase`, `flow=payment_sheet` pack branches). Keep the subscription branches intact.
- `app/services/stripe_dev_bootstrap.py` — remove pack Product/Price seeding; keep Pro subscription seeding.
- `app/config/__init__.py` + `app/.env.example` — remove any `CREDIT_PACK_*`, `PACK_PRICE_CENTS`, `CREDIT_PACK_V1_CREDITS_MILLI`, `PACK_STRIPE_PRICE_ID` constants.
- `app/repositories/subscription_repo.py` — remove `call_credit_apply_pack_purchase` if present, or the methods that only pack needed.

Migrations (pre-launch destructive, in place):
- New migration `0058_remove_credit_pack_artifacts.sql`:
  - Drop the `credit_apply_pack_purchase` RPC.
  - Drop the `idx_credit_ledger_pack_ref` partial UNIQUE index.
  - `ALTER TABLE credit_ledger DROP CONSTRAINT` + `ADD CONSTRAINT` to narrow the `type` CHECK enum: remove `credit_pack_purchase`.
  - Proper `-- DOWN:` section recreating the dropped surface.
- `0050_credit_grants_and_allotment_rpcs.sql` — do NOT edit in place (it is already applied in every dev/staging DB). The 0058 drop is the canonical source of pack absence.

Mobile:
- `mobile/components/subscription/CreditPackGrid.tsx` — delete.
- `mobile/components/paywall/CreditPackCard.tsx` — delete.
- `mobile/components/paywall/PaywallModal.tsx` — remove the pack slot; update the CTA matrix so (Pro-active + insufficient) shows "next refill on {date}" (no purchase CTA).
- `mobile/lib/hooks/use-purchase-flow.ts` — remove the `purchasePack` / `CreditPack` branches; keep Pro subscription paths.
- `mobile/app/subscription.tsx` — remove pack grid references.
- `mobile/constants/premium-benefits.ts` — remove pack bullets (if any).

Tests:
- `tests/test_webhooks_packs.py` — delete.
- `tests/test_credit_purchases_intent.py` — delete (or slice to Pro-only if it covers shared surface; confirm before deleting).
- `tests/test_plan_versions.py` — remove any pack-schema assertions.

**Verification:**
- `rg -i "credit_pack|pack_purchase|creditPack|PACK_SKU|CreditPackCard|CreditPackGrid" app mobile card-web tests` returns zero hits in live code. Historical references in `docs/brainstorms/*` are acceptable (already marked SUPERSEDED).
- `make format && make lint && make test` clean.
- `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false` clean.
- Fresh DB reset (`docker compose down -v && make up`) applies 0058 without error and `credit_ledger.type` CHECK no longer lists `credit_pack_purchase`.

### Unit 2 — "Unlimited" copy rewrite + constants + CI grep gate

**Backend constants** (`app/config/__init__.py`):
- Add `MONTHLY_ALLOTMENT_MILLI: int = 3000`.
- Add `GLOWUP_COST_MILLI: int = 100`.
- Add `ADA_COST_MILLI: int = 15`.
- Add `PRO_MONTHLY_PRICE_USD: str = "$9.99"` (mirrors the Stripe Price object). Pull from env if set.
- Update `app/.env.example` with the new keys.

**Backend cleanup:**
- `app/services/limits.py:11` — delete `UNLIMITED = "unlimited"` tier-enum residue. The module itself is legacy pre-credits-only; if the entire module is dead after this delete, remove it (grep consumers first).

**Mobile constants** (`mobile/constants/premium-benefits.ts` or a new `mobile/constants/pricing.ts`):
- `PRO_MONTHLY_GLOWUPS = 30` — derived from backend entitlement response where possible; hardcoded constant is the fallback for pre-auth paywall rendering.
- `PRO_MONTHLY_ADA_APPROX = 200`.
- `FREE_SIGNUP_GLOWUPS = 3`.
- `PRO_MONTHLY_PRICE_USD = "$9.99"`.

**Mobile copy rewrites:**
- `mobile/copy/paywall.ts:48` — replace `"Go Pro for unlimited looks, or grab a credit pack to get started."` with a template that concatenates the Free line + Pro line. Free line conditional on Unit 3's capabilities flag (see below).
- `mobile/constants/premium-benefits.ts:3` — replace `"Unlimited glow-up analyses"` with `"${PRO_MONTHLY_GLOWUPS} glow-ups every month"` and add `"Shared with Ada — about ${PRO_MONTHLY_ADA_APPROX} advisor messages"`.
- `mobile/components/subscription/PremiumUpsell.tsx:88` — replace `"Go Unlimited"` CTA label with `"Go Pro"`.
- Review `mobile/copy/` and `mobile/components/paywall/` for any other "Unlimited" strings discovered during implementation; each must be replaced with the concrete cap, never silently dropped.

**CI grep gate** (new Makefile target + GitHub Actions step):
- Add `make copy-lint`:
  ```makefile
  copy-lint:
  	@echo "Scanning for banned marketing copy…"
  	@! rg -i "unlimited" mobile/ app/ card-web/ --glob '!**/node_modules/**' --glob '!**/*.test.*' --glob '!docs/**'
  ```
- Wire into `.github/workflows/ci.yml` (or the existing lint job) so PRs fail when a new "unlimited" lands.

**Female-first audit (R24):** every rewrite reads as female-first copy (`feedback_female_user_targeting`). No male/beard-coded example.

**Verification:**
- `make copy-lint` passes.
- `rg -i "unlimited" app mobile card-web` returns zero hits outside `docs/` and tests.
- Manual paywall screenshot on sim: confirm "Go Pro — 30 glow-ups a month" copy visible.
- `cd mobile && npm test` clean.

### Unit 3 — Capabilities field for `weekly_free_grant_enabled`

**Backend:**
- Add `weekly_free_grant_enabled: bool` to the `GET /v1/features` response (the capabilities-module response, per napkin rule "feature gating only via the capabilities module"). Value = `NOT is_kill_switch_enabled("weekly_free_grant")` — i.e., TRUE when the regen cron is live.
- The backing read happens at `app/runtime_flags.py::is_kill_switch_enabled("weekly_free_grant")`. Pass through a single DB query per request (no caching in v1; capabilities endpoint is already called infrequently).
- Schema file: update the Pydantic model for `/v1/features` response.

**Mobile:**
- `mobile/lib/capabilities.ts` (or wherever `useCapabilities()` lives) — add `weekly_free_grant_enabled` to the context shape.
- `mobile/copy/paywall.ts` — Free copy becomes:
  - When `weekly_free_grant_enabled === true`: `"Free: ${FREE_SIGNUP_GLOWUPS} to start + 1 free glow-up every week."`
  - When `false` OR `undefined`: `"Free: ${FREE_SIGNUP_GLOWUPS} to start."` (no regen line).
- Empty-state copy for balance-zero (if the screen already renders a next-refill hint) — same conditional.
- **No env fallbacks** (napkin user-directive #2): if the capabilities field is missing, treat as `false` (hide regen line). Do NOT default to true.

**Tests:**
- Backend unit test: toggle `app_kill_switches.weekly_free_grant` → `GET /v1/features` response flips `weekly_free_grant_enabled`.
- Mobile: snapshot (or Jest RTL) test rendering paywall copy in both flag states.

**Verification:**
- `make test` + `cd mobile && npm test -- --runInBand --watchman=false` clean.
- Manual: flip switch via `make kill-switch-pause` / `kill-switch-resume`; paywall copy updates on next app launch.

### Unit 4 — Plan doc `2026-04-19-002` synchronization

- Mark all pack-related units in `docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md` as `[SUPERSEDED 2026-04-20 — DELETED]` with a pointer back to this plan.
- Add references at the unit-index level to Units 1-3 of this plan so a reader of 2026-04-19-002 sees the diff.
- Do NOT retro-edit unit bodies — the SUPERSEDED header is enough.

## Shared decisions

- **Branch naming per unit:** `feat/unit-1-pack-rip`, `feat/unit-2-pro-copy`, `feat/unit-3-weekly-regen-cap`, `docs/unit-4-plan-sync`.
- **Merge order:** Unit 1 → Unit 2 → Unit 3 → Unit 4. Unit 2's copy template depends on Unit 3's capabilities field (hence Unit 2 ships the unconditional "Go Pro — 30/mo" Pro copy first; the Free-line conditional lands in Unit 3's mobile edits).
- **Grandfathering posture:** `plan_versions` row(s) seeded in Unit 2's migration carry the final numbers. Any future `ADA_COST_MILLI` change creates a NEW row; existing subscribers stay bound to the row they originally subscribed to (R12).
- **Commit hygiene:** each unit is one PR with a single logical change (one commit or tight series). No cross-unit bundles.

## Verification Loop (per unit)

Before merging any unit's PR:

1. `make format` — auto-fix formatting.
2. `make lint` — ruff clean.
3. `make test` — pytest clean.
4. `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false` — mobile clean.
5. Manual screenshot check for any UI surface touched by the unit (iOS simulator). Confirm the copy/feature behaves in both flag states where applicable.
6. Fresh DB reset (Units 1 + 3) — `docker compose down -v && make up`; confirm migrations apply cleanly and the expected DB shape is in place.

## Risk & Rollback

- **Unit 1** — pack rip. Low blast radius pre-launch (no production packs purchased). Risk: orphan references missed during the rip leave type errors on mobile build. Mitigation: CI failure surfaces these; `npx expo lint` + TS build are the gate.
- **Unit 2** — copy rewrite. Zero functional risk; pure string + constant changes. CI grep gate prevents regression.
- **Unit 3** — capabilities field. Mobile app may cache old capabilities response if TTL is long; worst case the weekly-regen line shows stale for one launch cycle. Acceptable.
- **Unit 4** — doc sync. Zero runtime risk.

Rollback posture: pre-launch destructive — revert the PR. No data migration considerations (no production pack purchases, no live Pro subscriptions).

## Out of Scope (Separate Initiatives)

- R14b drift-protection buffer — still v1.1.
- R21 fixture pipeline — still v1.1.
- Full `last_authoritative_fetch_at` + Stripe re-fetch — v1.1.
- Mobile UI refresh to adopt the new copy in any flow outside paywall/subscription/upsell surfaces — track separately if discovered.
