---
status: complete
created: 2026-03-16
last_updated: 2026-03-16
project: nxme
total_cases: 331
---

# Test Cases: NXME

All tests are **manual acceptance tests** run against staging after all 30 stories are implemented.

**Test Case Format:**
- Priority: P1 (critical) → P2 (high) → P3 (medium) → P4 (low)
- Technique: BVA = Boundary Value Analysis, EP = Equivalence Partitioning, ST = State Transition, DT = Decision Table, EG = Error Guessing

---

## Epic 1: Foundation

### TC-001: DB Migration — All 13 Tables Created
- **Priority**: P1 | **Story**: 1-1 | **Technique**: EP
- **Preconditions**: Fresh Supabase staging project
- **Steps**: 1. Run migration scripts in order; 2. Inspect schema via Supabase dashboard
- **Expected**: 13 tables exist: `users`, `analyses`, `face_analysis_results`, `recommendations`, `generated_images`, `posts`, `reactions`, `comments`, `reports`, `entitlement_events`, `credit_transactions`, `advisor_conversations`, `advisor_messages`, `user_memories`, `processed_webhook_events`
- **Postconditions**: All indexes present; no migration errors

### TC-002: DB Migration — CHECK Constraints Enforced
- **Priority**: P1 | **Story**: 1-1 | **Technique**: EP
- **Steps**: Attempt INSERT into `posts` with `status = 'invalid_status'`
- **Expected**: PostgreSQL CHECK constraint violation; INSERT rejected

### TC-003: DB Migration — FK Cascade on User Deletion
- **Priority**: P1 | **Story**: 1-1 | **Technique**: ST
- **Steps**: 1. Create user; 2. Create post for user; 3. Delete user from `auth.users`
- **Expected**: Post row deleted via ON DELETE CASCADE; no orphaned rows in any user-linked table

### TC-004: DB Migration — Up/Down Cycle Idempotent
- **Priority**: P1 | **Story**: 1-1 | **Technique**: EG
- **Steps**: 1. Run all up migrations; 2. Run all down migrations; 3. Run all up migrations again
- **Expected**: Final state matches original up migration state; no errors on second up run

### TC-005: pgvector Extension Enabled
- **Priority**: P1 | **Story**: 7-1 | **Technique**: EP
- **Steps**: Run `SELECT extname FROM pg_extension WHERE extname = 'vector'` on staging DB
- **Expected**: Row returned; extension present

### TC-006: user_memories Table — Embedding Column Exists (1536-dim)
- **Priority**: P1 | **Story**: 7-1 | **Technique**: EP
- **Steps**: Run `SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'user_memories' AND column_name = 'embedding'`
- **Expected**: Row returned; data_type = `USER-DEFINED` (vector); `SELECT typname FROM pg_type WHERE oid = (SELECT atttypid FROM pg_attribute WHERE attrelid = 'user_memories'::regclass AND attname = 'embedding')` returns `vector`

### TC-007: IVFFlat Index on user_memories.embedding
- **Priority**: P2 | **Story**: 7-1 | **Technique**: EP
- **Steps**: `SELECT indexname FROM pg_indexes WHERE tablename = 'user_memories' AND indexdef ILIKE '%ivfflat%'`
- **Expected**: Index present

### TC-008: ADR Resolution — OQ-1 Social Providers Documented
- **Priority**: P2 | **Story**: 1-2 | **Technique**: EP
- **Steps**: Check that ADR document exists in docs/ recording the decision to support Google OAuth + Apple Sign In
- **Expected**: ADR file present with OQ-1 resolved; legal basis for Apple Sign In (required for iOS) documented

### TC-009: Named Tier Constants — No Inline Strings
- **Priority**: P2 | **Story**: 1-2 | **Technique**: EP
- **Steps**: Search codebase for raw strings `"trial"`, `"credit_holder"`, `"premium"` outside of config/tiers.py and test fixtures
- **Expected**: Zero occurrences of raw tier strings in non-config code; all references use the `UserTier` enum

---

## Epic 2: Auth & Account Management

### TC-101: Registration — Valid Email + Strong Password
- **Priority**: P1 | **Story**: 2-1 | **Technique**: EP
- **Test Data**: `user@example.com`, password meeting requirements (8+ chars, mixed case, digit)
- **Steps**: POST /auth/register with valid payload
- **Expected**: 201; verification email sent; user row created in DB with `email_verified = false`; trial balance = `FREE_TRIAL_ANALYSES` (from config)

### TC-102: Registration — Invalid Email Format → 400
- **Priority**: P1 | **Story**: 2-1 | **Technique**: BVA
- **Test Data**: `notanemail`, `@nxme.ai`, `user@`
- **Steps**: POST /auth/register with each invalid email
- **Expected**: 400 Bad Request; validation error message; no user created

### TC-103: Registration — Duplicate Email → 409
- **Priority**: P1 | **Story**: 2-1 | **Technique**: EP
- **Steps**: Register same email twice
- **Expected**: Second request returns 409 Conflict; no duplicate user row

### TC-104: Registration — Device Fingerprint Rate Limit (5/device/day → 429)
- **Priority**: P1 | **Story**: 2-1 | **Technique**: BVA
- **Steps**: Register 5 accounts from same device fingerprint within 24h, then attempt a 6th
- **Expected**: First 5 succeed (or per config); 6th returns 429 Too Many Requests
- **Note**: Verify against `TIER__TRIAL_REGISTRATION_DAILY_LIMIT` or equivalent config value

