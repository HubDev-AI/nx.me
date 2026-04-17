# Glow-Up UX Polish + Advisor Nudges Tuning — Requirements

**Date:** 2026-04-17
**Owner:** @trifonov
**Status:** Ready for planning
**Scope:** Standard (pre-launch UX polish bundle across mobile + 1 backend nudge flip)

## Problem

Seven pre-launch rough edges degrade the glow-up flow and the advisor surface:

1. **Premature "not ready" screen.** Tapping Analyze on `upload.tsx` sometimes lands on the result screen's terminal-error / "Go to Profile" state before the worker has a chance to produce images. User sees a failure-shaped screen instead of a waiting state.
2. **Profile grid crowds the profile bar.** In `profile.tsx`, the first row of `GlowUpGrid` sits too close to the `ProfileHeader` card. Needs visual breathing room.
3. **Glow-up cells are dead.** `GlowUpGrid` accepts an `onItemPress` prop but `profile.tsx` never passes one. Tapping a thumbnail does nothing. The existing before/after slider screen (`result/[jobId].tsx`) is the intended destination.
4. **Waiting screen lacks reassurance.** The `isWaiting` branch in `result/[jobId].tsx` has a Go-to-Profile button, but the copy does not make it obvious that generation continues in the background if the user leaves.
5. **No pending or errored state on profile.** Queued / in-flight glow-ups do not appear on the profile grid. Failed ones do not appear either, so the user has no way to see that a credit was spent or that a job errored.
6. **Nudges feel clinical.** Post-analysis nudges (Sonnet) lead with traits like "Oval face shapes are versatile…". Voice is off even when the facts are correct. Needs warmer tone.
7. **Ada's chat opener is too broad.** First reply to "Hello" is "Hey — what are you working on?" — gives no hint that Ada is a style / grooming / fit advisor. New users do not know what to ask.

## Goals

- Restore trust in the Analyze → Result flow: waiting screen shows a waiting state, profile shows pending cells, errors auto-refund with an honest signal.
- Make the profile grid navigable: tap opens the existing before/after slider detail view.
- Protect Ada's first-impression and passive-surface voice as a product differentiator: warmer nudges (Haiku), scoped empty-state chat opener.

**Scope note:** Decisions 1-4, 6, 7 are refinements to existing flows. **Decision 5 is a new surface** — pending-cell lifecycle + backend history endpoint expansion + server-ack refund dedup. Ships in the same PR as everything else per user call, but planning should budget Decision 5 at higher risk/LOC than the other six combined.

## Non-goals

- New glow-up styles, prompt variants, or analysis fields.
- Redesigning `ProfileHeader`, `GlowUpGrid` card styling, or the before/after slider itself.
- Rewriting `SOUL.md` persona beyond adding a scoped chat-opener surface.
- Any refund mechanism beyond errored glow-ups (failed analyses, cancelled jobs, network errors stay out of scope).

## Decisions

### 1. Premature "not ready" screen

Root cause unverified. Two candidate branches exist and may be **both** live (treat as AND, not XOR):
- QueryStateView error branch (`mobile/app/result/[jobId].tsx:218-223`) firing after the 10s 404 grace window when the worker's job row lands slowly.
- Terminal-failure branch (`:245-278`) firing when `status=completed` but image URLs are null.

Fix both to tolerate worker latency / partial state.

**Acceptance:**
- 404 within the grace window → waiting view renders (unchanged).
- 404 after grace window → extend grace or convert to waiting until a hard timeout (planning picks the threshold); do not fall to error branch during normal queue latency.
- `status=completed` with null image URLs → waiting view until URLs land or a hard timeout (~60s) elapses, only then show "Images didn't come through".
- Reproduction harness: planning adds a dev-only toggle to inject 15s delay before worker row insert and a toggle to emit `completed` with null URLs, so both paths fire under QA.

### 2. Profile grid vs profile bar spacing

Increase vertical gap between `ProfileHeader` (rendered as `ListHeaderComponent`) and the first grid row. Current padding lives in `mobile/components/profile/GlowUpGrid.tsx` `gridContent.paddingTop` (`THEME.spacing.sm`). Planning picks the exact value, but visible separation must match the rhythm between other header + content pairs in the app (roughly `THEME.spacing.xl`).

