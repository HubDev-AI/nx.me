---
title: "Blocking auto-save to keep shared URLs durable"
date: 2026-04-19
category: best-practices
module: mobile
problem_type: best_practice
component: mobile
severity: high
related_components:
  - rails_controller
  - background_job
applies_when:
  - A UI action produces a URL that points to server-side persistent state
  - Background retention, TTL, or moderation can purge the target
  - The user would not notice the URL breaking until a recipient clicks it
  - Fire-and-forget save/persist patterns in sharing, copy-link, publish flows
tags:
  - share-link
  - blocking-save
  - r5-no-404-links
  - r8-durable-share
  - retention-survivable
  - useShareDialog
related_prs:
  - "HubDev-AI/nx.me#167"
related_docs:
  - docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md
  - docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md
---

# Blocking auto-save to keep shared URLs durable

## Context

PR #167's Share flow (`mobile/components/result/useShareDialog.ts`) previously opened the native share sheet while firing `POST /v1/jobs/{id}/save` in parallel. The URL handed to the native sheet points at `card-web`, which resolves the `/{username}/glow-up/{share_hash}` hash route against server state. Unsaved jobs are reaped by the retention worker (see sibling doc `enumerate-before-cascade-with-cas-2026-04-19.md`); the parallel save was best-effort, so any failure or slow network meant the user had already broadcast a URL whose backing row would be purged days later. Recipients then clicked a dead link and got a 404.

R5 ("no silent 404 links") and R8 ("share auto-saves to survive retention") codify the fix: if a share URL addresses server-side state subject to retention, TTL, or moderation, the state must be durably committed BEFORE the URL is broadcast — not racing the broadcast in the background.

## Guidance

When a user action broadcasts a URL to external state, block on the durable-commit step and abort the broadcast on failure. The commit must finish before the share sheet (or copy-link toast, or publish confirmation) opens.

From `handleShare` in `mobile/components/result/useShareDialog.ts`:

```ts
// Step 1 — block on auto-save when the job isn't saved yet (R8).
// Wrapped in `raceWithTimeout` so a slow network can't hang the
// Share row forever; on either failure or timeout we MUST abort
// and never open the native sheet.
if (job.saved_at === null) {
  setSaveState("saving");
  try {
    const { saved_at } = await raceWithTimeout(
      saveJobFn(job.id),
      SAVE_TIMEOUT_MS,
    );
    setSaveState("saved");
    onSaveSuccess?.(saved_at);
  } catch (err) {
    setSaveState("pending");
    if (err instanceof SaveTimeoutError) {
      showToast({ kind: "error", message: SAVE_TIMEOUT_MESSAGE });
    } else {
      const app = parseApiError(err);
      showToast({ kind: "error", message: app.message });
    }
    return; // Abort — do NOT open the sheet on save failure/timeout.
  }
}
// ... only after commit succeeds: build hash URL, call generateAndShare(...)
```

Three rules make this pattern work in practice:

1. **Await the commit.** The save is `await`ed before building the URL or calling `generateAndShare`. Fire-and-forget save is the anti-pattern.
2. **Cap the wait.** `raceWithTimeout(..., SAVE_TIMEOUT_MS)` rejects with `SaveTimeoutError` so a stalled network fails loudly (`SAVE_TIMEOUT_MESSAGE` toast) rather than wedging the dialog. A separate error class keeps the timeout branch distinguishable from API failures.
3. **Abort on failure.** The catch block surfaces a toast and `return`s before the share sheet opens. There is no fallback to "share anyway with a link that might 404."

The server-side analogue lives in `app/api/posts.py`: the `POST /v1/posts` handler PRE-RECORDS the uploaded public-bucket keys to `orphaned_storage_keys` with `reason=PUBLISH_PENDING_REASON` BEFORE the M-5 re-verify and `INSERT INTO posts`. On insert success the DLQ rows are deleted in the same request; on any failure (TOCTOU 409, exhausted retry, 5xx, mid-request crash), the DLQ rows survive and the nightly `reclaim_orphaned_blobs` sweeper collects the orphans. Same shape, different recovery mechanism: "make the cleanup story durable before you broadcast success to the client."

## Why This Matters

The concrete failure mode is silent and asymmetric:

1. User taps Share on an unsaved glow-up. The share sheet opens immediately. User picks "Messages," types a note, hits Send.
2. Meanwhile, the background `saveJob` call fails (transient 502, airplane mode toggled mid-request, server hiccup).
3. The message lands in the recipient's inbox with a live-looking `card-web` URL. Sender sees a successful share and moves on.
4. Retention worker runs that night (or any subsequent night within `RETENTION_JOB_DAYS`) and purges the unsaved job. The hash URL now resolves to nothing.
5. Recipient taps the link one or more days later. 404. Sender has no signal — they already dismissed the share flow.

