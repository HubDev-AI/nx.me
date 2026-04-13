# Glow Up — Tier 3 Architecture Refactor Plan

**Status:** Planned (ready for implementation).
**Date:** 2026-04-12.
**Source:** Extracted from [`docs/research/ai-makeup-mapping.md`](../research/ai-makeup-mapping.md) Decision Log. Grill-me session resolved Q1–Q8 for this refactor.
**Context:** nxme.ai is pre-launch. No backward-compat concerns. No mobile rollout risk. API + DB breaking changes free. Optimize for architectural cleanness.
**Goal:** Restructure Glow Up feature so its UI + backend become the shared foundation that the future Makeup feature (out of scope for this plan) will drop into.

---

## 1. Scope

### In scope
Items extracted from the Makeup research plan that apply to Glow Up:

| Plan Q | Glow Up impact |
|---|---|
| Q6 | Rename `analyses` → `uploads`. Split `glowup_analyses` table. Rename `glow_up_jobs` → `jobs` with polymorphic `source_type` + `source_id`. New routes `POST /uploads` + `POST /uploads/{id}/glowup/analyze` + `POST /uploads/{id}/glowup/generate`. Delete `app/api/analyses.py` |
| Q11 | Replace `BeforeAfterReveal.tsx` (wipe animation) with draggable `BeforeAfterSlider`. Full-width, 50/50 default split, entrance spring anim. Glow-ring ports to slider handle |
| Q12 | All Glow Up generations get 7-day TTL. Explicit "Save" = indefinite persistence. Nightly worker purges unsaved older than 7 days |
| Q13 | Static 2-up composite share (before + after, thin divider, labels). Client-side composition via `react-native-view-shot`. Always watermarked "nxme.ai · AI" |
| Q13b | Shared mobile components under `mobile/components/result/`: `BeforeAfterSlider`, `ShareComposite`, `Watermark`, `ResultActions` |
| Q14 | Slider entrance animation 0% → 50% spring on mount (~600ms), then draggable. Brand glow-ring ports to slider handle. Delete `BeforeAfterReveal.tsx` |
| Q17 | First-use face-mod consent modal (shared `FaceModConsent.tsx`). "AI-generated · not a photo" footer on result screen. Share composite carries combined "nxme.ai · AI" mark. Persistence via DB column `users.face_mod_consent_at` |
| Q18 | Verify client debounce (disable Analyze button during in-flight) + server `idempotency_key` work end-to-end. Infrastructure partially exists — add enforcement |
| Q19 | 30-day rolling upload retention. `uploads.last_accessed_at` updates on every read. Nightly purge worker. Upload-screen disclosure |
| Q21 (partial) | Analytics event schema for Glow Up: `glowup.upload.created`, `glowup.analyze.completed`, `glowup.generation.completed/failed`, `glowup.save`, `glowup.share`, `glowup.consent.granted`. **MST classifier deferred to Makeup milestone** (column exists, stays NULL) |

### Out of scope (Makeup-only — handled in separate feature plan)
- Makeup IA + feature card (Q1, Q2)
- Region chips (Q3)
- Session tap-to-try generation loop (Q4)
- `MakeupBackend` strategy, fal preset endpoint (Q5)
- Per-preset × intensity ArcFace thresholds (Q7)
- Preset YAML library (Q8)
- Preset selection (Q9)
- Intensity UX (Q10)
- Out-of-credits UX (Q15)
- Day-1 MST-stratified fairness benchmark (Q16)
- Age gate changes (Q20)
- Runtime MST classifier (Q21 — deferred)

---

## 2. Decision Log

