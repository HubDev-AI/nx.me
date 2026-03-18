# Review Sweep — Comprehensive Remediation Plan

**Date:** 2026-03-17
**Source:** `docs/reviews/claude/SKIPPED-FINDINGS.md` (60+ findings)
**Approach:** 7 sprints, foundation-first, all items included — nothing deferred.

---

## Sprint 1 — Critical Security & Data Integrity

**Theme:** Make it safe before making it clean.

| ID | Item | Category |
|---|---|---|
| LR-3 | RLS on all 16 user-scoped tables (users, images, analyses, credit_reservations, glow_up_jobs, credit_ledger, subscriptions, posts, reactions, comments, reports, usage_events, user_memories, advisor_conversations, advisor_messages, advisor_nudges) | Large refactor |
| LR-4 | Credit ledger RPCs (4 functions) | Large refactor |
| LR-5 | Non-transactional multi-step writes (reactions, comments, webhooks) | Large refactor |
| DB-1 | usage_events FK → public.users | Migration |
| QF-8 | display_name XSS prevention (strip `<>"`) | Quick fix |

**Why first:** Data breach vector (RLS), financial inconsistency (ledger RPCs), data corruption (non-transactional writes), wrong cascade target (FK). These are the items where "not fixing" has the worst consequences. LR-3 + LR-4 + LR-5 are closely related — all Postgres functions/policies deployed as one migration batch. DB-1 is a one-line FK fix that ships with the same migration.

**Definition of done:** All 16 user-scoped tables have RLS + FORCE RLS with `USING (auth.uid() = user_id)` policies, service role bypass, and read-only public access for posts/comments. Credit ledger RPCs exist and pass integration tests. Reactions/comments/webhooks execute atomically. usage_events FK references public.users. `display_name` field rejects `<`, `>`, `"` characters.

---

## Sprint 2 — Repository Layer + Async Foundation

**Theme:** Make the codebase workable.

| ID | Item | Category |
|---|---|---|
| LR-2 | Repository layer extraction (users, jobs, analyses, images, posts, comments, reports, subscriptions, processed_webhook_events) | Large refactor |
| LR-1 | Sync Supabase calls blocking event loop (60+ call sites) | Large refactor |
| LE-3 | Default tier query duplicated in auth.py | Low effort |
| ME-4 | CreditLedger ad-hoc instantiation in 7+ places | Medium effort |

**Why here:** LR-2 is the single highest-leverage refactor. Once repositories exist, LR-1 becomes "add `run_in_executor` in one place per repo method" instead of touching 60+ call sites. LE-3 and ME-4 fall out as free side effects of proper DI through repositories.

**Definition of done:** Every `supabase.table(...)` call lives in a repository class. `supabase.rpc(...)` calls used by handlers/workers are routed through repository/service methods. Blocking Supabase SDK usage in async code (`table`, `rpc`, `storage`, `auth.admin`) runs through `run_in_executor` or equivalent via repositories/adapters/helpers. No ad-hoc `CreditLedger(supabase)` construction outside DI.

---

## Sprint 3 — API Consistency & Error Handling

**Theme:** Make the API predictable.

| ID | Item | Category |
|---|---|---|
| ME-1 | Unified error response format (`raise_api_error` helper) | Medium effort |
| QF-1 | DELETE /posts → 204 No Content; already_deleted → 409 Conflict | Quick fix |
| QF-2 | POST /credits/purchase and POST /subscriptions → 201 Created | Quick fix |
| QF-3 | POST /jobs/{id}/cancel → explicit status_code=200 | Quick fix |
| QF-4 | Remove empty SubscriptionRequest model | Quick fix |
| QF-6 | Logout 502 error shape normalization | Quick fix |
| QF-7 | ValueError → RateLimitExceeded custom exception | Quick fix |
| ME-2 | Split SubscriptionResponse into Create/Cancel | Medium effort |
| ME-3 | Type recommendations as list[RecommendationItem] | Medium effort |
| ME-5 | Idempotency key → header (with body backward compat) | Medium effort |
| LE-1 | Retry-After headers on all 429 responses | Low effort |
| LE-5 | Login rate limit independent constants | Low effort |

**Why here:** ME-1 (unified error handler) is the keystone — once that exists, QF-1/2/3/6 become trivial decorator changes. All API contract changes grouped so mobile client updates happen once.

**Definition of done:** All endpoints return `{"error": {"code": "...", "message": "..."}}` on failure. Status codes match REST conventions, including `DELETE /posts` returning 204 on success and 409 for already-deleted posts, and both checkout-creating endpoints (`POST /credits/purchase`, `POST /subscriptions`) returning 201. All 429s include Retry-After. Typed response models for all endpoints.

---

## Sprint 4 — Database Migrations & Worker Cleanup

**Theme:** Fix the data layer and the biggest functions.

