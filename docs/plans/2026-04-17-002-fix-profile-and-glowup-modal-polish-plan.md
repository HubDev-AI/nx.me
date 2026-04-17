---
title: "fix: Profile tab + glow-up modal + chat sort polish"
type: fix
status: active
date: 2026-04-17
origin: none  # Direct user request; follows PR #121 (2026-04-17-001) post-merge user-reported polish
---

# fix: Profile tab + glow-up modal + chat sort polish

## Overview

Follow-up polish on the Glow-Up UX bundle shipped in PR #121 (plan:
`docs/plans/2026-04-17-001-feat-glowup-ux-polish-and-advisor-nudges-plan.md`).
User-reported issues after testing the shipped flow on device:

- Profile tab top row sits under a large phantom gap — the nav header
  (tabs header) already consumes the top safe-area inset, and the screen
  **also** applies `paddingTop: insets.top`. The result is the safe-area
  reserved **twice**, so the profile card floats far below the nav
  header. Any conditionally-hidden element in `ProfileHeader` (stats row
  when social is off, etc.) also needs to collapse without leaving a
  hole.
- "Share Profile" button in the expanded `ProfileHeader` renders even when
  `features.social_enabled` is off, which contradicts the global rule that
  non-social deployments hide all sharing/public-link surfaces.
- Tapping a completed glow-up cell opens `/result/[jobId]` but the route
  renders without a header/back button, leaving the user stranded on the
  slider until they swipe or kill the screen.
- `BeforeAfterSlider` horizontal drag gets cancelled the moment the user
  moves a few pixels vertically — the parent `ScrollView` wins the gesture.
- BEFORE and GLOW UP pill badges can land on the same half of the image
  (both visible over the BEFORE photo) because GLOW UP is parented to the
  clipped after-layer and positioned to that clip's right edge.
- Default split is 0.5; user wants the after ("glow-up") image visible at
  100 % by default with the handle at the right edge, so the slider is an
  "optional reveal of the before photo" rather than a forced 50/50 split.
- No way to tap either image to open a full-screen zoomable view.
- Advisor chat history renders **newest at top, oldest at bottom** — the
  reverse of standard chat UX. Root cause: `ChatView.tsx:118-119` assumes
  the API returns newest-first and calls `.slice().reverse()`, but the
  backend (`app/repositories/advisor_repo.py:101` —
  `.order("created_at", desc=False)`) actually returns **oldest-first**.
  The client reversal flips a correct order into a wrong one.
- JS reload no longer rotates the accent colour. Earlier builds picked
  a new random accent on every reload ("random-accent demo vibe");
  current build persists the chosen accent to `AsyncStorage` under
  `nxme_session_accent` and re-reads it on mount, so the accent is
  pinned across reloads. Root cause: `theme-context.tsx:40-44`
  calls `loadOrCreateSessionTheme()` in a mount `useEffect` which
  overwrites the fresh random pick with the persisted index. Not
  user-related — it's a client persistence side-effect, same for every
  session mode.
- Camera opens on the rear-facing lens when the user taps "Take photo"
  on the glow-up upload screen. Every glow-up input is a selfie, so the
  front camera should be the default. Root cause:
  `mobile/components/upload/PhotoPicker.tsx:187-192` calls
  `ImagePicker.launchCameraAsync({ mediaTypes: ["images"], allowsEditing:
  true, aspect, quality })` without a `cameraType` option — the
  expo-image-picker default is `back`.

All fixes are mobile-only and ship as one bundle because they share the
same screen pair (profile tab + glow-up result modal) and overlap in
testing surface.

## Problem Frame

The pre-launch Glow-Up flow landed functionality in PR #121 but the
on-device UX has rough edges that block the app from feeling finished.
Every item above was reported by the user after real device testing;
none are hypothetical. The fixes are surgical — no new product scope,
no redesign — and stay within existing patterns (`HeaderBackButton`,
`useCapabilities()`, `PanResponder`, the existing `BeforeAfterSlider`).

## Requirements Trace

- **R1.** Profile tab sits flush under the tab nav header — no duplicated
  safe-area padding. The collapsed `ProfileHeader` card renders with a
  consistent, single `THEME.spacing.md` gap beneath the nav header on
  every iOS notch/Dynamic Island layout (SE, 13 mini, 15 Pro, 15 Pro
  Max). Any conditionally-hidden child of `ProfileHeader` (stats row
  when social is off, Share Profile button when social is off) collapses
  its vertical footprint to zero — no phantom hole, no leftover padding
  gap.
- **R2.** When `features.social_enabled === false`, the "Share Profile"
  icon button in `ProfileHeader` is not rendered. With `social_enabled`
  true, behavior is unchanged from PR #121.
- **R3.** `/result/[jobId]` renders a visible header row with a
  back-chevron on every branch (loading, waiting, success, terminal
  failure). Tapping back returns to the previous route.
- **R4.** Dragging `BeforeAfterSlider` horizontally keeps the divider
  under the user's finger even when the initial touch drifts a few
  pixels vertically. Vertical drags on the slider pass through to the
  parent `ScrollView` so the user can still scroll the page.
- **R5.** Only one label pill is visible on each half of the slider at
  any split position: BEFORE shows only over the before (right of
  divider) region, GLOW UP shows only over the after (left of divider)
  region. At the extreme splits (0, 1) the corresponding label hides.
- **R6.** `BeforeAfterSlider` defaults to `split = 1` — the glow-up
  image fully covers the before image on first mount, with the handle
  at the right edge. Entrance animation still runs (spring into
  position). User can still drag left to reveal the before photo.
- **R7.** Tapping the visible image on the result screen opens a
  full-screen zoomable viewer where the user can pinch to zoom, pan the
  zoomed image, and dismiss via a back chevron or swipe-down. The
  viewer honours the same before/after state — user can switch between
  viewing the before and the glow-up image without leaving zoom.
- **R8.** Advisor chat (`ChatView`) renders messages oldest-first at the
  top of the list, newest-first at the bottom — matching standard chat
  UX (iMessage, WhatsApp, Slack, etc.). The FlatList auto-scrolls to
  the bottom on new message arrival. Pagination via `onStartReached`
  (scroll up) loads older messages and prepends them above the current
  window.
- **R9.** Every JS reload (cold start, Expo Fast Refresh, `r` in the
  Metro terminal, shake-menu reload) picks a fresh random accent from
  the 20-colour palette. The accent is not persisted across reloads.
  `refreshTheme()` (pull-to-refresh) still works as before but does
  not write the index to storage either.
