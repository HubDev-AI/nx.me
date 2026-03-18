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

#### AI Generation Strategy (revised 2026-03-16, v3 — after model benchmarking)

**LESSONS LEARNED:**
- Kontext [pro] was tested on fal.ai playground. It has NO `strength`/`denoise` parameter — the only control is prompt text. Conservative prompts produce zero visible change. Assertive prompts help but the model lacks the dials needed for controlled glow-ups.
- The right approach needs: (1) a `strength` parameter to control how much the image changes, AND (2) face identity conditioning to prevent drift. Neither Kontext alone provides both.

##### Recommended Primary Pipeline: Flux PuLID

**Endpoint:** `fal-ai/flux-pulid`
**Why:** Only model on fal.ai that combines Flux-quality generation with a dedicated `id_weight` parameter (0-1) for identity preservation. You can push styling changes via prompt while independently tuning identity strength. This decouples "how much to change" from "how much face to preserve" — exactly what glow-ups need.

**Parameters:**
```
prompt: "{glow-up styling prompt}"
reference_image_url: "{source selfie URL}"
id_weight: 0.85              # Strong identity lock (tune: 0.75-0.95)
guidance_scale: 4.0           # Prompt adherence
num_inference_steps: 30       # Quality/speed balance
negative_prompt: "plastic skin, beauty filter, airbrushed, cartoon, blurry, distorted face, extra fingers, different person, altered bone structure"
image_size: "square_hd"       # 1024x1024
```

**Cost:** ~$0.033/megapixel = ~$0.035 at 1024x1024. Within budget.

##### Enhancement Pass: REMOVED

**`fal-ai/image-editing/face-enhancement` has been REMOVED from the pipeline.**
**Why removed:** This model performs skin retouching — it smooths skin, removes freckles, removes blemishes, and produces the exact "beauty filter" effect NXME must avoid. Natural skin features (freckles, moles, texture, pores) are identity markers that must be preserved. The PuLID output is the final image — no post-processing step.

**Total pipeline cost:** ~$0.035/generation (PuLID only). Well within ceiling.

##### Fallback Pipeline: Flux Dev img2img + IP-Adapter

**Endpoint:** `fal-ai/flux-general/image-to-image`
**Why:** Has both `strength` parameter (0.01-1.0) for controlling change magnitude AND `ip_adapters` list for face conditioning. More complex to configure but full control.

**Parameters:**
```
prompt: "{glow-up styling prompt}"
image_url: "{source selfie URL}"
strength: 0.55                # Sweet spot: visible change + identity preservation
guidance_scale: 4.5
num_inference_steps: 35
negative_prompt: "plastic skin, beauty filter, airbrushed, cartoon, distorted"
ip_adapters: [{               # Face identity conditioning
    path: "h94/IP-Adapter-FaceID",
    image_url: "{source selfie URL}",
    scale: 0.6
}]
```

**Cost:** ~$0.025/MP = ~$0.026 at 1024x1024. Cheapest option.

##### Tertiary Fallback: InstantID (SDXL)

**Endpoint:** `fal-ai/instantid`
**Why:** SDXL-based, dedicated identity preservation, cheapest. Lower quality than Flux but reliable.

**Parameters:**
```
prompt: "{glow-up styling prompt}"
face_image_url: "{source selfie URL}"
controlnet_conditioning_scale: 0.80
guidance_scale: 5.0
num_inference_steps: 30
model_type: "SDXL-v2-plus"    # Best quality variant
width: 1024, height: 1024
negative_prompt: "plastic skin, beauty filter, airbrushed, blurry, cartoon"
```

**Cost:** ~$0.02/image.

##### Model Selection Priority

| Priority | Model | When Used | Cost |
|----------|-------|-----------|------|
| 1 | Flux PuLID (no post-processing) | Default pipeline | ~$0.035 |
| 2 | Flux Dev img2img + IP-Adapter | PuLID circuit breaker open | ~$0.026 |
| 3 | InstantID (SDXL) | Both Flux models down | ~$0.02 |

