---
status: complete
feature: nxme
created: 2026-03-15T21:00:00.000Z
---

# Plan: NXME

## Decomposition Strategy

**Selected: Option A — Backend-First Vertical Slices**

Backend services are built and tested before mobile UI consumes them. This ensures mobile development targets verified API contracts rather than aspirational specs, eliminates cross-story interface mismatches, and makes each backend story independently deployable and testable. Foundation → Auth → Image Pipeline → Analysis → Entitlement → Generation → Social → Sharing & Profile → Mobile UIs.

*Alternatives considered:*
- Option B (Mobile-First with mocked backend): Faster early demo but accumulates mock debt and requires rework when real APIs differ from mocks.
- Option C (Full-Stack per feature): Creates horizontal coupling that forces same-wave ordering — breaks wave independence.

**PD-1: Backend-First Vertical Slices — LOCKED**
- Rationale: Wave independence requires a consumer (mobile UI) to depend on a provider (API). Reversing this creates circular same-wave dependencies.

---

## Epic 1: Foundation

### Story 1-1: Database Schema, Migrations & App Config [M]
**User Story:** As a developer, I want all database tables and application configuration constants defined before implementation begins, so that all stories code against verified schemas and constants rather than ad-hoc definitions.
**Dependencies:** None
**Wave:** 1

**Acceptance Criteria:**
- Given all 13 tables from the architecture (users, analyses, glow_up_jobs, credit_reservations, credit_ledger, subscriptions, images, posts, reactions, comments, shareable_cards, reports, processed_webhook_events), When migrations are applied, Then schema matches the architecture data models exactly including all CHECK constraints, indexes, and foreign keys.
- Given a fresh database with migrations applied, When a CI migration cycle (up → seed → down → up) runs, Then it completes without errors.
- Given the config module, When any component reads `FREE_TRIAL_ANALYSES`, `IDENTITY_SIMILARITY_THRESHOLD`, `GENERATION_TIMEOUT_SECONDS`, `MAX_CONCURRENT_GENERATIONS_PER_USER`, `MAX_UPLOAD_SIZE_MB`, `MAX_IMAGE_DIMENSION_PX`, `CREDIT_COST_ALERT_USD`, `IMAGE_GEN_COST_CEILING_USD`, Then it reads from a named constant — grep asserts zero inline numeric literals for these values outside the config module.
- Given the tier identifier module, When any code uses tier values, Then it uses exactly `TRIAL`, `CREDIT_HOLDER`, `PREMIUM` from named constants — grep asserts zero inline string literals outside the constants file.

**FR Coverage:** FR-2 (trial constant), FR-7, FR-8 (face_shape/symmetry_score schema)
**NFR Coverage:** NFR-16 (CI gate foundation)

---

### Story 1-2: ADR-1, ADR-2, and OQ-1 Resolution [S]
**User Story:** As a developer, I want all critical architecture decisions documented as ADRs before implementation begins, so that stories touching biometric data and reactions are built on a defined legal and design basis.
**Dependencies:** None
**Wave:** 1

**Acceptance Criteria:**
- Given ADR-1 (Biometric Data Lifecycle), When the ADR file is read, Then it documents that landmark vectors and ArcFace embeddings are ephemeral (computed in-request, never persisted), specifies the legal basis under GDPR, and documents the consent model (AC-A4).
- Given ADR-2 (Guest Attribution), When the ADR file is read, Then it documents the `guest_session_token` strategy: a durable 32-byte CSPRNG token issued at first app open, stored in Expo SecureStore, with 365-day server-side TTL, and analytics attribution on account creation.
- Given OQ-1 (Guest Reaction Attribution), When the ADR file is read, Then it documents the resolution: guest reactions are session-scoped (ephemeral) — not retroactively attributed on account creation — with documented rationale; this ADR file must exist before the reactions story (5-2) enters implementation (AC-D3).
- Given the ADR directory, When the ADR file names are checked, Then they follow the naming convention `docs/adr/ADR-NNN-{title}.md`.

**FR Coverage:** FR-20 (guest reaction attribution model), FR-5 (biometric data deletion)
**NFR Coverage:** NFR-10 (biometric data lifecycle), NFR-12 (encryption documentation)

---

## Epic 2: Auth & Account Management

### Story 2-1: Auth API — Registration, Email Verification & Trial Grant [M]
**User Story:** As a guest, I want to create an account with email/password or social login, so that I receive my free trial analyses and can access the full app.
**Dependencies:** 1-1
**Wave:** 2

**Acceptance Criteria:**
- Given `POST /register` with valid email + password, When the request is handled, Then a user row is created with `tier = 'TRIAL'`, `trial_analyses_remaining = FREE_TRIAL_ANALYSES`, `email_verified = false`, and a verification email is sent; free trial credits are NOT granted until email is verified.
- Given a user who completes email verification, When `TrialGrantor.grant(user_id)` is called, Then `trial_analyses_remaining` is set to `FREE_TRIAL_ANALYSES` idempotently — calling twice does not double-grant.
- Given registration from the same device fingerprint, When ≥3 account creation attempts occur within 24 hours, Then HTTP 429 is returned and no new account is created (AC-A8).
- Given a disposable email domain, When registration is attempted, Then HTTP 422 is returned and no trial credits are granted (AC-A8).
- Given a fresh account, When `GET /entitlement` is called, Then the response returns `{ "tier": "TRIAL", "trial_analyses_remaining": <FREE_TRIAL_ANALYSES>, "credit_balance": 0, "can_generate": true }`.
- Given an age-gate check during registration (AC-U7), When the user confirms they meet minimum age, Then the `is_minor` field is set appropriately and the account is created; minor-flagged accounts cannot access the upload endpoint until a consent step is completed.

**Interface Contract:**
- `TrialGrantor.grant(user_id: UUID) -> None` — Location: `entitlement/trial_grantor.py`
- `POST /register` → `{ user_id, username, email_verification_required: bool }` — HTTP 201

**FR Coverage:** FR-1, FR-2, FR-3
**NFR Coverage:** NFR-16 (≥80% coverage — TrialGrantor unit tests required)

---

### Story 2-2: Auth API — Social Login, JWT Validation, Logout & Account Deletion [M]
**User Story:** As a registered user, I want to log in with social providers, manage my session, and permanently delete my account, so that I control my data and can access the app securely.
**Dependencies:** 2-1
**Wave:** 3