| # | Decision | Locked answer |
|---|---|---|
| R1 | Refactor scope | Extract Q6, Q11, Q12 (extended to Glow Up), Q13, Q13b, Q14, Q17, Q18, Q19, Q21 (partial — no MST classifier). Rest Makeup-only |
| R2 | Phasing | **5 stacked PRs**. Order: (1) DB migration → (2) backend API restructure ∥ (3) shared mobile components → (4) mobile wire → (5) retention worker + analytics. Dev branch allowed broken between Phase 1 merge and Phase 4 merge. Ship-able at Phase 4 end |
| R3 | DB migration shape | **Fresh-start, single file** `0034_glowup_tier3_restructure.sql`. `DROP TABLE ... CASCADE` legacy tables. CREATE new schema. Dev seed data loss accepted |
| R4 | Backend API shape | **Two-step upload + service-class layer**. `POST /uploads` (fast, ~500ms) stores image + NSFW gate. Client then calls `POST /uploads/{id}/glowup/analyze` (slow, ~3s) for face analysis. Service classes `UploadService`, `GlowupService` wrap repos + pipeline. Routes thin |
| R5 | Mobile component libs | **Reanimated 3 custom slider + `react-native-view-shot` composite**. No `react-native-image-compare`. Custom ~150 LOC slider matches brand. View-shot offscreen JSX → PNG → native Share |
| R6 | Consent modal | **Ship with refactor + DB-backed**. `FaceModConsent.tsx` shared, persistence via `users.face_mod_consent_at TIMESTAMPTZ NULL`. Server rejects `POST /uploads/{id}/glowup/analyze` with HTTP 428 if unconsented. `POST /users/me/face-mod-consent` endpoint to record |
| R7 | Two-step upload UX | **Progressive auto-upload**. Photo picked → auto-triggers `POST /uploads` → upload errors surface in place → "Analyze" button enables on success → tap triggers `POST /uploads/{id}/glowup/analyze` → navigate to result. Mobile `UploadPhase` enum extends to `uploading` / `uploaded` / `analyzing` |
| R8 | MST classifier timing | **Deferred to Makeup milestone**. `uploads.mst_bin` column lands in Phase 1 (NULL-filled). Classifier dep + ~50ms overhead not added in this refactor |

---

## 3. Phases

### Phase 1 — DB migration

**Single PR. Blocks Phases 2–5.**

**File:** `app/migrations/0034_glowup_tier3_restructure.sql`

**Changes:**
1. Drop legacy tables with CASCADE:
   - `glow_up_jobs`
   - `analyses`
   - Any RLS policies on above
2. Drop dependent FK constraints in `credit_reservations`, `credit_ledger`, `usage_events` (if any reference `analyses` or `glow_up_jobs`) — verify before drafting DDL.
3. Create `uploads`:
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
   - `image_url TEXT NOT NULL`
   - `nsfw_result TEXT NOT NULL`
   - `face_detected BOOLEAN NOT NULL DEFAULT FALSE`
   - `last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `mst_bin SMALLINT NULL` (reserved for Makeup classifier; stays NULL for Glow Up in this refactor)
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Index on `(user_id, created_at DESC)`, `(last_accessed_at)`
4. Create `glowup_analyses`:
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE`
   - `face_shape TEXT`
   - `symmetry_score REAL`
   - `recommendations JSONB`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Unique index on `upload_id` (one analysis per upload)
5. Create `jobs` (generic, polymorphic):
   - `id UUID PK DEFAULT gen_random_uuid()`
   - `user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE`
   - `source_type TEXT NOT NULL CHECK (source_type IN ('glowup_analysis', 'makeup_session'))`
   - `source_id UUID NOT NULL` (app-layer FK integrity — PostgreSQL cannot do polymorphic FK)
   - `status TEXT NOT NULL` (`pending`, `queued`, `processing`, `finalizing`, `completed`, `failed`, `cancelled`)
   - `before_image_url TEXT`
   - `after_image_url TEXT`
   - `failure_reason TEXT`
   - `saved_at TIMESTAMPTZ NULL` (Q12)
   - `user_tier_at_enqueue TEXT`
   - `idempotency_key TEXT`
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - Unique index on `(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL`
   - Indexes on `(source_type, source_id)`, `(status)`, `(saved_at) WHERE saved_at IS NOT NULL`
6. Add `users.face_mod_consent_at TIMESTAMPTZ NULL` (R6).
7. Re-create RLS policies on `uploads`, `glowup_analyses`, `jobs`.

**Acceptance criteria:**
- `make migrate` applies cleanly on a fresh local Supabase.
- `make test` passes (tests will fail until Phase 2 lands — expected).
- RLS verified: user cannot read another user's `uploads` / `glowup_analyses` / `jobs`.
- Verification command: `ruff check app/` (migration file only) + SQL lint if configured.

**Risks:**
- CASCADE might drop rows in `credit_reservations` / `credit_ledger` / `usage_events` referencing jobs. Verify before running — may need to null out references instead.
- RLS policies on legacy tables must be dropped before the tables. Draft with explicit `DROP POLICY IF EXISTS` before `DROP TABLE`.

---

### Phase 2 — Backend API restructure

**Single PR. Depends on Phase 1 merged.**