**Acceptance:** Visual QA screenshot on iPhone 15 Pro Simulator — clear air gap between the `@username` card and the top of the first grid row.

### 3. Tap glow-up cell → open before/after slider

`profile.tsx` passes an `onItemPress` handler to `GlowUpGrid` that navigates to `/result/[jobId]` for that glow-up. The slider component (`components/result/BeforeAfterSlider`) already supports static (non-polling) inputs via the completed branch of `result/[jobId].tsx`.

**Acceptance:** Tapping any completed glow-up cell opens the result screen with that job's before / after, slider interactive.

### 4. Waiting screen: leave-is-safe messaging

Keep the existing "Go to Profile" button. Rewrite the copy so the user knows leaving does not cancel the job.

- **Headline:** "Your glow-up is being generated."
- **Body (1 sentence):** "You can leave this screen — we'll drop the result on your profile when it's done."
- **Primary CTA:** `Go to Profile` (unchanged).
- Keep the hourglass icon and `PageBackground`.

**Acceptance:** Copy renders exactly as above. Pressing Go-to-Profile does not cancel the worker job (verified by confirming the cell appears on profile and completes).

### 5. Pending cells on profile (no errored cells)

**Scope call:** the grid shows **only processing and completed** glow-ups. Failed and cancelled jobs do **not** render on the grid — the user learns about errors via toast only, and the grid stays clean. Rationale: errored cells would be clutter on a profile meant to celebrate transformations; the refund toast is the entire error-signal surface.

**Pending:** optimistic insert. The moment Analyze fires a successful `generateGlowup` and returns a `job_id`, a placeholder cell appears pinned to the top of the grid with a shimmer state. Cell polls `GET /v1/jobs/{jobId}` (existing endpoint). On `status='completed'` with both image URLs present, cell cross-fades (150ms) to the real thumbnail. On `status='failed'` or `'cancelled'`, cell **removes itself from the grid** (no error state, no muted variant). Toast fires in parallel (see Refund below).

**Rehydrate on cold start:** expand `GET /v1/users/{username}/history` (`app/api/users.py:377-432`) to include rows where the latest job is in `running` / `queued` / `processing` state. `HistoryEntry` (`app/api/users.py:94-101`) adds `job_id: str | None` and `status: str` fields. Do **not** include `failed` or `cancelled` rows (per the scope call above). This also provides the `job_id` that Decision 3 needs for tap-through on completed cells.

**Refund:** server-side auto-refund **already exists** (`app/generation/worker.py:761-836 _fail_job`; `usage_event.status='released'` is idempotent). `JobStatusResponse.credit_refunded: bool` (`app/api/jobs.py:168-174`) is the authoritative toast gate.

**Toast dedup = server ack.** Add a `refund_acknowledged_at: timestamptz` column to the relevant jobs / usage-events row (planning picks exact table) and a `POST /v1/jobs/{jobId}/ack-refund` endpoint. Mobile client calls ack after showing the toast. `GET /v1/jobs/{jobId}` returns `credit_refunded=true, refund_acknowledged_at=null` only while ack pending; toast only fires in that window. Survives app kills and device changes because it's server-sourced.

**Polling load:** per-cell polling at `ANALYSIS_CONFIG.INTERVAL_MS = 1500ms` is the baseline. Cap visible pending cells at 3 (entitlement usually caps lower anyway). Do not build a batched poll endpoint in this bundle — revisit if real usage shows load problems.

**Pending cell vanishes on error, user gets the toast.** If the user is on a different tab when the flip happens, the toast still fires on whatever screen they return to (mobile toast queue handles this). The pending cell's disappearance is the non-verbal cue that matches "that one's on us — your credit's back."

**Acceptance:**
- Pending cell visible within ~200ms of Analyze tap (in-session).
- Pending cell rehydrates on cold start from history endpoint when a job is still running.
- On `status='completed'`, cell cross-fades to thumbnail.
- On `status='failed'` or `'cancelled'`, cell removes itself and toast fires once (server-ack-gated).
- `GET /v1/jobs/{id}` returns `credit_refunded=true`; after mobile shows toast and calls ack, `refund_acknowledged_at` is set and the toast never re-fires for that job.
- Max 3 concurrent pending cells render; extras queue but don't render until a slot frees.