- **R10.** Tapping "Take photo" on the glow-up upload flow launches
  `ImagePicker.launchCameraAsync` with the **front-facing** camera
  selected by default. User can still switch to rear via the camera
  UI's built-in flip control.

## Scope Boundaries

- No backend changes.
- No changes to the `jobs` table, image storage, or share-composite
  flow.
- No redesign of `ProfileHeader`'s expand/collapse animation, stats
  row, or Edit Profile button.
- No changes to the `GlowUpGrid` cell rendering or pending-job polling.
- No change to the BeforeAfterSlider entrance spring or handle visuals
  beyond what R5 / R6 require.
- No adoption of `react-native-gesture-handler` as a new dependency in
  this plan (see Key Technical Decisions → Zoom viewer).
- No application of the zoom viewer to `post/[postId].tsx` or
  `card/[username].tsx` in this plan (can land later if reusable).

### Deferred to Separate Tasks

- Root-level `<Slot/>` → `<Stack/>` migration in `mobile/app/_layout.tsx`
  — a broader navigation refactor that would make `<Stack.Screen>` work
  natively for every pushed route. Tracked separately; this plan uses
  the `HeaderBackButton`-inside-screen pattern already in the codebase
  (`post/[postId].tsx`, `subscription.tsx`, `upload.tsx`).
- Adopting the new zoom viewer component on `post/[postId].tsx` and
  `card/[username].tsx`. Same component, later PR.

## Context & Research

### Relevant Code and Patterns

- `mobile/app/(tabs)/profile.tsx` — profile screen; wraps
  `ProfileHeader` + `GlowUpGrid`; already consumes `useCapabilities()`
  and pipes `showStats={caps.canSeeFeed}` into `ProfileHeader`. New
  `showShareProfile` prop follows the same pattern.
- `mobile/components/profile/ProfileHeader.tsx` — collapsible header
  with Edit Profile + Share Profile row (lines 212–251). Share button
  currently renders unconditionally.
- `mobile/app/result/[jobId].tsx` — result screen; current
  `<Stack.Screen options=…>` (line 360) is inert because root layout
  is a `<Slot/>` not a `<Stack/>`.
- `mobile/components/result/BeforeAfterSlider.tsx` — PanResponder-based
  slider; `onMoveShouldSetPanResponder: () => true` unconditionally
  claims every gesture.
- `mobile/components/ui/HeaderBackButton.tsx` — shared chevron button,
  44×44 hit target, used by `subscription.tsx:28-30`, `upload.tsx:44-46`,
  `post/[postId].tsx:273` (which sets `headerShown:false` then renders
  the custom header inline).
- `mobile/lib/capabilities.ts` — adds capabilities via `useMemo` over
  `(features, session)`; matrix-tested in `capabilities.test.ts`. The
  existing `canSeeFeed: features.social_enabled` is the correct
  template; `canShareProfile` joins it.
- `mobile/lib/capabilities.test.ts` — capability matrix table tests. New
  capability must add a row.

### Institutional Learnings

- `docs/plans/2026-04-17-001-feat-glowup-ux-polish-and-advisor-nudges-plan.md`
  — shipped in PR #121. Touches the same screens; plan did **not**
  include: directional gesture gating, pill layering, default split=1,
  share-profile gating, zoom viewer, or profile top spacing.
- `docs/plans/2026-04-15-001-feat-feature-flags-redesign-plan.md` — the
  canonical capability-gating contract; confirms the new capability
  must flow through `useCapabilities()` and not read raw
  `features.social_enabled` in UI.
- `MEMORY.md → feedback_disabled_button_ux.md` — cancel/back/close must
  always be CLICKABLE when the corresponding action exists; never
  hidden. Applies directly to R3 (back button) and R7 (zoom-close).
- `MEMORY.md → feedback_feature_gating_centralized.md` — gating only
  via `useCapabilities()` (mobile); reinforces R2 path.
- `mobile/AGENTS.md:37-39` — action buttons stay visible when disabled;
  never hidden.

### External References

No external research required. The feature surface is entirely local
React Native / Reanimated / PanResponder work and follows patterns
already present in the repo.

## Key Technical Decisions

- **Header pattern for `/result/[jobId]`: custom in-screen header row,
  not a Stack migration.** Root `app/_layout.tsx` is a `<Slot/>`, so
  `<Stack.Screen>` is inert. Migrating to `<Stack/>` is a cross-cutting
  change that touches every pushed route's header semantics and
  deserves its own plan. Here, match the existing pattern in
  `post/[postId].tsx:273` — set `<Stack.Screen options={{ headerShown:
  false }} />` defensively and render a custom header row using
  `HeaderBackButton`.

- **Directional gesture gating without `react-native-gesture-handler`.**
  The package is **not** installed (grepped `mobile/package.json`;
  absent). Rather than introduce a native dependency (native rebuild,
  peer-config for `RNGestureHandlerRootView`, migration of every
  existing `PanResponder` call site), extend the slider's
  `onMoveShouldSetPanResponder` to return `true` only when
  `Math.abs(gestureState.dx) > Math.abs(gestureState.dy) +
  DIRECTION_THRESHOLD`. The slider still grabs immediately on tap (via
  `onStartShouldSetPanResponder`) so tap-to-jump is preserved; the
  parent `ScrollView` wins the vertical case. Threshold constant lives
  next to the other slider constants.

- **Label pill layering: lift both badges out of the clipped
  after-layer.** Currently BEFORE is at the container root and GLOW UP
  is a child of the `afterClip` view — so GLOW UP is positioned
  relative to the clip width (= `split × sliderWidth`). At split 0.5
  the clip's right edge lands over the left half of the image, so both
  badges render on the same half. Fix: render both badges as siblings
  at the container root, position each using a Reanimated derived
  style driven by `splitPosition`. BEFORE label fades out as split → 1;
  GLOW UP label fades in as split → 1 (the opacity curve is the simple
  visibility rule, so the badge sitting on a sliver of image disappears
  before it overlaps its neighbour).

- **Default split = 1.0, entrance spring intact.** Change `initialSplit`
  default from 0.5 to 1.0 in `BeforeAfterSlider`; keep the entrance
  spring (`withSpring(initialSplit, ENTRANCE_SPRING)`) so the handle
  slides in from the left and settles at the right edge. The
  accessibility toggle (`handleAccessibilityToggle`) currently flips
  between 0.25 and 0.75 — update to pivot around 0.5 so VoiceOver users
  still get a meaningful before/after toggle regardless of default.

