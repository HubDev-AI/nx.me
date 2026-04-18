# Save / Share / Publish / Delete for Glow-ups — Requirements

**Date:** 2026-04-18
**Status:** Draft (brainstorm output — not yet planned)
**Scope:** Mobile (`mobile/`), backend (`app/`), card-web (`card-web/`)

## 1. Problem

Today the three user-facing "what do I do with my glow-up result" actions are muddled:

- **Save** (`POST /v1/jobs/{id}/save`) retains the job indefinitely on the user's profile — but the button label has read like "save to phone" historically.
- **Share** on the result screen builds a local before/after composite PNG and hands it to the native share sheet. For authed users it also appends a `card-web/{username}` URL — which **404s if the user has never published a post**, because `card-web` reads from the `posts` table.
- **Publish** (`POST /v1/posts`, social-gated) exists but has **no mobile UI entry point**. The card-web surface is therefore unreachable except for users who somehow posted via another path.

The user's intent:
- Keep Save and Publish as two **distinct** actions.
- Make the feature work with `social_enabled=false` (no Publish, no card-web — but Save and a reduced Share still work).
- A single **Delete** action that removes a saved glow-up from every surface (profile row, post if published, card-web URL, storage assets, analysis).
- A **unified sharing dialog** that explains what each option does (private vs public) so the user never posts publicly by accident.

## 2. Verified current state

From code audit (repo-relative paths):

| Surface | Save | Share | Publish | Delete |
|---|---|---|---|---|
| `mobile/app/(tabs)/profile.tsx` | ✅ `saved_at` via `POST /v1/jobs/{id}/save` | ❌ | ❌ | ❌ (only long-press dismiss of **failed/cancelled** cells via `ERRORED_STATUSES`) |
| `mobile/app/result/[jobId].tsx` + `mobile/components/result/ResultActions.tsx` | ✅ "Save on profile" button (outline) | ✅ "Share" button → `useShareComposite` native sheet w/ `shareUrl` + `shareMessage` params plumbed through | ❌ no entry point | ❌ |
| `app/api/posts.py` | — | — | ✅ `POST /v1/posts` (gated on `social_enabled`) | ✅ `DELETE /v1/posts/{id}` soft-delete (`is_deleted=TRUE`) |
| `app/api/public.py` | — | — | — | card-web reads `posts` via `/public/cards/{username}` + `/public/cards/{username}/{share_hash}` — **requires a non-deleted post** |
| `app/workers/retention.py` | Unsaved jobs purged after `RETENTION_JOB_DAYS`; `saved_at IS NOT NULL` preserves indefinitely | — | — | — |

Capabilities (`mobile/lib/capabilities.ts`):
- `canShareGlowup = share_enabled` — result-card share button visibility.
- `canShareProfile = social_enabled` — profile-share (card-web link) button.
- `canReact`, `canSeeFeed` = `social_enabled`.

## 3. Goals

1. **Three distinct user-facing actions**, each with clear public-vs-private framing:
   - **Save** — private, profile only. No external surface.
   - **Share** — native share sheet. Sends composite PNG + (if published) card-web link. Works for anyone with a result.
   - **Publish** — makes the glow-up appear on the social feed + card-web. Explicit, confirmed.
2. **Single unified Share dialog** launched from the result screen and from any saved glow-up on profile. Dialog explains each option plainly before the user commits.
3. **Works with `social_enabled=false`:** Save + local-image Share remain. Publish and card-web link are hidden.
4. **Unified Delete semantics:** deleting a glow-up removes **every** server-side remnant — `jobs` row (hard), `posts` row (hard), generated/original images in storage, `glowup_analyses` row, card-web reachability. Mirrors the `DELETE /auth/account` invariant: nothing remains.
5. **Delete UI on both profile grid and result screen** for completed glow-ups.
6. **Guest parity** where possible: guests can Save + Share (local image, no card-web link), cannot Publish.

## 4. Non-goals

- No redesign of the feed, card-web layout, or post detail.
- No caption editor, mentions, or hashtags in Publish (caption stays as today — optional `<=500` chars, HTML-stripped).
- No migration of old `saved_at` rows — behavior change is forward-only.
- No change to `DELETE /posts/{id}` semantics for users who found the post detail screen (it stays soft-delete there). The new glow-up Delete flow is a **separate** operation that may invoke post deletion as a sub-step.

## 5. User-facing behavior

### 5.1 Result screen (immediately after a successful generation)