### 6. Nudges: flip back to Haiku

Change `app/advisor/nudge_scheduler.py:166` (usage site; doc previously referenced line 163) from `settings.ADVISOR_MODEL_SONNET` to `settings.ADVISOR_MODEL_HAIKU` (confirmed present at `app/config/__init__.py:100`). Keep existing prompts in `app/advisor/nudge_templates.py` unchanged.

**Do not delete the prior code comment.** Rewrite it to a historical note so future engineers have context: `"# Haiku → Sonnet switch in <prev PR> was reverted 2026-04-17: Sonnet's post-analysis output read as clinical ('Oval face shapes are versatile...'). Re-evaluate if grounded-output complaints rise."`

**Why:** user found Sonnet's post-analysis output too clinical. Warmer voice is worth trading a small amount of groundedness per the user's call (confirmed in this brainstorm). Prompt rewrite is out of scope **for this bundle**, not indefinitely — a separate lightweight brainstorm can revisit prompt framing if Haiku regresses on groundedness.

**Acceptance:**
- Adapter call uses Haiku model ID (verifiable via adapter log line).
- Dev-env spot-check: run three `post_analysis` nudges on real insights from the dev DB and review for tone **before** merging. If any reads as ungrounded (e.g. references features not in the insight), pause the flip and either revert to Sonnet or open a prompt-scope brainstorm.
- Existing cooldown, entitlement gate, and skip-on-missing-insight behavior preserved (tests in `tests/test_advisor_nudge_post_analysis_grounded.py` must pass unchanged).

### 7. Chat opener: replace AdvisorEmptyOverlay with scoped seed card

**Replaces** the existing `AdvisorEmptyOverlay` rendered in `mobile/components/advisor/ChatView.tsx:325-331` (currently "Start a conversation / Ask Ada for style advice"). The new card renders in the same slot inside `listArea` — not a new overlay on top. Composer stays mounted beneath; keyboard-avoiding behavior matches current overlay (no layout regression on open).

**Empty-state card contents:**
- Title: "Hi, I'm Ada."
- Body: "I can help with hair, beard, fit, skincare, or grooming — *or ask me anything else you're thinking about.*" (final clause prevents the chip list reading as an exhaustive capability list.)
- Starter chips (horizontal scroll strip, pill-shaped buttons matching existing `THEME` pill pattern):
  - "What hairstyle would suit me?"
  - "Should I try a beard?"
  - "How do I fix the fit of my clothes?"
  - "What should I focus on next?"

**Chip interaction:** tap chip → text fills composer AND the LLM call fires immediately (no extra Send tap). User can edit the composer instead of tapping a chip at any time.

`SOUL.md` is **not** modified. Hardcoded scope in the card body must be kept in sync with `SOUL.md` if the persona's lanes ever change (add inline code comment pointing to `app/advisor/SOUL.md`).

**Paywall interaction:** if the send returns 402 (free user hits premium gate), the existing paywall modal handles the failure. When the paywall is dismissed and `messages.length === 0` still holds, the empty-state card **re-renders** — it is a pure function of conversation length, not a one-time dismissal.

**Acceptance:**
- First-time user on `/(tabs)/advisor` (Chat tab) sees the new card in place of `AdvisorEmptyOverlay`.
- Tapping any chip sends that message immediately; card hides as first message posts.
- Reopening the tab with existing history skips the card (same `messages.length === 0` gate as the overlay).
- 402 paywall dismissal with no messages sent → card re-renders.

## Open questions

All resolved in this brainstorm. Recorded for trail:

- **Pending-cell durability:** resolved → server rehydrate via expanded history endpoint. No errored cells ever render (user's call). See Decision 5.
- **Toast dedup:** resolved → server ack (`refund_acknowledged_at` + POST ack endpoint). See Decision 5.
- **Polling load:** resolved → cap at 3 pending cells, per-cell poll at existing 1.5s. Revisit if telemetry shows load problems.
- **PR shape:** resolved → single PR, all seven decisions together (user's call, overriding reviewer recommendation to split).

## File references (verified)

- `mobile/app/upload.tsx` — Analyze button + auto-upload flow.
- `mobile/app/result/[jobId].tsx` — waiting / terminal / success state machine.
- `mobile/app/(tabs)/profile.tsx` — renders `GlowUpGrid`, needs `onItemPress` wiring.
- `mobile/components/profile/GlowUpGrid.tsx` — grid + cell, needs pending / error variants.
- `mobile/components/profile/ProfileHeader.tsx` / `GlowUpGrid.tsx:203-212 gridContent.paddingTop` — spacing site; note flexGrow math around empty-state centering — visual QA must cover both populated and empty profile.
- `mobile/components/profile/types.ts:23-31 GlowUpItem` — **lacks `job_id` and `status`**. Decision 3 (tap cell → result screen) and Decision 5 (pending + errored cells) both require these fields added.
- `mobile/components/advisor/ChatView.tsx:325-331 AdvisorEmptyOverlay` — Decision 7 replaces this.
- `app/api/users.py:94-101 HistoryEntry` model and `:377-432` history handler — **filters to `after_key` present** (completed only). Must change to return `job_id`, `status`, and non-terminal jobs for Decisions 3 + 5.
- `app/api/jobs.py:108-112 get_job` — session-scoped ownership check; works for same guest token or same JWT `sub`. Cross-session paths (guest → signed-in account merge) would 404 on historical jobs.
- `app/api/jobs.py:168-174 JobStatusResponse.credit_refunded` — already exposed; toast gates on this flag = `true`, not on `status=failed` alone (handles promo-only paths where no refund applies).
- `app/advisor/nudge_scheduler.py:166` — Sonnet → Haiku swap site.
- `app/config/__init__.py:100 ADVISOR_MODEL_HAIKU = "claude-haiku-4-5-20251001"` — confirmed.
- `app/generation/worker.py:761-836 _fail_job` — **server-side auto-refund already exists**. Calls `_ledger.refund()` / `_ledger.release()` on every non-user-caused failure. `usage_event.status='released'` marks refund idempotent. No new backend hook required for the refund itself; the only new backend work is the history endpoint expansion (see above).
- `app/api/jobs.py:249-315 cancel_job` — cancelled jobs use the same refund path as `_fail_job`. Decision 5 treats `status='cancelled'` identically to `'failed'` (cell removed, toast fires with cancellation copy).
- `mobile/components/profile/types.ts:23-31 GlowUpItem` and `app/api/users.py:94-101 HistoryEntry` — schema update (`job_id`, `status`) needed on both sides.

## Addendum: cancelled jobs

`status='cancelled'` cells are **not rendered** on the grid (same rule as `failed`). Server refunds on cancel via the existing `_ledger.release()` path. Toast fires once per cancelled job via the same server-ack mechanism, with cancellation-specific copy.

## Addendum: pending-cell interaction states

- **Pending cell tap:** navigates to `/result/[jobId]` in its waiting state. User can track the same job from either the upload flow or the profile grid, which matches the "leave is safe" message in Decision 4.
- **Polling failure on pending cell:** if three consecutive polls fail (network / 5xx), cell flips to a "stalled" variant with a Retry button. This is **not** the errored state — no refund has occurred — just a signal that polling gave up. User can retry manually or wait for the next app-foreground cycle to restart polling.
- **Pending cell position:** pinned to the top of the grid in insertion order (most-recent Analyze tap first), regardless of `created_at`. Limit: max 3 concurrent pending cells visible; additional pending jobs queue but don't render until a slot frees. (Also constrained naturally by entitlement credit count.)
- **Completion swap animation:** cross-fade (150ms) from shimmer to the real thumbnail once `after_image_url` is present. No spring, no layout shift.
- **Disappearance on error:** when `status` flips to `failed` or `cancelled`, the pending cell animates out with a 150ms fade. The toast fires on whatever screen the user is on at that moment.

## Addendum: refund toast copy

- Failed (worker error): **"That one's on us — your credit's back. Try a new photo?"**
- Cancelled: **"Canceled — your trial is back."**
- Toast fires once per job, gated by server `refund_acknowledged_at` (see Decision 5).
