---
status: complete
created: 2026-03-16
last_updated: 2026-03-16
project: nxme
test_case_count: 331
coverage_percent: 75
---

# Test Strategy: NXME

## Constraints

**Zero automated tests during development.** All 30 stories are implemented without test code. After all stories are complete, the following sequence applies:

1. **Manual acceptance testing** — tester runs `docs/test-cases.md` against staging
2. **E2E automation** — Playwright tests authored only after manual validation passes

## Test Scope

| Area | In Scope | Out of Scope |
|------|----------|--------------|
| API endpoints | All 30+ endpoints across 7 epics | Supabase internal infrastructure |
| Mobile app (Expo) | All 9 mobile UI stories | App Store review process |
| Image pipeline | NSFW screening, EXIF strip, face analysis, generation | fal.ai internal model accuracy |
| Payments | Stripe test mode, webhooks, subscriptions | Live payment processing |
| Social features | Feed, reactions, comments, reports, post CRUD | Content moderation at scale |
| Personal advisor | Chat (paid tier), nudges (free tier), memory CRUD | Claude model output quality |
| Shareable card | Next.js SSR rendering, OG tags | SEO ranking |
| Auth | Email/password, Google OAuth, Apple Sign In | Identity provider internals |
| Tier system | All 6 LimitType branches, feature flags | Business pricing decisions |

## Test Types

| Type | Purpose | Tools | When |
|------|---------|-------|------|
| Manual Acceptance | Verify all story ACs against staging | Real API keys, Supabase dashboard, Stripe CLI, ExifTool, physical devices | After all 30 stories complete |
| E2E Automation | Regression for ~30 critical flows | Playwright | After manual validation passes |

Unit tests, integration tests, and contract tests: **not written during development.**

## Test Environments

| Environment | Purpose | Data |
|-------------|---------|------|
| Staging (nxme-staging) | Primary manual testing | Seeded synthetic + real API test keys |
| Local (nxme-dev) | Developer smoke testing | Developer's own test data |
| Production smoke | Post-deploy spot checks | Production (minimal touch, no PII generated) |

**Required tools for manual testing:**
- Stripe CLI (`stripe trigger`) — webhook simulation
- ExifTool — EXIF strip verification
- Physical iOS device (15.0+) — Apple Sign In + VoiceOver testing
- Android device or emulator (API 29+) — cross-platform + TalkBack testing
- Supabase dashboard — DB state inspection
- testssl.sh or equivalent — TLS version verification
- curl / Postman — direct API testing
- Browser DevTools — network inspection, SSR verification

## Entry Criteria

Before manual testing begins:
- All 30 stories in `docs/sprint-status.yaml` have `status: done`
- Application deployed to staging environment
- All env vars configured: `ANTHROPIC_API_KEY`, Stripe test keys, fal.ai key, Rekognition credentials
- Supabase pgvector extension enabled on staging
- Stripe CLI connected to staging webhook endpoint
- Test accounts prepared for each tier: trial, credit_holder, premium
- nxme-dev Supabase project accessible with admin credentials

## Exit Criteria

Manual testing complete when:
- All P1 test cases pass (zero P1 open defects)
- ≥85% of P2 test cases pass (P2 failures logged, non-blocking)
- Critical gaps verified: AC-D4, AC-U8, AC-NFR12, AC-NFR13, AC-NFR15
- Defect retest complete (all fixed defects re-verified)
- E2E automation can begin

## Risk Assessment

### Quality Risks

| ID | Risk | Probability | Impact | Priority | Mitigation |
|----|------|-------------|--------|----------|------------|
| QR-001 | Credit ledger race condition — double-spend or phantom credits under concurrent load | M | H | P1 | TC-332–334: reserve/release/commit invariants |
| QR-002 | NSFW bypass — adversarial image passes Rekognition | L | H | P1 | TC-203–205: explicit content + edge cases |
| QR-003 | Facial landmark data stored in DB | L | H | P1 | TC-209: DB inspection post-analysis |
| QR-004 | Stripe webhook duplicate delivery → double credits | M | H | P1 | TC-341: Stripe CLI replay idempotency |
| QR-005 | fal.ai unavailability → credit loss without notification | M | H | P1 | TC-320–321: circuit breaker + credit release |
| QR-006 | Identity preservation failure — generated image doesn't look like user | M | H | P1 | TC-801: similarity score threshold block |
| QR-007 | WCAG AA non-compliance — legal accessibility exposure | L | M | P2 | TC-812–813: contrast + screen reader |
| QR-008 | TierConfig misconfiguration — free users get unlimited access | L | H | P1 | TC-350–355: all 6 LimitType branches |

### External Dependencies

| Dependency | Risk | Contingency |
|------------|------|-------------|
| fal.ai | Latency spike or outage | Circuit breaker caps wait; credit not consumed; retry available |
| AWS Rekognition | Mis-classification of safe content | Audit trail + manual review queue |
| Stripe | Webhook delivery failure | Idempotency key + replay via CLI |
| Anthropic Claude API | Rate limit or outage | Advisor chat graceful error; session state preserved |
| Supabase | Slow query or cold start | pgvector IVFFlat index; connection pooler |

## Testability Analysis

### Testable: 28/31 FRs (fully testable pre-launch)

All core user flows, payment paths, image pipeline, tier enforcement, and social features are
testable manually with real API keys against staging.

### Deferred to Post-Launch Monitoring (Untestable Pre-Launch)

| NFR | Reason | Verification Method |
|-----|--------|---------------------|
| NFR-1: API P95 ≤500ms | Requires production traffic volume | CloudWatch P95 alarm, 30-day rolling |
| NFR-5: API uptime ≥99.9% | Requires 30-day window | Uptime monitoring service |
| NFR-6: NSFW accuracy ≥99% | Requires statistical sampling at scale | Weekly production sample review |