**Layout change:** `ResultActions` becomes a two-row bar.
- Row 1 (primary): **Save on profile** (outline, persists) + **Share & Publish…** (primary, opens dialog)
- Row 2 (secondary): **New glow-up** + credit badge (unchanged)

Tapping **Share & Publish…** opens the **Share dialog** (§5.3).

Why one button not three: three primary buttons on the result screen crowd the layout and make the user guess which one is "the post it" button. The dialog pattern lets us give each option a sentence of context.

### 5.2 Profile grid (saved glow-ups)

Each completed cell gets a long-press menu (replaces current "nothing happens on long-press for completed"):
- **Share & Publish…** → opens Share dialog
- **Delete** → confirms, then hard-deletes (§5.4)

Failed/cancelled long-press stays as-is (dismiss via `DISMISS_ERRORED_JOB_*`).

Short-press still navigates to `/result/[jobId]`, where the same Share dialog + Delete action are reachable.

### 5.3 Share dialog

Bottom sheet with three actions, each with a one-line subtitle explaining **who sees it**. Rough shape:

```
┌─────────────────────────────────────┐
│ Share your glow-up                  │
│                                     │
│ [🔖]  Save on profile               │ ← hidden if already saved
│       Private. Only you can see it. │
│                                     │
│ [📤]  Share                         │
│       Send the image (and your card │
│       link if you've posted) to any │
│       app.                          │
│                                     │
│ [🌐]  Publish to feed               │ ← hidden if !social_enabled or guest
│       Public. Appears on the social │
│       feed and your card-web page.  │
│                                     │
│ [Cancel]                            │
└─────────────────────────────────────┘
```

Visibility rules:

| Row | Shown when |
|---|---|
| Save on profile | `saved_at` is null AND user has write access to their profile (`canEditProfile`) |
| Share | always (result exists) |
| Publish to feed | `canSeeFeed` (= `social_enabled`) AND session is real user (not guest) AND not already published for this job |

If the dialog would show only one row, open that action directly instead (e.g. social off + already saved → just invoke Share, skip the dialog).

### 5.4 Publish flow

Tapping **Publish to feed** presents a **confirmation** because the action is public and one-way-by-default (delete is possible but an explicit reversal):

```
Publish to the feed?

Your before/after will appear on the public feed and at
nxme.ai/{username}. You can delete it any time.

[Cancel]   [Publish]
```

Optional: the same sheet offers a **caption** input (single line, 500 chars). We keep it optional — captions are already supported server-side, and gating Publish behind a required caption would add friction without helping.

On confirm → `POST /v1/posts` → on success, dialog closes and result screen updates to show "Published" state (the **Publish** row disappears, **Share** now appends the card-web URL).

### 5.5 Share flow

Always available when a result exists. Behavior:

- **Published** OR **card-web reachable for this hash** → composite PNG + `shareMessage` containing `https://nxme.ai/{username}` (or the `/glow-up/{share_hash}` variant — decided in planning).
- **Not published** OR `social_enabled=false` → composite PNG only, no link.
- Today's code already plumbs `shareUrl`/`shareMessage` through `useShareComposite`. The only change is: **never append a card-web URL unless a post exists**. Breaking-link behavior (baseline bug) goes away.

### 5.6 Delete flow

Available on: profile cell long-press + result screen. Triggers a confirm:

```
Delete this glow-up?

This removes the before/after, any post you've published,
and the public link. It cannot be undone.

[Cancel]   [Delete]
```

On confirm → `DELETE /v1/jobs/{job_id}` (new endpoint — see §6) → hard-deletes:

- `jobs` row
- `posts` row (if any), with `is_deleted=true` path kept for the existing soft-delete UX, but the glow-up-scoped delete uses a **hard** delete because the invariant is "nothing remains"
- `glowup_analyses` row associated with the job's `source_id`
- `images` rows (before + after), and blobs in `raw-selfies` + `generated-images` buckets. Follow the `delete_account` pattern: record orphaned storage keys to `orphan_storage` queue + ARQ wipe task, so the HTTP response is fast.
- `card-web/{username}` automatically 404s for this `share_hash` because the post row is gone; the user's main `card-web/{username}` page falls back to the next latest post.

Failure handling mirrors `delete_account`: best-effort; record orphan keys; never block the user-visible confirmation on a storage wipe.

Guest deletes: same endpoint, same scope, identified via `X-Guest-Token` (consistent with how `save` already uses `get_user_or_guest`).