**Acceptance Criteria:**
- Given `POST /login` with a social OAuth PKCE authorization code, When validated, Then a JWT is issued; implicit-flow tokens are rejected with HTTP 401; custom URI scheme redirects are rejected; `id_token` claims (`iss`, `aud`, `exp`, `nonce`) are validated (AC-A9).
- Given `POST /logout`, When the request is processed, Then the session is invalidated server-side within ≤1s; subsequent API requests with the invalidated token return HTTP 401; the client navigates to unauthenticated state (AC-FR9).
- Given `DELETE /account`, When the request is processed, Then primary storage deletion completes within 72h; the shareable card URL returns HTTP 410; the username is reserved (not reassignable) for 180 days (AC-FR5).
- Given a rate-limited IP sending ≥4 account creation attempts per hour, When registration is attempted, Then HTTP 429 is returned (AC-A8 per-IP limit).

**Interface Contract:**
- JWT validation middleware: `validate_jwt(token: str) -> UserClaims` — Location: `api/middleware/auth.py`

**FR Coverage:** FR-3, FR-4, FR-5
**NFR Coverage:** NFR-12 (TLS, JWT validation)

---

### Story 2-3: Mobile Auth UI — Login, Signup Screens [M]
**User Story:** As a guest on the mobile app, I want to register or log in through a clear native interface, so that I can access my account and start using NXME.
**Dependencies:** 2-2, 6-5
**Wave:** 9

