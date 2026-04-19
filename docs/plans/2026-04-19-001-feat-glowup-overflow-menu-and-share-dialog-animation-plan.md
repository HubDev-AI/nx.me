---
title: "feat: Glow-up overflow menu + ShareDialog animation match EditProfileSheet"
type: feat
status: active
date: 2026-04-19
origin: docs/brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md
---

# feat: Glow-up overflow menu + ShareDialog animation match EditProfileSheet

## Overview

Two scoped UX fixes on the Your Glow-Up result screen:

1. The header 3-dot ellipsis currently opens a `Alert.alert` Delete confirm directly (`mobile/app/result/[jobId].tsx:412`). Replace with a bottom-sheet overflow menu (list-item rows) so the affordance reads as "menu", leaves room for future actions (Report, Copy link, Edit caption), and keeps the aesthetic consistent with the rest of the in-app modals.
2. The unified `ShareDialog` (`mobile/components/result/ShareDialog.tsx`) has a spring-based slide-up + a top-right X close that feels "awkward" next to the app's established `EditProfileSheet` pattern (Cancel text button header + linear timing slide). Port ShareDialog to the EditProfile animation + header shape inline — no shared primitive extracted yet (YAGNI; two copies is not enough drift pressure).

No backend changes. No capability changes. No copy changes.

## Problem Frame

From user observation (2026-04-19, iOS Simulator, build on `dev @ 5a2d01c`):

- Result header ellipsis → immediate destructive confirm. User expects a menu the ellipsis opens, from which Delete is one option. Radial menu was considered and rejected — single-item radial reads as novelty chrome, not a menu.
- ShareDialog slides up with a bouncy spring + closes via a small X; adjacent modals (Edit Profile) slide with linear timing and a "Cancel" text button left-aligned in a header row. The mismatch is the "awkward animation" the user called out.

## Requirements Trace

