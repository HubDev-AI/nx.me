# Architecture Corrections

Findings from production risk analysis and red team review (2026-03-16).
Tracked by target story. Story-creator agent reads this file to inline corrections into story files.

---

## CS-1: Corrections for Completed Stories

Bundled correction story for findings in stories 2-1, 2-2, 3-1, 4-1.

### L-1 CRITICAL: Non-atomic credit ledger fallback paths (Story 4-1)

**File:** `app/entitlement/ledger.py` — `_reserve_fallback`, `_release_fallback`, `_commit_fallback`
**Risk:** If Write 1 succeeds and Write 2 fails, ledger invariants break. Double-spend possible.
**Fix:** Remove fallback paths. If RPC is unavailable, fail the operation and return error. The RPC exists for atomicity — the fallback defeats its purpose. If the RPC must have a fallback, implement compensation (check-and-rollback if second write fails).

### L-2 HIGH: TOCTOU in release/commit status check (Story 4-1)

**File:** `app/entitlement/ledger.py` — `release()`, `commit()`
**Risk:** Concurrent release/commit calls both read `status = 'reserved'`, both proceed, double-credit.
**Fix:** RPC functions must use `UPDATE credit_reservations SET status = $1 WHERE id = $2 AND status = 'reserved' RETURNING *`. Check return: if no rows returned, the reservation was already resolved.

### T-1 HIGH: Hardcoded disposable email blocklist (Story 2-1)

**File:** `app/services/disposable_email.py`
**Risk:** ~60 domains in a hardcoded frozenset. Thousands of disposable services exist.
**Fix:** Replace with `disposable-email-domains` package (PyPI: `disposable-email-domains`, ~3000+ domains, community-maintained). Fall back to hardcoded list if package unavailable.

### T-2 HIGH: Device fingerprint is optional and client-supplied (Story 2-1)

**File:** `app/api/auth.py:79,102-103`
**Risk:** Without fingerprint, rate limit collapses to IP-only. IP resets every hour = 96 accounts/day from one IP.
**Fix:** Add CAPTCHA (hCaptcha or Cloudflare Turnstile) after first registration attempt from an IP within a window. Make fingerprint mandatory for mobile user-agents.

### T-3 MEDIUM: Social login bypasses all registration rate limits (Story 2-2)

**File:** `app/api/auth.py:351-450`
**Risk:** Zero rate limiting on POST /login. Multiple Google accounts = unlimited NXME accounts.
**Fix:** Add per-IP rate limit to `/login` endpoint (same window as registration: 4/hour).

### N-1 MEDIUM: Mock adapter can leak to production (Story 3-1)

**File:** `app/config.py:31` — `ADAPTER__NSFW_ADAPTER: str = "mock"`
**Risk:** If config default leaks to staging/prod, all NSFW content passes.
**Fix:** Add startup guard: if `APP_ENV != "development"` and any adapter is `"mock"`, log CRITICAL and fail fast.

### D-1 MEDIUM: No row-affected check on account deletion (Story 2-2)

**File:** `app/api/auth.py:514-526`
**Risk:** Double-delete doesn't update username reservation. Concurrent deletes proceed to auth deletion.
**Fix:** Check update result count. If 0 rows affected, return 404/409.

### D-2 MEDIUM: No reservation/job cleanup on account deletion (Story 2-2)

**File:** `app/api/auth.py:493-535`
**Risk:** Active credit reservations and in-flight jobs become orphaned.
**Fix:** Before soft-delete: release all `reserved` credit reservations. Cancel all pending generation jobs.

---

## Corrections for Backlog Stories

These are NOT implemented yet. The story-creator agent must inline them when creating story files.

### Story 4-2: Generation Queue & ARQ Worker (Wave 5, L)

**Add to ACs:**

1. **Worker scaling policy:** Define ECS autoscaling — target: queue depth / worker count ratio. Scale-out trigger at queue depth > 50 per worker. Target 50 workers at launch, autoscale to 200.
2. **Hard queue depth limit:** If total queued jobs > `MAX_QUEUE_DEPTH` (config, default 15,000), return 503 immediately. Check via Redis `LLEN`.
3. **Lane fairness:** After processing N premium jobs, drain at least 1 credit job (weighted round-robin).
4. **fal.ai circuit breaker:** After 5 consecutive failures within 60s, open circuit for 120s. Return `PROVIDER_ERROR` immediately without calling fal.ai. Log alert.
5. **fal.ai health probe:** Periodic (every 30s) lightweight API call from one worker.
6. **Cost tracking:** Add `estimated_cost_usd DECIMAL(6,4)` to `glow_up_jobs`. Record fal.ai reported cost.
7. **Rolling 24h cost counter:** Redis `INCR cost:24h:<hour_bucket>` with 1-hour TTL buckets, summed at enqueue time.
8. **Emergency stop:** `GENERATION_EMERGENCY_STOP: bool = False` in config, checked before enqueue. Redis-backed for instant toggle without deploy.
9. **Per-user daily cap:** `MAX_GENERATIONS_PER_USER_PER_DAY: int = 50` independent of tier limits.
10. **ArcFace model spec:** Use `insightface` buffalo_l. Pre-load at worker startup (like MediaPipe preload pattern).
11. **ArcFace retry:** Single retry on identity failure with increased ControlNet strength (+0.1).
12. **Identity failure monitoring:** CloudWatch metric `identity_check_failure_rate`, alarm at >15%.
13. **NSFW screening on generated output:** Run Rekognition on fal.ai result before commit. Quarantine if explicit.
14. **Prompt sanitization:** Allowlist of recommendation keywords for prompt interpolation. Strip injection patterns.
15. **Concurrent guard fix:** Replace read-only check with atomic INCR at API layer (INCR, check, DECR-if-over).