### Special Setup Requirements

| Requirement | Setup |
|-------------|-------|
| AC-NFR13 WCAG | iOS VoiceOver (Settings → Accessibility) + Android TalkBack |
| AC-NFR15 Min OS | iOS 15.0 device or simulator + Android API 29 device |
| AC-NFR12 TLS | `testssl.sh https://api.nxme.ai` |
| AC-U8 Refund flow | Requires a completed generation result (run flow through first) |
| AC-D4 Identity preservation | Requires mock or test fixture that returns low similarity score |

## Effort Estimation

### Test Case Summary

| Batch | Stories | Test Cases | P1 | P2 | P3 |
|-------|---------|-----------|----|----|-----|
| Epics 1+2 (Foundation + Auth) | 6 | ~72 | ~40 | ~26 | ~6 |
| Epics 3+4 (Image Pipeline + Monetization) | 10 | 83 | 45 | 16 | 2 |
| Epics 5+6 (Social + Sharing) | 10 | ~88 | ~48 | ~32 | ~8 |
| Epic 7 + cross-cutting (Advisor) | 8 | ~65 | ~35 | ~22 | ~8 |
| Gap tests (Step 7 additions) | — | 23 | 13 | 7 | 3 |
| **Total** | **30** | **~331** | **~181** | **~103** | **~27** |

### Effort Breakdown

| Activity | Hours | Notes |
|----------|-------|-------|
| Manual execution — P1 (~181 tests) | 30h | ~10 min avg per test |
| Manual execution — P2 (~103 tests) | 12h | ~7 min avg per test |
| Manual execution — P3 (~27 tests) | 2h | ~5 min avg per test |
| Test environment setup | 8h | API keys, devices, Stripe CLI, testssl.sh |
| Defect retesting | 10h | ~20% buffer on execution time |
| **Manual first pass total** | **62h** | **~8 person-days** |
| E2E test authoring (Playwright) | 32h | ~30–35 critical flows |
| **E2E automation total** | **32h** | **~4 person-days** |

### Total Effort

| Phase | Person-Days | When |
|-------|-------------|------|
| Manual testing — initial pass | 7–8 days | After all 30 stories implemented |
| E2E automation investment | 4–5 days | After manual validation passes |
| Per regression cycle (E2E automated) | 0.5h | CI headless Playwright run |

## Coverage Report

### Final Coverage

| Area | Coverage | Status |
|------|----------|--------|
| Functional Requirements (31) | 87% full / 100% touched | ⚠️ 4 partial |
| NFR Requirements (16) | 75% direct + 3 deferred | ⚠️ Deferred acceptable |
| AC-U User Experience (10) | 70% — 1 gap (AC-U8) | ⚠️ Gap addressed in TC-802 |
| AC-FR Functional (10) | 80% — 2 partial | ⚠️ Advisory |
| AC-A Architecture/Security (12) | 75% — 3 partial | ⚠️ Advisory |
| AC-D Developer/Maintainer (8) | 63% — 1 gap (AC-D4) | ⚠️ Gap addressed in TC-801 |
| AC-NFR Non-Functional (16) | 56% direct — 4 gaps | ⚠️ Gaps addressed in TC-811–814 |
| Integrations (6) | 83% partial+ | ⚠️ Claude API error paths addressed in TC-820 |

### Critical Gaps — Addressed in test-cases.md (TC-801+)

| Gap | AC | Test Case |
|-----|-----|-----------|
| Identity preservation block | AC-D4 | TC-801 |
| "Doesn't look like me" refund flow | AC-U8 | TC-802 |
| All 6 TierConfig LimitType branches | FR-22 | TC-803–808 |
| TLS 1.2+ enforcement + AES-256 at rest | AC-NFR12 | TC-811 |
| WCAG 2.1 AA accessibility | AC-NFR13 | TC-812–813 |
| Minimum OS device testing | AC-NFR15 | TC-814 |
| CI coverage gate verification | AC-NFR16 | TC-815 |
| Anthropic Claude API failure path | FR-25 | TC-820 |
| Polyglot file rejection + dimension pre-decode | AC-A10 | TC-821–822 |
| UNKNOWN failure-reason alert | AC-D6 | TC-823 |
| AC-FR10 no-attractiveness-field assertion | FR-6 | TC-824 |
| Minor account upload-block | AC-U7 | TC-825 |
| Concurrent username registration | AC-A5 | TC-826 |
| Username immutability post-creation | AC-A5 | TC-827 |
| Account deletion per-data-store deadlines | AC-FR5 | TC-828–829 |
| Reaction reconciliation job | FR-12 | TC-830 |
| Rollback 100% branch coverage assertion | AC-D2 | TC-831 |

## E2E Test Flows (Playwright — Post-Manual)

To be authored after manual validation passes. Priority flows:

| Flow | Priority | Estimated Duration |
|------|----------|--------------------|
| Registration → email verify → trial grant | P1 | 45s |
| Social login (Google) → JWT-protected endpoint | P1 | 30s |
| Image upload → NSFW pass → analysis → generation | P1 | 90s |
| Credit exhaustion → 402 gate → paywall | P1 | 60s |
| Stripe subscription purchase → entitlement unlock | P1 | 120s |
| Generation cancel → credit release | P1 | 60s |
| Guest reaction → dedup on same session | P2 | 30s |
| Shareable card render → OG tags present | P2 | 20s |
| Advisor chat (paid) → 403 (free) | P2 | 45s |
| Account deletion → 401 on subsequent request | P1 | 45s |