- **Theme reload: drop the `AsyncStorage` persistence round-trip; let
  every mount pick a fresh random accent.** The synchronous
  `useState(() => buildSessionTheme())` in `theme-context.tsx:37`
  already picks a random accent on first render. The follow-up
  `useEffect` that calls `loadOrCreateSessionTheme()` overwrites it
  with the previously-persisted index — kill the effect, and the
  random pick survives. Also drop `persistAccentIndex` from
  `refreshTheme` so the pull-to-refresh accent is not remembered
  across reloads. The `nxme_session_accent` key becomes orphaned;
  stale entries on device are harmless (no code reads the key once
  the loader is removed). Export `buildSessionTheme` stays; the
  `loadOrCreateSessionTheme` and `persistAccentIndex` functions in
  `dynamic-theme.ts` can be removed (their only caller is this
  provider) — treat deletion as part of the unit.

- **Camera defaults to front: pass
  `cameraType: ImagePicker.CameraType.front` to
  `launchCameraAsync`.** The glow-up flow is selfie-only; defaulting
  to rear is a small-but-persistent papercut. Pass the option at the
  `PhotoPicker.pickFromCamera` call site. Do **not** touch
  `EditProfileSheet.tsx:209` — that uses `launchImageLibraryAsync`,
  not the camera, and the avatar flow is happy with either lens when
  the user does eventually use the camera through another entry
  point. Audit: only one `launchCameraAsync` call site exists in
  `mobile/` (`PhotoPicker.tsx`).

- **Advisor chat: remove the client-side `.reverse()`, keep API as
  the source of truth for order.** Backend
  `app/repositories/advisor_repo.py:96-104` returns messages in
  **ascending** `created_at` order (`desc=False`) — i.e., oldest-first.
  The client comment in `ChatView.tsx:118` says "API returns newest
  first; we display oldest first, so reverse" — the comment is stale
  and the reversal inverts a correct ordering. Fix: drop the `.slice().reverse()`
  in both `loadMessages` (line 119) and `loadOlderMessages` (line 149),
  replace the stale comment with one that matches reality. Pagination
  flow is unchanged: `onStartReached` fires at top, we prepend older
  batches via `[...older, ...prev]` (older still sorted ascending;
  prepending keeps overall order ascending). No backend change — this
  is a client-only fix.

- **Zoom viewer: build a local `ZoomableImageModal` using `Modal` +
  `PanResponder` + Reanimated shared values.** Pure-JS pinch math off
  `evt.nativeEvent.touches` (distance between two fingers / initial
  distance → scale). Pan translates when `scale > 1`. Double-tap resets
  to scale 1. Decision justification: adding
  `react-native-gesture-handler` requires a native rebuild,
  `RNGestureHandlerRootView` at the app root, and introduces ongoing
  peer-dep drift — too expensive for a pre-launch polish bundle when
  we only need pinch-zoom on two images on one screen. If the zoom
  surface grows (post detail, card page, feed photos), revisit by
  adopting gesture-handler project-wide and re-implementing this
  component against `Gesture.Pinch()` — the props API stays stable.

- **Profile top spacing fix: remove the double safe-area padding, don't
  add more.** Previous assumption (add more padding) was wrong. Root
  cause: `profile.tsx:302` wraps content in `<View style={[
  styles.container, { paddingTop: insets.top }]}>` **while** the tab
  navigator is rendering its own header that already consumes the top
  safe-area inset. Result: safe area reserved twice, creating a large
  phantom gap between the nav header and the profile card. Fix: drop
  the inline `paddingTop: insets.top` entirely. The nav header claims
  the safe area; the screen body starts directly below it. Add a
  single `THEME.spacing.md` gap between the nav header baseline and
  the profile card via `ProfileHeader`'s existing `marginTop` — which
  is already `THEME.spacing.sm` at the component level; bump to `md`
  only if the flush layout reads cramped on device.

- **Phantom-hole elimination in `ProfileHeader`.** Conditionally-hidden
  children (stats row gated on `showStats`, Share Profile gated on
  the new `showShareProfile`) must occupy **zero** vertical space when
  hidden. Current code already renders `null` in both slots, so there
  is no explicit hole — but the `buttonsRow` flex container still
  reserves its own margin even when it has a single child. Fix: when
  `showShareProfile === false` and only the Edit Profile button is
  present, the `buttonsRow` still renders with the edit button
  stretching (`flex: 1` already handles this naturally); no margin
  change needed. Verified no other hidden-element holes in the header.
  Same discipline applies to any future hidden sub-sections: prefer
  rendering `null` over a 0-height spacer.

## Open Questions

### Resolved During Planning

- **Do we install `react-native-gesture-handler` for the zoom viewer?**
  Resolved: no. Build a PanResponder + Reanimated viewer locally.
  Tracked as a Key Technical Decision.
- **Where does the share-profile gate live — ProfileHeader, the menu,
  or the screen?** Resolved: ProfileHeader receives a
  `showShareProfile` prop (mirroring the existing `showStats` prop);
  the screen derives it from `useCapabilities()` and passes it down.
- **Stack migration vs custom in-screen header for `/result/[jobId]`?**
  Resolved: in-screen custom header with `HeaderBackButton`. Stack
  migration is deferred.

### Deferred to Implementation

- **Exact opacity curve for BEFORE / GLOW UP labels** — plan specifies
  monotonic fade with split; the exact easing (linear vs smoothstep)
  can be tuned during implementation against the visual reviewer.
- **Pinch-zoom damping and rubber-band limits** — behavioural tuning
  values (max scale, min scale, over-pinch resistance) belong with the
  component and are easier to dial during device testing.
- **Whether the header row background on `/result/[jobId]` should be
  `THEME.colors.bg` (current) or `THEME.colors.glass`** — pick during
  implementation so the header reads on top of `PageBackground`.

## Output Structure

    mobile/
      app/
        (tabs)/
          profile.tsx            # modify: drop double insets.top padding, pass showShareProfile
        result/
          [jobId].tsx            # modify: custom header row, open zoom viewer
      components/
        advisor/
          ChatView.tsx           # modify: drop client-side .reverse() on message fetch
        profile/
          ProfileHeader.tsx      # modify: accept showShareProfile prop
        result/
          BeforeAfterSlider.tsx  # modify: directional gate, pill layering, default 1
        ui/
          ZoomableImageModal.tsx # NEW: pinch-zoom full-screen viewer
          __tests__/
            ZoomableImageModal.helpers.test.tsx  # NEW: pure helper tests
        upload/
          PhotoPicker.tsx        # modify: launch camera with cameraType: front
      lib/
        capabilities.ts          # modify: add canShareProfile
        capabilities.test.ts     # modify: matrix row for canShareProfile
        theme-context.tsx        # modify: drop storage load + persist; random on every mount
        dynamic-theme.ts         # modify: remove loadOrCreateSessionTheme + persistAccentIndex

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

