---
title: "feat: Advisor empty-state overlay + shared composer"
type: feat
status: active
date: 2026-04-15
origin: docs/brainstorms/2026-04-15-advisor-empty-state-and-composer-requirements.md
---

# feat: Advisor empty-state overlay + shared composer

## Overview

Two mobile-UI fixes on the advisor feature (Chat / Nudges / Memories tabs):

1. **Empty state** — render at a fixed vertical center inside the advisor content area so Chat, Nudges, and Memories all show their zero-state copy at the same on-screen position. Currently `EmptyState` flex-centers inside the list container, so any sibling composer or form shifts the center.
2. **Shared composer** — extract the chat input (pill-shape TextInput + round accent action button) into `AdvisorComposer` and reuse it in `MemoryList`'s add-memory form. Keep the Goal / Note type chips as-is.

Light memory-card polish is included as a soft goal; revert if it regresses the filled state.

Work happens inside a `git worktree` off `dev`. Single PR.

## Problem Frame

See origin: `docs/brainstorms/2026-04-15-advisor-empty-state-and-composer-requirements.md`.

Short form: Chat feels centered because the chat input sits below its FlatList; Nudges drifts up because no input offsets the center downward; Memories drifts down because `AddMemoryForm` (~140px of chrome) pushes the center below the true midpoint. Separately, `MemoryList` reimplements the chat composer with subtle divergence instead of reusing it.

## Requirements Trace

- **R1.** Empty-state copy lands at the same vertical position across Chat, Nudges, and Memories, measured from the top of the advisor content area. (origin §Goals/1, §Acceptance/1)
- **R2.** Empty-state overlay does not intercept taps on composers, forms, or type chips. (origin §Acceptance/2)
- **R3.** Empty state is hidden during loading and error states. (origin §Acceptance/3)
- **R4.** Chat and Memories render the same composer component; invocation diff limited to `placeholder`, `submitIcon`, `maxLength`, `onSubmit`. (origin §Goals/3, §Acceptance/4)
- **R5.** Memories filled state has no visual regression; Goal/Note chips still work; swipe-to-delete still works. (origin §Acceptance/5)
- **R6.** `npx expo lint` passes; no new TS errors. (origin §Acceptance/6)

## Scope Boundaries

- No changes to empty-state **copy** or **icon** (current: `sparkles-outline`, `bookmark-outline`).
- No changes to advisor tab navigation or tab-pill aesthetic.
- No changes to server contracts, fetch logic, pagination, paywall, skeletons, swipe-to-delete, or Goal/Note type chip selector.
- No new mobile unit test files — the project has no RN component test infrastructure (`mobile/__tests__/` does not exist). Verification is lint + type-check + manual simulator sweep.

### Deferred to Separate Tasks

- None. Single PR covers everything in this plan.

## Context & Research

### Relevant Code and Patterns

- `mobile/components/ui/EmptyState.tsx` — existing shared empty-state visual (icon + heading + body + optional action). Keep its visual contract; change how it is **positioned** by the caller.
- `mobile/app/advisor/index.tsx` — advisor screen with top tab pills and content `View` (line 105-109). Root mount point for the overlay.
- `mobile/components/advisor/ChatView.tsx:380-413` — canonical pill-composer (TextInput + round send button) with focus glow, active accent, disabled state, `ActivityIndicator` swap while sending.
- `mobile/components/advisor/MemoryList.tsx:321-367` — duplicate composer inside `AddMemoryForm`; needs to be replaced with the extracted component.
- `mobile/components/advisor/NudgeFeed.tsx:220-237` — has no composer; empty state is the only concern.
- `mobile/constants/theme.ts` — `THEME.colors`, `THEME.spacing`, `THEME.radius`, `THEME.shadow.glass`, `THEME.shadow.glow(accent)` — reuse these tokens; no new constants.
- `mobile/constants/config.ts` — `MIN_TOUCH_TARGET`, `ADVISOR_CONFIG.MESSAGE_MAX_LENGTH`. Memory max length (500) stays inline in `AddMemoryForm` or moves into `ADVISOR_CONFIG.MEMORY_MAX_LENGTH` (see Key Decisions).
- `mobile/app/(tabs)/_layout.tsx:24` — `TAB_BAR_HEIGHT = 90`. Chat already accounts for this in its input `paddingBottom`; the overlay must **not** try to — the overlay is inside the advisor content View, which is naturally above the floating tab bar.
- `mobile/lib/theme-context.tsx` — `useTheme()` for accent color on composer focus/submit states.

### Institutional Learnings