- **U1**. Result-screen ellipsis opens a menu UI, not the destructive confirm directly. Delete remains accessible via that menu, still gated by an `Alert.alert` confirm (matches the project's destructive-confirm pattern per `feedback_disabled_button_ux`).
- **U2**. ShareDialog enter/exit animation matches `EditProfileSheet`. Header chrome (Cancel text button + centered title) also matches. The in-dialog "Publish confirm" two-mode panel is preserved unchanged (Cancel / Publish buttons already mirror the pattern the user approved).
- **U3**. No regression in any ShareDialog test scenario from the prior plan (`docs/plans/2026-04-18-001-feat-save-share-publish-delete-glowup-plan.md` §Unit 7 test matrix).

## Scope Boundaries

- No redesign of `ResultActions` primary-row buttons.
- No change to the profile-grid long-press menu (`mobile/app/(tabs)/profile.tsx` / `GlowUpGrid.tsx`) — it already uses `Alert.alert` and is out of scope for this polish pass.
- No new copy. Overflow menu row labels reuse the existing Delete-confirm copy constants where possible.
- No extraction of a shared `BottomSheetModal` primitive. Two consumers (EditProfile, ShareDialog) is not enough drift pressure to justify the abstraction yet. Revisit if a third in-app modal lands with the same shape.
- Not migrating `CancelSubscriptionSheet` animation — it already has a spring feel that product has approved in purchase flows; leaving it as the divergent one.

### Deferred to Separate Tasks

- **Bug #3 — Publish `NO_GENERATED_IMAGE` 422** — Root cause identified: `app/repositories/job_repo.py::get_jobs_for_post` SELECTs `id, user_id, status, before_image_url, after_image_url` but `app/api/posts.py::create_post` reads `job_data["original_image_id"]` / `job_data["generated_image_id"]` (gap was explicitly acknowledged in `tests/test_posts_create_idempotency.py` module docstring). Fixed in this same session via one-line SELECT extension + test docstring update. Tracked here so a reader of this plan can trace the co-committed fix.
- **Bug #4 — post-glow-up nudges silent (regression)** — Handed to `/ce:debug`. Enqueue path intact at `app/generation/worker.py:727`; investigation will cover `ADVISOR_ENABLED`, style_profile presence, rapid_retry dedup, ARQ pool availability, and mobile refetch.
- **Bug #5 — delete-account client stuck on "Deleting…" after server returns 204** — Handed to `/ce:debug`. Backend log (`13:39:47 … DELETE /v1/auth/account HTTP/1.1 204 No Content`) shows server success incl. storage wipe + username reservation; client never advances. Likely client-side auth reset / navigation signal not firing. Related to the hard-reset change in #166 (`2f443df`).

## Context & Research

### Relevant Code and Patterns

- `mobile/app/result/[jobId].tsx:412-425` — current `handleDeletePress` fires `Alert.alert` directly from the ellipsis tap; ellipsis lives in the custom header row at `result/[jobId].tsx:584-605`.
- `mobile/components/result/ShareDialog.tsx` — current Reanimated + spring + X-close + absolute-positioned sheet. All row/confirm behavior (`mode`, `handleRequestPublish`, `handleConfirmPublish`, `handleCancelConfirm`) stays.
- `mobile/components/profile/EditProfileSheet.tsx` — reference for the target animation + header. Uses legacy RN `Animated.Value` + `Animated.timing(useNativeDriver: true)`, 300ms enter / 200ms exit, translateY interpolated from 400, "Cancel" (left) / "Title" (center) / optional pill (right) header row, glass `THEME.colors.glass` sheet background, handle bar on top.
- `mobile/components/subscription/CancelSubscriptionSheet.tsx` — sibling modal that also uses Reanimated + spring; intentionally **not** being migrated (different product context).
- `mobile/app/(tabs)/profile.tsx::handleItemLongPress` — profile-grid long-press → `Alert.alert` action sheet with "Share & Publish…" / "Delete" / "Cancel". Pattern to keep consistent with; the new overflow menu on the result screen reuses the same action verbs and the same `DELETE /v1/jobs/{id}` call path.

### Institutional Learnings

- `feedback_disabled_button_ux` — Cancel stays clickable at all times.
- `feedback_ui_skill_required` — routing UI work through a design-aware pass before hand-tuning. The inline animation match is a mechanical port from EditProfileSheet, not a net-new UI; a design pass is not required but screenshots on the simulator are per `feedback_verify_before_claiming_fixed`.

### External References

None. Both targets are established in-app patterns.

## Key Technical Decisions

- **Bottom-sheet list for the overflow menu, not `Alert.alert`.** The profile-grid long-press uses `Alert.alert` already, but on the result screen the ellipsis is a visually persistent affordance. A bottom-sheet list signals "menu with room to grow" (Report, Copy link, Edit caption if published, etc.) and matches the Share dialog's aesthetic. User confirmed pattern A on 2026-04-19.
- **Single row today: "Delete glow-up".** YAGNI — do not pre-add disabled placeholders. The bottom-sheet shape scales naturally when the next row lands.
- **Delete flow is two-tap: menu row → existing `Alert.alert` destructive confirm.** Keeps the irreversible action gated by the native destructive-confirm affordance the user already recognizes. The menu is a navigation surface, not a confirm surface.
- **No shared `BottomSheetModal` primitive.** Two consumers is not enough. If the third lands (e.g., a future Report sheet), extract then. Current deliverable is inline ports.
- **Port EditProfileSheet animation by copy, not by abstraction.** The `Animated.Value` + `Animated.timing(useNativeDriver: true)` shape is stable, tested in production, and does not rely on any EditProfile-specific state. Duplication is cheap; the abstraction cost is a shared prop surface we don't yet know the shape of.
- **Drop the X close button from ShareDialog.** Replace with a "Cancel" text button in the same header row shape EditProfileSheet uses. Keeps dismissal-scrim tap behavior as a secondary exit so no existing path is removed.
- **Preserve ShareDialog's Publish-confirm in-dialog panel.** Port the outer-shell animation and header chrome; leave `mode === "confirm"` rendering logic + confirm-panel button layout untouched.
- **Keep `isClosingRef` race guard semantics.** Even though we swap Reanimated for legacy `Animated`, the "re-open mid-exit" race still exists. Legacy `Animated.timing(…).start(callback)` fires `finished` the same way; the guard translates 1:1.
- **Background color drift: glass vs surfaceElevated.** EditProfileSheet uses `THEME.colors.glass`; ShareDialog currently uses `THEME.colors.surfaceElevated`. Take the EditProfile value to match the target aesthetic fully — pick `THEME.colors.glass` for ShareDialog and the new overflow menu. If readability suffers on the result screen's dark background, revisit in the verification step.

## Open Questions

### Resolved During Planning

- **Menu pattern** → Bottom-sheet list (user pick, 2026-04-19).
- **Shared primitive extraction** → Deferred until a third consumer appears.
- **CancelSubscriptionSheet migration** → Out of scope; divergent animation acceptable.
- **ShareDialog header: keep X, add Cancel, or swap?** → Swap. Single Cancel text button left-aligned matches EditProfile and avoids two dismiss affordances competing.

### Deferred to Implementation

- **Exact menu title string** (e.g., "Options" vs no title). Try no title first — single-row menu reads cleaner without redundant chrome. Writer review not required for a lone action.
- **Whether the menu sheet uses `statusBarTranslucent={true}` like EditProfile** — match EditProfile's current value verbatim.

## Implementation Units

- [ ] **Unit 1: ShareDialog — port animation + header chrome from EditProfileSheet**

**Goal:** Make ShareDialog's enter/exit animation and header row indistinguishable from EditProfileSheet. No behavior changes; pure shell polish.

**Requirements:** U2, U3

**Dependencies:** None.

**Files:**
- Modify: `mobile/components/result/ShareDialog.tsx`
- Test: `mobile/components/result/__tests__/ShareDialog.test.tsx` (if present; update mocks if animation lib changes break harness — the legacy `Animated` API is already Jest-safe with `useNativeDriver: true` by default in RN's mock)

**Approach:**
- Replace `useSharedValue` / `useAnimatedStyle` / `withSpring` / `withTiming` imports with the legacy RN `Animated` + `useRef(new Animated.Value(0))` shape from EditProfileSheet.
- Replace `SHEET_OFFSCREEN_Y = 600` + spring damping/stiffness with an interpolated `translateY` range of `[0, 1] → [400, 0]` and `Animated.timing(.., { duration: ENTER | EXIT, useNativeDriver: true })`.
- Keep `ENTER_DURATION_MS` / `EXIT_DURATION_MS` — point them at the EditProfile values (300/200), which happen to already equal `PAYWALL_ANIMATION.ENTER_DURATION_MS` / `EXIT_DURATION_MS`. Safer to inline the constants than to assume config parity.
- Replace the top-right `Pressable` X close with a header row that mirrors EditProfileSheet: left slot Cancel text button, centered `Heading size="md"` title, right slot spacer (`MIN_TOUCH_TARGET` square) so the title stays optically centered.
- Keep drag indicator bar, scrim `Pressable` dismissal, `isClosingRef` exit-race guard (translated 1:1 to `Animated.timing(…).start(({ finished }) => …)`).
- Swap sheet background from `THEME.colors.surfaceElevated` to `THEME.colors.glass`, add the hairline top border EditProfileSheet has (`sheetTopBorder` style).
- Leave `mode === "confirm"` rendering + confirm-panel buttons untouched.
- Header Cancel tap → existing `handleClose` (respects the `isPublishing` guard).
- `onRequestClose` on the outer Modal → `handleClose` (unchanged).

**Patterns to follow:**
- `mobile/components/profile/EditProfileSheet.tsx` — animation + header structure.
- `feedback_disabled_button_ux` — header Cancel stays clickable; Publish confirm's Cancel button inside the confirm panel already honors this.

**Test scenarios:**
- Happy path: dialog opens, scrim fades from 0 to target opacity over ENTER_DURATION_MS; sheet translates from +400 to 0 over the same window.
- Happy path: dialog closes on backdrop tap, sheet translates back to +400 and the Modal unmounts after EXIT_DURATION_MS.
- Happy path: header Cancel tap dismisses the dialog identically to backdrop tap.
- Edge case: rapid open → close → open within the EXIT_DURATION_MS window does not unmount the re-opened dialog (`isClosingRef` race guard).
- Edge case: `isPublishing === true` disables header Cancel + backdrop dismissal (matches existing `handleClose` guard).
- Integration: switching into Publish confirm panel (`mode === "confirm"`) preserves the new header — Cancel still visible, title swaps to `PUBLISH_CONFIRM_TITLE`.

**Verification:**
- `npx expo lint` clean for `ShareDialog.tsx`.
- iOS Simulator screenshot (per `feedback_verify_before_claiming_fixed`): ShareDialog open on result screen next to a second screenshot of EditProfileSheet — animations side-by-side should read identically.

- [ ] **Unit 2: Overflow menu — new component + result-screen wiring**

**Goal:** Replace the direct `Alert.alert` Delete confirm fired from the header ellipsis with a bottom-sheet menu. Menu contains one row today (Delete). Tapping the row raises the existing `Alert.alert` destructive confirm, which then calls `DELETE /v1/jobs/{id}` through the existing `runDelete` handler.

**Requirements:** U1

**Dependencies:** Unit 1 (shared aesthetic — reuse the same animation + header shape). Not a strict code dependency; the new component duplicates the animation shape directly from EditProfileSheet / the ported ShareDialog.

**Files:**
- Create: `mobile/components/result/GlowupOverflowMenu.tsx`
- Modify: `mobile/app/result/[jobId].tsx` (ellipsis `onPress`, new `shareOverflowVisible` state + wiring, unchanged `runDelete` + `handleDeletePress`)
- Test: `mobile/components/result/__tests__/GlowupOverflowMenu.test.tsx`

**Approach:**
- `GlowupOverflowMenu` props: `visible`, `onClose`, `onDelete`. Keep the surface tiny — no job payload, no capability checks. The parent screen owns the action list composition for future rows.
- Internals mirror the Unit-1-ported ShareDialog: Modal + scrim + handle bar + Cancel-header row + single list-row body. Title can be omitted (single-row menu reads cleaner); if we include one later the slot is ready.
- Row shape: icon circle + label + optional destructive tint. Reuse `DialogRow` styles from ShareDialog by porting a local `OverflowMenuRow` (do not import from ShareDialog — drift risk, and the two will evolve independently). 10-line duplication is cheap.
- Tap on Delete row → `onDelete()` (fire-and-forget from the menu; menu closes via `onClose`). Parent `[jobId].tsx` reshapes `handleDeletePress` into two steps:
  1. Ellipsis → set `overflowVisible = true`.
  2. Delete row tap → close menu, then fire the existing `Alert.alert` → `runDelete` chain. `Alert.alert` inside a `Modal` can race on iOS; close the menu first (unset `visible`), wait for exit via a completion callback or `setTimeout(…, EXIT_DURATION_MS)` before raising the alert.
- Accessibility: menu exposes `accessibilityRole="menu"` on the container, `accessibilityRole="menuitem"` on each row. Parity with `RadialMenu`'s existing roles so screen readers treat it as a menu.
- No capability gate on the Delete row: destructive glow-up deletion is available to owner + guest per the #167 requirements (R3, R7).

**Patterns to follow:**
- `mobile/components/profile/EditProfileSheet.tsx` — animation + header.
- `mobile/components/result/ShareDialog.tsx` (post Unit 1) — row shape + exit-race guard.
- `mobile/app/result/[jobId].tsx::runDelete` — unchanged; it already invalidates + navigates correctly.

**Test scenarios:**
- Happy path: tap ellipsis → menu slides up; Delete row visible; Cancel in header + backdrop both dismiss without firing delete.
- Happy path: tap Delete row → menu animates out; after exit, `Alert.alert` opens with the existing title/body/buttons. Confirm Delete → `DELETE /v1/jobs/{id}` → navigation to profile. Cancel in the alert → stays on result screen with menu already closed.
- Edge case: tap Delete row then rapidly tap backdrop → menu still closes; alert still raises (Delete tap ran `onDelete` before close animation completed). Acceptable — user already committed to opening the confirm.
- Edge case: ellipsis hidden on non-success branches (waiting / terminal-failure). Menu state cannot be opened from those branches (already gated at `result/[jobId].tsx:588`).
- Integration: menu mounting does not steal gesture from the before/after slider — slider has its own absolute-positioned `ShareCompositeView` offscreen; menu lives at Modal layer.

**Verification:**
- `npx expo lint` clean.
- iOS Simulator: screenshot the open menu on the result screen + the subsequent `Alert.alert` destructive confirm. Attach both per `feedback_verify_before_claiming_fixed`.
- Manual: delete a real glow-up end-to-end; confirm profile grid invalidates + navigation to `/(tabs)/profile` fires exactly once.

## System-Wide Impact

- **Interaction graph:** One new component (`GlowupOverflowMenu`), one modification to an existing screen (`result/[jobId].tsx` ellipsis `onPress`). No new API calls. No capability module changes.
- **Error propagation:** Unchanged — `runDelete`'s existing best-effort 204 + toast on failure path is preserved.
- **State lifecycle risks:** Two `Modal`s stacked (menu + alert) on iOS can race when the menu closes while the alert opens. Mitigated by closing the menu first and deferring the alert to the exit-animation completion. Tests cover the rapid-tap case.
- **API surface parity:** No external contract surface touched. `DELETE /v1/jobs/{id}` still the only endpoint in the delete path.
- **Integration coverage:** Unit 1's animation change affects every ShareDialog mount site (result screen + profile long-press from plan #167 Unit 9). Manual verification must include both entry points.
- **Unchanged invariants:** ShareDialog's Save / Share / Publish row visibility, auto-save blocking on Share, Publish confirm copy, Publish-error inline display — all preserved. `ResultActions` primary row composition — unchanged.

## Risks & Dependencies

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Legacy `Animated` regression mid-exit race (different callback shape than Reanimated's `withTiming` completion) | Low | Medium | `start(({ finished }) => …)` returns the same boolean; translate `isClosingRef` guard 1:1; add explicit test for rapid open/close/open. |
| `THEME.colors.glass` background reads too light on result screen's dark image backdrop | Low | Low | Visual check on simulator; fall back to `surfaceElevated` if translucency fails the contrast check. Per `feedback_ui_skill_required`, do not hand-tune in isolation — compare side-by-side with EditProfileSheet on its dark screen. |
| Alert-within-Modal race dismisses alert buttons on iOS when menu unmounts synchronously | Medium | Medium | Close menu first, defer `Alert.alert(…)` until the menu's exit animation completes (either via completion callback or `setTimeout(EXIT_DURATION_MS)`); test explicitly. |
| ShareDialog tests relying on Reanimated mocks break after port | Low | Low | Legacy `Animated` is natively Jest-safe in RN; removing the Reanimated imports should remove mock boilerplate, not add it. |
| Second X-close affordance removed — users accustomed to tapping top-right to close | Low | Low | Cancel text button is more discoverable per iOS HIG for sheets with a confirm mode; backdrop tap still dismisses. No telemetry exists on X vs backdrop usage, so no migration metric is warranted. |

## Documentation / Operational Notes

- No AGENTS.md updates needed — both components remain in the same module boundary.
- No migration, no feature flag.
- Visual QA: capture screenshots of the open menu, the ported ShareDialog (rows mode + confirm mode), and the EditProfileSheet side-by-side. Attach to the PR per `feedback_verify_before_claiming_fixed`.

## Success Metrics

- Zero new user-facing bug reports on "awkward animation" or "can't find Delete" in the result screen after rollout.
- ShareDialog open → dismiss cycle on iOS Simulator reads identically to EditProfileSheet (frame-by-frame side-by-side in QuickTime recording).
- Delete flow remains one confirm tap from the menu open.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md](../brainstorms/2026-04-18-save-share-publish-delete-glowup-requirements.md)
- **Predecessor plan:** [docs/plans/2026-04-18-001-feat-save-share-publish-delete-glowup-plan.md](./2026-04-18-001-feat-save-share-publish-delete-glowup-plan.md)
- **Related bug fix (this session):** `app/repositories/job_repo.py::get_jobs_for_post` SELECT extended with `original_image_id, generated_image_id`; `tests/test_posts_create_idempotency.py` docstring updated to reflect closed gap.
- **Deferred debug targets (this session):** Bug #4 (nudges post-glowup silent) and Bug #5 (delete-account client stuck post-204) to be investigated via `/ce:debug` immediately after this plan writes.
- Related code:
  - Ellipsis + delete confirm: `mobile/app/result/[jobId].tsx:412-425,584-605`
  - ShareDialog current shape: `mobile/components/result/ShareDialog.tsx`
  - Target animation/header: `mobile/components/profile/EditProfileSheet.tsx`