**New files:**
- `app/api/uploads.py` — `POST /uploads` endpoint (shared primitive).
- `app/api/glowup.py` — `POST /uploads/{id}/glowup/analyze` + `POST /uploads/{id}/glowup/generate`.
- `app/api/jobs.py` — `GET /jobs/{id}`, `POST /jobs/{id}/save`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/refund`.
- `app/api/user_consent.py` — `POST /users/me/face-mod-consent`.
- `app/services/upload_service.py` — wraps `ImagePipeline` + `upload_repo`. Returns `{upload_id, face_detected}`.
- `app/services/glowup_service.py` — wraps `FaceAnalysisService` + `glowup_analysis_repo`. Returns `{glowup_analysis_id, face_shape, symmetry_score, recommendations}`.
- `app/repositories/upload_repo.py` — CRUD on `uploads` including `last_accessed_at` update-on-read.
- `app/repositories/glowup_analysis_repo.py` — CRUD on `glowup_analyses`.

**Modified files:**
- `app/repositories/job_repo.py` — rename `analysis_id` → `source_id`, add `source_type`, `saved_at` handling. Consumers updated.
- `app/generation/modules/styling.py` — if it reads `analysis_id` directly, rename. Likely receives `analysis_result` object; minimal change.
- `app/api/deps.py` — new dependency injectors for `UploadService`, `GlowupService`, `upload_repo`, `glowup_analysis_repo`.
- `app/api/middleware/auth.py` — no change expected.
- `app/main.py` (or wherever routers mount) — register new routers, unregister deleted ones.
- `app/api/generation.py` — split: `GET /jobs/{id}` + `POST /jobs/{id}/cancel|refund` move to `app/api/jobs.py`. Add `POST /jobs/{id}/save` (Q12). `POST /analyses/{id}/generate` logic moves to `POST /uploads/{id}/glowup/generate`. Delete file.

**Deleted files:**
- `app/api/analyses.py`
- `app/repositories/analysis_repo.py`

**Endpoint contracts:**

```
POST /uploads
  Request:  multipart file
  Response: { upload_id: UUID, face_detected: bool }
  Errors:   422 NSFW_QUARANTINE, 422 FORMAT_INVALID, 413 FILE_TOO_LARGE
  Timing:   ~500ms

POST /uploads/{upload_id}/glowup/analyze
  Request:  {}
  Response: { glowup_analysis_id: UUID, face_shape: str, symmetry_score: float, recommendations: [...] }
  Errors:   404 UPLOAD_NOT_FOUND, 422 FACE_NOT_DETECTED, 428 FACE_MOD_CONSENT_REQUIRED
  Timing:   ~3s

POST /uploads/{upload_id}/glowup/generate
  Request:  { idempotency_key: str | null }
  Response: { job_id: UUID, status: str, estimated_wait_seconds: int, queue_position: int }
  Errors:   404 ANALYSIS_NOT_FOUND, 402 PAYMENT_REQUIRED, 409 CONCURRENT_LIMIT, 428 FACE_MOD_CONSENT_REQUIRED, 409 IDEMPOTENT_DUPLICATE (returns cached job_id)
  Timing:   ~200ms (enqueue only)
  Notes:    Implicitly requires glowup_analysis for the upload. Resolves it server-side.

GET /jobs/{job_id}
  Response: { job_id, status, before_image_url, after_image_url, identity_preserved, failure_reason, saved_at, ... }
  Polling-safe

POST /jobs/{job_id}/save
  Response: { saved_at }
  Sets saved_at to NOW(). Idempotent.

POST /users/me/face-mod-consent
  Request:  {}
  Response: { consented_at }
  Sets users.face_mod_consent_at to NOW(). Idempotent — already-consented call is a no-op.
