# Advisor empty states + shared composer — requirements

**Date:** 2026-04-15
**Scope:** mobile (`mobile/`)
**Size:** Lightweight → Standard (UI polish + component extraction)
**Related files:** `mobile/components/advisor/{ChatView,NudgeFeed,MemoryList}.tsx`, `mobile/components/ui/EmptyState.tsx`

## Problem

Two UX inconsistencies on the advisor feature (Chat / Nudges / Memories tabs).

### 1. Empty-state vertical position drifts per tab

`EmptyState` flex-centers inside whatever list container wraps it. Effective center differs by tab because sibling components change available height:

| Tab      | Siblings above list       | Siblings below list       | Visual center |
|----------|---------------------------|---------------------------|---------------|
| Chat     | none (inside FlatList)    | input bar + tab bar offset | Looks centered (baseline) |
| Nudges   | none                      | floating tab bar overlay   | Drifts upward |
| Memories | `AddMemoryForm` (~140px)  | floating tab bar overlay   | Drifts downward |

User-visible effect: the same copy lands in different places depending on which tab is open. Chat feels right; Nudges and Memories feel wrong.

### 2. Memories "add" input diverges from chat composer

`ChatView` has a pill-shaped `TextInput` + round accent send button (`mobile/components/advisor/ChatView.tsx:380-413`). `MemoryList` has a near-duplicate pill+button pair (`MemoryList.tsx:321-367`) with slightly different padding, shadow, and focus behaviour. Two similar components, no shared source of truth.

## Goals

1. Empty state renders at the **same vertical center** across Chat, Nudges, Memories regardless of whether the tab has a composer, form, or extra top chrome.
2. Empty state only appears when the tab truly has no content (loaded + zero items).
3. One reusable composer component (pill input + round accent action button) used by Chat and Memories.
4. Memory cards get a light display polish so the filled state reads cleanly on first viewing.

## Non-goals

- Redesigning advisor tab navigation.
- Changing empty-state copy or icons (keep current: `sparkles-outline`, `bookmark-outline`).
- Touching server contracts, fetch logic, pagination, or swipe-to-delete behaviour.
- Replacing or restyling the Goal / Note type chips — keep as-is per user direction.
- Reworking paywall, skeleton, or error/retry UX.

## Solution sketch

### Empty state — `AdvisorEmptyState` (or extend `EmptyState`)

Absolute-position the empty state at the vertical center of the **advisor content area** — the `View` rendered at `mobile/app/advisor/index.tsx:105-109` between the top tab pills and the system tab bar.

- Sibling composers, forms, and inputs render on top of this overlay without affecting its position.
- Content area center = true midpoint of the tab's visible region; identical on all three tabs.
- Overlay is `pointerEvents="none"` so it never steals taps meant for the composer or add form.
- Mount only when `isLoading === false && error === null && items.length === 0`.

Implementation shape (pseudo):

```tsx
// New variant on EmptyState OR new AdvisorEmptyState wrapper
<View style={StyleSheet.absoluteFill} pointerEvents="none">
  <View style={{ flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: THEME.spacing.xxxl }}>
    <Ionicons ... /><Heading ... /><Body ... />
  </View>
</View>
```

Rendered as a **sibling** to the FlatList (not as `ListEmptyComponent`) inside each tab's root container, so its position is not constrained by list content insets or the composer height.

### Shared composer — `AdvisorComposer`

Extract from `ChatView`'s input bar. New file: `mobile/components/advisor/AdvisorComposer.tsx`.

Props (minimal surface):

```ts
interface AdvisorComposerProps {
  value: string;
  onChangeText: (v: string) => void;
  onSubmit: () => void;
  placeholder: string;
  disabled?: boolean;           // true while sending/adding
  submitIcon?: "send" | "add";  // chat → "send", memories → "add"
  maxLength?: number;           // chat: ADVISOR_CONFIG.MESSAGE_MAX_LENGTH, memories: 500
  accessibilityLabel: string;
  submitAccessibilityLabel: string;
  /** Optional bottom inset applied to the bar itself (chat handles keyboard+tab bar). */
  bottomPadding?: number;
}
```

- Chat: uses `submitIcon="send"`, handles its own `KeyboardAvoidingView` + `bottomPadding` (already does).
- Memories: uses `submitIcon="add"`, no `bottomPadding` (form sits at top of content area, above the list).
- Type chips (Goal / Note) stay in `AddMemoryForm` and render **above** the composer. The composer itself knows nothing about type selection.

### Memory card polish (light-touch, author's discretion)

User hasn't seen the filled state yet and deferred to us. Keep changes small and low-risk:

- Replace the uppercase two-column `GOAL | date` header with a single inline pill-tag (icon + label) matching the tab-pill aesthetic at smaller scale. Move the date to a compact caption under the body text.
- Keep the circular icon badge but tighten its margin to the text column.
- Leave swipe-to-delete unchanged.
- No color changes beyond what the existing `theme.accent` already drives.

If any of this turns out to regress the filled view during implementation, revert the card tweaks and ship only the empty-state + composer changes. Cards are not the blocking win here.

## Acceptance criteria

1. With zero items on any advisor tab, the empty state copy renders at the **same on-screen vertical position** across Chat, Nudges, and Memories (measured from the top of the advisor content area).
2. The empty state overlay does not intercept taps on the memories composer, chat composer, or type chips.
3. The empty state is hidden while loading and while an error state is displayed.
4. Chat and Memories render the same composer component. Diff between their invocations is limited to `placeholder`, `submitIcon`, `maxLength`, and `onSubmit`.
5. Memories filled state (≥1 goal or note) renders without visual regression vs. current behaviour; swipe-to-delete still works; Goal/Note chips still select type.
6. `npx expo lint` passes; no new TypeScript errors.

## Risks / open items

- `MemoryList` currently wraps the form + list in a single `View` with `paddingTop`. Moving empty state to an absolute overlay means the list below can be empty-but-scrollable without the overlay feeling detached from the form. Mitigation: overlay's vertical anchor is the content area, not the list; visually this lines up with the chat baseline by design.
- `AdvisorComposer` needs to live in `mobile/components/advisor/` (not `mobile/components/ui/`) because it carries advisor-specific concerns (send/add icon choice, pill+glow styling tuned for this feature). Revisit only if a third consumer shows up.
- Card tweaks are the softest goal. Easy to revert without affecting the other two.

## Phasing

Work in a worktree (`use git worktree`). Single branch, single PR. Keep commits atomic:

1. Add `AdvisorComposer`; switch `ChatView` to use it (no behaviour change).
2. Add empty-state overlay pattern; convert Chat, Nudges, Memories.
3. Switch `AddMemoryForm` input+button to `AdvisorComposer`; keep type chips.
4. Light memory card polish (optional, revert on regression).

Verify after each phase: `cd mobile && npx expo lint` + visual check on iOS simulator.