## 6. Backend surface

New:
- `DELETE /v1/jobs/{job_id}` — hard-delete a completed job and everything it produced. Auth: `get_user_or_guest` (same as `save`, for guest parity). 204 on success. 404 if not owned / not found / already deleted.

Unchanged:
- `POST /v1/jobs/{job_id}/save` — stays as-is.
- `POST /v1/posts` — stays as-is, still gated on `social_enabled`.
- `DELETE /v1/posts/{id}` — stays as-is. The new glow-up delete invokes an equivalent cascade internally; it does not call this endpoint.
- `GET /v1/public/cards/...` — stays as-is; unaffected because post rows simply disappear.

Schema impact (for planning to confirm against current migrations):
- Need hard-delete of `posts` rows in this flow. `DELETE /v1/posts/{id}` currently soft-deletes; the glow-up cascade should be a true `DELETE FROM posts WHERE glow_up_job_id = ?`. Verify FK direction and any reaction/comment cascade behavior during planning.
- `glowup_analyses` row is referenced by `jobs.source_id` when `source_type='glowup_analysis'`; the cascade must delete or null-out accordingly.

## 7. Feature-flag + session matrix

Two flags already govern this surface: `social_enabled` and `share_enabled`. No new flags needed.

| State | Save | Share | Publish |
|---|---|---|---|
| real user, social on, share on | ✅ | ✅ (w/ link after publish) | ✅ |
| real user, social on, share off | ✅ | ❌ | ✅ |
| real user, social off | ✅ | ✅ (image only) | ❌ hidden |
| guest, social on | ✅ | ✅ (image only) | ❌ hidden (guests can't post) |
| guest, social off | ✅ | ✅ (image only) | ❌ hidden |
| share off, social off | ✅ | ❌ | ❌ (dialog degrades to "Save on profile" only — open directly, skip dialog) |

Delete is always available when the user owns the job. Not gated on any flag.

## 8. Accepted answers from the user

1. **Save vs Publish**: both, distinct actions.
2. **Social-disabled mode**: feature works with `social_enabled=false`.
3. **Delete scope**: cascade everything — profile, post, card-web, storage, analysis.
4. **UX for three options**: unified sharing dialog that explains what each does; prevent accidental public posts.
5. **Card-web link in Share by default**: yes, **but** only when a post actually exists (fix the current broken-link bug).
6. **Delete visible from both profile and result screen**: yes.

## 9. Open questions for planning

- Exact label strings (writer review required before shipping — feedback_female_user_targeting).
- Whether the Share dialog is a `react-native-bottom-sheet` or the existing `ActionSheetIOS` pattern used elsewhere — consistency check during planning.
- Retention semantics for an unsaved job that a user only Shares: it still expires after `RETENTION_JOB_DAYS` unless saved or published. Share does not imply save. Planning should confirm this is the intended rule (alternative: Share implicitly saves).
- Whether Publish should prompt for a caption or not — default is "no, keep it one-tap; allow edit later via post detail."
- Analytics event taxonomy: keep `glowup_save` as-is; add `glowup_publish`, `glowup_delete`, `glowup_share_dialog_opened` with action taken.
- Card-web URL shape in Share message: `/{username}` (latest) or `/{username}/glow-up/{share_hash}` (stable). Latter is more correct for social posts; planning to decide.

## 10. Success criteria

- Share never appends a card-web URL that 404s.
- A user can publish to the feed from the mobile app in one confirmed tap from the result screen or a saved glow-up.
- Deleting a saved glow-up leaves zero server-side remnants (same invariant tests as `delete_account`).
- With `social_enabled=false`, Publish is invisible and Share silently omits the card-web URL.
- Guest users see Save + Share, never Publish, and can delete their own glow-ups.

## 11. Handoff

Next: `/ce:plan` to break this into implementable tasks. Files worth re-reading when planning:

```
mobile/app/result/[jobId].tsx
mobile/components/result/ResultActions.tsx
mobile/components/result/ShareComposite.tsx
mobile/app/(tabs)/profile.tsx
mobile/components/profile/GlowUpGrid.tsx
mobile/lib/capabilities.ts
app/api/jobs.py           # add DELETE here
app/api/posts.py          # reference for cascade pattern
app/api/auth.py           # reference for delete_account orphan queue
app/workers/retention.py  # saved_at semantics
app/services/public_url.py
```