```

**Acceptance criteria:**
- `make lint` passes.
- `make test` passes (new tests for each new endpoint).
- `make up` serves new endpoints; `curl` smoke test against each returns expected contracts.
- `/analyses` and `/analyses/{id}/generate` return 404 (deleted).
- `POST /uploads/{id}/glowup/analyze` returns 428 for users with `face_mod_consent_at IS NULL`.
- `POST /uploads/{id}/glowup/generate` reuses existing credit-reserve + ARQ enqueue flow via `job_repo.create_job(source_type='glowup_analysis', source_id=...)`.
- Worker picks up jobs correctly via polymorphic `source_type` (existing worker code adapted).
- Idempotency key — second call with same key within 5 min returns cached `job_id`, zero fal spend, zero credit reserve.

**Risks:**
- Worker code (in `app/generation/modules/` + ARQ task) may tightly couple to `analysis_id`. Audit + adapt.
- Existing tests likely reference `/analyses` — update test fixtures.
- RLS must accept `user_id`-scoped reads on new tables — verify migration policies.

---

### Phase 3 — Shared mobile components

**Parallel-able with Phase 2. Depends on nothing external. Blocks Phase 4.**

**New files:**
- `mobile/components/result/BeforeAfterSlider.tsx` — draggable, entrance spring anim.
- `mobile/components/result/ShareComposite.tsx` — hook + offscreen view that renders 2-up + watermark.
- `mobile/components/result/Watermark.tsx` — subtle corner "nxme.ai · AI" mark.
- `mobile/components/result/ResultActions.tsx` — Save / Share / Try-again button bar.
- `mobile/components/consent/FaceModConsent.tsx` — first-use consent modal.

**Deleted files:**
- `mobile/components/result/BeforeAfterReveal.tsx`

**Dependency additions (`mobile/package.json`):**
- `react-native-view-shot` — new. Version: latest stable (verify via `pnpm info` or equivalent).

**Component specs:**

```tsx
// BeforeAfterSlider.tsx
interface Props {
  beforeUrl: string;
  afterUrl: string;
  rightLabel: string;  // e.g. "Glow Up" for this feature, "Clean Girl · Dewy" for Makeup
  initialSplit?: number;  // default 0.5
  entranceDurationMs?: number;  // default 600
  onAccessibilityToggle?: () => void;  // VoiceOver action
}

// ShareComposite.tsx (hook-based, headless)
const { generateAndShare } = useShareComposite();
await generateAndShare({
  beforeUrl,
  afterUrl,
  rightLabel: "Glow Up",
  // internal: render offscreen RN View with both images + <Watermark />, captureRef(ref, {format:'png', quality:1, result:'tmpfile'}), pass URI to Share.share
});

// Watermark.tsx
interface WatermarkProps {
  position?: "bottom-right" | "bottom-left";  // default "bottom-right"
  imageHeightPx: number;  // for 3% size calc
}

// ResultActions.tsx
interface Props {
  onSave: () => void;
  onShare: () => void;
  onTryAnother: () => void;
  saveState: "pending" | "saving" | "saved";
  creditsRemaining?: number | null;  // optional credit-badge display
}

