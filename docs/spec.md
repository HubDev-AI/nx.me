---
status: complete
created: 2026-03-13T13:15:00.000Z
feature: nxme
brief: docs/research.md
---

# Specification: NXME

## Overview

NXME is an AI-powered social app where users upload a selfie, receive personalized appearance improvement suggestions grounded in their facial geometry, see a realistic before/after "glow-up" simulation, and share that transformation as social content. The social layer (feed, reactions, comments, shareable cards) is fully free. Face analysis and glow-up generation require credits (pay-per-use) or a Premium subscription (unlimited). 1–2 free trial analyses are included at signup.

## Use Cases

- **UC-1: First-Time Glow-Up (Trial Path)** — New user signs up, uses their free trial, sees their first before/after result; covers validation failure and generation failure recovery.
- **UC-2: Credit Purchase and Paid Analysis** — User with exhausted trial purchases a credit pack and runs a new analysis; covers payment failure and paywall dismissal.
- **UC-3: Publish Glow-Up to Feed** — User publishes a completed result to the public feed with optional caption; shareable card is created/updated at `nxme.ai/{username}`.
- **UC-4: Viral Acquisition via Shared Card** — Guest clicks a shared link, sees the full before/after card without login, taps the CTA, and converts to a registered user.
- **UC-5: Subscribe to Premium** — Registered user upgrades to unlimited monthly subscription from the paywall, profile settings, or credit balance screen.
- **UC-6: Browse Feed and React** — Any user (including guest) browses trending transformations and reacts; authentication only prompted when attempting to comment.

## Functional Requirements (Capability Contract)

### Onboarding & Account
- **FR-1:** [Guest] can [create an account] [using an email address or a supported social login provider]
- **FR-2:** [Guest] can [receive free trial analyses] [automatically upon account creation, limited to 1–2 analyses before any payment is required]
- **FR-3:** [Registered User] can [log in to their account] [from any supported mobile device]
- **FR-4:** [Registered User] can [log out of their account] [at any time from any screen]
- **FR-5:** [Registered User] can [delete their account and all associated personal data] [from their profile settings]

### Face Analysis & Glow-Up Pipeline
- **FR-6:** [Registered User] can [upload a selfie for analysis] [subject to automated face validation: single person present, face clearly visible and unobstructed]
- **FR-7:** [Registered User] can [receive a face shape classification] [from the set: oval, round, square, heart, or oblong — derived from facial landmark proportions without displaying an attractiveness score]
- **FR-8:** [Registered User] can [receive a facial symmetry and feature assessment] [based on landmark-derived measurements of eyes, eyebrows, hairline, and facial proportions]
- **FR-9:** [Registered User] can [receive a ranked list of top 5 personalized style improvement suggestions] [tied to their classified face shape and measured feature proportions, framed as achievable style changes with no reference to attractiveness]
- **FR-10:** [Registered User] can [generate a before/after glow-up simulation using their free trial allowance] [limited to 1–2 analyses granted at signup; AI modifications restricted to hair, eyebrows, style, and lighting — bone structure, nose, jaw, and face shape must remain unchanged]
- **FR-11:** [Credit Holder] can [generate a before/after glow-up simulation] [consuming one credit per generation; same identity-preservation constraints as FR-10 apply]
- **FR-12:** [Premium User] can [generate a before/after glow-up simulation] [without consuming per-use credits; same identity-preservation constraints as FR-10 apply]
- **FR-13:** [Registered User] can [view their improvement suggestions alongside the before/after simulation] [as a combined result screen immediately after analysis completes]