### TC-105: Trial Grant — Idempotent on Double Registration Attempt
- **Priority**: P1 | **Story**: 2-1 | **Technique**: EG
- **Steps**: Simulate duplicate registration request (same idempotency key or race condition)
- **Expected**: Exactly one trial grant event in `entitlement_events`; credit balance = `FREE_TRIAL_ANALYSES` (not doubled)

### TC-106: Email Verification — Valid Link Activates Account
- **Priority**: P1 | **Story**: 2-1 | **Technique**: ST
- **Steps**: 1. Register; 2. Click verification link from email
- **Expected**: Account `email_verified = true`; can now log in

### TC-107: Email Verification — Expired Link → Error
- **Priority**: P2 | **Story**: 2-1 | **Technique**: BVA
- **Steps**: Use a verification link older than expiry window
- **Expected**: 410 Gone or 400; message explains link expired; resend option available

### TC-108: Social Login — Google OAuth → JWT Issued
- **Priority**: P1 | **Story**: 2-2 | **Technique**: EP
- **Steps**: Tap "Continue with Google" on mobile; complete Google auth flow
- **Expected**: JWT access token issued; user row created or linked; Supabase session active

### TC-109: Social Login — Apple Sign In (iOS) → JWT Issued
- **Priority**: P1 | **Story**: 2-2 | **Technique**: EP
- **Preconditions**: Physical iOS device (Apple Sign In requires real device or TestFlight)
- **Steps**: Tap "Continue with Apple"; complete Apple auth
- **Expected**: JWT issued; user row created or linked

### TC-110: JWT Expiry → 401 on Protected Route
- **Priority**: P1 | **Story**: 2-2 | **Technique**: ST
- **Steps**: Use expired JWT on GET /analyses
- **Expected**: 401 Unauthorized; `WWW-Authenticate` header present

### TC-111: Logout — Session Invalidated
- **Priority**: P1 | **Story**: 2-2 | **Technique**: ST
- **Steps**: 1. Log in; 2. Call POST /auth/logout; 3. Use previous JWT on protected endpoint
- **Expected**: Logout returns 200; subsequent request with old JWT returns 401; app navigates to unauthenticated state

### TC-112: Account Deletion — Cascade to All User Data
- **Priority**: P1 | **Story**: 2-2 | **Technique**: ST
- **Steps**: 1. Create user; 2. Upload analysis, create post, add memory; 3. DELETE /users/me; 4. Inspect DB
- **Expected**: User row deleted; all `analyses`, `posts`, `reactions`, `comments`, `entitlement_events`, `advisor_conversations`, `user_memories` rows deleted; Supabase Storage files deleted (or scheduled for deletion)

### TC-113: Account Deletion — Shareable Card Returns 410
- **Priority**: P2 | **Story**: 2-2 | **Technique**: ST
- **Steps**: 1. Create user with shareable card; 2. Delete account; 3. Navigate to `nxme.ai/{username}` web app
- **Expected**: HTTP 410 Gone (not 404); page shows "Account no longer available" message

### TC-114: Mobile Auth UI — Login Screen Renders
- **Priority**: P2 | **Story**: 2-3 | **Technique**: EP
- **Steps**: Launch app on fresh install; observe login screen
- **Expected**: Email/password fields visible; "Continue with Google" and "Continue with Apple" buttons visible; no layout overflow

### TC-115: Mobile Auth UI — Signup Validation
- **Priority**: P2 | **Story**: 2-3 | **Technique**: BVA
- **Steps**: Submit signup form with empty email
- **Expected**: Inline validation error shown; form not submitted; no network call made