- No `docs/solutions/` entries exist — repo has not yet accumulated those.
- Per recent observations: frontend test coverage is minimal vs. backend (memory S13638). This plan does not add RN component tests; it aligns with current repo posture.

### External References

- None required. Standard React Native composition patterns, `StyleSheet.absoluteFill`, `pointerEvents="none"` — all widely used in this codebase (see multiple overlays in `mobile/components/**`).

## Key Technical Decisions

- **Empty state rendered as a sibling overlay, not `ListEmptyComponent`.** `ListEmptyComponent` centers inside the list's content-inset-aware area, which is exactly what currently causes the drift. An absolute-positioned sibling overlay anchored to the advisor content area gives each tab an identical reference frame. (See origin §Solution sketch/empty-state.)
- **Overlay wrapper `pointerEvents="none"`** so taps pass through to whatever interactive element is under it — composer, form, scroll area. Keeps the overlay visually present without stealing gestures. (Satisfies R2.)
- **Gate rendering on `!isLoading && !error && items.length === 0`** in each tab's container. Prevents overlay from flashing during skeleton loads or conflicting with `EmptyState` error-variant. (Satisfies R3.)
- **New component path `mobile/components/advisor/AdvisorComposer.tsx`** (not `components/ui/`) — advisor-specific concerns (send vs add icon, keyboard offset prop for chat). Move to `ui/` only if a third consumer appears. (origin §Risks.)
- **Composer prop shape is minimal; Goal/Note chips live outside it.** Chips stay in `AddMemoryForm` and render above the composer. Composer exposes `submitIcon: "send" | "add"` and nothing else about type selection. Matches user direction (origin §Non-goals) and user's answered preference (single-purpose composer).
- **`MEMORY_MAX_LENGTH` constant.** Move the inline `500` in `AddMemoryForm` to `mobile/constants/config.ts::ADVISOR_CONFIG.MEMORY_MAX_LENGTH = 500` to match how `MESSAGE_MAX_LENGTH` is already exported. Honors the "no magic numbers" rule.
- **Keyboard handling stays in `ChatView`.** `AdvisorComposer` does not wrap itself in `KeyboardAvoidingView`. Chat keeps its existing `KeyboardAvoidingView` + keyboard show/hide listeners; memories does not need any of that because its form sits at the top of the content area. Composer exposes a `bottomPadding` prop so chat can pass the computed `insets.bottom + tabBarOffset` from outside.
- **Memory card polish is scoped and revertible.** Implemented as a single commit. If the filled view regresses, revert that commit without touching the other three units. Specifically: replace the `UPPERCASE GOAL | date` header with an inline pill-tag (icon + label) at the top-left, demote date to a small caption under the body. Keep circular icon badge for now — removing it is a second step I will only take if the tag pill visibly replaces it without feeling hollow.

## Open Questions

### Resolved During Planning

- *Should Memories composer render below the Goal/Note chips or alongside them?* **Below.** Chips are a type selector; composer is input. Keeping them vertically stacked preserves the current `AddMemoryForm` shape and avoids redesigning the selector.
- *Does the overlay need to animate in/out?* **No.** Mount/unmount is instant; matches current `ListEmptyComponent` behaviour. Adding motion is out of scope.
- *Where does 500-char memory limit live?* **In `ADVISOR_CONFIG`.** One place, consistent with `MESSAGE_MAX_LENGTH`.

### Deferred to Implementation

- Exact `pointerEvents` behaviour on Android vs iOS if issues appear during simulator testing. Current plan uses `pointerEvents="none"` on the overlay wrapper; escalate to `box-none` only if empty-state children themselves need to be interactive (e.g., if we add a CTA later — not in this PR).
- Whether to memoize the overlay component. Defer until profiling; premature.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

Overlay layering inside each advisor tab's root `View`:

```
advisor content <View style={flex:1}>
├── <FlatList>                                 ← list content (paginated, scrollable)
├── <AdvisorComposer>                          ← chat & memories only (absent in nudges)
└── <AdvisorEmptyOverlay>                      ← absoluteFill + pointerEvents=none
     └── centered icon + title + description   ← same copy as today
```

Overlay is rendered conditionally: `!isLoading && !error && items.length === 0`. It paints over the list and composer but does not block gestures. The center of the overlay is always the midpoint of the tab's root `View`, which is identical across tabs by construction.

Composer prop flow:

```
ChatView  → AdvisorComposer {value, onChangeText, onSubmit, placeholder:"Message Ada...",
                             submitIcon:"send", maxLength:MESSAGE_MAX_LENGTH,
                             disabled:isSending, bottomPadding:<computed>}

MemoryList → AdvisorComposer {value, onChangeText, onSubmit, placeholder:<goal|note hint>,
                              submitIcon:"add", maxLength:MEMORY_MAX_LENGTH,
                              disabled:isAdding}
                                   ^
                                   | rendered below Goal/Note chips, no bottomPadding
```

## Implementation Units

- [ ] **Unit 1: Extract `AdvisorComposer` and migrate `ChatView`**

**Goal:** Introduce the shared pill-input + round action button component, drop-in replace the chat input bar. No UX change visible to the user.

**Requirements:** R4, R6.

**Dependencies:** None.

**Files:**
- Create: `mobile/components/advisor/AdvisorComposer.tsx`
- Modify: `mobile/components/advisor/ChatView.tsx`
- Modify: `mobile/constants/config.ts` (add `ADVISOR_CONFIG.MEMORY_MAX_LENGTH = 500` while we're in the file; keep export site alphabetized)
- Test: *no new test file — see Key Decisions*

**Approach:**
- Copy the existing chat input bar JSX + styles from `ChatView.tsx:380-413` + `styles.inputBar|textInput|sendButton*` into `AdvisorComposer.tsx`.
- Props: `{value, onChangeText, onSubmit, placeholder, disabled?, submitIcon?:"send"|"add", maxLength?, accessibilityLabel, submitAccessibilityLabel, bottomPadding?}`.
- Swap `Ionicons` name based on `submitIcon` (`send` = existing; `add` = `"add"` at size 24 to match the current memories button).
- Apply `paddingBottom: bottomPadding ?? 0` to the input bar wrapper; everything else stays in `THEME.spacing.sm`.
- Preserve focus-glow behaviour: track `isFocused` internally so both callers get it for free (MemoryList's existing behaviour).
- `ChatView` replaces its input section with `<AdvisorComposer ... bottomPadding={inputBottomPadding} />`. `KeyboardAvoidingView` stays wrapping the composer.
- Delete the now-unused `styles.inputBar`, `styles.textInput`, `styles.sendButton*` entries from `ChatView.tsx`.

**Patterns to follow:**
- Use `useTheme()` for `theme.accent`, matching how `MemoryList` and `ChatView` already do it.
- Button active/disabled state pattern: `canSubmit = value.trim().length > 0 && !disabled`, `THEME.shadow.glow(theme.accent)` for the glow, `borderWidth: 0` when active.
- `ActivityIndicator` swaps in when `disabled && value.length === 0` is false (i.e., while submitting) — mirror the current `isSending` / `isAdding` handling.

**Test scenarios:**
- Manual: chat send flow end-to-end in iOS simulator (type message → press send → message appears in list; empty input → button is disabled; focus → accent border appears).
- Lint/type: `cd mobile && npx expo lint` must pass; `npx tsc --noEmit` must pass.

**Verification:**
- Chat tab behaviour is visually indistinguishable from `dev`. All chat interactions (type, send, paywall dismiss-and-restore, error banner) still work.
- `AdvisorComposer.tsx` has no references to chat-specific concepts (no `sendMessage`, no paywall, no message list).

- [ ] **Unit 2: Empty-state overlay pattern applied to all three advisor tabs**

**Goal:** Render empty-state copy at the same vertical position across Chat, Nudges, and Memories by promoting `EmptyState` into an absolute-positioned sibling overlay instead of `ListEmptyComponent`.

**Requirements:** R1, R2, R3, R6.

**Dependencies:** Unit 1 (not strictly required, but sequencing this second means we only edit each tab file once).

**Files:**
- Modify: `mobile/components/advisor/ChatView.tsx` (remove `ListEmptyComponent` prop; add overlay sibling)
- Modify: `mobile/components/advisor/NudgeFeed.tsx` (same)
- Modify: `mobile/components/advisor/MemoryList.tsx` (same)
- Optional: `mobile/components/ui/EmptyState.tsx` — add a new prop `overlay?: boolean` that applies `StyleSheet.absoluteFill` + `pointerEvents="none"` wrapping, OR introduce a small wrapper `AdvisorEmptyOverlay` in `mobile/components/advisor/` that composes `EmptyState`. Prefer the wrapper — keeps `EmptyState` agnostic to advisor concerns.
- Create: `mobile/components/advisor/AdvisorEmptyOverlay.tsx` (thin wrapper)

**Approach:**
- `AdvisorEmptyOverlay` renders `<View style={StyleSheet.absoluteFill} pointerEvents="none"><View style={{flex:1, alignItems:"center", justifyContent:"center", paddingHorizontal: THEME.spacing.xxxl}}><EmptyState center={false} ... /></View></View>`. Passing `center={false}` to `EmptyState` is important — the overlay handles centering; `EmptyState`'s own `flex:1` centered mode fights the outer flex parent otherwise. (See `EmptyState.tsx:106-118`.)
- In each advisor tab component:
  - Remove the `ListEmptyComponent={<EmptyState .../>}` prop from the FlatList.
  - Add `{!isLoading && !error && items.length === 0 && <AdvisorEmptyOverlay icon="..." title="..." description="..." />}` as a sibling inside the root `View`.
  - Keep error-variant `EmptyState` (retry button) as a **full-screen replacement** — its current flow still applies only when `items.length === 0` and `error !== null`.
- The Chat case is subtle: `ChatView` currently returns `<KeyboardAvoidingView>` as root, not a `<View>`. Wrap the overlay inside that same `KeyboardAvoidingView` so it covers the whole chat surface. The composer (Unit 1's child) sits at the bottom; the overlay paints on top of empty list + composer but `pointerEvents="none"` keeps the composer tappable.

**Patterns to follow:**
- Existing shadow/overlay pattern from `PageBackground` (layered sibling inside screen root).
- `StyleSheet.absoluteFill` + `pointerEvents` is used in other components for non-interactive overlays.

**Test scenarios:**
- Manual: open a fresh dev session with no messages, no nudges, no memories. Cycle through all three tabs; the empty-state title + description should sit at the same Y-coordinate on each tab (eyeball + take screenshots to compare).
- Manual: focus the chat input and confirm the empty-state overlay does not block keyboard-open or typing.
- Manual: focus the memory input and confirm Goal/Note chips, input, and add button are all tappable while the overlay is visible.
- Manual: trigger an error (airplane mode → load) and confirm the error-variant `EmptyState` with the retry button still renders and the overlay does **not**.

**Verification:**
- On all three tabs, zero-state screenshots show title copy at matching Y-positions (within ~4px tolerance given safe-area variance).
- Empty-state overlay never mounts while `isLoading` is true or `error` is truthy.
- All existing interactions below the overlay still work.

- [ ] **Unit 3: Migrate `AddMemoryForm` to `AdvisorComposer`**

**Goal:** Replace the duplicate input-and-button inside `AddMemoryForm` with `AdvisorComposer`. Goal/Note chips stay; their placement above the composer is unchanged.

**Requirements:** R4, R5, R6.

**Dependencies:** Unit 1.

**Files:**
- Modify: `mobile/components/advisor/MemoryList.tsx`

**Approach:**
- Strip the inline `<TextInput>` + `<PressableScale>` add button from `AddMemoryForm` (lines ~321-367).
- Replace with `<AdvisorComposer value={content} onChangeText={setContent} onSubmit={handleAdd} placeholder={...} submitIcon="add" maxLength={ADVISOR_CONFIG.MEMORY_MAX_LENGTH} disabled={isAdding} accessibilityLabel="Memory content" submitAccessibilityLabel="Add memory" />`.
- Delete `formStyles.inputRow`, `formStyles.input`, `formStyles.addButton` — now dead. Keep `formStyles.container` and `formStyles.typeRow`/`typeChip` because those are still the chip row.
- Preserve the placeholder-per-type logic (`selectedType === "goal" ? "e.g. Grow out my hair..." : "e.g. I prefer minimal jewelry"`).
- Preserve `content` reset on successful submit.

**Patterns to follow:**
- Same prop contract as chat's invocation from Unit 1.

**Test scenarios:**
- Manual: switch between Goal and Note chips, type a value, submit, confirm card appears in the list.
- Manual: long value (>500 chars) is clamped by `maxLength`; submit with empty value is disabled.
- Manual: optimistic UI + toast on error still function (no change to `handleAdd` flow).

**Verification:**
- Memory-add flow is behaviorally identical to pre-change.
- Chat composer and memories composer are visually matched (same pill shape, same glow, same button size).
- `npx expo lint` and type-check pass.

- [ ] **Unit 4: Memory card polish (soft goal, revertible)**

**Goal:** Tighten the filled memory-card visual so the Goal/Note card reads cleanly now that empty/add states are unified.

**Requirements:** R5 (must not regress). Not tied to any hard requirement.

**Dependencies:** Independent of Units 1-3; can land last or be dropped entirely.

**Files:**
- Modify: `mobile/components/advisor/MemoryList.tsx` (the `SwipeableMemoryRow` and `rowStyles` block)

**Approach:**
- Replace the `[typeLabel][spacer][date]` row with a single inline pill-tag: icon + type label, small size, sits at the top of the text column. Uses existing `Caption` + `Ionicons` + `theme.accentMuted`/`theme.accent` tokens.
- Move the date to a short caption line below the body (`THEME.colors.textMuted`, small font).
- Tighten icon-badge margin to text column by `THEME.spacing.xs`.
- If at end of unit the filled view looks worse than the current implementation in the simulator with ≥3 seeded memories, **revert this commit** and ship Units 1-3 only.

**Patterns to follow:**
- Inline chip: mirror the tab pill from `mobile/app/advisor/index.tsx:87-99` but at a smaller scale.

**Test scenarios:**
- Manual: seed a Goal, a Note, and an Insight memory; confirm all three variants render without clipping or alignment jitter.
- Manual: swipe each row left and confirm delete still snaps and fires `onDelete`.
- Manual: toggle themes (if theme switch exists) and confirm accent color updates.

**Verification:**
- Filled state reads at least as clean as before; cards aren't taller or shorter than ~8px of their current height.
- Swipe-to-delete threshold and animation unchanged.
- `npx expo lint` and type-check pass.

## System-Wide Impact

- **Interaction graph:** Only advisor components. No backend, no routing, no auth, no other tabs.
- **Error propagation:** Unchanged. Error `EmptyState` (retry) still renders fullscreen when fetches fail; the overlay is only for the happy-empty case.
- **State lifecycle risks:** None beyond render gating on `items.length === 0` + `!isLoading` + `!error`. `pointerEvents="none"` avoids any gesture-swallowing regressions.
- **API surface parity:** `AdvisorComposer` is a new internal component. `EmptyState`'s public API gains one behaviour at most (`center={false}` is already supported per `EmptyState.tsx:51,114`) — no change.
- **Integration coverage:** Visual-only changes. Paywall (402), send/add flows, pagination, swipe-delete all unchanged and re-verified in test scenarios above.
- **Unchanged invariants:** `EmptyState`'s visual contract (icon/title/description/action), Goal/Note selector chip UX, `ADVISOR_CONFIG.MESSAGE_MAX_LENGTH`, `TAB_BAR_HEIGHT`, chat `KeyboardAvoidingView` behaviour, paywall flow, swipe-to-delete.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Overlay `pointerEvents="none"` behaves differently on Android vs iOS | Test on both simulators if available; escalate to `box-none` if empty-state children need interactivity later. Chat already tested on iOS per prior work. |
| Chat composer regression from the extract (keyboard offset, bottom padding, disabled transitions) | Unit 1 is behaviour-preserving; visual regression is catchable in the simulator within minutes of the commit. Lint + type-check + manual pass before Unit 2 lands. |
| Memory card polish (Unit 4) worsens filled state | Unit 4 ships as a standalone commit. Revert locally before pushing if it regresses. Ship Units 1-3 unconditionally. |
| `AdvisorComposer` acquires too many props over time as future consumers appear | Prop surface is intentionally minimal (9 props). If a third consumer wants type chips built-in, that change is a separate refactor, not this PR. |
| User can't see filled memory cards in current state to validate Unit 4 | Seed 3 memories locally (Goal + Note + Insight) via the existing add flow before inspecting. If seeding is painful, drop Unit 4 entirely — the plan explicitly permits that. |

## Documentation / Operational Notes

- No docs changes. No env changes. No migration. No flag.
- Work happens in a `git worktree` off `dev`. One feature branch, one PR, merge to `dev` per `feedback_pr_workflow.md`.
- Pre-PR verification: `cd mobile && npx expo lint` + `npx tsc --noEmit` + manual simulator sweep of all three tabs (empty + filled).
- Before opening the PR, invoke a code-review skill on the diff per `feedback_code_review_before_pr.md`.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-15-advisor-empty-state-and-composer-requirements.md](../brainstorms/2026-04-15-advisor-empty-state-and-composer-requirements.md)
- Related code:
  - `mobile/components/ui/EmptyState.tsx`
  - `mobile/components/advisor/ChatView.tsx`
  - `mobile/components/advisor/MemoryList.tsx`
  - `mobile/components/advisor/NudgeFeed.tsx`
  - `mobile/app/advisor/index.tsx`
  - `mobile/app/(tabs)/_layout.tsx` (TAB_BAR_HEIGHT)
  - `mobile/constants/config.ts` (ADVISOR_CONFIG)
- Related PRs / prior work: #88 (mobile UI overhaul — latest polish pass on this surface area).
- External docs: none.