**Acceptance Criteria:**
- Given the signup screen, When a user completes registration, Then the `AuthModule` calls `POST /register`; an email verification prompt is shown; after verification, the user is navigated to the home feed with trial count visible.
- Given the login screen, When a user submits valid credentials, Then the `AuthModule` calls `POST /login`; the JWT is stored in Expo SecureStore; the app navigates to the authenticated home feed.
- Given a social login button (Google, Apple), When tapped, Then the OAuth PKCE flow opens in an in-app browser; Universal Links handle the callback redirect; custom URI scheme redirects are not used.
- Given the screen design, When rendered on iOS 15+ and Android 10+, Then all interactive elements meet WCAG 2.1 AA contrast (4.5:1 for normal text), buttons use `--color-accent-after-filled` (#E11D48) for white label backgrounds.

**FR Coverage:** FR-1, FR-3
**NFR Coverage:** NFR-13 (WCAG AA), NFR-15 (iOS 15+, Android 10+)

---

### Story 2-4: Contextual Onboarding & Push Notification Registration [S]
**User Story:** As a new user arriving from a shared card CTA, I want a contextual welcome screen that shows my trial count and prompts me to try my own analysis, so that I immediately understand the product's value.
**Dependencies:** 2-3, 6-2
**Wave:** 10

**Acceptance Criteria:**
- Given a new user who completed signup via the shared card CTA, When the app navigates post-registration, Then the destination screen shows (a) the remaining free trial count (`FREE_TRIAL_ANALYSES`) and (b) a prominent upload/analyze prompt — NOT a generic home feed (AC-U6).
- Given any new user, When the onboarding screen is shown, Then a push notification opt-in prompt is displayed using Expo Notifications; declining does not block app access.
- Given a user on the contextual onboarding screen, When they tap the analyze prompt, Then they are navigated directly to the upload screen (Story 3-4).

**FR Coverage:** FR-2, FR-28
**NFR Coverage:** NFR-15

---

## Epic 3: Image Upload & Face Analysis

### Story 3-1: Image Pipeline Service — NSFW Screening, EXIF Strip & Storage [M]
**User Story:** As the platform, I need every uploaded selfie to pass safety screening and have all metadata removed before storage, so that NSFW content is never stored and user PII (EXIF) is never exposed.
**Dependencies:** 1-1
**Wave:** 3

**Acceptance Criteria:**
- Given an uploaded image with magic bytes not matching JPEG/PNG/HEIF, When `ImagePipeline.process()` is called, Then HTTP 422 `IMAGE_FORMAT_REJECTED` is returned and no file is written to storage (AC-A10).
- Given an image exceeding `MAX_UPLOAD_SIZE_MB` or `MAX_IMAGE_DIMENSION_PX × MAX_IMAGE_DIMENSION_PX`, When processed, Then HTTP 422 `IMAGE_TOO_LARGE` is returned with no storage write.
- Given an image that AWS Rekognition scores ≥80% confidence for explicit content, When processed, Then an `images` row is created with `status = 'quarantined'`, `storage_key = NULL`; no file is written to the `raw-selfies` bucket; HTTP 422 `IMAGE_QUARANTINED` is returned within ≤5s (AC-A3, AC-NFR14).
- Given an accepted image, When the full pipeline runs (validate → NSFW screen → strip EXIF → re-encode), Then the stored file has zero EXIF/IPTC/XMP metadata — uploading a JPEG with GPS coordinates results in zero location metadata in the stored file (AC-FR3).
- Given the `raw-selfies` bucket, When an unsigned request attempts to read any object, Then HTTP 403 is returned (AC-NFR10).

**Interface Contract:**
- `ImagePipeline.process(file_bytes: bytes, content_type: str) -> ProcessedImage` — Location: `image_pipeline/pipeline.py`
- `ProcessedImage = { storage_key: str, image_id: UUID, status: Literal['cleared', 'quarantined'] }`

**FR Coverage:** FR-6
**NFR Coverage:** NFR-10 (signed URLs / private bucket), NFR-14 (NSFW ≤5s)

---

### Story 3-2: Face Analysis Service — MediaPipe, Classification & Recommendations [M]
**User Story:** As a registered user, I want my selfie analyzed to receive a face shape classification, symmetry score, and top 5 improvement suggestions, so that I understand my unique features and get personalized style advice.
**Dependencies:** 1-1
**Wave:** 4

**Acceptance Criteria:**
- Given an image with a clearly visible single face, When `FaceAnalysisService.analyze()` is called, Then it returns a `face_shape` from `{oval, round, square, heart, oblong}` and a `symmetry_score` in `[0.0, 1.0]`; no attractiveness score or rank is present in the response (AC-FR10).
- Given the MediaPipe FaceMesh model, When the ECS container starts, Then the model is pre-loaded in the FastAPI `lifespan` handler; `GET /health` returns HTTP 200 only after model load; the first analysis request after scale-out does not trigger a cold-load delay.
- Given a standard analysis request, When the full pipeline (validate → extract landmarks → classify → score → recommend) runs on 4-core hardware with pre-loaded model, Then total latency is ≤3s at P95 (AC-NFR1).
- Given two identical images, When analyzed, Then landmark vectors are NOT stored — only `face_shape`, `symmetry_score`, and `recommendations` are written to the `analyses` table (ADR-1 enforcement).
- Given the `recommendations` output, When reviewed, Then no suggestion text contains attractiveness-rating language; all 5 suggestions are tied to the classified face shape and measured proportions.

**Interface Contract:**
- `FaceAnalysisService.analyze(image_storage_key: str) -> AnalysisResult` — Location: `face_analysis/service.py`
- `AnalysisResult = { face_shape: FaceShape, symmetry_score: float, recommendations: list[Suggestion] }`

**FR Coverage:** FR-7, FR-8, FR-9
**NFR Coverage:** NFR-1 (≤3s P95), NFR-16 (≥80% coverage CI gate)

---

### Story 3-3: Analysis API Endpoint — POST /analyses [S]
**User Story:** As a registered user, I want to submit a selfie for face analysis via the API, so that I receive an analysis ID and can retrieve results.
**Dependencies:** 3-1, 3-2
**Wave:** 5

**Acceptance Criteria:**
- Given `POST /analyses` with a valid selfie, When the handler runs, Then `ImagePipeline.process()` runs first (NSFW gate), then `FaceAnalysisService.analyze()` runs; an `analyses` row is created with `status = 'completed'`; HTTP 201 is returned with `{ analysis_id, face_shape, symmetry_score, recommendations }`.
- Given a quarantined image, When `POST /analyses` is called, Then `FaceAnalysisService.analyze()` is never called; HTTP 422 `IMAGE_QUARANTINED` is returned; no trial or credit is consumed.
- Given `GET /analyses/{id}`, When called by the owning user, Then the full analysis result is returned; when called by a different user, HTTP 403 is returned.
- Given a face validation failure (no face detected, multiple faces, obstructed), When `POST /analyses` is processed, Then a distinct `IMAGE_FORMAT_REJECTED` or appropriate error code is returned; no trial is consumed (AC-U4).

**FR Coverage:** FR-6, FR-7, FR-8, FR-9, FR-13
**NFR Coverage:** NFR-1 (pipeline latency), NFR-16 (coverage gate on image pipeline)

---

### Story 3-4: Mobile Upload & Result UI [M]
**User Story:** As a registered user, I want a native mobile screen to upload a selfie and see my before/after glow-up result with improvement suggestions, so that I can experience the full transformation reveal.
**Dependencies:** 3-3, 4-3, 2-3
**Wave:** 10

**Acceptance Criteria:**
- Given the upload screen, When the user opens it, Then the remaining free trial count is visible; the "Analyze" CTA is disabled until a photo is selected (wireframe Screen 3 states).
- Given a selected photo, When the user taps "Analyze My Glow-Up", Then `UploadModule` calls `POST /analyses`; a loading state with elapsed timer is shown within ≤2s of submission (AC-U1/AC-NFR2).
- Given face validation failure, When a distinct error code is returned (`FACE_NOT_DETECTED`, `MULTIPLE_FACES`, etc.), Then the UI displays a distinct actionable message for each failure mode with resolution guidance; trial count is unchanged (AC-U4).
- Given a completed glow-up job, When the result screen (Screen 2) renders, Then the before/after reveal animation plays (before slides in → pause → after wipes from right + glow ring expands → suggestion pills stagger up → CTAs fade in); tapping before/after opens fullscreen lightbox.
- Given the "This doesn't look like me" feedback action (AC-U8), When tapped, Then the credit/trial is automatically refunded, a re-generation is offered without re-upload, and the refund completes within 30s.
- Given a Cancel action during generation, When tapped before result delivery, Then `POST /jobs/{id}/cancel` is called; trial count and credit balance are unchanged (AC-U1, AC-U3).

**FR Coverage:** FR-6, FR-10, FR-11, FR-12, FR-13, FR-16
**NFR Coverage:** NFR-2 (≤30s generation, progress indicator ≤2s), NFR-13 (WCAG AA), NFR-15

---

## Epic 4: Entitlement, Generation & Monetization

### Story 4-1: Entitlement Service — Credit Ledger, State Machine & Trial Grant [M]
**User Story:** As the platform, I need a single authoritative entitlement module that manages credit balances, subscription states, and trial grants, so that no feature handler ever directly reads raw credit or subscription database fields.
**Dependencies:** 1-1
**Wave:** 4

**Acceptance Criteria:**
- Given `EntitlementService.get_entitlement(user_id)`, When called, Then it recomputes from `credit_ledger + subscriptions` tables; `users.tier` is updated as a denormalized cache in the same transaction but is never the sole source of truth (AC-D1).
- Given `EntitlementService.can_generate(user_id)`, When called, Then it returns `{ can_generate: bool, reason: str | None }` — a user with `tier = 'TRIAL'` and `trial_analyses_remaining = 0` returns `can_generate: False`.
- Given the credit ledger, When `CreditLedger.reserve(user_id)` is called, Then a ledger entry with `type='reserve', delta=-1` is created; `CreditLedger.release(reservation_id)` creates `type='release', delta=+1`; `CreditLedger.commit(reservation_id)` creates `type='commit', delta=0` — all three invariants (reserve+release=0, reserve+commit=-1) are verified by unit tests (Section 3.5 invariants).
- Given a grep scan of the entire codebase, When `EntitlementService` is complete, Then zero occurrences of direct `credit_ledger` or `subscriptions` table reads exist outside the entitlement module (AC-D1).
- Given any code referencing tier values, When scanned, Then only `TRIAL`, `CREDIT_HOLDER`, `PREMIUM` string constants are used — zero inline literals.

**Interface Contracts:**
- `EntitlementService.get_entitlement(user_id: UUID) -> EntitlementState` — Location: `entitlement/service.py`
- `EntitlementService.can_generate(user_id: UUID) -> CanGenerateResult` — Location: `entitlement/service.py`
- `CreditLedger.reserve(user_id: UUID) -> UUID` (reservation_id) — Location: `entitlement/ledger.py`
- `CreditLedger.release(reservation_id: UUID) -> None` — Location: `entitlement/ledger.py`
- `CreditLedger.commit(reservation_id: UUID) -> None` — Location: `entitlement/ledger.py`

**FR Coverage:** FR-10, FR-11, FR-12, FR-14, FR-16
**NFR Coverage:** NFR-16 (≥80% coverage — entitlement module CI gate)

---

### Story 4-2: Generation Queue & ARQ Worker [L]
**User Story:** As the platform, I need an async priority job queue with per-tier lanes, credit lifecycle management, and a stuck-job watchdog, so that glow-up generation scales to 10k concurrent requests without dropping jobs or permanently consuming credits on failure.
**Dependencies:** 4-1
**Wave:** 5

**L Justification:** Priority lane configuration, job lifecycle state machine, stuck-job watchdog, circuit breakers, and `GlowUpGeneratorPort` are all deeply interdependent. Testing priority ordering requires the full worker configuration; the credit release on stuck jobs requires the watchdog. Splitting creates an untestable intermediate state where the queue exists but the safety guarantees do not.

**Acceptance Criteria:**
- Given three queue lanes (`generation:premium`, `generation:credit`, `generation:trial`), When an ARQ Worker with explicit queue ordering is started, Then premium jobs are always processed before credit jobs, which are processed before trial jobs — verified by asserting order under mixed-lane load.
- Given 12,000 simultaneous generation requests, When submitted, Then zero HTTP 5xx responses occur; excess requests are queued and all clients receive a queued-status response within ≤5s (AC-NFR6).
- Given a job that exceeds `GENERATION_TIMEOUT_SECONDS + 30`, When the stuck-job watchdog runs, Then the job transitions to `status='failed'`, `failure_reason='GENERATION_TIMEOUT'`, and the credit reservation is released — credits are never permanently consumed by a stuck job (AC-D2).
- Given the `GlowUpGeneratorPort` Protocol, When a mock implementing it is injected, Then `process_generation_job` completes the full lifecycle (reserve → generate → identity check → commit/release) using only the port interface — no direct fal.ai API calls in the worker function.
- Given rolling 24h cost average exceeding `IMAGE_GEN_COST_CEILING_USD`, When the circuit breaker checks, Then new `TRIAL` lane enqueues are throttled and an alert is emitted (AC-A6, AC-NFR9).

**Interface Contracts:**
- `GlowUpGeneratorPort.generate(source_image_url: str, prompt: str, options: GenerationOptions) -> GenerationResult` — Protocol location: `generation/ports.py`
- `FalAiAdapter` implements `GlowUpGeneratorPort` — Location: `generation/adapters/falai.py`
- `process_generation_job(ctx, job_id: UUID) -> None` — ARQ worker function, Location: `generation/worker.py`

**FR Coverage:** FR-10, FR-11, FR-12
**NFR Coverage:** NFR-2 (≤30s P95), NFR-6 (10k concurrent queue), NFR-8 (99.0% uptime), NFR-9 (≤$0.05/image)

---

### Story 4-3: Generation API — POST /generate, Job Polling & Cancel [M]
**User Story:** As a registered user, I want to trigger glow-up generation, poll for job status, and cancel in-flight jobs, so that I see my result within 30 seconds and never lose a credit to a failure.
**Dependencies:** 4-2, 3-3
**Wave:** 6

**Acceptance Criteria:**
- Given `POST /analyses/{id}/generate` by a user with `can_generate = True`, When handled, Then: (1) `SELECT FOR UPDATE` checks in-flight count ≤ `MAX_CONCURRENT_GENERATIONS_PER_USER`; (2) `CreditLedger.reserve()` is called; (3) job is enqueued into the user's tier lane; HTTP 202 `{ job_id }` is returned.
- Given a second concurrent generation request from the same user while one is in-flight, When submitted, Then HTTP 409 `CONCURRENT_LIMIT` is returned; credit is not reserved (AC-A11).
- Given any generation failure (timeout, provider error, identity preservation failed), When the worker fails, Then `CreditLedger.release()` is called before the error response; `GET /jobs/{id}` reflects the failure reason; the credit balance is unchanged compared to before the job started (AC-U3, AC-D2).
- Given `POST /jobs/{id}/cancel` called before completion, When handled, Then `CreditLedger.release()` is called; the job transitions to `status='cancelled'`; trial count and credit balance are unchanged (AC-U1).
- Given `GET /jobs/{id}` with `status='queued'`, When responded, Then `{ status: 'queued', estimated_wait_seconds: <int> }` is returned within ≤2s (AC-NFR2 progress indicator).

**FR Coverage:** FR-10, FR-11, FR-12
**NFR Coverage:** NFR-2, NFR-8, NFR-16

---

### Story 4-4: Stripe Adapter — Credit Purchase, Subscription & Webhook Idempotency [M]
**User Story:** As the platform, I need Stripe integrated for credit pack purchases and subscription lifecycle, with idempotent webhook handling, so that no raw card data touches NXME servers and payment events are processed exactly once.
**Dependencies:** 4-1
**Wave:** 6

**Acceptance Criteria:**
- Given `POST /credits/purchase`, When processed, Then a Stripe checkout session is created; no raw card data (PAN, CVV, expiry) is transmitted through any NXME-controlled endpoint — verified by network traffic audit (AC-NFR11).
- Given Stripe webhook `checkout.session.completed` delivered twice (retry scenario), When processed, Then the first delivery inserts into `processed_webhook_events(provider='stripe', event_id='evt_xxx')` and processes; the second delivery returns HTTP 200 immediately without re-processing (idempotency constraint).
- Given `customer.subscription.deleted` webhook, When processed, Then `subscriptions.status = 'expired'`; `EntitlementService.get_entitlement()` recomputes tier — if `credit_balance > 0` → `CREDIT_HOLDER`, else → `TRIAL`.
- Given a Stripe webhook without a valid `stripe-signature` header, When received, Then HTTP 401 is returned and no processing occurs.
- Given a Premium subscription cancellation, When `billing_period_end - 1s`, Then Premium access is granted; at `billing_period_end + 1s`, access is reverted — verified by clock-controlled test (AC-FR4).

**FR Coverage:** FR-15, FR-17, FR-18
**NFR Coverage:** NFR-11 (PCI-DSS SAQ-A)

---

### Story 4-5: Monetization API — Subscription CRUD & Credits Entitlement Endpoint [S]
**User Story:** As a registered user, I want API endpoints to manage my subscription and view my entitlement state, so that the mobile app can display real-time credit balance and paywall options.
**Dependencies:** 4-4
**Wave:** 7

**Acceptance Criteria:**
- Given `GET /entitlement`, When called by any authenticated user, Then `{ tier, trial_analyses_remaining, credit_balance, can_generate, subscription_status, billing_period_end }` is returned with ground truth from the ledger (never from `users.tier` cache).
- Given `POST /subscriptions`, When called, Then a Stripe checkout session is returned; the subscription flow is initiated; HTTP 402 is not returned for users who already have an active subscription.
- Given `DELETE /subscriptions`, When called, Then `cancel_at_period_end` is set on Stripe; the subscription row has `cancelled_at` set; Premium access continues until `billing_period_end`.
- Given `GET /entitlement` for a user with 0 trials, 0 credits, no subscription, When the paywall is triggered, Then the response includes all purchase options: available credit pack sizes and Premium subscription pricing (AC-FR2).

**FR Coverage:** FR-14, FR-15, FR-16, FR-17, FR-18
**NFR Coverage:** NFR-11

---

### Story 4-6: Mobile Paywall UI — Credits Screen & Stripe Payment Sheet [M]
**User Story:** As a registered user who has exhausted my free trials, I want a clear paywall screen showing credit pack options and Premium subscription pricing, so that I can purchase more analyses.
**Dependencies:** 4-5, 2-3
**Wave:** 10

**Acceptance Criteria:**
- Given a user with `can_generate = false`, When they tap the generate action, Then the paywall modal appears before any generation pipeline call is made; the modal shows all credit pack sizes and Premium subscription pricing (AC-U2, AC-FR2).
- Given the paywall screen (wireframe Screen 6), When rendered, Then the credit badge shows remaining balance; credit packs and subscription options are displayed with correct pricing; "Subscribe Now" uses Stripe Payment Sheet via React Native SDK.
- Given a successful subscription purchase, When the Stripe webhook is processed, Then the credit chip in the app updates with animation; Premium access is immediately reflected in `GET /entitlement`.
- Given a purchase in progress, When the button state is checked, Then a loading state is shown; the button is not tappable during processing.
- Given the screen design, When rendered, Then all text meets WCAG 2.1 AA contrast; primary CTA uses `--color-accent-after-filled` (#E11D48) for white label text (4.70:1 ≥ 4.5:1).

**FR Coverage:** FR-14, FR-15, FR-16, FR-17, FR-18
**NFR Coverage:** NFR-11, NFR-13 (WCAG AA)

---

## Epic 5: Social Layer

### Story 5-1: Social Feed API — Paginated Feed & Sort Strategies [M]
**User Story:** As any user (guest or registered), I want to browse the social feed with filtering options, so that I can discover transformations ordered by newest, trending, or biggest improvements.
**Dependencies:** 1-1
**Wave:** 7

**Acceptance Criteria:**
- Given `GET /feed` with no auth header, When called, Then HTTP 200 with feed posts is returned — zero authenticated API calls are required (AC-FR6).
- Given `GET /feed?sort=newest`, When called, Then posts are ordered by `created_at DESC`; posts with `images.status != 'cleared'` are excluded from all results (AC-D7).
- Given `GET /feed?sort=biggest_improvements`, When called, Then posts are ordered by `reaction_count DESC`; no AI-computed appearance score, symmetry delta, or model output field is referenced in the sort query (AC-U10).
- Given 10,000 concurrent feed readers on simulated 4G, When `GET /feed` is called, Then first 10 posts render within ≤2s at P95 (AC-NFR3).
- Given cursor-based pagination, When `cursor` param is provided, Then the next page continues from the correct position without duplicates.

**FR Coverage:** FR-19, FR-22
**NFR Coverage:** NFR-3 (≤2s P95 feed), NFR-5 (50k concurrent)

---

### Story 5-2: Guest Session & Reactions [M]
**User Story:** As a guest user, I want to react to feed posts without creating an account, so that I can engage with the community immediately.
**Dependencies:** 5-1, 1-2
**Wave:** 7

**Acceptance Criteria:**
- Given first app launch (no account), When the app starts, Then a durable 32-byte CSPRNG guest session token is issued and stored in Expo SecureStore; all reaction requests include `X-Guest-Token` header.
- Given `POST /posts/{id}/react` with a valid `X-Guest-Token`, When handled, Then: (1) Redis `INCR posts:{id}:reactions` counter (optimistic); (2) reactions DB row inserted via ARQ background task with retry queue (not fire-and-forget); HTTP 200 `{ reaction_count: <updated> }` returned immediately.
- Given the same guest token reacting to the same post twice in the same session, When the second reaction is sent, Then it is deduplicated (UNIQUE constraint on `post_id, guest_session_token`); HTTP 200 returns the same count (AC-U9).
- Given the reaction edge (≥10 reactions per IP per 5 minutes), When exceeded, Then HTTP 429 is returned; posts with reaction velocity >3 std deviations above baseline are flagged (AC-A12).
- Given a nightly reconciliation job, When it runs, Then `posts.reaction_count` and Redis counters are reconciled from `COUNT(reactions)` for all posts active in the previous 48 hours.

**FR Coverage:** FR-20
**NFR Coverage:** NFR-5

---

### Story 5-3: Comments, Reports & Post CRUD API [S]
**User Story:** As a registered user, I want to post comments, report posts, create posts from analysis results, and delete my own posts, so that I can participate in the community.
**Dependencies:** 5-1, 4-3
**Wave:** 8

**Acceptance Criteria:**
- Given `POST /posts/{id}/comments` without authentication, When called, Then HTTP 401 is returned; registration is required to comment (AC-U6, assumption A-6).
- Given `GET /posts/{id}/comments`, When called without auth, Then HTTP 200 with comments is returned — public read requires no account (FR-22, AC-FR6).
- Given `POST /posts` from a user with a completed glow-up job, When a caption is optionally included, Then a post row is created; the user's shareable card at `nxme.ai/{username}` is updated via on-demand ISR revalidation; if the user already has a shareable card, a confirmation dialog payload is included in the response (AC-U5).
- Given `DELETE /posts/{id}` by the post owner, When processed, Then `is_deleted = TRUE`; the post no longer appears in feed or profile; the shareable card is updated (AC-FR5 content deletion flow).
- Given `POST /posts/{id}/report`, When submitted, Then a `reports` row is created with `status='pending'`; the reporter does not see the post removed immediately.

**FR Coverage:** FR-21, FR-22, FR-23, FR-24, FR-25
**NFR Coverage:** NFR-14 (content moderation reporting)

---

### Story 5-4: Mobile Social Feed UI [M]
**User Story:** As any user, I want to browse the social feed with reaction buttons and tab navigation, so that I can discover transformations and engage with the community from my phone.
**Dependencies:** 5-2, 5-3, 6-5
**Wave:** 10

**Acceptance Criteria:**
- Given the feed screen (wireframe Screen 1), When rendered, Then the first 10 posts display within ≤2s on 4G; infinite scroll loads skeleton cards at the bottom.
- Given a reaction button on a feed card, When tapped by a guest, Then an optimistic UI update shows the incremented count immediately; the same post cannot be reacted to twice in the same session.
- Given the tab bar (wireframe Screen 1 bottom), When the active tab is home, Then the home tab icon is coral with a 2px top strip; other tabs are in `--color-accent-before`.
- Given pull-to-refresh, When triggered, Then a coral spinner appears and the feed refreshes.
- Given a long-press on a post card, When triggered, Then a context menu appears with share and report options.

**FR Coverage:** FR-19, FR-20, FR-22
**NFR Coverage:** NFR-3, NFR-13, NFR-15

---

### Story 5-5: Mobile Comments UI [S]
**User Story:** As a registered user, I want to view and post comments on a feed post, so that I can engage in discussions about transformations.
**Dependencies:** 5-4, 5-3
**Wave:** 11

**Acceptance Criteria:**
- Given tapping a comment icon on a feed card, When triggered, Then a bottom sheet slides up showing the comment list.
- Given a guest tapping the comment input, When they attempt to type, Then an authentication prompt appears asking them to create an account.
- Given a registered user posting a comment, When submitted, Then the comment appears in the list immediately (optimistic UI); on API failure, the comment is removed with an error toast.
- Given the comment list, When rendered, Then it shows the commenter's avatar, display name, timestamp, and comment text; deleted comments show "Comment removed" placeholder.

**FR Coverage:** FR-21, FR-22
**NFR Coverage:** NFR-13, NFR-15

---

## Epic 6: Sharing, Profile & Acquisition

### Story 6-1: Shareable Card API [S]
**User Story:** As the platform, I need a public API endpoint that returns card data for a given username, supporting HTTP 410 for deleted accounts, so that the Next.js card page can render without authentication.
**Dependencies:** 5-3
**Wave:** 8

**Acceptance Criteria:**
- Given `GET /api/public/cards/{username}` for a user with a published post, When called without auth, Then HTTP 200 returns `{ username, before_image_url, after_image_url, recommendations: [top-5], reaction_count, comment_count }` — zero authentication required (AC-FR8, AC-A7).
- Given `GET /api/public/cards/{username}` for a deleted account or deleted post, When called, Then HTTP 410 Gone is returned; the Next.js page renders a 410 response.
- Given a username blocked by the reserved-word list (`feed`, `api`, `login`, `pricing`, `static`, `admin`, `health`), When registration attempted with that username, Then HTTP 422 is returned (AC-A5).
- Given two users attempting to register the same username simultaneously, When both requests are processed, Then exactly one succeeds and the other receives HTTP 409; usernames are globally unique (AC-A5).

**FR Coverage:** FR-26, FR-27
**NFR Coverage:** NFR-4 (card FCP — this endpoint must respond within ≤500ms to enable the 2s FCP target)

---

### Story 6-2: Next.js Shareable Card Web App [M]
**User Story:** As a guest opening a shared link, I want to see the full before/after glow-up card without logging in, so that I'm motivated to try NXME myself.
**Dependencies:** 6-1
**Wave:** 9

**Acceptance Criteria:**
- Given `nxme.ai/{username}` loaded in an unauthenticated browser, When the page loads, Then the before/after images and all 5 improvement suggestions are fully visible without any login prompt (AC-FR8).
- Given Next.js ISR with `revalidate: 60`, When the page is served, Then FCP occurs within ≤2s at P95 on 4G from 3+ geographic regions (AC-NFR4); before/after images are served from CloudFront CDN with public read access.
- Given the page Open Graph tags, When a shared link is previewed in WhatsApp/Twitter/iMessage, Then `og:image` shows the before/after composite at 1200×630 with the username.
- Given the "Get Your Free Glow-Up →" CTA, When tapped on a device with the app installed, Then a Universal Link opens the app; on a device without the app, then the App Store/Play Store is opened.
- Given on-demand revalidation triggered by post deletion, When the Next.js revalidate API is called, Then the card page reflects the deletion within ≤60s maximum staleness.

**FR Coverage:** FR-27, FR-28
**NFR Coverage:** NFR-4 (≤2s FCP)

---

### Story 6-3: User Profile & History API [S]
**User Story:** As a registered user, I want API endpoints for my public profile and transformation history, so that I can view my past analyses and share my public profile.
**Dependencies:** 1-1, 5-3
**Wave:** 8

**Acceptance Criteria:**
- Given `GET /users/{username}/profile`, When called without auth, Then the public profile data is returned: `{ username, display_name, avatar_url, post_count, reaction_count, streak_days }`.
- Given `GET /users/{username}/history` called by the profile owner, When the user has completed N analyses, Then N entries are returned in reverse chronological order with before/after images and recommendations (AC-FR7).
- Given `GET /users/{username}/history` called by a different user, When processed, Then HTTP 403 is returned — transformation history is private.
- Given a user updating display name or avatar via `PATCH /users/{username}`, When the request is valid, Then `display_name` or `avatar_storage_key` is updated; username itself cannot be changed (AC-A5).

**FR Coverage:** FR-29, FR-30, FR-31
**NFR Coverage:** NFR-5

---

### Story 6-4: Mobile Profile UI [M]
**User Story:** As a registered user, I want to view my profile page with transformation history, stats, and sharing controls, so that I can track my journey and manage my presence on NXME.
**Dependencies:** 6-3, 5-4
**Wave:** 11

**Acceptance Criteria:**
- Given the profile screen (wireframe Screen 4), When opened for my own profile, Then avatar, username, post count, reaction count, and streak days are displayed; "Edit Profile" and "Share" buttons are visible.
- Given the "All Glow-Ups" tab, When active, Then a 3-column grid of before/after thumbnails is shown with coral reaction count badges in each corner.
- Given the "Reactions" tab, When active, Then posts the user has reacted to are listed.
- Given the "Edit Profile" button, When tapped, Then a sheet opens allowing display name and avatar photo changes; `PATCH /users/{username}` is called on save.
- Given the share button, When tapped, Then the native share sheet opens with the `nxme.ai/{username}` URL and a card preview.

**FR Coverage:** FR-29, FR-30, FR-31
**NFR Coverage:** NFR-13, NFR-15

---

### Story 6-5: Deep Links, Navigation Shell & App Initialization [M]
**User Story:** As a mobile app user, I want the app to handle Universal/App Links correctly and render the tab bar navigation shell, so that shared links open the right screen and I can navigate between all features.
**Dependencies:** 2-1
**Wave:** 9

**Acceptance Criteria:**
- Given a `nxme.ai/{username}` Universal Link opened on a device with the app installed, When handled, Then the app navigates to the shareable card detail view; the user is not redirected to the browser.
- Given a `nxme.ai/signup?card={username}` deep link from the shared card CTA, When handled, Then the signup flow starts with the originating card tracked for contextual onboarding (AC-U6).
- Given the tab bar shell (wireframe bottom nav: Home, Search, +, Notifications, Profile), When rendered, Then the active tab shows a coral icon with 2px top strip; the "+" tab opens the Upload & Analyze bottom sheet.
- Given the app is opened from a cold start, When initialization runs, Then the guest session token is retrieved from SecureStore (or created if missing); Expo Notifications token is registered (if permitted).
- Given a custom URI scheme redirect attempt during OAuth, When detected, Then it is rejected — only Universal Links / App Links are accepted (AC-A9).

**FR Coverage:** FR-3, FR-28
**NFR Coverage:** NFR-15

---

## FR Coverage Map

| FR | Requirement | Stories | Status |
|----|-------------|---------|--------|
| FR-1 | [Guest] can create account | 2-1, 2-3 | ✅ |
| FR-2 | [Guest] can receive free trial analyses | 2-1, 1-1 | ✅ |
| FR-3 | [Registered User] can log in | 2-2, 2-3 | ✅ |
| FR-4 | [Registered User] can log out | 2-2 | ✅ |
| FR-5 | [Registered User] can delete account and data | 2-2 | ✅ |
| FR-6 | [Registered User] can upload selfie for analysis | 3-1, 3-3 | ✅ |
| FR-7 | [Registered User] can receive face shape classification | 3-2, 3-3 | ✅ |
| FR-8 | [Registered User] can receive facial symmetry assessment | 3-2, 3-3 | ✅ |
| FR-9 | [Registered User] can receive top 5 improvement suggestions | 3-2, 3-3 | ✅ |
| FR-10 | [Registered User] can generate glow-up using trial | 4-2, 4-3, 3-4 | ✅ |
| FR-11 | [Credit Holder] can generate glow-up | 4-3 | ✅ |
| FR-12 | [Premium User] can generate glow-up | 4-3 | ✅ |
| FR-13 | [Registered User] can view result screen | 3-3, 3-4 | ✅ |
| FR-14 | [Registered User] can view pricing | 4-5, 4-6 | ✅ |
| FR-15 | [Registered User] can purchase credit pack | 4-4, 4-5 | ✅ |
| FR-16 | [Registered User] can view credit balance | 4-5, 3-4 | ✅ |
| FR-17 | [Registered User] can subscribe to Premium | 4-4, 4-5 | ✅ |
| FR-18 | [Premium User] can cancel subscription | 4-4, 4-5 | ✅ |
| FR-19 | [Any User] can browse social feed without account | 5-1, 5-4 | ✅ |
| FR-20 | [Any User] can react to a post | 5-2, 5-4 | ✅ |
| FR-21 | [Registered User] can post a comment | 5-3, 5-5 | ✅ |
| FR-22 | [Any User] can read comments | 5-3, 5-4, 5-5 | ✅ |
| FR-23 | [Registered User] can report a post | 5-3 | ✅ |
| FR-24 | [Registered User] can publish glow-up to feed | 5-3 | ✅ |
| FR-25 | [Registered User] can delete their post | 5-3 | ✅ |
| FR-26 | [Registered User] can share glow-up as shareable card | 5-3, 6-1 | ✅ |
| FR-27 | [Any User] can view shared glow-up card | 6-1, 6-2 | ✅ |
| FR-28 | [Any User] can navigate from card to signup | 6-2, 6-5 | ✅ |
| FR-29 | [Registered User] can view transformation history | 6-3, 6-4 | ✅ |
| FR-30 | [Registered User] can view public profile | 6-3, 6-4 | ✅ |
| FR-31 | [Registered User] can edit display name and profile photo | 6-3, 6-4 | ✅ |

**Coverage: 31/31 (100%)**

---

## NFR Coverage Strategy

| NFR | Path | Story / Note |
|-----|------|--------------|
| NFR-1 Face analysis ≤3s P95 | Direct | Story 3-2 — load test AC in CI |
| NFR-2 Generation ≤30s P95 | Direct | Stories 4-2, 4-3, 3-4 — E2E timing AC |
| NFR-3 Feed ≤2s P95 | Direct | Story 5-1 — load test at 10k concurrent |
| NFR-4 Card FCP ≤2s P95 | Direct | Story 6-2 — synthetic monitoring from 3+ regions |
| NFR-5 50k concurrent sessions | Cross-cutting | Architecture constraint (ECS Fargate horizontal scaling); verified by load test at 50k |
| NFR-6 10k concurrent generation queue | Direct | Story 4-2 — load test asserting zero 5xx at 12k |
| NFR-7 Core API 99.5% uptime | Cross-cutting | Architecture (multi-AZ ECS, Supabase managed HA); monitored via uptime tool |
| NFR-8 Generation 99.0% uptime | Direct | Stories 4-2, 4-3 — stuck-job watchdog + credit release ACs |
| NFR-9 ≤$0.05/image | Direct | Story 4-2 — cost circuit breaker + alert at $0.04 |
| NFR-10 Image access security | Direct | Story 3-1 — unsigned request returns 403 AC |
| NFR-11 PCI-DSS SAQ-A | Direct | Story 4-4 — network traffic audit AC; SAQ-A completed before story ships |
| NFR-12 TLS 1.2+ + AES-256 | Cross-cutting | Architecture (ALB TLS termination, Supabase encryption at rest); verified by TLS scan |
| NFR-13 WCAG 2.1 AA | Cross-cutting | Design system applied in all UI stories (2-3, 2-4, 3-4, 4-6, 5-4, 5-5, 6-2, 6-4, 6-5) |
| NFR-14 NSFW screening ≤5s | Direct | Story 3-1 — quarantine AC with ≤5s timing |
| NFR-15 iOS 15+, Android 10+ | Cross-cutting | All mobile UI stories target Expo SDK with `minSdkVersion 29` (Android 10) and `iOS: 15.0` |
| NFR-16 ≥80% coverage | Direct | Stories 3-2, 4-1 — explicit CI gate ACs; cross-cutting: all stories include unit tests |

**Coverage: 16/16 (100%)**

---

## Interface Contracts

### `GlowUpGeneratorPort`
- **Defined by:** Story 4-2
- **Consumed by:** Story 4-3
- **Signature:** `generate(source_image_url: str, prompt: str, options: GenerationOptions) -> GenerationResult`
- **Location:** `generation/ports.py`

### `EntitlementService.get_entitlement` / `can_generate`
- **Defined by:** Story 4-1
- **Consumed by:** Story 4-3, Story 4-5
- **Signatures:**
  - `get_entitlement(user_id: UUID) -> EntitlementState`
  - `can_generate(user_id: UUID) -> CanGenerateResult`
- **Location:** `entitlement/service.py`

### `CreditLedger.reserve / release / commit`
- **Defined by:** Story 4-1
- **Consumed by:** Story 4-3 (via worker 4-2)
- **Signatures:**
  - `reserve(user_id: UUID) -> UUID` (returns reservation_id)
  - `release(reservation_id: UUID) -> None`
  - `commit(reservation_id: UUID) -> None`
- **Location:** `entitlement/ledger.py`

### `ImagePipeline.process`
- **Defined by:** Story 3-1
- **Consumed by:** Story 3-3
- **Signature:** `process(file_bytes: bytes, content_type: str) -> ProcessedImage`
- **Location:** `image_pipeline/pipeline.py`

### `FaceAnalysisService.analyze`
- **Defined by:** Story 3-2
- **Consumed by:** Story 3-3
- **Signature:** `analyze(image_storage_key: str) -> AnalysisResult`
- **Location:** `face_analysis/service.py`

### `TrialGrantor.grant`
- **Defined by:** Story 2-1
- **Consumed by:** Story 2-1 (post-email-verification hook), Story 6-5 (post-registration via shared card)
- **Signature:** `grant(user_id: UUID) -> None` (idempotent)
- **Location:** `entitlement/trial_grantor.py`

---

## Dependency Graph

```
Wave 1:  1-1 ─────────────────────────────── (foundation)
         1-2 ─────────────────────────────── (ADRs — must precede 5-2)

Wave 2:  2-1 ──← 1-1

Wave 3:  2-2 ──← 2-1
         3-1 ──← 1-1

Wave 4:  3-2 ──← 1-1
         4-1 ──← 1-1

Wave 5:  3-3 ──← 3-1, 3-2
         4-2 ──← 4-1

Wave 6:  4-3 ──← 4-2, 3-3
         4-4 ──← 4-1

Wave 7:  4-5 ──← 4-4
         5-1 ──← 1-1
         5-2 ──← 5-1, 1-2

Wave 8:  5-3 ──← 5-1, 4-3
         6-1 ──← 5-3
         6-3 ──← 1-1, 5-3

Wave 9:  2-3 ──← 2-2, 6-5
         6-2 ──← 6-1
         6-5 ──← 2-1

Wave 10: 2-4 ──← 2-3, 6-2
         3-4 ──← 3-3, 4-3, 2-3
         4-6 ──← 4-5, 2-3
         5-4 ──← 5-2, 5-3, 6-5

Wave 11: 5-5 ──← 5-4, 5-3
         6-4 ──← 6-3, 5-4
```

---

## Wave Assignments

| Wave | Stories | Rationale |
|------|---------|-----------|
| 1 | 1-1, 1-2 | No dependencies — database and ADRs must exist before everything |
| 2 | 2-1 | Registration depends only on schema; isolated from image pipeline |
| 3 | 2-2, 3-1 | Auth completion + image pipeline have no inter-dependency; both depend only on Wave 1-2 |
| 4 | 3-2, 4-1 | Face analysis + entitlement service both depend only on schema; no inter-dependency |
| 5 | 3-3, 4-2 | Analysis API needs pipeline + analysis (Wave 4); generation queue needs entitlement (Wave 4); no inter-dependency |
| 6 | 4-3, 4-4 | Generation API needs queue (Wave 5); Stripe adapter needs entitlement (Wave 4); no inter-dependency |
| 7 | 4-5, 5-1, 5-2 | Monetization API needs Stripe (Wave 6); feed API needs schema only; reactions needs feed + ADR-2 (Wave 1); no inter-dependency |
| 8 | 5-3, 6-1, 6-3 | Post CRUD needs feed (Wave 7) + generation (Wave 6); card API needs posts; profile API needs schema + posts; no inter-dependency |
| 9 | 2-3, 6-2, 6-5 | Mobile auth UI needs auth API + nav shell; card web app needs card API; nav shell needs registration; no inter-dependency |
| 10 | 2-4, 3-4, 4-6, 5-4 | All mobile UIs depend on Wave 9 (auth UI + nav shell); no inter-dependency within wave |
| 11 | 5-5, 6-4 | Comments UI needs feed UI (Wave 10) + comments API (Wave 8); profile UI needs profile API (Wave 8) + feed UI (Wave 10) |

---

## Plan Decisions

**PD-1: Backend-First Vertical Slices — LOCKED**
- Alternatives: Mobile-first with mocks, full-stack per feature
- Rationale: Wave independence requires consumers to depend on providers; reversing creates circular same-wave coupling

**PD-2: ADR-1 as Standalone Story — LOCKED**
- Alternatives: Fold into 3-2 (analysis service)
- Rationale: ADR-1 (biometric lifecycle) and ADR-2 (guest attribution) must exist before any story touching biometrics or reactions. Making it a prerequisite story (Wave 1) ensures AC-D3 is satisfied before implementation begins.

**PD-3: Generation Queue as L Story — LOCKED**
- Alternatives: Split into queue-setup + worker
- Rationale: Priority lanes, job lifecycle, stuck-job watchdog, and `GlowUpGeneratorPort` are mutually dependent. An intermediate state (queue without watchdog) would not satisfy AC-D2 (credit release on all failure paths) and could not be tested independently.

**PD-4: Design System Contract Point Applied — LOCKED**
- `docs/design-system.md` status: complete
- All mobile UI stories (2-3, 2-4, 3-4, 4-6, 5-4, 5-5, 6-2, 6-4, 6-5) reference design system tokens
- Button backgrounds use `--color-accent-after-filled` (#E11D48) — white text at 4.70:1 passes WCAG AA
- Spacing tokens from `src/styles/tokens/spacing.css`; typography from `src/styles/tokens/typography.ts`