### TC-116: Onboarding — First-Time User Sees Onboarding Flow
- **Priority**: P2 | **Story**: 2-4 | **Technique**: ST
- **Steps**: Register new account; complete email verification; open app
- **Expected**: Onboarding screens shown (≥1 screen explaining the app's purpose); can skip or complete

### TC-117: Onboarding — Push Notification Permission Requested
- **Priority**: P2 | **Story**: 2-4 | **Technique**: EP
- **Steps**: Complete onboarding; observe permission prompt
- **Expected**: OS-level push notification permission dialog shown (iOS or Android); device token registered in DB on permission grant

---

## Epic 3: Image Upload & Face Analysis

### TC-201: POST /analyses — Valid JPEG Under Limit → Success
- **Priority**: P1 | **Story**: 3-3 | **Technique**: EP
- **Test Data**: 800KB JPEG selfie
- **Steps**: POST /analyses with valid image and auth token
- **Expected**: 202 Accepted; analysis job queued; response includes `analysis_id`

### TC-202: POST /analyses — File Over 10MB → 413
- **Priority**: P1 | **Story**: 3-1 | **Technique**: BVA
- **Test Data**: 11MB image file
- **Steps**: POST /analyses with oversized file
- **Expected**: 413 Payload Too Large; file not stored; no job queued

### TC-203: POST /analyses — NSFW Content → 422 + Audit Trail
- **Priority**: P1 | **Story**: 3-1 | **Technique**: EP
- **Test Data**: Explicit image (use Rekognition test fixture)
- **Steps**: POST /analyses with explicit image
- **Expected**: 422 Unprocessable; image NOT written to Supabase Storage; row in NSFW audit table; user credit NOT consumed

### TC-204: POST /analyses — NSFW Screening Completes Within 5s
- **Priority**: P1 | **Story**: 3-1 | **Technique**: EP
- **Steps**: Submit image; measure time from request to NSFW result (pass or fail)
- **Expected**: NSFW decision returned in ≤5 seconds (time with stopwatch or request logs)

### TC-205: POST /analyses — PNG Accepted
- **Priority**: P1 | **Story**: 3-1 | **Technique**: EP
- **Test Data**: Valid PNG selfie
- **Steps**: POST /analyses with PNG
- **Expected**: 202 Accepted; same behavior as JPEG

### TC-206: POST /analyses — HEIC Accepted
- **Priority**: P2 | **Story**: 3-1 | **Technique**: EP
- **Test Data**: iOS HEIC format photo
- **Steps**: POST /analyses with HEIC
- **Expected**: 202 Accepted (HEIC is valid input)

### TC-207: POST /analyses — GIF Rejected → 415
- **Priority**: P2 | **Story**: 3-1 | **Technique**: EP
- **Test Data**: GIF file
- **Steps**: POST /analyses with GIF
- **Expected**: 415 Unsupported Media Type

### TC-208: EXIF Strip — No GPS Data in Stored Image
- **Priority**: P1 | **Story**: 3-1 | **Technique**: EP
- **Test Data**: JPEG with GPS EXIF data embedded
- **Steps**: 1. Upload image with GPS EXIF; 2. Retrieve stored image; 3. Run `exiftool stored_image.jpg`
- **Expected**: Zero GPS-related EXIF fields in stored file; all EXIF/IPTC/XMP metadata stripped

### TC-209: Face Analysis — No Landmark Vectors in DB
- **Priority**: P1 | **Story**: 3-2 | **Technique**: EP
- **Steps**: 1. Complete analysis; 2. Query `face_analysis_results` table in Supabase
- **Expected**: No column storing raw landmark coordinates or embeddings; only derived classification fields (`face_shape`, `symmetry_score`, `key_features`)

### TC-210: Face Analysis — face_shape from Valid Enum
- **Priority**: P1 | **Story**: 3-2 | **Technique**: EP
- **Steps**: Complete analysis; inspect response
- **Expected**: `face_shape` ∈ {oval, round, square, heart, oblong}; `symmetry_score` ∈ [0.0, 1.0]

### TC-211: Face Analysis — No Attractiveness Field in Response
- **Priority**: P1 | **Story**: 3-2 | **Technique**: EG
- **Steps**: Complete analysis; parse full response JSON
- **Expected**: Zero fields named `score`, `rating`, `rank`, `attractiveness`, or any synonym; only approved fields present

### TC-212: Face Analysis — P95 Latency ≤3s
- **Priority**: P1 | **Story**: 3-2 | **Technique**: EP
- **Steps**: Submit 10 analysis requests; record completion time for each
- **Expected**: At least 9/10 complete within 3 seconds (P90 proxy for P95 in small sample)

### TC-213: Analysis API — Unsigned Raw Bucket Request → 403
- **Priority**: P1 | **Story**: 3-3 | **Technique**: EP
- **Steps**: Attempt to access raw selfie via direct Supabase Storage URL without signed token
- **Expected**: 403 Forbidden; image not accessible without valid signed URL

### TC-214: Mobile Upload UI — Upload Progress Visible
- **Priority**: P2 | **Story**: 3-4 | **Technique**: EP
- **Steps**: Initiate upload on mobile; observe UI
- **Expected**: Progress indicator visible ≤5s of tap; cancel button present

---

## Epic 4: Entitlement, Generation & Monetization

### TC-301: Trial Balance — New Account = FREE_TRIAL_ANALYSES Credits
- **Priority**: P1 | **Story**: 4-1 | **Technique**: EP
- **Steps**: Register new account; GET /entitlement/balance
- **Expected**: Balance = value of `TIER__TRIAL__GENERATION__LIMIT` config (default: 3); `tier = 'TRIAL'`

### TC-302: Free Tier — Credit Exhaustion → 402 Before Generation
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: 1. Exhaust all trial credits; 2. Attempt POST /generate
- **Expected**: 402 Payment Required returned BEFORE any fal.ai call; paywall options shown in response; zero credits consumed

### TC-303: Credit Reserve — Balance Reduced Before Job Enqueue
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: 1. Note balance; 2. POST /generate; 3. Immediately GET /entitlement/balance
- **Expected**: Balance reduced by 1 before generation completes; job is in queued/processing state

### TC-304: Credit Release — Cancel During Processing Restores Credit
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: 1. POST /generate; 2. While job is processing, POST /generate/{id}/cancel
- **Expected**: Credit balance restored to pre-generation value; `entitlement_events` shows `status = 'released'`

### TC-305: Credit Commit — Successful Generation Consumes Credit
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: 1. POST /generate; 2. Wait for completion; 3. GET /entitlement/balance
- **Expected**: Balance reduced by exactly 1; `entitlement_events` shows `status = 'committed'`

### TC-306: Credit Ledger Invariant — Sum of Events Matches Balance
- **Priority**: P1 | **Story**: 4-1 | **Technique**: EG
- **Steps**: After multiple generations (mix of success/cancel), run: `SELECT SUM(delta) FROM entitlement_events WHERE user_id = ?`
- **Expected**: Sum equals current `credit_balance`; no phantom credits or debits

### TC-307: Generation Queue — Premium Jobs Process Before Trial Jobs
- **Priority**: P1 | **Story**: 4-2 | **Technique**: DT
- **Steps**: 1. Enqueue 3 trial jobs; 2. Immediately enqueue 1 premium job; 3. Monitor queue processing order via ARQ dashboard
- **Expected**: Premium job exits queue before any of the 3 trial jobs

### TC-308: Generation Queue — Per-User Concurrency Limit
- **Priority**: P1 | **Story**: 4-2 | **Technique**: BVA
- **Steps**: Submit 3 concurrent generation requests from same premium user; attempt 4th
- **Expected**: 3 jobs accepted; 4th returns 409 Conflict; message explains concurrent limit reached

### TC-309: Generation Queue — Stuck Job Watchdog Rescues
- **Priority**: P1 | **Story**: 4-2 | **Technique**: EG
- **Steps**: Simulate stuck job (e.g., mock fal.ai to never respond); wait for watchdog timeout
- **Expected**: After `GENERATION_TIMEOUT_SECONDS`, job transitions to failed state; credit released; user notified

### TC-310: Generation Queue — Circuit Breaker Trips After Consecutive fal.ai Failures
- **Priority**: P2 | **Story**: 4-2 | **Technique**: ST
- **Steps**: Simulate 5+ consecutive fal.ai failures; attempt new generation
- **Expected**: Circuit breaker OPEN; new jobs rejected fast (no wait for timeout); credits not consumed; circuit resets after cooldown period

### TC-311: POST /generate — Returns Job ID for Polling
- **Priority**: P1 | **Story**: 4-3 | **Technique**: EP
- **Steps**: POST /generate with valid payload
- **Expected**: 202 Accepted; response contains `job_id` and `poll_url`; job status = 'queued'

### TC-312: GET /generate/{id} — Polling Returns Status Progression
- **Priority**: P1 | **Story**: 4-3 | **Technique**: ST
- **Steps**: Poll `poll_url` every 2s until completion
- **Expected**: Status transitions: queued → processing → completed; final response includes `image_url` (signed URL)

### TC-313: Generation — End-to-End Completes Within 60s
- **Priority**: P1 | **Story**: 4-3 | **Technique**: EP
- **Steps**: POST /generate; poll until completion; measure total elapsed time
- **Expected**: Completion in ≤60 seconds P90 (proxy for P95 in small sample)

### TC-314: Generation — System Failure Does Not Consume Trial Credit
- **Priority**: P1 | **Story**: 4-3 | **Technique**: EG
- **Steps**: Trigger a system-side generation failure (mock fal.ai 500)
- **Expected**: Credit/trial balance unchanged; specific error message returned; retry available without re-upload

### TC-315: Generation — Cost Circuit Breaker Alert
- **Priority**: P2 | **Story**: 4-2 | **Technique**: BVA
- **Steps**: Simulate rolling 24h average cost reaching `CREDIT_COST_ALERT_USD` (default $0.04)
- **Expected**: Alert emitted (check monitoring log); generation still proceeds; at $0.05 ceiling, trial lane throttled

### TC-320: fal.ai — Provider Unavailability → Credit Not Consumed
- **Priority**: P1 | **Story**: 4-2 | **Technique**: EG
- **Steps**: Mock fal.ai returning 503; submit generation job
- **Expected**: Job transitions to failed; credit released (not committed); user sees error with retry option

### TC-321: fal.ai — Malformed Response Handled Gracefully
- **Priority**: P2 | **Story**: 4-2 | **Technique**: EG
- **Steps**: Mock fal.ai returning malformed JSON (missing required fields)
- **Expected**: Job fails with `failure_reason = 'PROVIDER_ERROR'`; credit released; no unhandled exception

### TC-341: Stripe Webhook — Duplicate Delivery Idempotent
- **Priority**: P1 | **Story**: 4-4 | **Technique**: EG
- **Test Data**: `stripe trigger customer.subscription.created`
- **Steps**: 1. Send webhook event via Stripe CLI; 2. Note credit balance; 3. Resend same event (same `event.id`)
- **Expected**: Balance identical after second delivery; `processed_webhook_events` has exactly one row for that event ID; second delivery returns HTTP 200

### TC-342: Stripe — Subscription Created → Premium Entitlement Unlocked
- **Priority**: P1 | **Story**: 4-4 | **Technique**: ST
- **Steps**: 1. Subscribe via paywall; 2. Complete Stripe checkout in test mode; 3. GET /entitlement/status
- **Expected**: Tier upgraded to PREMIUM; advisor chat feature flag = true; generation limit = monthly config value

### TC-343: Stripe — Subscription Cancelled → Access Until Period End
- **Priority**: P1 | **Story**: 4-4 | **Technique**: ST
- **Steps**: 1. Subscribe; 2. Cancel subscription; 3. Verify access before `billing_period_end`; 4. Fast-forward clock past period end; 5. Verify access revoked
- **Expected**: Premium access continues until period end; tier reverts to credit_holder or trial at `billing_period_end + 1s`

### TC-344: Stripe — Invalid Webhook Signature → 400
- **Priority**: P1 | **Story**: 4-4 | **Technique**: EG
- **Steps**: POST to webhook endpoint without valid Stripe signature header
- **Expected**: 400 Bad Request; no entitlement changes

---

## Epic 5: Social Layer

### TC-401: Social Feed — Unauthenticated Access Returns 200
- **Priority**: P1 | **Story**: 5-1 | **Technique**: EP
- **Steps**: GET /feed without Authorization header
- **Expected**: 200 OK; paginated posts returned (public content); no auth error

### TC-402: Social Feed — Pagination
- **Priority**: P1 | **Story**: 5-1 | **Technique**: BVA
- **Steps**: GET /feed?limit=10; follow cursor to next page
- **Expected**: Exactly 10 posts per page; cursor in response for next page; last page has no cursor

### TC-403: Social Feed — Sort by Recent
- **Priority**: P2 | **Story**: 5-1 | **Technique**: EP
- **Steps**: GET /feed?sort=recent
- **Expected**: Posts ordered by `created_at` descending

### TC-404: Guest Reaction — Dedup Within Same Session
- **Priority**: P1 | **Story**: 5-2 | **Technique**: EP
- **Steps**: 1. React to post as guest; 2. React to same post again (same session token)
- **Expected**: Second reaction ignored (deduplicated); `reaction_count` not incremented twice; Redis key confirms single count

### TC-405: Guest Reaction — Rate Limit (10/IP/5min → 429)
- **Priority**: P1 | **Story**: 5-2 | **Technique**: BVA
- **Steps**: Send 11 reactions from same IP within 5 minutes
- **Expected**: First 10 succeed; 11th returns 429; `Retry-After` header present

### TC-406: Guest Reaction — Resets on Session Restart
- **Priority**: P2 | **Story**: 5-2 | **Technique**: ST
- **Steps**: 1. React as guest; 2. Clear app state (new session token); 3. React to same post again
- **Expected**: Second reaction accepted (different session token); post shows 2 reactions total

### TC-407: Comments — Create + Read
- **Priority**: P1 | **Story**: 5-3 | **Technique**: EP
- **Steps**: 1. Authenticated POST /posts/{id}/comments with text; 2. GET /posts/{id}/comments
- **Expected**: Comment appears in list; `author_id` matches authenticated user

### TC-408: Comments — Delete Own Comment Only
- **Priority**: P1 | **Story**: 5-3 | **Technique**: EP
- **Steps**: 1. User A creates comment; 2. User B attempts DELETE /comments/{id}
- **Expected**: User B's request returns 403; comment remains

### TC-409: Reports — Submit Moves to Moderation Queue
- **Priority**: P2 | **Story**: 5-3 | **Technique**: EP
- **Steps**: POST /posts/{id}/report with reason
- **Expected**: 200; report row created; post status unchanged; admin review queue updated

### TC-410: Post CRUD — Owner Can Delete Own Post
- **Priority**: P1 | **Story**: 5-3 | **Technique**: EP
- **Steps**: DELETE /posts/{id} as post owner
- **Expected**: 200; post removed from feed; associated images deleted from storage

### TC-411: Post CRUD — Non-Owner Cannot Delete
- **Priority**: P1 | **Story**: 5-3 | **Technique**: EP
- **Steps**: DELETE /posts/{id} as different authenticated user
- **Expected**: 403 Forbidden; post remains

---

## Epic 6: Sharing, Profile & Acquisition

### TC-501: Shareable Card — API Returns Valid URL
- **Priority**: P1 | **Story**: 6-1 | **Technique**: EP
- **Steps**: POST /posts/{id}/card (generate shareable card)
- **Expected**: 200; response includes `card_url` = `nxme.ai/{username}`; OG meta tags generated

### TC-502: Shareable Card — Web App Renders Without Auth
- **Priority**: P1 | **Story**: 6-2 | **Technique**: EP
- **Steps**: Navigate to `nxme.ai/{username}` in browser (no login)
- **Expected**: Before/after images visible; top-5 suggestions shown; no auth required; correct OG tags in `<head>`

### TC-503: Shareable Card — Server-Side Rendered (No Client Auth Call)
- **Priority**: P2 | **Story**: 6-2 | **Technique**: EP
- **Steps**: Navigate to card URL; inspect Network tab in DevTools
- **Expected**: HTML fully rendered on server (not empty shell); no API call to auth-gated endpoint on critical render path; images loaded from CDN

### TC-504: Shareable Card — Post-Signup CTA Deep Link
- **Priority**: P2 | **Story**: 6-2 | **Technique**: ST
- **Steps**: Tap "Try NXME" CTA on shareable card; complete signup
- **Expected**: Post-signup destination shows trial count + upload prompt (not generic home screen)

### TC-505: User Profile — Analysis History Paginated, Reverse Chronological
- **Priority**: P1 | **Story**: 6-3 | **Technique**: EP
- **Steps**: Create 15 analyses; GET /profile/history
- **Expected**: Analyses in reverse chronological order; correct total count; pagination works

### TC-506: Deep Links — Universal Link Opens Correct Screen
- **Priority**: P2 | **Story**: 6-5 | **Technique**: EP
- **Steps**: Open `nxme.ai/deeplink/analysis/{id}` on mobile
- **Expected**: App opens (or installs) and navigates directly to that analysis result screen

---

## Epic 7: Personal Advisor

### TC-601: Advisor Chat — Free Tier → 403
- **Priority**: P1 | **Story**: 7-2 | **Technique**: DT
- **Steps**: POST /advisor/messages with free-tier (trial) auth token
- **Expected**: 403 Forbidden; response body explains chat is a paid feature; nudges still available

### TC-602: Advisor Chat — Paid Tier → Response from Claude
- **Priority**: P1 | **Story**: 7-2 | **Technique**: DT
- **Steps**: POST /advisor/messages with premium-tier auth token; body = `{"message": "What hairstyle suits my face shape?"}`
- **Expected**: 200; response contains `advisor_message` with substantive content; conversation persisted in `advisor_messages`

### TC-603: Advisor Chat — Context Includes Recent Analysis
- **Priority**: P1 | **Story**: 7-2 | **Technique**: EP
- **Steps**: 1. Complete face analysis; 2. Chat with advisor; 3. Inspect prompt context in logs
- **Expected**: Advisor response references analysis data (face shape, recommendations); analysis snapshot used (not raw image unless visual comparison requested)

### TC-604: Advisor Nudge — Free Tier Receives Nudge
- **Priority**: P1 | **Story**: 7-2 | **Technique**: EP
- **Steps**: Trigger post-analysis nudge condition as free-tier user; GET /advisor/nudges
- **Expected**: Nudge present; message is advisor-initiated (not user-initiated); `is_read = false`

### TC-605: Advisor Nudge — Free Tier Limit Enforced (Config-Driven)
- **Priority**: P1 | **Story**: 7-2 | **Technique**: BVA
- **Steps**: Trigger nudges until limit reached (default: `TIER__TRIAL__ADVISOR_NUDGES__LIMIT = 3` per week); attempt to generate 4th
- **Expected**: 4th nudge not sent within rolling 7-day window; limit configurable without code change

### TC-606: Memory — Add Goal/Note
- **Priority**: P1 | **Story**: 7-2 | **Technique**: EP
- **Steps**: POST /memories with `{"type": "goal", "content": {"text": "Improve jawline definition"}}`
- **Expected**: 201; memory stored; embedding generated and stored in `user_memories.embedding`

### TC-607: Memory — Semantic Search Returns Relevant Result
- **Priority**: P1 | **Story**: 7-2 | **Technique**: EP
- **Steps**: 1. Add memory about jawline; 2. Add memory about hairstyle; 3. Chat with advisor asking about "facial structure"
- **Expected**: Advisor context includes jawline memory (cosine similarity); hairstyle memory ranked lower

### TC-608: Memory — Delete Single Memory
- **Priority**: P2 | **Story**: 7-2 | **Technique**: EP
- **Steps**: DELETE /memories/{id}
- **Expected**: 200; memory row deleted; no longer returned in GET /memories

### TC-609: Memory — Wipe All Memories
- **Priority**: P2 | **Story**: 7-2 | **Technique**: EP
- **Steps**: DELETE /memories (wipe all)
- **Expected**: All `user_memories` rows for this user deleted; GET /memories returns empty list

### TC-610: Nudge Scheduler — Post-Analysis Trigger
- **Priority**: P1 | **Story**: 7-3 | **Technique**: ST
- **Steps**: Complete analysis; check ARQ job queue within 30s
- **Expected**: `advisor:nudge` job enqueued with correct `user_id` and `trigger = 'post_analysis'`

### TC-611: Nudge Scheduler — Weekly Check-In Trigger
- **Priority**: P2 | **Story**: 7-3 | **Technique**: ST
- **Steps**: Advance clock by 7+ days since last nudge; observe ARQ scheduler
- **Expected**: Weekly `advisor:nudge` job enqueued

### TC-612: Mobile Advisor UI — Nudge Feed Visible to Free Tier
- **Priority**: P2 | **Story**: 7-4 | **Technique**: EP
- **Steps**: Log in as free-tier user; navigate to advisor screen
- **Expected**: Nudge feed visible; unread badge shown; chat input not present (or disabled with upgrade prompt)

---

## Cross-Cutting Scenarios

### TC-701: Tier Gate — All Protected Endpoints Reject Free Tier at API Layer
- **Priority**: P1 | **Technique**: DT
- **Test Data**: Free trial user token
- **Steps**: Attempt POST /advisor/messages; POST /generate (when 0 credits); any premium-only endpoint
- **Expected**: 403 (not 200 with empty response); error at API layer, not filtered at UI layer

### TC-702: Biometric Data Ephemeral — No Landmarks in DB After Analysis
- **Priority**: P1 | **Technique**: EP
- **Steps**: Complete full analysis pipeline; query all tables for any vector/coordinate data
- **Expected**: `face_analysis_results` contains only derived fields; no raw landmark arrays or coordinate vectors stored anywhere

### TC-703: NSFW Safety — All Image Paths Screened
- **Priority**: P1 | **Technique**: EP
- **Steps**: Attempt to submit explicit image via POST /analyses; attempt via any other image upload endpoint
- **Expected**: All paths go through NSFW screening; explicit content never stored

### TC-704: Credit Ledger Integrity Under Concurrent Requests
- **Priority**: P1 | **Technique**: EG
- **Test Data**: User with 3 trial credits
- **Steps**: Send 5 concurrent POST /generate requests from same user
- **Expected**: At most 3 jobs accepted (concurrent limit enforced); remaining rejected with 409 or 402; final credit balance never goes below 0

---

## Gap Tests (Coverage Analysis Step 7)

### TC-801: Identity Preservation — Block Result Below Threshold
- **Priority**: P1 | **Story**: 4-3 | **Technique**: EG
- **Preconditions**: Test environment with mock fal.ai returning `identity_similarity_score < IDENTITY_SIMILARITY_THRESHOLD`
- **Steps**: 1. Submit generation; 2. Mock returns image with low similarity score; 3. Observe system behavior
- **Expected**: Job transitions to `failed` with `failure_reason = 'IDENTITY_PRESERVATION_FAILED'`; result NOT delivered to user; credit released; structured log fields `identity_similarity_score` and `identity_preserved = false` emitted

### TC-802: "Doesn't Look Like Me" — Self-Serve Credit Refund
- **Priority**: P1 | **Story**: 4-3 | **Technique**: ST
- **Preconditions**: Completed generation result visible to user
- **Steps**: 1. Tap "Doesn't look like me" feedback on generated image; 2. Confirm refund; 3. GET /entitlement/balance
- **Expected**: Credit/trial restored within 30s; re-generation offered without re-uploading image; no support ticket required; completion time ≤30s

### TC-803: TierConfig — TOTAL LimitType Enforced
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: Set `TIER__TRIAL__GENERATION__TYPE=total`, `LIMIT=2`; create 2 generations; attempt 3rd
- **Expected**: 3rd attempt returns 402; balance = 0; lifetime count = 2

### TC-804: TierConfig — DAILY LimitType Enforced
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: Set `TIER__TRIAL__GENERATION__TYPE=daily`, `LIMIT=1`; create 1 generation; attempt 2nd same day
- **Expected**: 2nd attempt returns 402; next calendar day, attempt succeeds

### TC-805: TierConfig — WEEKLY LimitType Enforced
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: Set `TIER__TRIAL__GENERATION__TYPE=weekly`, `LIMIT=3`; create 3 in 7 days; attempt 4th
- **Expected**: 4th returns 402 within the rolling 7-day window

### TC-806: TierConfig — PERIOD LimitType Enforced (Custom Seconds)
- **Priority**: P1 | **Story**: 4-1 | **Technique**: ST
- **Steps**: Set `TIER__TRIAL__GENERATION__TYPE=period`, `LIMIT=1`, `PERIOD_SECONDS=3600`; create 1 generation; attempt 2nd immediately; attempt again after 3601s
- **Expected**: 2nd attempt returns 402; attempt after period expires succeeds

### TC-807: TierConfig — UNLIMITED LimitType Allows All
- **Priority**: P1 | **Story**: 4-1 | **Technique**: EP
- **Steps**: Set `TIER__PREMIUM__GENERATION__TYPE=unlimited`; create 20+ generations as premium user
- **Expected**: All succeed; no 402 returned; only other limits apply (concurrent cap, cost ceiling)

### TC-808: TierConfig — CREDITS LimitType Uses Ledger
- **Priority**: P1 | **Story**: 4-1 | **Technique**: DT
- **Steps**: Set `TIER__CREDIT_HOLDER__GENERATION__TYPE=credits`; credit_holder user with 0 credits attempts generation
- **Expected**: 402 returned; with 1+ credits, generation succeeds; credit consumed from ledger

### TC-811: TLS 1.2+ Enforcement
- **Priority**: P1 | **Technique**: EP
- **Steps**: Run `testssl.sh https://api.nxme.ai`; attempt TLS 1.0 handshake: `openssl s_client -tls1 -connect api.nxme.ai:443`
- **Expected**: testssl.sh reports TLS 1.2 and 1.3 supported; TLS 1.0 and 1.1 handshake rejected (connection refused or handshake failure); AES-256 confirmed as cipher for at-rest encryption in Supabase dashboard

### TC-812: WCAG 2.1 AA — Automated Contrast Scan
- **Priority**: P1 | **Technique**: EP
- **Steps**: Run automated accessibility scan (e.g., axe DevTools or Expo accessibility linter) on all 9 mobile UI screens
- **Expected**: Zero contrast failures on primary text against background; interactive elements meet 3:1 contrast ratio; no critical WCAG violations

### TC-813: WCAG 2.1 AA — VoiceOver + TalkBack Manual Flow
- **Priority**: P1 | **Technique**: EP
- **Preconditions**: iOS VoiceOver enabled; Android TalkBack enabled
- **Steps**: Navigate full primary flow (registration → upload → view results → social feed → paywall) using screen reader only
- **Expected**: All interactive elements have meaningful labels; focus order is logical; no screen reader trap; images have alt text

### TC-814: Minimum OS — iOS 15.0 + Android API 29
- **Priority**: P1 | **Technique**: EP
- **Preconditions**: iOS 15.0 device or simulator; Android API 29 device or emulator
- **Steps**: Complete primary user flow on both minimum OS versions
- **Expected**: App launches without crash; all screens render; upload, generation, social feed, and paywall functional

### TC-815: CI Coverage Gate — face_analysis + entitlement ≥80%
- **Priority**: P2 | **Technique**: EP
- **Steps**: Run `pytest --cov=app/face_analysis --cov=app/entitlement --cov-fail-under=80`
- **Expected**: Both modules ≥80% line coverage; CI build fails if either drops below threshold

### TC-820: Anthropic Claude API — Error Path
- **Priority**: P1 | **Story**: 7-2 | **Technique**: EG
- **Preconditions**: Claude API mocked to return 500
- **Steps**: POST /advisor/messages as premium user
- **Expected**: User receives specific error message ("Advisor temporarily unavailable"); no message appended to `advisor_messages`; conversation session state consistent; no credit/session rollback issue

### TC-821: Polyglot File — JPEG Magic Bytes Wrapping Malicious Content Rejected
- **Priority**: P1 | **Story**: 3-1 | **Technique**: EG
- **Test Data**: Construct a file with valid JPEG magic bytes (FFD8FF) but ZIP content
- **Steps**: POST /analyses with polyglot file
- **Expected**: 422 Unprocessable; file rejected; not stored; magic-byte check confirms real JPEG required

### TC-822: Image Dimension — Pre-Decode Rejection at 8193px
- **Priority**: P1 | **Story**: 3-1 | **Technique**: BVA
- **Test Data**: Image with 8193×8193 pixel dimensions
- **Steps**: POST /analyses with oversized-dimension image
- **Expected**: 422 returned; image rejected before full decode; no memory exhaustion; rejection ≤1s

### TC-823: UNKNOWN Failure Reason Triggers Alert
- **Priority**: P2 | **Story**: 4-3 | **Technique**: EG
- **Steps**: Inject an unhandled exception type in generation worker; trigger generation
- **Expected**: Job fails with `failure_reason = 'UNKNOWN'`; alert emission logged; credit released; no silent failure

### TC-824: Analysis Response — No Attractiveness Field (Explicit Negative Assertion)
- **Priority**: P1 | **Story**: 3-2 | **Technique**: EG
- **Steps**: Complete analysis; parse full response JSON; check all field names
- **Expected**: Assertion passes: ZERO fields with names containing `score` (other than `symmetry_score`), `rating`, `rank`, `attractiveness`, `beauty`, or `hotness`

### TC-825: Minor Account — Upload Blocked Without Consent Step
- **Priority**: P1 | **Story**: 2-1 | **Technique**: ST
- **Steps**: Register account with age below minimum threshold; attempt POST /analyses without completing consent step
- **Expected**: 403 Forbidden; error explains consent required; consent step can be completed to unlock

### TC-826: Username Uniqueness — Concurrent Registration Race
- **Priority**: P1 | **Story**: 2-1 | **Technique**: EG
- **Steps**: Send two simultaneous POST /auth/register requests with identical username
- **Expected**: Exactly one returns 201; the other returns 409 Conflict; no duplicate username rows in DB

### TC-827: Username Immutability — Cannot Change After Creation
- **Priority**: P2 | **Story**: 2-1 | **Technique**: EP
- **Steps**: PATCH /users/me with `{"username": "newusername"}`
- **Expected**: 400 Bad Request or 405 Method Not Allowed; username unchanged; all existing shareable card URLs remain valid

### TC-828: Account Deletion — Primary Data Deleted Within 72h
- **Priority**: P2 | **Story**: 2-2 | **Technique**: ST
- **Steps**: Delete account; after 72 hours, verify primary data absence
- **Expected**: User row, analyses, posts, entitlement events deleted; Supabase Storage files deleted or scheduled for deletion within 72h

### TC-829: Account Deletion — Username Reserved for 180 Days
- **Priority**: P2 | **Story**: 2-2 | **Technique**: BVA
- **Steps**: Delete account with username "testuser"; immediately attempt to register with same username
- **Expected**: 409 Conflict; username reservation enforced for 180 days

### TC-830: Reaction Reconciliation — Counter Matches DB After Reconciliation Job
- **Priority**: P2 | **Story**: 5-2 | **Technique**: EG
- **Steps**: 1. Create known discrepancy (Redis counter = 10, DB reaction rows = 8); 2. Run reconciliation job; 3. Check `posts.reaction_count`
- **Expected**: `reaction_count` updated to match actual DB count (8); no data loss; Redis counter reset to authoritative value

### TC-831: Credit Rollback — All failure_reason Branches Release Credit
- **Priority**: P1 | **Story**: 4-3 | **Technique**: DT
- **Steps**: For each `failure_reason` enum value (`FACE_VALIDATION_FAILED`, `GENERATION_TIMEOUT`, `NSFW_QUARANTINE`, `IDENTITY_PRESERVATION_FAILED`, `PROVIDER_ERROR`, `UNKNOWN`), trigger the corresponding failure condition
- **Expected**: Each branch: credit released (not committed); `entitlement_events` shows `status = 'released'`; balance restored; no orphaned reserved credits

---

## Test Execution Checklist

Before starting manual testing run:
- [ ] All 30 stories at `status: done` in sprint-status.yaml
- [ ] Staging deployment verified (API responds to GET /health → 200)
- [ ] Stripe CLI connected to staging: `stripe listen --forward-to https://staging-api.nxme.ai/webhooks/stripe`
- [ ] Test user accounts created: trial (email+pw), credit_holder (credited), premium (subscribed)
- [ ] Supabase dashboard open with admin access
- [ ] Physical iOS device available for Apple Sign In + VoiceOver tests
- [ ] Android device or emulator (API 29) available for TalkBack tests
- [ ] ExifTool installed: `exiftool --version`
- [ ] testssl.sh available for TLS test (TC-811)
- [ ] fal.ai test credentials configured

After P1 tests pass:
- [ ] Begin E2E Playwright test authoring (see `docs/test-strategy.md` E2E Flows section)