The sender cannot recover: they have no record of which recipients got the dead URL, and no mechanism to re-send a live one. Trust damage is compounded because the failure is invisible at the moment of sharing — the bug ships as "my friend said the link didn't work" weeks later. The blocking-save pattern converts this invisible silent-loss failure into a visible loud failure (toast at share time), which the user can act on (retry, check their connection, try again).

This also keeps the client's R5/R8 story legible in one file: the invariant ("no 404 links leave this app") lives next to the code that enforces it.

## When to Apply

Apply this pattern when:

- A UI action hands external parties a URL that resolves against server-side state with a retention/TTL/moderation lifecycle (share sheet, copy link, publish-and-broadcast, export-and-email).
- The sender cannot observe the URL breaking — no round-trip signal tells them the recipient hit a 404.
- The commit is short (single API call, sub-second expected latency) so a blocking wait is UX-acceptable with a timeout guard.

Do NOT apply this pattern when:

- **Fire-and-forget analytics / telemetry.** Event beacons do not produce user-visible artifacts; their failure is not the user's problem. Keep them non-blocking and swallow-wrapped.
- **UI-only state changes.** Toggling a local filter, expanding a detail card, or updating a client-side preference produces no URL and no external target. No durable commit needed before the UI animates.
- **Fully idempotent broadcasts against already-durable state.** Re-sharing a link that points at state which is already saved (the `saved_at !== null` branch) — no blocking step needed. The hook's guard (`if (job.saved_at === null)`) encodes exactly this: skip the block when the durability precondition is already satisfied.
- **In-request atomic writes.** If the broadcast and the persistence can go through one atomic DB transaction, there is no race to defend against. The pattern is specifically for the case where the broadcast (native share sheet, HTTP response, email send) escapes the backend boundary.

## Examples

### Call site 1 — client-initiated blocking save (mobile)

- `mobile/components/result/useShareDialog.ts::handleShare`
- Named constants: `SAVE_TIMEOUT_MS` (upper bound), `SAVE_TIMEOUT_MESSAGE` (toast copy distinct from image-composite timeout), `SaveTimeoutError` (typed branch), `raceWithTimeout` (helper), `HASH_URL_SEGMENT` (URL builder token).
- Flow: check `saved_at`; if null, `raceWithTimeout(saveJobFn(job.id), SAVE_TIMEOUT_MS)` → on success continue; on failure/timeout show toast and `return`. Only past the guard do we build the `${UNIVERSAL_LINK_ORIGIN}/${username}/${HASH_URL_SEGMENT}/${job.share_hash}` URL and hand off to `generateAndShare`.
- Recovery mechanism: user-visible toast + aborted broadcast. The user retries.
- Re-entry guard (`isSharingRef`) prevents double-tap from firing two saves; not the core pattern but part of the same handler.

### Call site 2 — server-initiated durable pre-record (backend)

- `app/api/posts.py::POST /v1/posts`
- Named constant: `PUBLISH_PENDING_REASON` (module-level, never user-derived).
- Flow: upload blobs to `PUBLIC_BUCKET` → `orphan_repo.record(PUBLIC_BUCKET, before_key, PUBLISH_PENDING_REASON)` + same for `after_key` → M-5 re-verify job status → `INSERT INTO posts`. On insert success, DLQ rows are deleted in-request; on any failure path, they survive.
- Recovery mechanism: the `reclaim_orphaned_blobs` sweeper drains the DLQ asynchronously. The client sees 4xx/5xx and retries; the blobs never orphan.
- Shape match: durable failure-recovery commitment BEFORE the externally-observable broadcast (the 201 response and the minted `share_hash` are the "broadcast" here).

## Related

- `docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md` — retention-side half of the contract: the reason URLs break in the first place is the retention worker purging unsaved jobs. Enumerate-before-cascade keeps that purge leak-free; blocking auto-save keeps the URL from being broadcast for a row that will get caught by it.
- `docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md` — "make the cleanup story durable before broadcasting the state change" pattern at the account-lifecycle scope. Same discipline, different surface.
- PR #167 — introduces the R5/R8 blocking-auto-save invariant in `useShareDialog.ts` and the `PUBLISH_PENDING_REASON` DLQ pre-record in `app/api/posts.py`.
