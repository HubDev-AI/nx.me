---
title: feat: Save / Share / Publish / Delete unified for glow-ups
type: feat
status: active
date: 2026-04-18
deepened: 2026-04-19
origin: docs/brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md
---

# feat: Save / Share / Publish / Delete unified for glow-ups

## Overview

Three user-facing actions on glow-ups — Save (private), Share (native share sheet), Publish (social feed + card-web) — surfaced through a single bottom-sheet dialog on the result screen and on saved-glow-up profile cells. Adds a new backend `DELETE /v1/jobs/{id}` that hard-cascades the job + post + reactions/comments/reports + images (DB rows via FK 0045) + `glowup_analyses` (app-layer ref-counted) + three storage buckets (`raw-selfies`, `generated-images`, `post-images`). Fixes the current 404-when-shared bug by attaching a card-web URL only when a post exists. Works with `social_enabled=false` (Save + image-only Share survive).

## Problem Frame

See origin: `docs/brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md` §1.

Current defects (confirmed in code audit):
1. `mobile/app/result/[jobId].tsx` appends `${UNIVERSAL_LINK_ORIGIN}/${username}` to share messages whenever `username` is truthy — producing 404 links for users who never posted or whose latest post was deleted/hidden.
2. `POST /v1/posts` exists and is `social_enabled`-gated, but no mobile UI ever calls it. Publishing has no entry point.
3. Completed glow-ups on the profile grid have no delete affordance (long-press only handles failed/cancelled via `DISMISS_ERRORED_JOB_*`).
4. Three actions (Save, Share, Publish) presented as same-bar buttons would not differentiate "private" vs "public" outcome. Risk: accidental public posts in a majority-female audience where that fear is acute.

## Requirements Trace