Slider gesture gate (directional claim, inside parent ScrollView):

```
onStartShouldSetPanResponder  → true           // tap-to-jump keeps working
onMoveShouldSetPanResponder   → |dx| > |dy| + DIRECTION_THRESHOLD
onPanResponderGrant           → decide grab-vs-jump as today
onPanResponderMove            → splitPosition = clamp(start + dx/w, 0, 1)
```

Slider label visibility (both pills are now siblings of the image, not
children of the after-clip):

```
beforeLabelOpacity ≈ 1 - splitPosition       // hides as glow-up fills the frame
afterLabelOpacity  ≈ splitPosition           // appears as glow-up reveals
```

Zoom viewer modal — state machine per touch event (conceptual):

```
idle        ─tap image────────────────→ open(src)
open        ─2 fingers────────────────→ pinching (track initialDist, scale)
pinching    ─<1 finger────────────────→ panning (if scale>1) / open (if scale==1)
panning     ─double tap───────────────→ reset(scale=1, translate=0)
any         ─back button / swipe-down─→ close
```

## Implementation Units

- [ ] **Unit 1: Add `canShareProfile` capability + wire through ProfileHeader**

**Goal:** Introduce a single source-of-truth capability for "show the
share-profile surface" and consume it from `profile.tsx`.

**Requirements:** R2

**Dependencies:** None

**Files:**
- Modify: `mobile/lib/capabilities.ts`
- Modify: `mobile/lib/capabilities.test.ts`
- Modify: `mobile/components/profile/ProfileHeader.tsx`
- Modify: `mobile/app/(tabs)/profile.tsx`

**Approach:**
- Add `canShareProfile: boolean` to the `Capabilities` interface.
- Return `canShareProfile: features.social_enabled` from the
  `useMemo`; add `features.social_enabled` to the dep array only once
  (already present for `canSeeFeed`).
- Extend `ProfileHeader` props with `showShareProfile: boolean` and
  wrap the Share button block (lines 232–251) in a ternary guard —
  the existing `showStats` prop is the precedent.
- In `profile.tsx`, pass `showShareProfile={caps.canShareProfile}`
  alongside `showStats={caps.canSeeFeed}`.

**Patterns to follow:**
- `mobile/lib/capabilities.ts` — matrix-tested capability pattern.
- `mobile/components/profile/ProfileHeader.tsx` — existing `showStats`
  prop ternary.

**Test scenarios:**
- **Happy path:** matrix row in `capabilities.test.ts` — with
  `social_enabled=true, session=user`, `canShareProfile === true`.
- **Happy path:** matrix row — with `social_enabled=true,
  session=guest`, `canShareProfile === true` (share target is the
  public card-web URL; guests can still share their own URL).
- **Edge case:** matrix row — with `social_enabled=false`,
  `canShareProfile === false` regardless of session mode.
- **Integration:** `profile.tsx` passes the prop through; no test
  needed beyond the capability matrix because `ProfileHeader` already
  has no unit tests (jest-expo cannot mount it).

**Verification:**
- `capabilities.test.ts` passes.
- Manual: with `social_enabled=false` locally, the Share Profile icon
  is gone; the Edit Profile button stretches to fill the row (existing
  `{ flex: 1 }` on the edit wrapper handles the layout naturally).
- With `social_enabled=true`, both buttons render as before.

---

- [ ] **Unit 2: Profile tab — remove double safe-area padding, verify no phantom holes**

**Goal:** Profile card sits flush under the tab nav header with no
duplicated safe-area gap and no phantom space from conditionally-hidden
children.

**Requirements:** R1

**Dependencies:** None (lands before or alongside Unit 1).

**Files:**
- Modify: `mobile/app/(tabs)/profile.tsx`
- Verify only: `mobile/components/profile/ProfileHeader.tsx` (no
  anticipated change; confirm no conditionally-hidden children leave a
  gap)

**Approach:**
- In `profile.tsx`, drop the inline `paddingTop: insets.top` from the
  root container style (line 302). The tab navigator's header already
  claims the top safe-area inset; the screen body starts immediately
  below it. Keep `insets` imported only if used elsewhere; remove the
  import if it becomes unused.
- Keep `TAB_BAR_HEIGHT` bottom padding unchanged (the floating tab bar
  still needs clearance).
- `ProfileHeader`'s internal `marginTop: THEME.spacing.sm` stays at
  `sm` (8 pt) — this is the intentional gap between the nav header
  baseline and the card. Only bump to `md` if manual verification
  shows the flush layout reads cramped.
- Audit `ProfileHeader` for any conditionally-rendered child that
  reserves vertical space when "hidden" — confirmed: stats row renders
  `null` when `showStats=false`, and the new Unit 1 Share Profile
  block renders `null` when `showShareProfile=false`. The `buttonsRow`
  container always renders, but its single child (Edit Profile with
  `flex: 1`) fills the row cleanly. No phantom hole.

**Patterns to follow:**
- `mobile/app/(tabs)/create.tsx` — other tab screens that do **not**
  manually pad `insets.top` when the nav header is shown.
- `mobile/AGENTS.md:40` — spacing constants only, no inline literals.

**Test scenarios:**
- Test expectation: none — cosmetic change with no behavioural branch.
  Verified in the manual screenshot review during Phase verification.

**Verification:**
- Manual: screenshot profile tab on iPhone 15 Pro simulator (notch /
  Dynamic Island) and iPhone SE simulator (no notch). Confirm the
  space between the nav header baseline and the top of the profile
  card is `THEME.spacing.sm` (8 pt) on both, not a large gap.
- Manual: toggle `social_enabled=false` via dev feature flags (or
  `mobile/.env`). Confirm Share Profile button is hidden (R2, Unit 1)
  **and** the Edit Profile button still renders cleanly with no
  phantom space where the share icon used to live.

---

- [ ] **Unit 7: Advisor chat — correct message sort order**

**Goal:** Messages render oldest-first at the top, newest-first at the
bottom — standard chat UX. The current client-side `.reverse()`
inverts a correctly-ordered API response; remove it.