| ID | Item | Category |
|---|---|---|
| DB-2 | usage_events index with status column (ESR) | Migration |
| DB-3 | reactions(created_at, post_id) index | Migration |
| DB-4 | reports table indexes (post_id, status) | Migration |
| DB-5 | IVFFlat → HNSW on user_memories | Migration |
| DB-6 | Drop redundant indexes (cards_slug, users_username) | Migration |
| DB-7 | prompt_experiments.job_id index | Migration |
| DB-8 | decrement_comment_count function | Migration |
| DB-9 | DOWN/rollback sections for migrations 0008, 0009, 0011 | Migration |
| LR-6 | Split process_generation_job (290 lines → 4 functions) | Large refactor |
| LR-7 | Split create_generation (215 lines → 4 functions) | Large refactor |

**Why here:** DB migrations batch naturally — one migration file, one deploy. LR-6 and LR-7 are pure refactors with no API surface change, safe to pair with DB work. Repository layer from Sprint 2 makes the function splits cleaner.

**Definition of done:** All indexes optimized per ESR rule. HNSW replaces IVFFlat. Comment count decrements work. All migrations have DOWN sections. Worker functions are each <50 lines.

---

## Sprint 5 — Code Quality & Mobile Fixes

**Theme:** Fix correctness bugs and UX gaps.

| ID | Item | Category |
|---|---|---|
| QF-5 | _SOUL_MD read error guard | Quick fix |
| QF-9 | TypingIndicator reduced motion | Quick fix |
| LE-2 | Timestamp cursor collision (comments, history) | Low effort |
| LE-4 | Redis SET-then-INCR drift fix | Low effort |
| LE-6 | prompts/ import path (move under app/) | Low effort |
| LE-7 | Rolling average cost math fix | Low effort |
| LE-8 | Weak advisor repetition detection | Low effort |
| LE-9 | ESLint missing @typescript-eslint/strict | Low effort |
| LE-10 | Inter font via next/font | Low effort |
| LE-11 | Advisor screen not reachable from tab bar | Low effort |
| LR-9 | Social login button dedup (use existing component) | Large refactor |
| LR-10 | FlatList nested in ScrollView (kill virtualization) | Large refactor |
| LR-11 | Modal focus management (PaywallModal, CommentsSheet, EditProfileSheet) | Large refactor |
| ME-6 | find_milestone_eligible → COUNT GROUP BY query | Medium effort |

**Why here:** These are all independent fixes. Most don't depend on earlier sprints. Can be parallelized heavily.

**Definition of done:** All cursor pagination uses composite cursors. Redis counters use INCR-only pattern. Cost averages use actual generation counts. All modals manage focus for screen readers. FlatList virtualization works.

---

## Sprint 6 — Resilience & Security Hardening

**Theme:** Harden the system.

| ID | Item | Category |
|---|---|---|
| LR-8 | Guest reaction tokens — server registry | Large refactor |
| LR-12 | Circuit breaker half-open state | Large refactor |
| LR-13 | Conversation summarization → soft-delete | Large refactor |
| FW-3 | CSP + security headers (HSTS, X-Content-Type-Options, etc.) | Feature |
| FW-10 | WebhookEvent typed (PaymentPort returns dataclass) | Feature |

**Why here:** These are cross-cutting resilience and security improvements that benefit from the repository layer (Sprint 2) and error handling (Sprint 3) already being in place.

**Note on FW-12:** "Async webhook handlers with sync Supabase calls" is fully covered by Sprint 2 (LR-1/LR-2). Once all Supabase calls go through repositories with `run_in_executor`, webhook handlers are fixed as a side effect. Not listed separately to avoid double-counting.

**Definition of done:** Guest tokens server-validated. Circuit breaker implements sliding window / half-open. Messages soft-deleted with retention. CSP headers on all responses. Webhook events typed.

---

## Sprint 7 — Feature Gaps & API Polish

**Theme:** Complete the API surface.

| ID | Item | Category |
|---|---|---|
| FW-1 | Pagination on advisor messages, nudges, memories | Feature |
| FW-2 | sitemap.ts + robots.ts for card-web | Feature |
| FW-4 | JSON-LD structured data on card page | Feature |
| FW-5 | card-web test script (smoke tests) | Feature |
| FW-6 | API path naming (verbs → nouns, versioned migration) | Feature |
| FW-7 | Location header on 201 responses | Feature |
| FW-8 | Sort parameter on comments | Feature |
| FW-9 | Filtering on nudges (?unread=true) | Feature |
| FW-11 | Deprecation markers + Sunset headers | Feature |

**Why here:** These are additive features that don't fix bugs — they improve the API surface and SEO. FW-6 (verb paths) requires mobile client coordination, so it goes last.

**Definition of done:** All list endpoints paginated. card-web has sitemap, robots, JSON-LD, and smoke tests. API paths follow noun convention with versioned migration. 201 responses include Location. Comments sortable. Nudges filterable. Deprecation infrastructure in place.

---

## Cross-Sprint Notes

- **Sprint 1 is primarily migrations + one app-level fix** (QF-8 display_name validation) — deploy together to close the biggest risks
- **Sprint 2 is the investment sprint** — repository layer pays dividends in every later sprint
- **Sprint 3 groups all API contract changes** — one mobile client update cycle
- **Sprints 5+ can be parallelized** — items are independent
- **Each sprint is self-contained** — codebase is strictly better after each one
- **Total items: 60** — all findings accounted for, zero deferred (FW-12 absorbed into Sprint 2's LR-1/LR-2 scope, counted once)