#### AI Model Selection (from model evaluation, 2026-03-16)

16. **Primary model: FLUX.1 Kontext [pro]** (`fal-ai/flux-pro/kontext`). Instruction-based editing — edits the existing photo rather than generating a new one. Best identity preservation (ArcFace cosine sim 0.88-0.95 for subtle changes). ~$0.04/image. Config: `FAL_MODEL_PRIMARY`, `FAL_PRIMARY_GUIDANCE_SCALE=3.5`, `FAL_PRIMARY_INFERENCE_STEPS=28`.
17. **Fallback model: InstantID** (`fal-ai/instantid`). SDXL-based with face embedding + keypoint conditioning. Used when Kontext circuit breaker is open or cost ceiling approached. ~$0.02-0.03/image. Config: `FAL_MODEL_FALLBACK`, `FAL_FALLBACK_CONTROLNET_SCALE=0.85`, `FAL_FALLBACK_IP_ADAPTER_SCALE=0.70`.
18. **Output resolution:** 1024x1024 for both models. ArcFace internally crops to 112x112 — any input above 256x256 is sufficient.
19. **Prompt templates as files:** `prompts/glowup_kontext.txt` (instruction-based) and `prompts/glowup_instantid_positive.txt` + `prompts/glowup_instantid_negative.txt` (traditional). Templates loaded at runtime, not hardcoded.
20. **Keyword allowlist:** `prompts/keyword_allowlist.py` — maps recommendation categories (hair, eyebrows, facial_hair, lighting, grooming) to fixed sets of allowed keywords. Only allowlisted keywords can appear in interpolated prompts. Prevents prompt injection.
21. **Max prompt keywords:** `MAX_PROMPT_KEYWORDS=4` — limits improvement keywords per generation to reduce identity drift risk.
22. **Identity retry strategy:** On ArcFace failure, retry once with `guidance_scale += 0.5` and reduce to top 2 keywords only. Do NOT switch to fallback model on first retry. Config: `IDENTITY_MAX_RETRIES=1`, `IDENTITY_RETRY_GUIDANCE_BUMP=0.5`.
23. **ArcFace implementation:** `insightface` with `buffalo_l` model pack, `CPUExecutionProvider`. Pre-loaded at worker startup. Embedding extraction ~50-100ms per image on CPU. Both embeddings discarded immediately after comparison (ADR-1).
24. **Face detection on output:** If ArcFace cannot detect a face in the generated image, treat as identity failure. Also run MediaPipe face detection confidence check — output must have confidence > 0.9.
25. **Cost tracking per job:** Record actual cost per job including retries (sum of all attempts). Cost ceiling circuit breaker uses actual spend, not per-attempt estimates. A retry chain (Kontext + Kontext retry) costs up to $0.08, exceeding the $0.05 per-image ceiling — the ceiling applies to 24h rolling average, not individual jobs.

### Story 5-2: Guest Session & Reactions (Wave 7)

**Add to ACs:**

1. **Per-guest-token rate limit:** Max 30 reactions/minute via Redis sliding window.
2. **Per-IP rate limit on react endpoint:** Max 100 reactions/minute.
3. **Per-post velocity guard:** If post receives >1000 reactions in 5 minutes, queue new reactions instead of processing immediately.
4. **Server-side guest token registry:** `guest_sessions` table with `token_hash`, `created_at`, `ip_address`. Validate token existence before accepting reactions.
5. **Token format validation:** Enforce minimum 32-byte length, hex/base64 format.
6. **Reconciliation frequency:** Run every 5-10 minutes for posts with recent activity, not just nightly.

### Story 6-1: Shareable Card API (Wave 8)

**Add to ACs:**

1. **Cache-Control header:** `Cache-Control: public, max-age=60, stale-while-revalidate=300` on `GET /api/public/cards/{username}`.
2. **CloudFront for public API:** Place CDN in front of `/api/public/*` paths.
3. **Per-IP rate limit on public endpoints:** 100 requests/minute.
4. **Signed image URLs:** Use signed CloudFront URLs with 5-minute TTL for card image delivery.

### Story 6-2: Next.js Shareable Card Web App (Wave 9)

**Add to ACs:**

1. **OG image generation:** Use `@vercel/og` (Satori-based) for OG images. 1200x630 PNG, before/after side-by-side with username overlay.
2. **OG image caching:** Same ISR revalidation cycle as card page.
3. **CloudFront cache-control headers** for OG image routes.
4. **robots.txt and X-Robots-Tag:** `noindex` on image URLs to prevent search engine indexing of facial images.

### Story 5-3: Comments, Reports & Post CRUD (Wave 8)

**Add to ACs:**

1. **Deleted user post cleanup:** Account deletion (or async cleanup job) must set `is_deleted = true` on all posts owned by the deleted user.

### Story 4-3: Generation API (Wave 6)

**Add to ACs:**

1. **Identity failure response:** Include `retry_eligible: true` with user-facing guidance ("try a clearer photo" or "this style was too dramatic").

---

## Deferred (Post-MVP)

These are real risks but acceptable for MVP launch. Document and revisit.

- **IP reputation scoring** (IPQualityScore/MaxMind) for registration — cost vs. benefit
- **Phone verification** for trial grant — friction vs. abuse prevention
- **Secondary NSFW model** (NudeNet/Azure Content Safety) — defense in depth
- **Image watermarking** on public card images — scraping deterrent
- **Proof-of-work challenge** for guest reactions if bot abuse detected
- **fal.ai billing reconciliation** — compare internal cost tracking vs invoices