- **R1**. Save and Publish are distinct user-facing actions. (origin §3 Goal 1; user answer #1)
- **R2**. Feature works with `social_enabled=false`: Save + image-only Share still function; Publish is hidden. (origin §3 Goal 3; §7 matrix; user answer #2)
- **R3**. Deleting a saved glow-up removes every server-side remnant: `jobs` + `posts` + reactions/comments/reports + `images` (DB rows + blobs in all three buckets) + `glowup_analyses` (when unreferenced) + card-web reachability. (origin §3 Goal 4; user answer #3)
- **R4**. A unified share dialog explains what each action does so users never post publicly by accident. (origin §3 Goal 2; user answer #4)
- **R5**. Share attaches a card-web URL only when a non-deleted, non-hidden post exists for the shared job. No silent 404 links. (origin §5.5; user answer #5)
- **R6**. Delete is reachable from both the profile grid and the result screen. (origin §3 Goal 5; user answer #6)
- **R7**. Guests can Save, Share (image-only), and Delete their own glow-ups. Guests cannot Publish. (origin §3 Goal 6)
- **R8**. Share auto-saves (sets `saved_at`) so the shared result survives retention. (user follow-up answer, 2026-04-18)
- **R9**. Result-card Share uses the stable hash URL `/{username}/glow-up/{share_hash}`. Profile-header Share uses `/{username}`. (user follow-up answer, 2026-04-18)
- **R10**. Post-detail `DELETE /posts/{id}` stays soft-delete. Glow-up delete does hard cascade. (user follow-up answer: keep divergent, 2026-04-18)

## Scope Boundaries

- No feed redesign, card-web layout change, or post-detail redesign.
- No caption editor, mentions, or hashtags in Publish. Caption stays optional ≤500 chars, HTML-stripped (existing server behavior).
- No change to `POST /v1/jobs/{id}/save` semantics — reused as-is, plus called from Share path (R8).
- No change to `DELETE /posts/{id}` semantics (stays soft-delete per R10). The new glow-up delete does not call it.
- No backfill of `orphan_storage` for existing public `post-images` left by prior deletes (pre-launch, per `feedback_pre_launch_destructive_ok`).
- No migration of existing `saved_at` rows; behavior change is forward-only.

### Deferred to Separate Tasks

- Unpublish-without-delete affordance (keeps analysis + before/after private) — future, only if user demand surfaces.
- **Published-state globe indicator on profile grid** — a visual marker on cells whose `post_id != null`. Nice-to-have UX but not required by R6 (which only demands delete reachability). Deferred to a dedicated UX pass with its own requirement. If added later, will require extending the profile glowups response with `post_id`.

## Context & Research

### Relevant Code and Patterns

- `app/api/jobs.py` — existing `POST /jobs/{id}/save`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/refund` with `get_user_or_guest` pattern. New DELETE lands here.
- `app/api/posts.py` — `POST /posts` + `DELETE /posts/{id}` (soft). Gated on `social_enabled` via router-level `Depends(require_app_feature("social_enabled"))`. Keep as-is per R10.
- `app/api/auth.py::delete_account` (lines 1313-1450) — reference pattern for enumerate-before-cascade, orphan DLQ insert on failure, ARQ enqueue for large-blob sets, idempotent 204 on missing row.
- `app/repositories/orphaned_storage_repo.py::OrphanedStorageKeyRepository.record(bucket, storage_key, reason)` — idempotent upsert into `orphaned_storage_keys`, never raises.
- `app/workers/orphan_reclaim.py::reclaim_orphaned_blobs` — nightly cron consumer, drains `list_pending` via `image_repo.remove`. No changes required.
- `app/services/public_url.py::publish_post_images` — existing public-bucket write. Needs a sibling cleanup helper.
- `app/migrations/0045_delete_account_cascade_completeness.sql` — confirms `posts.glow_up_job_id ON DELETE CASCADE FROM jobs`, and `reactions/comments/reports.post_id ON DELETE CASCADE FROM posts` (from earlier migrations; reports added in 0045). Deleting the `jobs` row cascades posts + children automatically at DB level.
- `app/workers/retention.py` — keeps `saved_at IS NOT NULL` indefinitely; purges others after `RETENTION_JOB_DAYS`. No changes needed; R8 fits this invariant naturally.
- `mobile/components/subscription/CancelSubscriptionSheet.tsx` — closest precedent for the new dialog: `Modal` + `react-native-reanimated` scale/fade + destructive confirm. Mobile has no external bottom-sheet library.
- `mobile/components/result/ResultActions.tsx` — current two-row button bar; primary row gets collapsed into "Save on profile" + "Share & Publish…" (opens dialog).
- `mobile/components/result/ShareComposite.tsx` — `useShareComposite` already plumbs `shareUrl` + `shareMessage`. Only the caller's decision rule changes.
- `mobile/app/(tabs)/profile.tsx` + `mobile/components/profile/GlowUpGrid.tsx` — profile grid. Long-press currently dismisses errored cells only; extended to completed cells here.
- `mobile/lib/capabilities.ts` — `useCapabilities()` is the single gating surface. New `canPublishGlowup` capability joins `canSeeFeed`/`canShareGlowup`.

### Institutional Learnings

- `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` — critical precedent:
  - **Enumerate blob keys BEFORE the DB cascade**, otherwise the join to find them dies with the row.
  - **DELETE endpoints are idempotent 204**, not 404, to tolerate client retries across flaky networks.
  - **Every new user-owned surface wires into the delete choke point.** This plan adds three buckets worth of enumeration; the helper extracted for per-job use must also work for `delete_account` (deferred follow-up).
  - **ARQ `enqueue_job` returns `None` on dedup** — check the return value or use `_job_id` carefully.
  - Compensating nightly sweeper (`retention.py::reconcile_orphaned_users`) catches partial failures.

### External References

None. The domain is well-patterned internally.

## Key Technical Decisions

- **Single endpoint, not two.** One `DELETE /v1/jobs/{job_id}` handles everything. Avoids a second cascade implementation and keeps the invariant testable as one unit.
- **Idempotent 204.** Matches `delete_account`. Prevents client-retry confusion after network failures.
- **Enumerate blobs before DB cascade.** The `jobs → posts → images` joins are gone after the cascade fires; collect `(bucket, storage_key)` tuples across all three buckets first, then issue the single DB delete, then inline-delete blobs with orphan DLQ on failure.
- **Inline blob wipe, not ARQ.** A single job touches at most ~5 blobs (before/after in `raw-selfies`, after in `generated-images`, before+after in `post-images`). `delete_account`'s 500-blob ARQ threshold doesn't apply. On any blob delete failure, record to `orphaned_storage_keys` with `reason="delete_glowup"`; the nightly reclaim job drains it. No new ARQ task. No separate helper — the wipe is inline in Unit 5 following the same three-arg `image_repo.remove(bucket, key)` call delete_account already uses.
- **No new `cleanup_post_images` helper.** Earlier draft proposed extracting one from `publish_post_images`. Audit (2026-04-18) confirms `delete_account` already enumerates `posts.before_image_url`/`after_image_url` into the `post-images` bucket via `user_repo.list_user_storage_keys` (docstring: `"post-images — posts.before_image_url + posts.after_image_url"`). The premise "delete_account has a post-images gap" was wrong. Extracting a helper for a single consumer is speculative generality; inline in Unit 5 instead.
- **`glowup_analyses` is app-layer ref-counted.** No FK cascade exists (confirmed: migration 0034 declares `source_id UUID NOT NULL` with no REFERENCES clause; retention worker comment confirms independent lifecycle). Peer definition: rows in `jobs` WHERE `source_id = <this.source_id>` AND `id != <this.id>` AND `status NOT IN ('cancelled')` (cancelled jobs already released their reservation and should not keep an analysis alive; completed/failed/processing/queued peers DO keep it). If peers = 0, the analysis row is deleted in the same request. Upload rows are NOT touched here — they have independent lifecycle managed by `retention.py` via `RETENTION_UPLOAD_DAYS`/`last_accessed_at`. Deleting an upload would break the retention contract and the re-generate-from-same-upload flow.
- **Partial UNIQUE(glow_up_job_id) WHERE is_deleted = FALSE AND is_hidden = FALSE on posts.** Prevents double-publish if the client races. Partial index permits re-publish after a soft-delete or auto-hide — a user whose first post was moderated can post again without the constraint blocking them. Pre-launch so no data migration needed. If a duplicate POST arrives (unique_violation), Unit 2's handler looks up the live post + re-checks ownership + returns it as 200 — caller idempotency.
- **`JobStatusResponse` gains `post_id` + `share_hash` fields.** Mobile client needs them for: (a) hiding the Publish row when already published, (b) deciding whether to append the card-web URL in Share, (c) building the hash-URL for result-card Share. Pattern: nullable `| None = None` optional fields, populated when a non-deleted post exists.
- **New capability `canPublishGlowup`.** `social_enabled AND session.isUser && !session.isGuest`. Never read `features.X` directly in the dialog per project rule.
- **Dialog reuses `CancelSubscriptionSheet.tsx` shape.** Modal + Reanimated, destructive-confirm idiom already in the app. No new dependency.
- **Hash-URL in result-card Share, `/{username}` stays for profile-header Share.** Per R9. Both endpoints already exist (`/public/cards/{username}` and `/public/cards/{username}/{share_hash}`) — no backend URL work.
- **Dialog always opens — no one-row skip.** The brainstorm proposed skipping the dialog when only one action is enabled. Skipped: the "Share & Publish…" label promises a menu; delivering a share sheet instead violates user expectation. If only one action is available, the dialog still shows it. Exception: if zero rows would be shown (impossible in practice — Share is always shown for completed jobs), short-circuit. Trade-off accepted to keep UX predictable.
- **"Share & Publish…" button label adapts.** When `canPublishGlowup === false`, label becomes "Share…" (no false promise). When already published, stays "Share…" (Publish row is hidden but Share with URL remains).
- **Long-press on completed profile cells opens the same dialog + adds "Delete".** Profile surface also gets a visible published-state icon on each cell (so users can see what's public without tapping).
- **Long-press on in-progress cells is a no-op** (swallow gesture, matching current "nothing happens" behavior for pending/processing/queued).
- **Delete endpoint is status-gated: `completed` | `failed` | `cancelled`.** Queued/processing jobs must be cancelled first (existing `POST /jobs/{id}/cancel` path). This matches `cancel_job`'s status-state separation and avoids racing ARQ.
- **Mobile post-delete state: navigate back to `(tabs)/profile` + invalidate `['job', id]` + `['profile.glowups', username]` query keys.** Result screen becomes invalid after delete; do not linger.

## Open Questions

### Resolved During Planning

- **Card-web URL shape for result-card Share** → hash-URL `/{username}/glow-up/{share_hash}` (user answer).
- **Divergent vs unified post delete** → keep divergent (user answer); post detail soft-delete unchanged.
- **Share → Save** → yes, Share auto-saves (user answer). Implementation: `shareGlowup` calls `POST /v1/jobs/{id}/save` before invoking `generateAndShare`. The save call is idempotent (returns original `saved_at` on second call), so no harm if user already saved.
- **Dialog skip-when-one-row** → removed; dialog always opens.
- **Capability gating** → new `canPublishGlowup` added; never read `features.X` directly.
- **DELETE response shape** → 204 idempotent (missing row + wrong owner both 204 to prevent ownership enumeration). Matches `delete_account`.
- **`post-images` cleanup** → inline in Unit 5 using the same enumerate-via-`posts.before_image_url`/`after_image_url` pattern `user_repo.list_user_storage_keys` + `delete_account` already use. No new helper (earlier draft's `cleanup_post_images` extraction was based on a false premise that delete_account had a gap — it doesn't).
- **Duplicate POST /posts** → `UNIQUE(glow_up_job_id)` constraint; endpoint catches IntegrityError and returns existing post as 200 with the same payload shape (caller-idempotent).
- **Long-press on in-progress cells** → no-op (swallow).

### Deferred to Implementation

- Exact dialog copy strings — deferred to design pass with writer review (see `feedback_female_user_targeting`). Use placeholder text in this plan; finalize before merge.
- Whether the delete confirm on the result screen uses `Alert.alert` (matching current `DISMISS_ERRORED_JOB_*` pattern on profile grid) or the same `Modal`-based sheet — implementer chooses based on visual consistency with `CancelSubscriptionSheet.tsx`.
- Exact FK direction for pre-0045 `reactions.post_id`, `comments.post_id` — verify during Unit 1 by reading the migration files; if not `ON DELETE CASCADE` already, add to the new migration.
- Analytics event payload shape (`glowup_publish`, `glowup_delete`, `glowup_share_dialog_opened`) — follow existing `events.glowup_save` shape in `app/analytics/events.py`.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

Delete cascade, left-to-right = user click to final state:

```
User taps Delete
     │
     ▼
DELETE /v1/jobs/{id}
     │
     ├─► owner check (get_user_or_guest; wrong owner → 204)
     ├─► status gate (completed|failed|cancelled; else 409)
     ├─► ENUMERATE blob keys  ◄── runs BEFORE cascade (joins exist)
     │      raw-selfies: jobs.before_image_url
     │      generated-images: jobs.after_image_url
     │      post-images: posts.before_image_id/after_image_id → images.storage_key (if post exists)
     ├─► REF-COUNT glowup_analyses
     │      peers = jobs where source_id = this.source_id AND id != this.id
     │      if peers = 0, mark analysis for delete
     ├─► DELETE FROM jobs WHERE id = this.id
     │      FK cascade fires:
     │        posts (glow_up_job_id)
     │          └─► reactions, comments, reports (post_id)
     │        images (before_image_id, after_image_id via posts)
     │        credit_reservations, prompt_experiments
     ├─► if peers = 0:
     │      DELETE FROM glowup_analyses WHERE id = source_id
     ├─► INLINE blob wipe across all collected keys
     │      on exception: orphan_repo.record(bucket, key, "delete_glowup")
     └─► 204 No Content
```

Mobile share dialog state machine:

```
[Share & Publish…] button
        │
        ▼
  Open dialog
        │
   Decide rows:
      Save       — show if saved_at is null
      Share      — always show (given result exists)
      Publish    — show if canPublishGlowup AND post_id is null

        │
   User taps row
        │
        ├─► Save   → POST /jobs/{id}/save → close dialog → update saveState
        ├─► Share  → ensure saved (auto-save if saved_at null, per R8)
        │            → build shareUrl from (post_id? hash : null)
        │            → useShareComposite.generateAndShare(...)
        └─► Publish → Confirm modal
                       → POST /v1/posts
                       → on 201: update local post_id + share_hash
                       → close dialog
```

Client post-existence signal (why `JobStatusResponse` grows):

```
GET /v1/jobs/{id}
     └─► includes post_id, share_hash when a non-deleted, non-hidden post exists for this job
Mobile derives:
     isPublished       = response.post_id != null
     resultShareUrl    = isPublished ? `${ORIGIN}/${username}/glow-up/${share_hash}` : undefined
     showPublishRow    = canPublishGlowup && !isPublished
```

## Implementation Units

- [ ] **Unit 1: DB — UNIQUE(glow_up_job_id) + FK verification pass**

**Goal:** Prevent duplicate posts per glow-up; confirm cascade FKs for reactions/comments.

**Requirements:** R3

**Dependencies:** None.

**Files:**
- Create: `app/migrations/0046_unique_post_per_glowup_job.sql`
- Modify: none
- Test: `tests/test_posts_unique_constraint.py`

**Approach:**
- Add **partial** `UNIQUE (glow_up_job_id) WHERE is_deleted = FALSE AND is_hidden = FALSE` on `posts`. Partial so a user can re-publish after their first post is soft-deleted or auto-hidden without hitting the constraint (otherwise the user is stuck — no path to a fresh post).
- Safe pre-launch per `feedback_pre_launch_destructive_ok` — verify no dup live rows first; if any exist, delete them in the same migration.
- `reactions.post_id` and `comments.post_id` **already have `ON DELETE CASCADE FROM posts`** (confirmed in `app/migrations/0001_initial.sql`). Migration 0045 adds the same for `reports.post_id`. This unit's migration does not need to re-declare them — but the accompanying integration test still verifies the cascade holds end-to-end (catches future schema drift).

**Patterns to follow:**
- `app/migrations/0045_delete_account_cascade_completeness.sql` — style for adding FK cascades.
- Ordering from `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` invariant 1.

**Test scenarios:**
- Happy path: `POST /v1/posts` for a fresh glow_up_job_id → 201.
- Edge case: `POST /v1/posts` for the same glow_up_job_id a second time → 200 (returns existing post; see Unit 2).
- Integration: FK direction test — insert post + reaction + comment + report, `DELETE FROM jobs WHERE id = ?`, assert all four rows are gone.

**Verification:**
- `make migrate` runs clean on a fresh DB.
- Unique constraint visible in `\d+ posts`.
- Integration test passes.

- [ ] **Unit 2: Backend — `POST /v1/posts` idempotent on duplicate glow_up_job_id**

**Goal:** Surface Unit 1's unique constraint as caller-idempotency rather than a 500.

**Requirements:** R3, R6 (indirectly — publish-once invariant)

**Dependencies:** Unit 1.

**Files:**
- Modify: `app/api/posts.py` (create_post endpoint)
- Modify: `app/repositories/post_repo.py` (add `get_by_glow_up_job_id`)
- Test: `tests/test_posts_create_idempotency.py`

**Approach:**
- On `IntegrityError` (unique_violation on `glow_up_job_id`), load existing live post (`is_deleted=FALSE AND is_hidden=FALSE`) for that job via the new repo method.
- **Ownership re-check:** if the existing post belongs to a different user (shouldn't happen — jobs are user-scoped — but defend in depth), return 404 like the create path does, not the existing post. Prevents leaking another user's post_id if a job_id ever gets re-assigned.
- If existing live post found AND owned by caller → return 200 with the same `PostResponse` shape the 201 branch produces. Preserve the Location header pointing at the existing id.
- If unique_violation fires but no live post is found (post was soft-deleted/hidden between INSERT attempt and lookup), retry INSERT once. The partial unique constraint (Unit 1) permits a fresh post after soft-delete. A second failure escalates as 500.
- Do not short-circuit with a pre-check (`SELECT` before `INSERT`) — that's a TOCTOU. Let the DB race the partial constraint.

**Patterns to follow:**
- `app/api/jobs.py::save_job` idempotency pattern (returns same `saved_at` on retry).

**Test scenarios:**
- Happy path: fresh `glow_up_job_id` → 201 Location header set.
- Edge case: second call with same `glow_up_job_id` → 200, body matches the 201 response.
- Error path: `glow_up_job_id` belongs to a different user → 404 (existing behavior).
- Error path: DB raises a non-unique IntegrityError (simulated) → 500 (current behavior preserved — only unique_violation is caught).

**Verification:**
- Two sequential POSTs from the same user with the same job_id produce identical `post_id` in both responses.

- [ ] **Unit 3: Backend — `JobStatusResponse` gains `post_id` + `share_hash`**

**Goal:** Give the client the signal it needs to gate Publish + build the correct Share URL.

**Requirements:** R4, R5, R9

**Dependencies:** Unit 1 (unique constraint ensures at most one post per job).

**Files:**
- Modify: `app/api/jobs.py` (`JobStatusResponse`, `get_job`)
- Modify: `app/repositories/post_repo.py` (add `get_active_by_glow_up_job_id` returning `{id, share_hash}` or None)
- Test: `tests/test_jobs_response_post_fields.py`

**Approach:**
- Add two nullable optional fields: `post_id: str | None = None`, `share_hash: str | None = None`.
- Populate them only when `status == COMPLETED` AND a non-deleted, non-hidden post exists for this job. One extra query per poll — cheap.
- Non-hidden test: `posts.is_deleted IS FALSE AND posts.is_hidden IS FALSE` (auto-hide per `posts.py` report threshold).

**Patterns to follow:**
- `app/api/jobs.py::get_job` state-gated field population.

**Test scenarios:**
- Happy path: completed job with active post → both fields populated.
- Edge case: completed job, no post → both null.
- Edge case: completed job with soft-deleted post → both null (breaking-link fix per R5).
- Edge case: completed job with auto-hidden post → both null.
- Integration: polling a `processing` job (no post yet) returns null fields.

**Verification:**
- Shape in tests matches `response["post_id"]` is set iff user can share a live card-web URL.

- [ ] **Unit 4 (dropped)** — was `cleanup_post_images` helper extraction. Removed after 2026-04-18 audit confirmed `delete_account` already enumerates `post-images` via `user_repo.list_user_storage_keys`. No cross-consumer helper needed. Per-job blob wipe is inlined in Unit 5.

- [ ] **Unit 5: Backend — `DELETE /v1/jobs/{job_id}` endpoint (the main event)**

**Goal:** Hard-cascade a glow-up and everything it produced. Idempotent. Status-gated. Rate-limited. Orphan-DLQ fallback.

**Requirements:** R3, R6, R7

**Dependencies:** Unit 1 (FK guarantees), Unit 3 (fresh post lookup).

**Files:**
- Modify: `app/api/jobs.py` (add `delete_job` endpoint; reuse `Response(204)` with no body)
- Modify: `app/repositories/job_repo.py` (add `enumerate_blob_keys_for_delete`, `count_peer_jobs_for_source`, `delete_by_id`, `delete_analysis_by_id`)
- Modify: `app/analytics/events.py` (add `glowup_delete`)
- Modify: `app/api/deps.py` or `app/services/rate_limiter.py` (add `check_delete_glowup_rate_limit` mirroring `check_delete_account_rate_limit`)
- Test: `tests/test_delete_glowup_cascade.py`

**Approach:**
- Auth: `get_user_or_guest` (guest parity per R7).
- **Rate limit:** per-caller Redis-backed limit mirroring `check_delete_account_rate_limit` (auth.py:1339). Guest callers keyed on `sub` (guest UUID from token), real users on `sub`. Conservative: 10 deletes/minute/caller. Prevents DoS sweep + unbounded orphan DLQ growth if blob wipes keep failing.
- Status gate: `completed | failed | cancelled`. Other statuses → 409 with existing `JOB_NOT_CANCELLABLE`-style error (user must cancel queued/processing first).
- **Enumerate-before-cascade (order matters — the joins vanish after cascade):**
  1. Fetch job (owner check: different owner → 204, see wrong-owner posture note below).
  2. Collect private-bucket keys: `job.before_image_url` (raw-selfies), `job.after_image_url` (generated-images).
  3. Look up active post (Unit 3's helper: `is_deleted=FALSE AND is_hidden=FALSE`). If present, read `posts.before_image_url` and `posts.after_image_url` directly (these are the `post-images` bucket keys, stored denormalized per `user_repo.list_user_storage_keys` convention — keeps enumeration path identical to `delete_account`).
  4. Ref-count source_id (see "peers" definition in Key Technical Decisions): `count_peer_jobs_for_source(source_id, exclude_id=job_id, exclude_statuses={"cancelled"})`. If 0, mark analysis row for deletion post-cascade. (TOCTOU acknowledged in Risks table; pre-launch state + nightly compensation accepted.)
- **DB cascade:** `DELETE FROM jobs WHERE id = ?`. FK 0045 + pre-existing cascades (confirmed in `0001_initial.sql` for reactions/comments) wipe posts/reactions/comments/reports/credit_reservations/prompt_experiments automatically. No app-layer cleanup needed for those.
- **Post-cascade app-layer cleanup:**
  1. If analysis was marked for deletion: `DELETE FROM glowup_analyses WHERE id = <this_job.source_id>` (the UUID read from the fetched job's `source_id` field — no FK, explicit query).
  2. Do NOT touch `uploads` — retention.py owns that lifecycle.
- **Inline blob wipe:**
  1. For each `(bucket, key)` collected across `raw-selfies`, `generated-images`, and (if post existed) `post-images`: call `image_repo.remove(bucket, key)`.
  2. On exception: `orphan_repo.record(bucket, key, "delete_glowup")`. The `reason` is a hardcoded server-side constant — never accept user input here. Continue; do not abort.
- **Emit `events.glowup_delete(job_id, user_id)`.**
- **Return 204.**
- **Idempotent 204 posture (intentional divergence from sibling /jobs endpoints):** missing job + wrong-owner + already-deleted all return 204. This mirrors `delete_account` and the `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` invariant (idempotent DELETE tolerates client retry over flaky networks). It diverges from `GET/cancel/refund/save` on the same resource which return 404 on wrong-owner. The divergence is deliberate — destructive ops that are retried must not return 404 on the second call, or clients can't tell success from "never existed". Document this in the endpoint docstring.

**Execution note:** Test-first. Write the cascade integration test (real DB, real blob cleanup mocked at `image_repo.remove`) before wiring the endpoint.

**Patterns to follow:**
- `app/api/auth.py::delete_account` (enumerate-before-cascade, orphan DLQ fallback, idempotent 204).
- `app/api/jobs.py::cancel_job` (status gate + ownership 404 idiom; adapt to 204).
- `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` invariants 1-5.

**Test scenarios:**
- Happy path: completed job with no post → job row gone, raw-selfies + generated-images blobs removed, no `post-images` touched, analysis ref-count >0 → analysis stays, 204 returned.
- Happy path: completed job with an active post → all above + posts + reactions + comments + reports rows gone (FK cascade), post-images blobs removed, card-web `/public/cards/{username}/{share_hash}` returns 404 after.
- Happy path: completed job with orphan analysis (peers=0) → analysis row also deleted.
- Happy path: completed job where analysis has peers (another undeleted job on same source_id) → analysis survives.
- Edge case: already-deleted job (second DELETE) → 204.
- Edge case: wrong owner → 204 (no enumeration leak).
- Edge case: guest caller with X-Guest-Token → same behavior as real user (R7).
- Edge case: failed job → cascades same as completed.
- Error path: `processing` job → 409 JOB_NOT_CANCELLABLE.
- Error path: `queued` job → 409 JOB_NOT_CANCELLABLE.
- Error path: `image_repo.remove` raises for the post-images `before` key → that key lands in `orphaned_storage_keys` with reason `"delete_glowup"`; endpoint still returns 204; DB row is still gone.
- Error path: `orphan_repo.record` itself raises (simulated) → endpoint returns 204 (do not block; the sweeper will still find leaked blobs, though the DLQ row won't exist — log at WARN).
- Integration: after delete, `GET /v1/jobs/{id}` returns 404, `GET /v1/public/cards/{username}/{share_hash}` returns 404, `GET /v1/public/cards/{username}` falls back to the next latest post if any.
- Integration: delete-account-parity — run `delete_account` on a user that has one published glow-up; confirm the same `post-images` blobs get enumerated (via this unit's helper reused).

**Verification:**
- All test scenarios pass against a real local Supabase (`make up`), not mocks.
- DB row count invariant: after delete, `SELECT count(*) FROM jobs WHERE id = ?` is 0; same for posts/reactions/comments/reports/images.
- Storage invariant: blob keys collected pre-cascade are either removed or present in `orphaned_storage_keys`. No silent leaks.

- [ ] **Unit 6: Mobile — `canPublishGlowup` capability**

**Goal:** Centralize the Publish gate; never read `features.X` directly in the dialog.

**Requirements:** R2, R4, R7

**Dependencies:** None.

**Files:**
- Modify: `mobile/lib/capabilities.ts`
- Modify: `mobile/lib/capabilities.test.ts`

**Approach:**
- Add `canPublishGlowup: boolean` → `features.social_enabled && session.isUser && !session.isGuest`.
- Add corresponding row to the matrix test so every (features × session) combination has a known expected value.

**Patterns to follow:**
- Existing `canShareGlowup`, `canSeeFeed`, `canViewBlockedUsers` derivations.

**Test scenarios:**
- Matrix: real user + social on → true.
- Matrix: real user + social off → false.
- Matrix: guest + social on → false.
- Matrix: guest + social off → false.
- Matrix: anon + any → false.

**Verification:**
- `npx expo lint` clean; capabilities test matrix passes.

- [ ] **Unit 7: Mobile — `ShareDialog` component**

**Goal:** The unified bottom-sheet that surfaces Save / Share / Publish with plain-language explanations.

**Requirements:** R1, R2, R4

**Dependencies:** Unit 6 (capability).

**Files:**
- Create: `mobile/components/result/ShareDialog.tsx`
- Create: `mobile/components/result/ShareDialog.test.tsx`

**Approach:**
- Modal + Reanimated, following `mobile/components/subscription/CancelSubscriptionSheet.tsx` shape.
- Props: `visible`, `onClose`, `job: { id, saved_at, post_id, share_hash }`, `onSave`, `onShare`, `onPublish`, `saveState: SaveState`.
- Rows computed at render time from `useCapabilities()` + job state:
  - Save: show when `saved_at` is null AND user has a valid session.
  - Share: always shown when the dialog opens.
  - Publish: show when `canPublishGlowup` AND `post_id` is null.
- Dialog always opens (no one-row skip — decision recorded above).
- Publish row tap → in-dialog confirm panel (replace rows with a Cancel / Publish confirm, avoiding a second modal stacked).
- **Publish confirm copy must name:** "Your before/after will appear on the public feed and at nxme.ai/{username}" — explicit about public-ness and where it shows. Matches R4 ("never by accident").
- **Share row subtitle must disclose auto-save** (see Unit 8 `onShare` handler). Non-disclosure = silent persistence mutation = R4 violation.
- **Delete confirm copy (triggered from Unit 8 + Unit 9) must name external-link breakage:** "Links you've already shared will stop working. This can't be undone." Otherwise the hash-URL contract from R9 leaves users with dead links they didn't know they were creating.
- Writer review blocking on all three copy strings per `feedback_female_user_targeting`. Implementer places placeholder strings + a `TODO(writer-review)` comment.

**Patterns to follow:**
- `mobile/components/subscription/CancelSubscriptionSheet.tsx` for Modal+Reanimated+destructive confirm.
- `mobile/components/result/ResultActions.tsx` for `ActionButton` idiom (visible-when-disabled, haptics).
- `feedback_disabled_button_ux` — Save row stays rendered when already-saved but visually disabled; Share row never disabled; Publish row disabled + opacity when in-flight.

**Test scenarios:**
- Happy path: real user + social on + not saved + not published → all three rows render.
- Happy path: real user + social off + not saved → Save + Share render; Publish hidden.
- Happy path: guest + not saved → Save + Share render; Publish hidden.
- Happy path: real user + saved + published → Share row only (others hidden).
- Edge case: Publish tap → confirm panel replaces rows; Cancel returns to rows.
- Integration: tapping Save calls `onSave` once; tapping Publish and confirming calls `onPublish` once.

**Verification:**
- Component test renders correct rows for each capability matrix cell.
- Manual check on iOS Simulator — sheet slides up, swipe-to-dismiss works.

- [ ] **Unit 8: Mobile — Result screen wiring**

**Goal:** Replace `ResultActions`'s current primary row with "Save on profile" + "Share & Publish…" (or "Share…" when `canPublishGlowup` is false). Add Delete via screen header overflow. Wire `ShareDialog` + confirmation + state after publish.

**Requirements:** R1, R4, R5, R6, R8, R9

**Dependencies:** Units 3, 4, 5, 6, 7.

**Files:**
- Modify: `mobile/components/result/ResultActions.tsx`
- Modify: `mobile/app/result/[jobId].tsx`
- Test: `mobile/app/result/__tests__/[jobId].test.tsx`

**Approach:**
- `ResultActions` primary row becomes: outline "Save on profile" (existing semantics) + primary "Share & Publish…" (opens dialog). Label swaps to "Share…" when `canPublishGlowup === false`.
- Dialog state lives on `[jobId].tsx` (parent screen).
- `onShare` handler (auto-save is **blocking** — failure must not silently proceed, else R5 "no 404 links" is violated when retention purges the unsaved job later):
  1. If `saved_at` is null: `await POST /v1/jobs/{id}/save` (R8). On 5xx/network error → surface inline error in dialog ("Couldn't save — try again"), do NOT open the native share sheet, do NOT call generateAndShare. User retries.
  2. On save success (or if already saved): update local state, build `shareUrl`: if `post_id` is set, `${UNIVERSAL_LINK_ORIGIN}/${username}/glow-up/${share_hash}` (per R9); else undefined.
  3. Call `useShareComposite.generateAndShare({ ..., shareUrl, shareMessage: copy-with-link })`.
- Share row subtitle must disclose the auto-save side-effect (e.g. "Sends the image and keeps it on your profile"). Writer review flagged in Deferred; non-disclosure violates R4 ("never by accident") in a subtler-than-publish form.
- `onPublish` handler: `POST /v1/posts` → on 201, refetch `GET /v1/jobs/{id}` (or merge response locally) to update `post_id`/`share_hash`; close dialog; emit `glowup_publish` analytics.
- **Delete:** add a header-right overflow action ("Delete glow-up"). On tap → `Alert.alert` confirm (matches `DISMISS_ERRORED_JOB_*` pattern on profile grid). Confirm → `DELETE /v1/jobs/{id}` → `router.replace('/(tabs)/profile')` → invalidate `['profile.glowups', username]`.
- Optimistic UI: the delete call is "best-effort 204"; if it fails (5xx), toast and keep the user on the screen. Do not auto-retry.

**Patterns to follow:**
- `mobile/app/(tabs)/profile.tsx`'s `headerRight` ellipsis pattern for the overflow entry.
- `useProfile` + React Query invalidation pattern.
- `mobile/components/result/ShareComposite.tsx` for `shareUrl`/`shareMessage` plumbing.

**Test scenarios:**
- Happy path: Share tap when `saved_at=null` + `post_id=null` → calls save + opens native sheet with `shareUrl=undefined`.
- Happy path: Share tap when `saved_at=null` + `post_id` set → calls save + opens sheet with hash URL.
- Happy path: Publish tap + confirm → POST /posts fires, dialog closes, `post_id` present locally.
- Edge case: guest session → dialog opens with Save + Share only; Publish row absent.
- Edge case: social_enabled=false → same as guest case.
- Edge case: Save already set (`saved_at` not null) → Save row hidden; Share skips the auto-save call.
- Error path: Publish POST fails 4xx → dialog shows inline error; does not close.
- Error path: Delete 5xx → toast error; user stays on screen; no navigation.
- Integration: after successful Publish, re-opening the dialog shows Publish row hidden (post_id now set).
- Integration: after successful Delete, `/result/[jobId]` is unreachable (refetch on re-mount returns 404 → screen shows terminal-error branch).

**Verification:**
- Manual: iOS Simulator. Perform each path above. Screenshot Publish confirm + Share sheet + Delete confirm per `feedback_verify_before_claiming_fixed`.

- [ ] **Unit 9: Mobile — Profile grid long-press → ShareDialog + Delete**

**Goal:** Delete + Share & Publish… reachable from each completed profile cell. Satisfies R6 with zero backend changes (dialog fetches `post_id`/`share_hash` on-open via existing `GET /v1/jobs/{id}` from Unit 3).

**Requirements:** R6

**Dependencies:** Units 3, 5, 7.

**Files:**
- Modify: `mobile/app/(tabs)/profile.tsx`
- Modify: `mobile/components/profile/GlowUpGrid.tsx`
- Test: `mobile/app/(tabs)/__tests__/profile.test.tsx`

**Approach:**
- Long-press on a **completed** cell → `Alert.alert` action sheet with three choices: "Share & Publish…" | "Delete" | "Cancel". `Alert.alert` chosen over custom modal here to match the existing `DISMISS_ERRORED_JOB_*` chrome on failed/cancelled cells — consistent long-press UX across the grid.
- Tap "Share & Publish…" → opens the same `ShareDialog` (Unit 7) for this job. Dialog fetches `post_id`/`share_hash` via `GET /v1/jobs/{id}` on open (single round-trip, uses existing React Query cache if fresh). No profile-endpoint changes needed.
- Tap "Delete" → second `Alert.alert` confirm → `DELETE /v1/jobs/{id}` → optimistic remove from grid → invalidate `['profile.glowups', username]`.
- Long-press on **failed/cancelled** cells → unchanged (`DISMISS_ERRORED_JOB_*`).
- Long-press on **pending/processing/queued** cells → no-op (swallow gesture).
- **Deferred: globe indicator** — see Scope Boundaries > Deferred to Separate Tasks. Future UX pass.

**Patterns to follow:**
- `handleItemLongPress` in `profile.tsx` for gesture dispatch by status.
- `ERRORED_STATUSES` set for status-based branching.
- `useProfile` for query invalidation.

**Test scenarios:**
- Happy path: long-press completed cell → action sheet shows Share & Publish… + Delete + Cancel.
- Happy path: tap Delete + confirm → cell disappears from grid; API called once.
- Happy path: tap Share & Publish… → ShareDialog opens with correct job context.
- Edge case: long-press processing cell → no menu appears.
- Edge case: long-press failed cell → existing dismiss menu (not the new one).
- Error path: delete 5xx → cell reappears; toast error.
- Integration: delete a published glow-up → after UI updates, `GET /v1/public/cards/{username}/{share_hash}` returns 404.

**Verification:**
- Manual on iOS Simulator: screenshots of long-press action sheet + delete-from-grid per `feedback_verify_before_claiming_fixed`.

- [ ] **Unit 10 (dropped)** — was documentation-only "confirm ProfileHeader uses `/{username}`". Behavior already correct (`ProfileHeader.tsx:69` reads `${UNIVERSAL_LINK_ORIGIN}/${profile.username}`). Per R9 profile-header stays as-is. URL-shape distinction comment is folded into Unit 8 alongside the result-card hash-URL construction.

## System-Wide Impact

- **Interaction graph:** Adding `DELETE /v1/jobs/{id}` creates a new entry point that cascades to `posts` (which is the only other entry point for post lifecycle). No new middleware. Mobile `ShareDialog` is a new component consumed by result screen + profile grid; long-press menu is a new gesture handler in `GlowUpGrid`.
- **Error propagation:** Backend delete collects blob failures into `orphaned_storage_keys`; never fails the HTTP request on a blob miss (matches `delete_account`). Mobile presents POST /posts failures inline in the dialog; DELETE failures via toast; does not silently swallow.
- **State lifecycle risks:** After delete, the result screen's `useJob(id)` query becomes stale — invalidation must happen in the same tick as `router.replace`. A user navigating back via gesture before invalidation would see a flash of cached data. Mitigation: call `queryClient.removeQueries(['job', id])` before `router.replace`.
- **API surface parity:** `DELETE /posts/{id}` stays soft-delete (R10); glow-up delete goes through the new endpoint. Documented in the plan + code comments. `delete_account` already enumerates `post-images` correctly via `user_repo.list_user_storage_keys` — the new endpoint follows the same enumeration pattern so the two paths stay symmetric without sharing code.
- **Integration coverage:** End-to-end integration tests (Unit 5) must hit a real Supabase. Mocks alone cannot prove FK cascades or storage cleanup.
- **Unchanged invariants:** `POST /v1/jobs/{id}/save` semantics untouched. `POST /v1/posts` 201 path untouched (only the IntegrityError branch is new). `DELETE /posts/{id}` soft-delete unchanged. Card-web public endpoints unchanged. Retention worker unchanged — `saved_at` still the sole keep-indefinitely signal.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| FK direction on `reactions.post_id` / `comments.post_id` isn't already CASCADE | None — confirmed in `0001_initial.sql` | — | Unit 1 test verifies end-to-end cascade regardless. |
| `glowup_analyses` ref-count races another in-flight job on same `source_id` (TOCTOU: peer count read before commit) | Low | Medium — one orphan analysis or deleted-mid-use analysis | App-layer count in same request. Accepted pre-launch. **No automatic reconciliation** — retention.py does not reap orphan analyses (only via upload CASCADE which is a 14-day lagging trigger). Add a one-off cleanup script to Deferred to Separate Tasks when first orphan is observed in production. |
| `post-images` bucket leaks on `image_repo.remove` failure | Medium | Low — blob orphans, but sweeper picks up | `orphaned_storage_keys` DLQ with `reason="delete_glowup"` + existing `reclaim_orphaned_blobs` cron. |
| External hash-URLs posted to social platforms break on Delete | Certainty | Medium — user may not realize shared links become dead | Delete confirm copy MUST name this consequence explicitly (e.g., "Links you've already shared will stop working"). Writer review blocker. |
| Mobile `post_id` stale after another device publishes | Low | Low — Publish row shows on one device | Unit 2 idempotency (partial unique + retry) returns existing live post; client merges response. |
| Race between user-initiated delete and nightly `retention.py` purge | Low | **Medium** — retention.py does NOT enumerate generated-images/post-images blobs before purging unsaved jobs; if retention wins the race, those blobs orphan silently | Idempotent 204 absorbs the HTTP-level race. Blob leak is a pre-existing bug in retention.py itself (unchanged by this plan). Tracked for follow-up: retention.py should enumerate-before-cascade like Unit 5. |
| Concurrent Publish + Delete on same job (TOCTOU) | Low | Medium — Publish may write post-images blobs after Unit 5's enumerate step; orphans with no DLQ record | Pre-launch accepted. If observed post-launch, add advisory lock on `job_id` around both flows. Documented here so it isn't forgotten. |
| ARQ worker writes blobs after status=COMPLETED but before DELETE fires | Low | Low — completed jobs are terminal today; no retry/embedding writers exist | Accepted. If a post-completion writer is added later, this risk upgrades. |
| Writer copy review delays merge | Medium | Low — blocking on strings | Ship behind `share_enabled` if needed; writer review flagged in Deferred to Implementation. |

## Phased Delivery

Plan is now 8 live units (Unit 4 and Unit 10 dropped after audit). Clean backend-then-mobile split:

**Phase 1 — Backend (Units 1, 2, 3, 5)**
Ships independently. DB constraints + endpoint behavior + response-shape additions all land together. Mobile keeps current behavior. Backwards compatible: mobile's `JobStatusResponse` consumer tolerates extra fields — new optional fields are picked up in Phase 2.

**Phase 2 — Mobile (Units 6, 7, 8, 9)**
Purely mobile. No backend files touched. Consumes Phase 1's API surface. Can gate behind `share_enabled` if writer-review copy isn't ready at PR time — Save button + result screen fall back to current behavior.

This split keeps each PR under 5 units and matches `feedback_batch_phases`.

## Documentation / Operational Notes

- Update `app/api/AGENTS.md` (or the closest AGENTS.md) with the DELETE /v1/jobs contract + idempotency note.
- `mobile/AGENTS.md` — note the new `ShareDialog` component + `canPublishGlowup` capability.
- Rollout: no feature flag needed (per `feedback_pre_launch_destructive_ok`). Both flags (`share_enabled`, `social_enabled`) already exist and the matrix in §7 defines behavior for each combination.
- Monitoring: add a Datadog/whatever-we-use counter on `orphaned_storage_keys` inserts with `reason="delete_glowup"` — spike = blob-wipe regression.
- Writer review: dialog copy + delete confirm copy + publish confirm copy per `feedback_female_user_targeting`. Block merge on this.

## Success Metrics

- Zero user-reported 404s on shared glow-up URLs after rollout.
- `orphaned_storage_keys` with `reason="delete_glowup"` stays <1% of deletes (indicator that inline wipe path is the common case).
- DELETE endpoint p95 < 500ms (no ARQ offload needed for the per-job blob count).
- Guest users successfully delete glow-ups end-to-end in manual QA per R7.
- Publish flow converts without support tickets about "how do I post to the feed".

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md](../brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md)
- Institutional learning: [docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md](../solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md)
- Related code:
  - Cascade precedent: `app/api/auth.py::delete_account` (lines 1313-1450)
  - Orphan DLQ: `app/repositories/orphaned_storage_repo.py`, `app/workers/orphan_reclaim.py`
  - Migration reference: `app/migrations/0045_delete_account_cascade_completeness.sql`
  - Share composite: `mobile/components/result/ShareComposite.tsx`
  - Dialog precedent: `mobile/components/subscription/CancelSubscriptionSheet.tsx`
  - Capability module: `mobile/lib/capabilities.ts`