**Requirements:** R8

**Dependencies:** None (standalone client-only fix).

**Files:**
- Modify: `mobile/components/advisor/ChatView.tsx`

**Approach:**
- In `loadMessages` (line 113), change
  `setMessages(response.messages.slice().reverse())` to
  `setMessages(response.messages)`.
- In `loadOlderMessages` (line 144), change
  `const older = response.messages.slice().reverse()` to
  `const older = response.messages`.
  Keep the prepend `setMessages((prev) => [...older, ...prev])`
  unchanged — older rows ascending, prepended above current window =
  overall ascending order preserved.
- Replace the stale comment on line 118 ("API returns newest first;
  we display oldest first, so reverse") with: "API returns oldest
  first; FlatList renders top-to-bottom for standard chat order."
  Keep the comment short.
- No change to `onStartReached` / `onStartReachedThreshold` — these
  still fire at the top of the list which is now the oldest edge,
  matching user intent (scroll up = load older).
- No change to the auto-scroll-to-end effect (line 265) — new messages
  appended at bottom, scroll-to-end still correct.
- Verify no backend contract change is needed by cross-referencing
  `app/repositories/advisor_repo.py:96-104` and
  `app/advisor/service.py:307-344` — both return ascending
  `created_at` today.

**Patterns to follow:**
- `app/repositories/advisor_repo.py:74-83` (`get_messages`) — the
  non-paginated variant explicitly documents "oldest first" in its
  docstring. The paginated variant is consistent.

**Test scenarios:**
- **Happy path (manual):** open Advisor → Chat tab with ≥2 messages
  already persisted. Oldest message renders at the top; newest renders
  just above the composer.
- **Happy path (manual):** send a new message. Optimistic user bubble
  appears at the bottom; Ada's reply appends below; auto-scroll keeps
  the new reply in view.
- **Edge case (manual):** scroll up to trigger pagination. Older
  messages load and prepend above the current top without reshuffling
  visible messages; relative order stays ascending end-to-end.
- **Edge case (manual):** send a message that triggers the 402 paywall.
  Optimistic bubble is removed; remaining order stays ascending.
- **Happy path (unit, optional):** if a pure helper is natural (e.g.,
  `mergeOlderPage(existing, older)`), add a 3-line test. Otherwise
  skip — this is a single-line behavioural fix that the manual test
  covers.

**Verification:**
- Manual: before/after screenshots of the Chat tab showing ordering
  reversed from shipped build.
- Automated: `cd mobile && npx expo lint` passes; `make lint` passes;
  `make test` passes (the fix does not touch test surface).

---

- [ ] **Unit 8: Theme reload — fresh random accent on every mount**

**Goal:** Every JS reload (cold start, Fast Refresh, shake-menu reload)
picks a new random accent from the 20-colour palette. No more
cross-reload persistence.

**Requirements:** R9

**Dependencies:** None (standalone client-only fix).

**Files:**
- Modify: `mobile/lib/theme-context.tsx`
- Modify: `mobile/lib/dynamic-theme.ts`

**Approach:**
- In `theme-context.tsx`: delete the mount `useEffect` that calls
  `loadOrCreateSessionTheme(...).then(setTheme)`. The synchronous
  `useState(() => buildSessionTheme())` already yields a fresh random
  pick per mount.
- In `refreshTheme` (same file), drop the `persistAccentIndex(index)`
  call. Pull-to-refresh still generates a new theme in-memory; it
  just doesn't write to storage.
- Remove the now-unused imports
  (`loadOrCreateSessionTheme`, `persistAccentIndex`).
- In `dynamic-theme.ts`: delete the `loadOrCreateSessionTheme` and
  `persistAccentIndex` functions, plus the `ACCENT_STORAGE_KEY`
  constant and the `AsyncStorage` import. Keep `buildSessionTheme`,
  `buildThemeFromIndex`, `hexToRgba`, `DEFAULT_THEME`, `DynamicTheme`.
- Stale `nxme_session_accent` entries on existing devices are
  harmless — nothing reads the key once the loader is removed. Do
  not add migration/cleanup code for it (pre-launch, no user data
  at risk — matches
  `MEMORY.md → feedback_pre_launch_destructive_ok.md`).

**Patterns to follow:**
- Existing `buildSessionTheme` — pure function, no I/O. After this
  unit, the theme layer becomes pure except for the optional runtime
  `refreshTheme` mutator.

**Test scenarios:**
- **Happy path (manual):** cold-start the app five times in a row.
  Accent is (statistically almost always) different across reloads —
  same palette, new pick. Running twice in a row with the same colour
  is possible (1/20 odds) and not a bug.
- **Happy path (manual):** dev Fast Refresh — press `r` in Metro or
  save a file. Accent rotates on each reload without user action.
- **Happy path (manual):** pull-to-refresh the feed (or wherever
  `refreshTheme` is wired) — accent changes mid-session, as today.
- **Edge case (unit):** if a pure helper feels useful, add a test
  that `buildSessionTheme()` returns a theme whose `accent` is one
  of the 20 palette entries. Otherwise skip.

**Verification:**
- Manual screenshots of the home tab across 3 cold-start reloads —
  different accents.
- `cd mobile && npx expo lint` passes.
- Grep after changes: zero references to `ACCENT_STORAGE_KEY`,
  `nxme_session_accent`, `loadOrCreateSessionTheme`,
  `persistAccentIndex` anywhere under `mobile/`.

---

- [ ] **Unit 9: Camera defaults to front for glow-up capture**

**Goal:** Tapping "Take photo" on the glow-up upload flow launches
the iOS / Android camera with the selfie (front-facing) lens already
selected.

**Requirements:** R10

**Dependencies:** None.

**Files:**
- Modify: `mobile/components/upload/PhotoPicker.tsx`

**Approach:**
- At the `ImagePicker.launchCameraAsync` call site (currently lines
  187–192), add `cameraType: ImagePicker.CameraType.front` to the
  options object. Exact shape:

  ```text
  mediaTypes: ["images"],
  allowsEditing: true,
  aspect: IMAGE_PICKER.ASPECT,
  quality: IMAGE_PICKER.QUALITY,
  cameraType: ImagePicker.CameraType.front,
  ```

- The API is part of `expo-image-picker` v14+; project is on
  `expo-image-picker@55.0.13` per `mobile/package.json:36`, so the
  `CameraType` enum is available — no version bump needed.
- Do **not** touch `EditProfileSheet.tsx:209` (library picker, not
  camera; avatar selection doesn't need a lens override).
- No other `launchCameraAsync` call sites in `mobile/` (verified via
  grep). Safe to do a surgical edit.

**Patterns to follow:**
- Existing `PhotoPicker.pickFromCamera` call; match the object-literal
  key ordering used for the other options.

**Test scenarios:**
- **Happy path (manual, iOS):** on a physical iPhone, tap "Take
  photo" on the upload screen → camera opens with front lens
  selected; user's face is visible.
- **Happy path (manual, Android):** same on an Android device (once
  a dev build is available).
- **Edge case (manual):** user taps the camera UI's built-in
  flip-camera button → rear camera engages; subsequent capture is
  accepted unchanged by the upload pipeline (server-side face
  detection handles either lens — confirmed by the existing
  "No face detected" copy in `upload.tsx:358`).
- **Permission path (manual):** on first-ever camera tap with no
  permission, the permission prompt fires first (unchanged); on
  grant, the camera opens with the front lens.

**Verification:**
- Manual on a physical device (simulators do not have a camera).
- `cd mobile && npx expo lint` passes.
- No type errors on `ImagePicker.CameraType.front` —
  `npx tsc --noEmit` in `mobile/` passes.

---

- [ ] **Unit 3: Custom in-screen header on `/result/[jobId]`**

**Goal:** Replace the inert `<Stack.Screen>` options with a real,
always-visible header row containing a back chevron that calls
`router.back()`.

**Requirements:** R3

**Dependencies:** None (independent of Units 4–6).

**Files:**
- Modify: `mobile/app/result/[jobId].tsx`

**Approach:**
- Keep `<Stack.Screen options={{ headerShown: false }} />` as a
  defensive no-op (mirrors `post/[postId].tsx:273`).
- Render a custom header row at the top of every branch (waiting,
  success, terminal-failure) — use `SafeAreaView edges={["top"]}` so
  the row clears the notch on every branch.
- Left slot: `HeaderBackButton` from `components/ui/HeaderBackButton.tsx`
  calling `router.back()` (fallback to `router.replace("/(tabs)/profile")`
  if `router.canGoBack?.()` is false and we're inside the dev-feature
  focus landing directly on the route).
- Center slot: the same title the current `<Stack.Screen>` tried to
  render — `"Your Glow-Up"` on success, `"Result"` otherwise.
- Right slot: `HeaderBackButtonSpacer` to keep the title centered.
- Header row uses `THEME.colors.bg` for background so it overlays the
  `PageBackground` cleanly; no shadow (match
  `headerShadowVisible: false`).

**Patterns to follow:**
- `mobile/app/post/[postId].tsx:273-` — `<Stack.Screen headerShown:false>`
  + custom header row.
- `mobile/components/ui/HeaderBackButton.tsx` — already exports
  `HeaderBackButton` and `HeaderBackButtonSpacer`.

**Test scenarios:**
- **Happy path:** on the success branch, the header row renders at the
  top of the scroll container; tapping back returns to the previous
  route.
- **Edge case:** on waiting branch, the header row is still visible
  above the centered hourglass.
- **Edge case:** on terminal-failure branch, the header row is still
  visible above the error copy and CTAs.
- **Edge case:** opening the route directly via dev-feature focus
  (`router.canGoBack()` returns false) — back button falls through to
  `/(tabs)/profile`.

**Verification:**
- Manual: tap a completed cell on profile → result screen shows header
  row with back chevron; tap back → returns to profile tab with the
  cell still focused.
- Manual: simulate waiting state (pending job) — header row visible.
- Manual: simulate terminal-failure (cancelled job row) — header row
  visible.

---

- [ ] **Unit 4: BeforeAfterSlider — directional gesture gating**

**Goal:** Horizontal drag on the slider keeps the divider under the
finger; vertical drag passes through to the parent `ScrollView`.

**Requirements:** R4

**Dependencies:** Unit 3 is optional — this unit only touches the
slider component.

**Files:**
- Modify: `mobile/components/result/BeforeAfterSlider.tsx`

**Approach:**
- Add a module-level constant
  `DIRECTION_THRESHOLD_PX = 10` near the other slider constants, with
  a short comment explaining that it's the slop the user has to clear
  horizontally before we claim the gesture.
- Change `onMoveShouldSetPanResponder` from `() => true` to
  `(_evt, gs) => Math.abs(gs.dx) > Math.abs(gs.dy) + DIRECTION_THRESHOLD_PX`.
- Keep `onStartShouldSetPanResponder: () => true` unchanged — tap-to-jump
  and tap-to-grab both require immediate responder claim on start.
- `onPanResponderTerminationRequest` returns `true` so the
  `ScrollView` can reclaim the gesture if the direction flips
  mid-drag.

**Patterns to follow:**
- Existing `BeforeAfterSlider.tsx` PanResponder (lines 132–166) — match
  its const-first / camelCase ordering.

**Test scenarios:**
- **Happy path (unit):** extract the direction-gate into a pure helper
  `shouldClaimHorizontal(dx, dy, threshold)` and unit-test it directly
  (`dx=20, dy=5 → true`; `dx=5, dy=20 → false`; `dx=15, dy=10 → false`
  because `15 > 10+10` is false).
- **Edge case (unit):** `dx=0, dy=0 → false` (pure tap — handled by
  `onStartShouldSet` path, not the move gate).
- **Integration (manual):** swipe horizontally across the slider on
  the result screen — divider follows the finger.
- **Integration (manual):** start touching near the slider and
  immediately swipe vertically — page scrolls; slider ignores it.
- **Integration (manual):** swipe diagonally — whichever axis exceeds
  the threshold first wins; expected horizontal wins most of the time
  because the threshold is symmetric.

**Verification:**
- Pure helper tests pass under `npx expo lint` + jest (or `npx jest`
  directly against the new helper).
- Manual: scroll the result screen page down while the slider is
  visible — page scrolls; slider does not flicker. Drag slider sideways
  — divider follows.

---

- [ ] **Unit 5: BeforeAfterSlider — label layering + default split 1.0**

**Goal:** BEFORE and GLOW UP label pills never occupy the same visible
half; default split hides the before image until the user drags left.

**Requirements:** R5, R6

**Dependencies:** Unit 4 (lands on the same component; order so
directional gate is in before we touch the layout).

**Files:**
- Modify: `mobile/components/result/BeforeAfterSlider.tsx`

**Approach:**
- Change the `initialSplit` default from `0.5` to `1.0`. Keep the
  caller (`result/[jobId].tsx`) unchanged — it already doesn't pass
  `initialSplit`, so the new default flows through.
- Update `handleAccessibilityToggle` to pivot around `0.5` (e.g.,
  current > 0.5 → 0.25; current ≤ 0.5 → 0.75) unchanged from today —
  the existing logic already handles both directions correctly and
  does not need to change as part of the default flip.
- Restructure the label pills: move **both** BEFORE and GLOW UP labels
  out of the clipped `afterClip` view so they are siblings of the
  divider container and share the full `sliderWidth` coordinate space.
- Drive each label's opacity from `splitPosition` via `useAnimatedStyle`:
  - BEFORE → opacity = `1 - splitPosition` (visible on the right side
    of the slider, hidden when glow-up covers everything).
  - GLOW UP → opacity = `splitPosition` (visible on the left side,
    hidden when nothing of the glow-up is yet revealed).
- BEFORE label anchors bottom-left using the existing
  `labelBadgeLeft.left = THEME.spacing.md`. GLOW UP anchors bottom-left
  too, but positioned at the left edge of the revealed after-image
  (equivalent to the old positioning semantic). Simplest: keep both at
  their current horizontal anchors (BEFORE bottom-left, GLOW UP
  bottom-right of full slider) and rely purely on opacity to avoid
  collision.
- Remove the now-empty `labelBadge` child from inside `afterClip` —
  the clip only holds the after image.

**Patterns to follow:**
- Existing `useAnimatedStyle` + `useSharedValue` usage in the same
  file (lines 168–176) — opacity styles go next to the divider/overlay
  style.

**Test scenarios:**
- **Happy path (unit, pure helpers):** extract
  `labelOpacities(split: number) → { before: number, after: number }`
  and assert `labelOpacities(0) = {before:1, after:0}`,
  `labelOpacities(1) = {before:0, after:1}`,
  `labelOpacities(0.5) = {before:0.5, after:0.5}`.
- **Edge case (unit):** clamp — `labelOpacities(-0.2)` and
  `labelOpacities(1.3)` stay in `[0,1]`.
- **Integration (manual):** mount the result screen with a completed
  job — first frame shows full glow-up image with slider handle at
  the right edge, GLOW UP badge visible bottom-right, BEFORE hidden.
- **Integration (manual):** drag divider all the way left — BEFORE
  badge fully visible, GLOW UP fades out; no overlap at any
  intermediate position.
- **Integration (manual):** accessibility "Toggle between before and
  after" action from VoiceOver flips the split as before — labels
  fade accordingly.

**Verification:**
- Pure helper tests pass.
- Manual: screenshot before/after on device at split 0, 0.25, 0.5,
  0.75, 1 — confirm exactly one badge on the visible side except at
  the midpoint where both may be ~50 % opacity (this is expected and
  matches the monotonic fade).

---

- [ ] **Unit 6: ZoomableImageModal — pinch + pan viewer**

**Goal:** Tap either image on the result screen to open a full-screen
modal with pinch-zoom, pan (when zoomed), double-tap reset, and
dismiss via back chevron or swipe-down.

**Requirements:** R7

**Dependencies:** Unit 3 (the result screen header patterns live in
place) and Unit 5 (slider internal layout stabilised so tap hit
targets on the slider are unambiguous).

**Files:**
- Create: `mobile/components/ui/ZoomableImageModal.tsx`
- Create: `mobile/components/ui/__tests__/ZoomableImageModal.helpers.test.tsx`
- Modify: `mobile/components/result/BeforeAfterSlider.tsx` (expose
  `onPressBefore` / `onPressAfter` callbacks).
- Modify: `mobile/app/result/[jobId].tsx` (mount the modal, hook up
  taps).

**Approach:**
- `ZoomableImageModal` props: `{ visible, sourceUri, altText, onClose }`.
- Internally wraps a React Native `Modal` (`presentationStyle="fullScreen"`,
  `animationType="fade"`, status bar content `light`) containing:
  - A top header row with a `HeaderBackButton` at the left that calls
    `onClose`.
  - A full-bleed `Animated.Image` sized `width: sliderWidth, height:
    sliderHeight` via `useWindowDimensions` for portrait 3:4.
  - A `PanResponder` attached to the image container.
- Shared values: `scale`, `translateX`, `translateY`. All driven by
  Reanimated.
- Pinch math: in `onPanResponderMove`, if
  `evt.nativeEvent.touches.length === 2`, compute the current
  two-finger distance; store initial distance + initial scale in
  `onPanResponderGrant`; set `scale = clamp(initialScale *
  (currentDist / initialDist), MIN_SCALE, MAX_SCALE)`.
- Pan math: when `evt.nativeEvent.touches.length === 1` and `scale >
  1`, translate by `gestureState.dx / dy` off the initial translate.
  When `scale === 1`, vertical drag translates downward and, on
  release past a threshold, calls `onClose` (swipe-down dismiss).
- Double-tap (two `onStartShouldSetPanResponder` within ~300 ms at ~same
  location): reset scale to 1 and translate to 0 with a spring.
- Extract pure helpers for test coverage:
  - `twoFingerDistance(touches) → number`
  - `clampScale(scale) → number`
  - `shouldDismissOnSwipeDown(translateY, velocityY) → boolean`
- `BeforeAfterSlider` gains optional callbacks
  `onPressBeforeImage?: () => void`, `onPressAfterImage?: () => void`.
  These are invoked only on tap (`gestureState.dx` + `dy` ≈ 0 at
  release). The existing tap-to-jump semantics stay — a tap inside
  the dead-zone still jumps the divider; a tap outside still jumps to
  that position; the new callback fires **in addition** when the tap
  is a pure tap (no drag, no jump distance ≥ some small threshold).
  Alternative considered: a separate Pressable layer. Rejected because
  it would fight the PanResponder for the gesture. Using the release
  hook keeps all gesture logic in one place.
- Result screen: wire both callbacks — tapping the visible side opens
  the zoom modal seeded with the visible image URL; when scrubbed,
  the user can swipe-down to dismiss and see the same slider state.

**Patterns to follow:**
- `mobile/components/paywall/PaywallModal.tsx` — existing
  swipe-down-dismiss Modal pattern.
- `mobile/components/ui/HeaderBackButton.tsx` — back chevron.

**Test scenarios:**
- **Happy path (unit):** `twoFingerDistance([{x:0,y:0},{x:3,y:4}])===5`.
- **Edge case (unit):** `clampScale(0.5)===1` (min), `clampScale(10)===MAX_SCALE`.
- **Edge case (unit):** `twoFingerDistance([])===0`,
  `twoFingerDistance([onePoint])===0`.
- **Error path (unit):** `shouldDismissOnSwipeDown(translateY=200,
  velocityY=1200) === true`; `(50, 0) === false`.
- **Integration (manual):** tap the before photo on result → modal
  opens showing only the before image; pinch to zoom; pan around;
  double-tap to reset; tap back — modal closes.
- **Integration (manual):** same for the glow-up image.
- **Integration (manual):** with slider at split 0 (pure before),
  tapping opens the before modal, not the glow-up. Same for split 1.
- **Edge case (manual):** hit the modal before the result screen has
  rendered image URLs (race) — modal never opens (callbacks are
  gated on `result?.before_image_url && result?.after_image_url`).

**Verification:**
- Helper unit tests pass.
- Manual: on a real device (iPhone), pinch-zoom feels correct at 2×,
  3×, max; no jank; pan works at scale > 1; double-tap resets; back
  chevron dismisses; swipe-down dismisses.
- Manual: VoiceOver announces "Before photo, enlarged view" on
  modal open; back button reads "Go back".

## System-Wide Impact

- **Interaction graph:**
  - `useCapabilities()` gains a consumer (`ProfileHeader` via
    `profile.tsx`). No other caller reads the new flag.
  - `BeforeAfterSlider` gains two optional callbacks; existing
    callers (none besides `result/[jobId].tsx`) remain compatible.
  - `HeaderBackButton` has a new call site in `ZoomableImageModal`
    and `result/[jobId].tsx`.
- **Error propagation:** gestures that fail directional gating simply
  pass through to the parent `ScrollView` — no error surface.
  `ZoomableImageModal` handles broken image URIs via the underlying
  `<Image>` component's `onError` (no retry / no toast needed; the
  modal can be closed).
- **State lifecycle risks:** `ZoomableImageModal`'s shared values must
  reset on close (scale → 1, translate → 0) so the next open starts
  fresh. The slider's split default change (1.0) is mount-time only;
  no existing state is persisted.
- **API surface parity:** capability test matrix gains one row; no
  public API changes beyond new props on `ProfileHeader` and
  `BeforeAfterSlider` (both additive, both optional with defaults).
- **Integration coverage:** directional gate + label layering are
  logic-heavy but deterministic — covered via pure helper unit tests
  because jest-expo cannot mount Reanimated components under the
  existing harness (noted in `profile.test.tsx:7-13`).
- **Unchanged invariants:** `BeforeAfterSlider` public props signature
  (`beforeUrl`, `afterUrl`, `rightLabel`, `initialSplit`,
  `onAccessibilityToggle`) remains; only `initialSplit`'s default
  changes and two optional callbacks are added. Result screen's
  success/waiting/terminal branches stay. Capability matrix remains
  backwards-compatible (all existing flags unchanged).

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Directional gate threshold too aggressive → slider feels sticky | Extract threshold as a named constant (`DIRECTION_THRESHOLD_PX`) and tune during Unit 4 manual testing. Start at 10 px; adjust if needed. |
| Directional gate too loose → parent scroll still cancels slider | Manual test on a real device with the slider mid-scroll; increase threshold to ~14 px if scroll wins too often. |
| PanResponder pinch math jitters because of rapid finger swaps | Track `initialDistance` inside `onPanResponderGrant` and reset to current distance whenever `touches.length` transitions from 1→2 (so the user can re-pinch without closing the modal). |
| Label opacity fade makes the midpoint unreadable | Accept midpoint overlap as the cleanest fade curve; if reviewer rejects, swap to step-function at split = 0.5 during Unit 5 tuning. |
| Back button not wired correctly when route opened via dev-feature focus | Use `router.canGoBack?.() ? router.back() : router.replace("/(tabs)/profile")` in Unit 3. |
| PR #121's shipped slider behaviour regresses on existing saved results | Changes are additive / non-breaking (new default, new callbacks, directional gate is strictly looser for parent scroll). Verify with at least one real saved job on device. |
| `react-native-gesture-handler` creeps in via another dependency update | Bound this plan to PanResponder / Reanimated only; if gesture-handler lands later, re-evaluate ZoomableImageModal in a follow-up PR. |

## Documentation / Operational Notes

- Update `mobile/AGENTS.md` only if new patterns emerge that deserve
  reuse (e.g., "screens pushed under `<Slot/>` must render their own
  header using `HeaderBackButton`" — if not already documented, add a
  short note after Unit 3 lands).
- No changelog/runbook needed — pre-launch.
- No Sentry / analytics event changes.

## Sources & References

- **Advisor chat backend sort:** `app/repositories/advisor_repo.py:74-83`,
  `app/repositories/advisor_repo.py:96-104` (both ascending / oldest-first).
- **Advisor chat client:** `mobile/components/advisor/ChatView.tsx:118-119`,
  `:149` (incorrect client-side reverse).
- **Theme persistence site:** `mobile/lib/theme-context.tsx:40-44`,
  `mobile/lib/dynamic-theme.ts:52-86` (storage round-trip to remove).
- **Camera default lens site:** `mobile/components/upload/PhotoPicker.tsx:187-192`
  (missing `cameraType` option).
- **Predecessor plan (PR #121):** `docs/plans/2026-04-17-001-feat-glowup-ux-polish-and-advisor-nudges-plan.md`
- **Capability gating contract:** `docs/plans/2026-04-15-001-feat-feature-flags-redesign-plan.md`
- **Profile top-level screen:** `mobile/app/(tabs)/profile.tsx`
- **Result screen:** `mobile/app/result/[jobId].tsx`
- **Slider component:** `mobile/components/result/BeforeAfterSlider.tsx`
- **Capability source + tests:** `mobile/lib/capabilities.ts`,
  `mobile/lib/capabilities.test.ts`
- **Shared header chevron:** `mobile/components/ui/HeaderBackButton.tsx`
- **Custom-header reference implementation:** `mobile/app/post/[postId].tsx`
- **Memory guidance:** `MEMORY.md` → `feedback_disabled_button_ux.md`,
  `feedback_feature_gating_centralized.md`,
  `feedback_no_hardcoded_urls.md` (magic-number constants for
  `DIRECTION_THRESHOLD_PX`, `MIN_SCALE`, `MAX_SCALE`, etc.).