16. **Primary model: Flux PuLID** (`fal-ai/flux-pulid`). `id_weight=0.85` for identity, prompt drives styling. `guidance_scale=4.0`, `num_inference_steps=30`.
17. **NO enhancement pass.** Face Enhancement model REMOVED — it strips freckles, moles, and skin texture (beauty filter behavior). PuLID output is the final image.
18. **Fallback 1: Flux Dev img2img** (`fal-ai/flux-general/image-to-image`). `strength=0.55`, IP-Adapter FaceID for identity. Used when PuLID unavailable.
19. **Fallback 2: InstantID** (`fal-ai/instantid`). SDXL with face embedding. Used when both Flux models down.
20. **Output resolution:** 1024x1024 (`square_hd` for PuLID, explicit `image_size` for others).

##### Prompt Strategy

21. **Prompt must be ASSERTIVE.** Tested: "do not change" / "preserve" language produces zero visible change with instruction-based models. Prompt describes what TO DO. Identity is enforced by `id_weight` (PuLID) / IP-Adapter (Flux Dev) / ArcFace post-check.
22. **Prompt template:** `prompts/glowup_pulid.txt` — positive styling prompt with face shape context.
23. **Negative prompt:** `prompts/glowup_negative.txt` — shared across all models. Targets: plastic skin, beauty filter, cartoon, identity drift, artifacts.
24. **Face-focused crop strategy:** If the input image has full body + environment, crop to head+shoulders (face bbox * 2.5x padding) before generation. After generation, composite back into original frame. This forces the model to focus on face/hair/grooming instead of background.
25. **Keyword allowlist:** `prompts/keyword_allowlist.py` — unchanged. Maps recommendation categories to allowed keywords.
26. **Max prompt keywords:** `MAX_PROMPT_KEYWORDS=6`.

##### Generation Parameters (by model)

| Parameter | PuLID | Flux Dev img2img | InstantID |
|-----------|-------|------------------|-----------|
| identity control | `id_weight=0.85` | IP-Adapter `scale=0.6` | `controlnet_scale=0.80` |
| guidance_scale | 4.0 | 4.5 | 5.0 |
| steps | 30 | 35 | 30 |
| strength/denoise | N/A (text-driven) | 0.55 | N/A |
| resolution | 1024x1024 | 1024x1024 | 1024x1024 |

##### Identity & Retry

27. **Identity retry:** On ArcFace failure (<0.80), retry once with `id_weight=0.95` (PuLID) or `strength=0.40` (Flux Dev) — more conservative. If second attempt fails → `IDENTITY_PRESERVATION_FAILED`, release credit, `retry_eligible: true`.
28. **ArcFace:** `insightface` buffalo_l, CPU, pre-loaded at startup. Embeddings ephemeral (ADR-1).
29. **Face detection on output:** No face detected → treat as identity failure.

##### Cost

30. **Revise cost ceiling:** `IMAGE_GEN_COST_CEILING_USD=0.06` (was 0.05, small bump for retry margin). `CREDIT_COST_ALERT_USD=0.05`. Pipeline costs ~$0.035 base, retry adds ~$0.035.
31. **Cost tracking:** Record actual cost per job including retries. Ceiling on 24h rolling average.

##### Style Keyword Injection from Face Analysis

32. **Face shape → prompt keywords mapping:**
    - Round face → "layered hairstyle with volume on top, angular accessories, contoured jawline"
    - Oval face → "versatile styling, soft waves, editorial portrait"
    - Square face → "textured layers, softening styles, rounded accessories"
    - Heart face → "side-swept styles, jaw-width accessories, forehead-balancing fringe"
    - Oblong face → "width-adding layers, horizontal emphasis, wide frames"
33. **Symmetry score influences lighting keyword:** High (>0.85) → "dramatic directional lighting". Lower → "soft even lighting, flattering angles".

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