// FaceModConsent.tsx
interface ConsentProps {
  visible: boolean;
  onAccept: () => void;  // triggers POST /users/me/face-mod-consent
}
```

**Implementation notes (validated via context7):**
- Slider: Reanimated 3 `useSharedValue(0)` → `value = withSpring(0.5, {damping: 15, stiffness: 150})` on mount → `Gesture.Pan().onChange(e => { shared.value = clamp(shared.value + e.changeX / width, 0, 1) })`. Clip right-side overlay using `useAnimatedStyle` returning `{ width: `${shared.value * 100}%` }`.
- Gesture + Reanimated: project already imports both. Verify RNGH version for callback naming (`onChange` vs `onUpdate`; current docs show `Gesture.Pan().onChange()` as v2+ pattern).
- Composite: offscreen `<View ref={viewRef} collapsable={false}>` sized 1080×1080 (or 1080×1350), absolutely positioned offscreen, parent `pointerEvents="none"`. Render two images + divider + `<Watermark />` inside. `captureRef(viewRef, {format:'png', quality:1, result:'tmpfile', width:1080, height:1080})` → URI → `Share.share({url})`.

**Acceptance criteria:**
- `cd mobile && npx expo lint` passes.
- Storybook-style smoke test screen (optional, `mobile/app/_devtools/components-preview.tsx` or similar) renders each component with mock props.
- Slider drag reaches 0% and 100% bounds without stuttering, entrance anim plays smoothly on mount.
- Share composite produces 1080×1080 PNG with both images visible + watermark in corner.
- Consent modal visible/dismiss states work with mock `onAccept`.
- VoiceOver action fires `onAccessibilityToggle` without requiring drag.

**Risks:**
- Reanimated + Gesture Handler API drift — confirm current callback names against project version in `package.json`.
- `react-native-view-shot` interaction with offscreen views: ensure parent `collapsable={false}` and view is laid out (not `display: none`) — common gotcha.
- Watermark text crispness at 1080×1080 — use `allowFontScaling={false}` + explicit font size.

---

### Phase 4 — Mobile wire + consent + AI disclosure

**Depends on Phase 2 + Phase 3 merged.**

**Modified files:**
- `mobile/app/upload.tsx` — switch to two-step upload (R7). Photo picked → auto `POST /uploads` → show errors in place → "Analyze" button enables → tap → `POST /uploads/{upload_id}/glowup/analyze` → navigate to result with analysis_id. `UploadPhase` enum extended: `idle | uploading | uploaded | analyzing | face_error | generating | error`.
- `mobile/app/result/[jobId].tsx` — replace `BeforeAfterReveal` import with `BeforeAfterSlider`. Add `ResultActions` component below gallery strip (Save + Share + "New Glow Up" replaces existing CTAs). Add "AI-generated · not a photo" footer. Wire Save → `POST /jobs/{id}/save`. Wire Share → `useShareComposite().generateAndShare(...)`.
- `mobile/lib/analysis.ts` — new functions: `createUpload(file)`, `analyzeGlowup(uploadId)`, `generateGlowup(analysisId, idempotencyKey)`, `saveJob(jobId)`, `grantFaceModConsent()`. Old `createAnalysis` + `startGeneration` deleted.
- `mobile/app/_layout.tsx` — mount `FaceModConsent` modal gated by a context hook that reads `user.face_mod_consent_at` (fetched with user profile). First Glow Up tap without consent → show modal → on accept, call `grantFaceModConsent()` → proceed.
- `mobile/components/result/SuggestionPills.tsx` — unchanged (Glow-Up-specific, stays where it is).
- `mobile/lib/api.ts` — update base paths if centralized.

**Deleted files:**
- Any old hooks/utilities referencing `createAnalysis` / `/analyses` endpoint.

**Acceptance criteria:**
- `cd mobile && npx expo lint` passes.
- Full flow works on iOS Simulator: photo pick → auto-upload → Analyze button → spinner → result screen → slider draggable → Save works (check DB `jobs.saved_at`) → Share produces 2-up composite in native share sheet.
- First-launch user without consent: modal appears on Analyze tap → accept → API call records consent → flow continues.
- Second-launch after consent: modal does not appear.
- "AI-generated · not a photo" footer visible on result screen.
- Retention disclosure visible on upload screen footer: "Photos auto-delete after 30 days of no activity."
- Manual QA on Android dev build.

**Risks:**
- Consent modal state: where does the `user.face_mod_consent_at` value live in client state? If fetched via `/me` endpoint, need to refresh after `POST /users/me/face-mod-consent`.
- Share composite offscreen render timing: `captureRef` called before images are laid out returns a blank PNG. Guard with Image `onLoad` → ready flag before enabling Share button.
- Existing `BeforeAfterReveal.tsx` import sites may extend beyond `result/[jobId].tsx` — grep before delete.

---

### Phase 5 — Retention worker + analytics

**Depends on Phase 4 merged (feature end-to-end working). Additive / non-blocking.**

**New files:**
- `app/workers/retention.py` — ARQ cron job. Nightly:
  - Delete `jobs` where `saved_at IS NULL AND created_at < NOW() - INTERVAL '7 days'`.
  - Delete `uploads` where `last_accessed_at < NOW() - INTERVAL '30 days'`. CASCADE drops `glowup_analyses` + `jobs` rows.
  - Also purges associated Supabase storage objects (image files).
- `app/analytics/events.py` — event schema + emitter.
  - `glowup.upload.created { upload_id, user_id, face_detected }`
  - `glowup.analyze.completed { glowup_analysis_id, upload_id, user_id, face_shape, symmetry_score, duration_ms }`
  - `glowup.analyze.failed { upload_id, user_id, failure_code }`
  - `glowup.generation.completed { job_id, analysis_id, user_id, arcface_score, latency_ms }`
  - `glowup.generation.failed { job_id, analysis_id, user_id, failure_code }`
  - `glowup.save { job_id, user_id }`
  - `glowup.share { job_id, user_id }`
  - `glowup.consent.granted { user_id }`

**Modified files:**
- `app/api/uploads.py`, `app/api/glowup.py`, `app/api/jobs.py`, `app/api/user_consent.py` — emit events at appropriate hooks.
- `app/repositories/upload_repo.py` — update `last_accessed_at` on read operations (ensures retention clock resets when user returns).
- `mobile/lib/analysis.ts` — fire client-side `glowup.share` event on Share completion (optional, or emit from server when implemented there).
- `worker.py` (or wherever ARQ workers are configured) — register retention task.
- `app/config/__init__.py` — `RETENTION_UPLOAD_DAYS = 30`, `RETENTION_JOB_DAYS = 7` (no magic numbers per `feedback_no_hardcoded_urls`).

**Acceptance criteria:**
- `make lint` passes, `make test` passes including retention worker unit tests.
- Retention worker run in dev with time-travel fixture (seed an upload with `last_accessed_at = NOW() - INTERVAL '31 days'`) → upload purged, CASCADE to analyses + jobs verified.
- Storage cleanup verified — Supabase storage bucket doesn't leak orphan image blobs.
- Analytics events appear in the configured sink (Mixpanel / PostHog / Amplitude — identify during planning; if no sink yet, log-only stub OK for v1).
- Retention disclosure on upload screen (Phase 4) matches the actual worker behavior.

**Risks:**
- Analytics sink identification: confirm what's in the project. If no sink, decide now — ship log-only events + add sink later, or pick a sink first.
- Supabase storage deletion requires service-role key + explicit bucket name — confirm env + perms.
- Retention worker on staging/prod needs scheduled invocation (Supabase cron pg_cron? ARQ periodic task? GH Actions schedule? — implementation call during Phase 5 PR).

---

## 4. Cross-phase risks + unknowns

- **Analytics sink not identified.** Resolve in Phase 5 PR kickoff — read existing integrations or make a pick.
- **Retention worker scheduling tech.** ARQ cron extension vs. pg_cron vs. external scheduler. Defer to Phase 5 impl call.
- **Worker code coupling to `analysis_id`.** Phase 2 audit required — the ARQ task that executes generation jobs likely references `analysis_id` directly; needs to read via polymorphic `source_id` + `source_type='glowup_analysis'` lookup.
- **Dev data re-seed.** Phase 1 nukes `analyses` + `glow_up_jobs` dev data. Teams that depend on seeded Glow Up test data must re-seed. Add a note to README runbook.
- **RNGH version drift.** Reanimated + Gesture Handler callback naming changed between major versions. Verify project's pinned version matches docs used (context7 examples showed `onChange`/`onFinalize`; project may be on older `onUpdate`/`onEnd`).
- **`face_mod_consent_at` on existing users.** Pre-launch = no prod users. Dev users get re-prompted on next launch. Accepted.

---

## 5. Verification loop (runs before each phase merge)

Per `CLAUDE.md` project conventions:

```bash
make format
make lint
make test
cd mobile && npx expo lint
```

Plus mobile manual QA on iOS Simulator for Phase 4. Code Review Graph per global CLAUDE.md: build graph + review delta before PR creation, fix criticals + highs, include summary in PR.

---

## 6. PR sequence + naming

1. **PR #1** — `feat(db): tier3 schema restructure (uploads, glowup_analyses, polymorphic jobs)` — Phase 1.
2. **PR #2** — `feat(backend): tier3 API restructure + service classes + consent endpoint` — Phase 2.
3. **PR #3** — `feat(mobile): shared BeforeAfterSlider, ShareComposite, ResultActions, FaceModConsent` — Phase 3 (mergeable independent of PR #2, UI-only).
4. **PR #4** — `feat(mobile): wire Glow Up to tier3 API + consent + AI disclosure + progressive upload` — Phase 4.
5. **PR #5** — `feat(ops): retention worker + analytics events` — Phase 5.

Between PR #1 merge and PR #4 merge the dev branch is broken end-to-end. Pre-launch so no deploy impact. Do not deploy to staging mid-sequence without completing #4.

---

## 7. Out-of-scope reminders

Anything Makeup-specific (Q1–Q5, Q7–Q10, Q15, Q16, Q20 from research) is **explicitly not part of this refactor**. The refactor prepares the ground; a separate Makeup feature plan implements on top.

Deferred to Makeup milestone:
- MST classifier + `uploads.mst_bin` population
- `makeup_sessions` table + `makeup` routes
- `MakeupBackend` strategy + fal preset endpoint
- `prompts/makeup_presets.yaml` + preset library
- Day-1 MST-stratified fairness benchmark
- Per-preset × per-intensity ArcFace threshold matrix
- Masculine preset set (v1.1 Makeup)
- Region chips (v1.1 Makeup)