### Monetization — Credits & Subscription
- **FR-14:** [Registered User] can [view pricing and feature differences] [between the free tier, available credit pack sizes, and the Premium subscription before committing to any purchase]
- **FR-15:** [Registered User] can [purchase a credit pack] [choosing from available pack sizes and completing payment through the platform's payment flow]
- **FR-16:** [Registered User] can [view their current credit balance] [at any time from their profile or before initiating an analysis]
- **FR-17:** [Registered User] can [subscribe to the Premium plan] [to gain unlimited face analyses and access to advanced transformation features, billed monthly]
- **FR-18:** [Premium User] can [cancel their subscription] [at any time, retaining Premium access until the end of the current billing period]

### Social Feed
- **FR-19:** [Any User] can [browse the social feed] [without an account, viewing trending transformations, newest posts, and biggest improvements]
- **FR-20:** [Any User] can [react to a post in the social feed] [without requiring account creation; reactions are reflected in the post's reaction count]
- **FR-21:** [Registered User] can [post a comment on any feed post] [comment is visible to all users including guests]
- **FR-22:** [Any User] can [read comments on any feed post] [without requiring an account]
- **FR-23:** [Registered User] can [report a post for moderation review] [from within the post detail view]

### Post Creation & Sharing
- **FR-24:** [Registered User] can [publish a completed glow-up result to the public feed] [with the option to add a caption before publishing]
- **FR-25:** [Registered User] can [delete any post they created] [at any time from the post detail view or their profile]
- **FR-26:** [Registered User] can [share their glow-up result as a public shareable card] [accessible at a permanent URL under their username, displaying the before/after image and top improvement suggestions]
- **FR-27:** [Any User] can [view a shared glow-up card page] [without any account or login requirement, seeing the before/after image and improvement suggestions in full]
- **FR-28:** [Any User] can [navigate from a shared glow-up card to the sign-up flow] [via a visible call-to-action, with the app opened or app store install prompted as appropriate]

### User Profile
- **FR-29:** [Registered User] can [view their transformation history] [as a chronological list of all past analyses and generated glow-up images stored in their account]
- **FR-30:** [Registered User] can [view their public profile page] [displaying all published posts and their current shareable glow-up card]
- **FR-31:** [Registered User] can [edit their display name and profile photo] [from their profile settings at any time]

## Non-Functional Requirements (measurable targets)

- **NFR-1: Face Analysis Latency** — Face validation + landmark analysis must complete in ≤3s at P95 on a mid-range 2021 smartphone
- **NFR-2: Glow-Up Generation Latency** — End-to-end generation (upload received → result displayed) must complete in ≤30s at P95 under normal load
- **NFR-3: Feed Load Performance** — Social feed initial render must display first 10 posts within ≤2s at P95 on a 4G connection (≥20 Mbps)
- **NFR-4: Shareable Card Performance** — Card page must reach first contentful paint within ≤2s at P95 on 4G
- **NFR-5: Scalability — Users** — System must sustain 1,000,000 registered users and 50,000 concurrent sessions without exceeding P95 latency targets
- **NFR-6: Scalability — Queue** — Generation pipeline must support ≥10,000 concurrent generation requests without dropping; excess requests queued with progress shown
- **NFR-7: Availability — Core API** — Feed, profile, and analysis submission endpoints must maintain ≥99.5% uptime on a rolling 30-day window
- **NFR-8: Availability — Generation** — Generation pipeline must maintain ≥99.0% uptime; any failure must surface a user-visible error within 60s and must not consume a credit
- **NFR-9: Image Generation Cost** — Per-glow-up AI generation infrastructure cost must not exceed $0.05 per image at any traffic level
- **NFR-10: Image Access Security** — Raw uploaded selfies must not be publicly enumerable; access requires a signed URL with ≤24h expiry; published before/after images on the feed may be publicly readable
- **NFR-11: Payment Security** — Payment processing must comply with PCI-DSS SAQ-A; no raw card data may be handled or stored on NXME servers
- **NFR-12: Encryption** — All data in transit must use TLS 1.2+; PII and uploaded images at rest must use AES-256 or equivalent
- **NFR-13: Accessibility** — All interactive UI elements must meet WCAG 2.1 AA (4.5:1 contrast for normal text, 3:1 for large text); operable via screen reader and keyboard navigation
- **NFR-14: Content Moderation** — User-uploaded images must pass automated screening before storage; flagged images quarantined within ≤5s and never displayed until cleared
- **NFR-15: Platform Compatibility** — App must be fully functional on iOS 15+ and Android 10+, covering ≥95% of devices in the 16–35 demographic
- **NFR-16: Test Coverage** — Automated test coverage for the face analysis pipeline and credit/subscription gating logic must be ≥80% line coverage, enforced in CI

## Constraints & Assumptions

### Constraints
- **C-1:** AI image generation must only modify hair, eyebrows, style, and lighting — bone structure, nose, jaw, and face shape must never be altered [LOCKED]
- **C-2:** Product must never display a numerical attractiveness rating or rank users by appearance [LOCKED]
- **C-3:** Social layer (feed, reactions, comments, shareable cards) must carry no paywall [LOCKED]
- **C-4:** Social feed and sharing features must ship with the initial MVP [LOCKED]
- **C-5:** Glow-up generation must use image-to-image diffusion to preserve facial identity [LOCKED]
- **C-6:** Product name is NXME; canonical domain is nxme.ai [LOCKED]
- **C-7:** Primary experience must be fully functional on iOS 15+ and Android 10+
- **C-8:** Per-glow-up AI generation cost must not exceed $0.05 per image

### Assumptions
- **A-1:** Guest reactions are permitted without account creation (social-free constraint requires frictionless engagement)
- **A-2:** Free trial floor is 1 analysis, ceiling is 2
- **A-3:** Subscription launch price modeled at $5/month (lower bound of $5–10 research range)
- **A-4:** A web-based sign-up path exists for guests opening shared card links without the app installed
- **A-5:** Automated content screening (NSFW) is required at launch despite full moderation policy (DD-10) being deferred
- **A-6:** Comment posting requires authentication; reactions do not

### Open Questions
- **OQ-1:** Should guest reactions be ephemeral or attributed retroactively if the guest later creates an account? Affects feed engagement accuracy, onboarding UX, and analytics attribution. Decision required before feed implementation.

## Quality Perspectives (Summary)

- **End User — 10 concerns:** Key P1: generation wait UX, trial count transparency, trial-not-consumed on failure, validation error messages.
- **Architect — 10 concerns:** Key P1: credit atomicity mechanism, guest reaction attribution model, NSFW screening placement, biometric data lifecycle.
- **Maintainer — 10 concerns:** Key HIGH: entitlement state machine testability, atomicity mechanism, OQ-1 schema impact, identity-preservation runtime signal.
- **Security Auditor — 12 concerns:** Key P1: free trial farming, EXIF metadata leakage, credit race condition.

## Acceptance Criteria

### User Experience (AC-U)

**AC-U1:** During glow-up generation, the progress screen displays (a) a time estimate or elapsed counter visible within 5s of submission, (b) reassurance copy confirming analysis is running, and (c) a Cancel button; tapping Cancel before result delivery does not decrement the user's trial count or credit balance — verified by injecting a 30s delay, tapping Cancel at T+10s, and asserting trial/credit count is unchanged.

**AC-U2:** The remaining free trial count is visible on both the home screen and the upload screen before the user triggers generation; when 0 trials remain and the user taps the generate action, the paywall modal appears before any generation pipeline call is made — verified by creating a fresh account, exhausting all trials, tapping generate, and asserting paywall appears with zero calls made to the generation service.

**AC-U3:** When glow-up generation fails due to a system-side error (pipeline error, timeout ≥60s, GPU unavailability), the user's trial count is not decremented and any consumed credit is fully refunded within the same session; the UI presents a specific error message and a retry option that does not require re-uploading the selfie — verified by injecting each failure type and asserting trial/credit count before equals count after.

**AC-U4:** When selfie validation fails, the UI displays a distinct, actionable error message for each failure mode (multiple faces detected, face obstructed, image too blurry, face not detected) with concrete resolution guidance; a validation failure does not decrement the user's trial count — verified by uploading test images matching each failure mode and asserting correct message and unchanged trial count.

**AC-U5:** When a user publishes a new glow-up result that would replace their existing shareable card at `nxme.ai/{username}`, a confirmation dialog explains that the card URL will be updated before the publish action completes; the user can choose to post to the feed without updating the card — verified by a user with an existing card publishing a new result and asserting dialog appears before any card update.

**AC-U6:** After a guest completes account creation via the CTA on a shared glow-up card (UC-4), the app navigates the new user to a contextual onboarding state that shows their remaining free trial count and prompts them to try their own analysis — not a generic home screen — verified by completing signup via a shared card CTA and asserting the destination screen shows trial count and an upload prompt.

**AC-U7:** During account creation (FR-1), users confirm they meet the minimum age requirement; in jurisdictions requiring parental consent for under-18 users, an appropriate disclosure or consent step is presented before the face analysis pipeline is accessible — verified by checking the registration flow includes an age gate and that minor-flagged accounts cannot reach the upload screen without completing the consent step.

**AC-U8:** The result screen (FR-13) includes a visible "This doesn't look like me" feedback action; when tapped, the system (a) automatically refunds the credit or trial use consumed, (b) logs the generation for model improvement, and (c) offers a one-tap re-generation without requiring selfie re-upload; the refund completes within the same session without a support ticket — verified by tapping the feedback action and asserting credit/trial balance is restored within 30s.

**AC-U9:** When a guest reacts to a post (FR-20), the reaction is visually confirmed immediately via optimistic UI update; within the same session the guest cannot react to the same post a second time (deduplication via session fingerprint); on session restart deduplication resets — verified by reacting as a guest, asserting UI confirmation, attempting a second reaction in the same session, and asserting it is blocked.

**AC-U10:** The "Biggest Improvements" feed filter (FR-19) orders posts by a metric derived solely from user engagement signals (reaction count, save count) — no AI-computed appearance score or symmetry delta is used as an ordering input; the filter label contains no language implying relative attractiveness judgment — verified by reviewing the sort query and asserting no appearance-model output field is referenced.

---

### Functional Requirements (AC-FR)

**AC-FR1:** A newly created account has a trial credit balance equal to `FREE_TRIAL_ANALYSES` (a named system constant) before any generation is attempted — verified by creating an account and asserting the balance endpoint returns the constant value.

**AC-FR2:** A user with no remaining trials, no credit balance, and no active subscription who taps generate sees the paywall with all purchase options (credit pack sizes and Premium subscription) before any generation is initiated — verified by exhausting all credits and confirming paywall displays all options.

**AC-FR3:** Published before/after images have all EXIF, IPTC, and XMP metadata stripped; no GPS coordinates, device identifiers, or personal metadata from the original upload are present in any stored or served image — verified by uploading an image with known GPS coordinates and asserting zero location metadata in the stored result.

**AC-FR4:** A Premium user who cancels their subscription (FR-18) retains full Premium access until the exact billing period end timestamp; at `billing_end + 1s` their entitlement reverts — verified by clock-controlled test asserting Premium access at `billing_end - 1s` and denied at `billing_end + 1s`.

**AC-FR5:** Account deletion (FR-5) removes all personal data within defined timelines: primary storage within 72 hours, CDN within 7 days, backups within 30 days; the shareable card URL returns HTTP 410 permanently; the deleted username is not reassignable for 180 days — verified by triggering deletion and checking each data store and URL at each deadline.

**AC-FR6:** The social feed (FR-19), reactions (FR-20), comments (FR-22), and shareable card (FR-27) are fully accessible without authentication — all complete with zero authenticated API calls — verified by making all feed/card API requests without an auth token and asserting HTTP 200 with complete content.

**AC-FR7:** A user's transformation history (FR-29) displays all analyses in reverse chronological order; each entry shows the before/after images and improvement suggestions; no entry is missing for any completed generation — verified by running N analyses and asserting N entries in correct order.

**AC-FR8:** The `nxme.ai/{username}` shareable card page (FR-27) renders the full before/after image and all top-5 improvement suggestions without any login prompt on both mobile and desktop browsers — verified by loading the URL in an unauthenticated browser and asserting full content visibility.

**AC-FR9:** When a registered user logs out (FR-4), their session is invalidated server-side within ≤1s; subsequent API requests using the invalidated session token return HTTP 401; the app navigates to the unauthenticated state — verified by logging out, capturing the session token, sending an authenticated request with that token, and asserting HTTP 401.

**AC-FR10:** The face analysis API returns a `face_shape` field containing exactly one value from `{oval, round, square, heart, oblong}` and a `symmetry_score` field in the range [0.0, 1.0] (FR-7, FR-8); neither field contains any attractiveness rating or rank — verified by asserting response schema and confirming no attractiveness-related fields are present in the response.

---

### Architecture & Security (AC-A)

**AC-A1:** Credit lifecycle implements reserve-before-enqueue: credit is reserved before the generation job is enqueued, committed on confirmed result delivery, and released on confirmed failure; the job carries an idempotent job ID preventing double-commit on retry — verified by injecting failures at each pipeline stage and asserting credit balance is never permanently reduced on failure.

**AC-A2:** A durable anonymous session token is issued to every app client at first launch; this token is sent with every reaction request and used for server-side deduplication — verified by asserting a reaction from the same token on the same post is deduplicated and counted once regardless of how many times the request is sent.

**AC-A3:** NSFW screening runs as a synchronous gate before any image is written to the raw selfie storage bucket; an image that fails screening is rejected with a user-facing error within ≤5s and is never written to any storage layer — verified by uploading a flagged test image and asserting zero objects created in the bucket and error returned within 5s.

**AC-A4:** The architecture documents the complete lifecycle of facial landmark vectors and identity embeddings — either ephemeral (computed in-request, never persisted) or persisted (with documented legal basis per jurisdiction, encryption specification, and consent model) — documented as an ADR before implementation begins.

**AC-A5:** Usernames are immutable after account creation and globally unique; a blocklist of reserved words (all application route prefixes: `feed`, `api`, `login`, `pricing`, `static`, `admin`, `health`) is enforced at registration — verified by attempting to register reserved-word usernames and asserting rejection, and attempting to change a username post-creation and asserting rejection.

**AC-A6:** The generation queue enforces: (a) per-user rate limit of ≤3 concurrent in-flight generations, (b) a queue depth circuit-breaker that applies backpressure when estimated cost exposure exceeds a configured threshold, (c) a maximum queue wait time after which the job is cancelled and the credit released, (d) priority ordering: Premium > Credit Holder > Trial — verified by load test asserting these limits hold at configured thresholds.

**AC-A7:** The `nxme.ai/{username}` card page is served via SSR or edge-cached static generation with no auth-gated API call on the critical render path; before/after images served from CDN with public read access — verified by loading the page with no auth headers and asserting FCP ≤2s.

**AC-A8:** Account creation is rate-limited to ≤2 accounts per device fingerprint per 24-hour window and ≤3 per IP per hour; email verification must complete before free trial credits are granted; disposable email domain accounts are denied free credits — verified by scripted account creation from same device/IP and asserting limits are enforced.

**AC-A9:** Social login uses Authorization Code flow with PKCE (RFC 7636); implicit flow is rejected; redirect URIs use Universal Links (iOS) or App Links (Android) — custom URI schemes are rejected; `id_token` claims (`iss`, `aud`, `exp`, `nonce`) are validated on every login — verified by attempting login with implicit-flow token and custom URI scheme and asserting both are rejected.

**AC-A10:** Image upload rejects files where magic bytes do not match JPEG, PNG, or HEIF; rejects files exceeding 20MB or 8192×8192 pixels before full decode; re-encodes all accepted images through a clean pipeline discarding the original byte stream; processes images in a sandboxed environment with no outbound network access — verified by uploading polyglot and oversized test files and asserting rejection.

**AC-A11:** If a generation is already in progress for a user, a second concurrent generation request returns HTTP 409 Conflict — verified by sending two simultaneous generation requests for the same user and asserting exactly one succeeds and one returns 409.

**AC-A12:** Reaction endpoints enforce ≤10 reactions per IP per 5-minute window at the edge; posts receiving reaction velocity exceeding 3 standard deviations above baseline are flagged for anomaly review and excess reactions excluded from displayed counts — verified by sending >10 reactions from one IP in 5 minutes and asserting rate limit response.

---

### Developer / Maintainer (AC-D)

**AC-D1:** All entitlement checks (trial remaining, credit balance, subscription status) are routed through a single entitlement module with a defined public API; no feature handler directly reads subscription or credit database fields — verified by grep asserting zero direct database field reads for entitlement data outside the entitlement module.

**AC-D2:** Every generation pipeline failure path executes a credit/trial rollback before any error response is returned; all rollback paths are covered by failure-injection unit tests — verified by code review of pipeline error handlers and CI asserting 100% branch coverage of rollback paths.

**AC-D3:** OQ-1 (guest reaction attribution: ephemeral vs. retroactive) is resolved and documented as an Architecture Decision Record (ADR) before any story touching the reactions feature enters the plan phase — verified by checking the ADR file exists with a decision and date before the reactions story is written.

**AC-D4:** Every glow-up generation job emits `identity_similarity_score` (float 0–1) and `identity_preserved` (boolean) as structured log fields; a test asserts that a job with a similarity score below the defined threshold is not delivered to the user — verified by CI test with a mock returning a below-threshold score and asserting the result is blocked.

**AC-D5:** The free trial analysis count is defined as a single named configuration constant; grep across the codebase returns zero occurrences of inline numeric literals for this value in entitlement checks or test fixtures — verified by CI lint rule or grep assertion.

**AC-D6:** Every generation pipeline failure event includes a `failure_reason` field from a closed enum (`FACE_VALIDATION_FAILED`, `GENERATION_TIMEOUT`, `NSFW_QUARANTINE`, `IDENTITY_PRESERVATION_FAILED`, `PROVIDER_ERROR`); unhandled exceptions map to `UNKNOWN` and trigger an automated alert — verified by asserting all exception handlers set the field and the UNKNOWN variant triggers an alert.

**AC-D7:** Every uploaded image has a queryable status field with values `pending`, `cleared`, `quarantined`; no feed endpoint or shareable card endpoint returns an image with status `quarantined` or `pending` — verified by test asserting a quarantined image is absent from all public-facing API responses.

**AC-D8:** A glossary defines `TRIAL`, `CREDIT_HOLDER`, and `PREMIUM` as canonical identifiers used verbatim in database schemas, API contract types, and structured log events — verified by grep asserting these exact identifiers appear in schema and log definitions.

---

### Non-Functional Requirements (AC-NFR)

**AC-NFR1:** Face validation + landmark analysis completes in ≤3s at P95 under load test simulating 1,000 concurrent uploads on mid-range 2021 smartphone equivalent hardware — verified by load test P95 report ≤3,000ms.

**AC-NFR2:** End-to-end glow-up generation completes in ≤30s at P95 under normal load; progress indicator visible within ≤2s of request acceptance — verified by load test P95 report and E2E test asserting indicator appears within 2s.

**AC-NFR3:** Social feed initial render displays first 10 posts within ≤2s at P95 on simulated 4G (20 Mbps, 60ms RTT) under 10,000 concurrent feed readers — verified by load test P95 report with network throttling.

**AC-NFR4:** Shareable card page reaches first contentful paint within ≤2s at P95 on simulated 4G with no auth headers — verified by synthetic monitoring from 3+ geographic regions.

**AC-NFR5:** Under 50,000 concurrent active sessions, P95 latency for NFR-1, NFR-2, and NFR-3 does not degrade beyond their stated targets simultaneously — verified by load test at 50K concurrent sessions.

**AC-NFR6:** Generation queue accepts ≥10,000 simultaneous requests without HTTP 5xx; excess requests are queued and a queued status is returned to the client within ≤5s — verified by load test injecting 12,000 concurrent requests and asserting zero 5xx and all clients receive queued status within 5s.

**AC-NFR7:** Core API availability ≥99.5% on rolling 30-day window with 30-second check interval; downtime defined as HTTP 5xx or unreachable for ≥30 consecutive seconds — verified by uptime monitoring reporting rolling monthly SLO compliance.

**AC-NFR8:** Generation pipeline availability ≥99.0% on rolling 30-day window; any failure surfaces user-visible error within ≤60s and does not consume a credit or trial use — verified by uptime monitoring and chaos test asserting user error within 60s and credit balance unchanged.

**AC-NFR9:** Per-image AI generation cost does not exceed $0.05 averaged over any rolling 24-hour window of ≥100 generations; a cost alert fires when rolling average exceeds $0.04 — verified by cost telemetry dashboard and alert configuration.

**AC-NFR10:** Raw uploaded selfies have no public-access policy; all reads require a signed URL expiring within ≤1 hour for in-app viewing; published before/after images on CDN have all EXIF metadata stripped — verified by asserting unsigned requests to raw bucket return HTTP 403 and checking signed URL expiry configuration.

**AC-NFR11:** No raw card data (PAN, CVV, expiry) is processed, transmitted, or stored on NXME infrastructure; all payment flows route through a PCI-DSS-certified third-party processor; PCI-DSS SAQ-A completed before payment feature ships — verified by network traffic audit showing zero card data in NXME-controlled payloads.

**AC-NFR12:** All client-server traffic uses TLS 1.2+; TLS 1.0/1.1 connections are rejected; PII and uploaded images at rest are encrypted with AES-256 or equivalent — verified by TLS scan showing minimum TLS 1.2 and storage configuration review.

**AC-NFR13:** All interactive UI elements meet WCAG 2.1 AA contrast ratios (4.5:1 normal text, 3:1 large text); all interactive elements are operable via screen reader (VoiceOver/TalkBack) and keyboard navigation — verified by automated contrast scan and manual screen reader test across all primary user flows.

**AC-NFR14:** 100% of user-uploaded images pass through automated NSFW screening before storage; non-compliant images are quarantined within ≤5s and never served to any user until cleared by human review — verified by uploading NSFW test images and asserting zero appear in feed, card, or history endpoints and quarantine completes within 5s.

**AC-NFR15:** The mobile app is fully functional on iOS 15.0 and Android 10.0 on minimum supported hardware — verified by device-farm test run covering all primary user flows on both OS minimum versions.

**AC-NFR16:** Automated test line coverage for the face analysis pipeline module and the credit/subscription entitlement module is ≥80%; this threshold is a CI gate that fails the build if either module falls below 80% — verified by CI build log showing coverage ≥80% for both modules.

## Traceability Matrix

| Requirement | Acceptance Criteria |
|-------------|-------------------|
| FR-1 | AC-FR6, AC-A8, AC-A9 |
| FR-2 | AC-U2, AC-FR1, AC-D5 |
| FR-3 | AC-A9 |
| FR-4 | AC-FR9 |
| FR-5 | AC-FR5, AC-A4 |
| FR-6 | AC-U4, AC-A3, AC-A10, AC-NFR1 |
| FR-7 | AC-D8, AC-FR10 |
| FR-8 | AC-D8, AC-FR10 |
| FR-9 | AC-U10 |
| FR-10 | AC-U1, AC-U2, AC-U3, AC-FR1, AC-FR2, AC-D5 |
| FR-11 | AC-A1, AC-A11, AC-D2 |
| FR-12 | AC-A1, AC-D1 |
| FR-13 | AC-U8, AC-D4 |
| FR-14 | AC-FR2 |
| FR-15 | AC-NFR11, AC-A1 |
| FR-16 | AC-FR2, AC-D5 |
| FR-17 | AC-NFR11 |
| FR-18 | AC-FR4 |
| FR-19 | AC-FR6, AC-U10, AC-A12 |
| FR-20 | AC-U9, AC-A2, AC-A12 |
| FR-21 | AC-FR6 |
| FR-22 | AC-FR6 |
| FR-23 | AC-A12 |
| FR-24 | AC-U5 |
| FR-25 | AC-FR7 |
| FR-26 | AC-U5, AC-A5 |
| FR-27 | AC-FR8, AC-A7 |
| FR-28 | AC-U6 |
| FR-29 | AC-FR7 |
| FR-30 | AC-FR8 |
| FR-31 | AC-A5 |
| NFR-1 | AC-NFR1 |
| NFR-2 | AC-NFR2, AC-U1 |
| NFR-3 | AC-NFR3 |
| NFR-4 | AC-NFR4, AC-A7 |
| NFR-5 | AC-NFR5 |
| NFR-6 | AC-NFR6, AC-A6 |
| NFR-7 | AC-NFR7 |
| NFR-8 | AC-NFR8, AC-U3, AC-A1, AC-D2 |
| NFR-9 | AC-NFR9 |
| NFR-10 | AC-NFR10, AC-FR3, AC-A4 |
| NFR-11 | AC-NFR11 |
| NFR-12 | AC-NFR12 |
| NFR-13 | AC-NFR13 |
| NFR-14 | AC-NFR14, AC-A3, AC-D7 |
| NFR-15 | AC-NFR15 |
| NFR-16 | AC-NFR16, AC-D1 |

## Content Quality Checks

| Check | Status | Details |
|-------|--------|---------|
| CQ-1 Density | ✅ PASS | No filler phrases detected |
| CQ-2 Impl Leakage | ✅ PASS | No tech names in FR capability text |
| CQ-3 Measurability | ✅ PASS | All NFRs have numeric targets |
| CQ-4 Traceability | ✅ PASS | Every FR → ≥1 AC (AC-FR9 covers FR-4; AC-FR10 covers FR-7/FR-8); every NFR → ≥1 AC |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| AI result looks like a different person | HIGH | HIGH | C-1 constraint + runtime similarity score gate (AC-D4) + user feedback refund (AC-U8) |
| Free trial farming destroys unit economics | HIGH | HIGH | Device fingerprint + email verification before credit grant (AC-A8) |
| Credit race condition allows free generation | MED | HIGH | Pessimistic lock + HTTP 409 for concurrent requests (AC-A1, AC-A11) |
| EXIF geolocation leakage from selfie images | MED | HIGH | Mandatory EXIF strip before storage (AC-FR3, AC-NFR10) |
| Biometric data legal exposure (BIPA, GDPR Art.9) | MED | HIGH | Lifecycle ADR + separate consent flow (AC-A4, AC-U7) |
| NSFW content posted to public feed | MED | HIGH | Synchronous pre-storage screening gate (AC-A3, AC-NFR14) |
| Generation pipeline cost spike at viral scale | MED | HIGH | Cost circuit-breaker + telemetry alert at $0.04 (AC-A6, AC-NFR9) |
| OQ-1 left unresolved at implementation | LOW | MED | ADR required before feed stories enter plan (AC-D3) |
| Username squatting on reserved routes | LOW | MED | Reserved-words blocklist at registration (AC-A5) |

## Out of Scope

- Face rating / attractiveness scoring (prohibited by C-2, DD-3)
- Full 3D digital twin or avatar
- Real-time AR camera mode (Phase 3)
- Direct e-commerce or affiliate clothing links (Phase 4)
- Clothing virtual try-on (Phase 3)
- Outfit analyzer (Phase 4)
- Future You mode / multi-style variant previews (Post-MVP)
- Glow-Up Battle: A vs B community voting (Phase 2)
- Glow-Up Timeline: multi-month progress tracking (Phase 2)
- Hairstyle and glasses virtual try-on (Phase 3)
- Style Categories: "1 selfie → 5 versions" (Phase 3)
- Creator economy and premium style packs (Phase 3+)
