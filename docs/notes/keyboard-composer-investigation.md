# Chat composer stays below the keyboard — root cause + fix

**Status:** proposed fix, 4th attempt candidate
**Files:** `mobile/components/advisor/ChatView.tsx`, `mobile/components/advisor/MemoryList.tsx`, `mobile/hooks/useAdvisorComposerLayout.ts`, `mobile/components/advisor/AdvisorComposer.tsx`
**Library:** `react-native-keyboard-controller@1.20.7`

## Root cause (one paragraph)

`react-native-keyboard-controller`'s `KeyboardAvoidingView` with `behavior="padding"` computes its lift as `paddingBottom = frame.y + frame.height - (screenHeight - keyboardHeight - keyboardVerticalOffset)` (see `node_modules/react-native-keyboard-controller/src/components/KeyboardAvoidingView/index.tsx:101-116`). `frame` comes from the KAV's own `onLayout`, so `frame.y` is **parent-relative** (0 in our layout, because the KAV is the root of `ChatView`, which is rendered inside the content slot of `<View style={styles.content}>` in `app/advisor/index.tsx`). That means `keyboardVerticalOffset` must equal the absolute screen-Y of the KAV's top edge — i.e. the total of every piece of chrome above it. The current hook passes only the react-navigation header height (~91 px on a 15 Pro). It omits the advisor SubTabs row (row styles in `app/advisor/index.tsx:119-127`: 8 top margin + 12 top pad + 44 min touch target + 12 bottom pad + 4 bottom margin ≈ **80 px**) and the hairline separator on `styles.content`. Because the offset under-reports by ~80 px, KAV's `paddingBottom` is ~80 px too small and the composer sits ~80 px below the keyboard — exactly the reported symptom. The library's own chat guide ("Why general-purpose components fall short") explicitly recommends NOT using `KeyboardAvoidingView` for chat.

## The exact change to make

Drop `KeyboardAvoidingView` from the advisor composers. Wrap the shared `AdvisorComposer` in `KeyboardStickyView` instead — it uses the native keyboard frame directly (`transform: [{ translateY: -keyboardHeight }]`) and is immune to any tree-structure drift above it.

### File 1 — `mobile/components/advisor/AdvisorComposer.tsx`

Change the outer `<View>` to `KeyboardStickyView`. The composer always knows its own keyboard behavior regardless of who mounts it.

```tsx
// Top of file
import { KeyboardStickyView } from "react-native-keyboard-controller";

// In the JSX root — replace the outer <View style={...}> with:
<KeyboardStickyView
  style={[
    styles.bar,
    separator && styles.barSeparator,
    bottomPadding !== undefined && { paddingBottom: bottomPadding },
  ]}
  // closed: 0 — resting position tracks natural layout (flex column bottom).
  // opened: 0 — when keyboard is up, sticky view already translates by
  // -keyboardHeight via its internal `height` value; no extra offset is
  // needed because the TextInput is what the keyboard opens on top of.
  offset={{ closed: 0, opened: 0 }}
>
  <TextInput ... />
  <Pressable ... />
</KeyboardStickyView>
```

The `AdvisorComposer` currently owns its own `bottomPadding` calc (floating tab bar + safe-area). That stays — `KeyboardStickyView` wraps its children, applies our style, and only touches `transform`. The inner `TextInput`/`Pressable` remain siblings.

### File 2 — `mobile/components/advisor/ChatView.tsx`

Remove `KeyboardAvoidingView`. The composer handles itself now.

```tsx
// Delete the import:
-import { KeyboardAvoidingView } from "react-native-keyboard-controller";

// Replace the JSX root:
-<KeyboardAvoidingView
-  style={styles.container}
-  behavior="padding"
-  keyboardVerticalOffset={keyboardVerticalOffset}
-  enabled={Platform.OS !== "web"}
->
+<View style={styles.container}>
   <View style={styles.listArea}>
     <FlatList ... />
   </View>
   {/* error banner */}
   <AdvisorComposer ... bottomPadding={inputBottomPadding} separator />
   <PaywallModal ... />
-</KeyboardAvoidingView>
+</View>
```

Also: drop `Platform` import if no longer used (check after edits), and drop `keyboardVerticalOffset` from the `useAdvisorComposerLayout()` destructure — we only need `inputBottomPadding` now.

### File 3 — `mobile/components/advisor/MemoryList.tsx`

Same change as ChatView — replace both `KeyboardAvoidingView` wrappers (initial-loading branch + main branch) with a plain `<View style={styles.container}>`. Drop the `keyboardVerticalOffset` destructure.

### File 4 — `mobile/hooks/useAdvisorComposerLayout.ts`

`keyboardVerticalOffset` is no longer needed. Two options:
- (a) **Preferred**: remove it from the returned shape. Simpler. The hook is internal — only ChatView and MemoryList consume it.
- (b) If we want to keep the name for migration safety, return `0`. Not recommended; dead code is worse than a rename.

Take option (a): delete `keyboardVerticalOffset` from the `AdvisorComposerLayout` interface and from the return object. Delete `HeaderHeightContext` + `useContext` imports if no other consumer remains (they won't).

### List content padding when keyboard is open

When the composer translates up, it may cover the bottom messages. Two belt-and-suspenders fixes (both cheap, pick both):

1. **ChatView** — in the existing `useEffect` that auto-scrolls on new messages, also subscribe to `Keyboard` `keyboardDidShow` and call `listRef.current?.scrollToEnd({ animated: true })`. Then the latest message stays visible.
2. **ChatView `listContent` style** — keep `paddingVertical: THEME.spacing.md`. The FlatList is still inside `listArea` (flex: 1) and shrinks to fit between the sub-tabs and the composer. Since the composer translates up via `transform` (not layout), the FlatList does NOT automatically shrink when the keyboard opens — it keeps its pre-keyboard height, so the last message that was at the bottom of the pre-keyboard composer position is still at the bottom of the list (now obscured by the lifted composer). Adding a keyboard-aware `paddingBottom` via a `useKeyboardState` hook avoids this. Prefer approach (1) for simplicity — scrolling to end on keyboard open keeps the newest message in view, which is what a chat user expects anyway.

## Why it works

`KeyboardStickyView` resolves its `translateY` from the `KeyboardProvider`'s `animated.height` (see `node_modules/react-native-keyboard-controller/src/components/KeyboardStickyView/index.tsx:53-66` + `src/animated.tsx:118` — `height` is `Animated.multiply(rawHeight, -1)`). `rawHeight` is pushed from the native `KeyboardControllerView` in real time (iOS UIKeyboard*Notification, Android WindowInsets). No layout measurement, no screen-Y guessing, no offset arithmetic. The composer translates **exactly** by the keyboard's visible height, flush with its top edge. The library's maintainer recommends this pattern in the official chat-app guide (see context7 output under "Chat Screen Implementation with Keyboard Controller").

This also eliminates the entire class of bugs the last three PRs have been chasing:
- PR #128 (hardcoded 90) — brittle constant.
- PR #129 (react-native-keyboard-controller KAV) — needs correct offset.
- PR #130 (behavior switch) — still needs correct offset.
- Every future wrapper we add between the advisor screen and the composer would re-break the math. With `KeyboardStickyView`, there is no math.

## Things to watch for on verification

1. **Native rebuild required.** `KeyboardProvider` is already in `app/_layout.tsx` and the pod is installed, so `npx expo start` (JS reload) should be enough. If the keyboard height animates to 0 or the composer doesn't move at all, `npx expo run:ios` to rebuild. Confirm with `KeyboardProvider` not logging its "Couldn't find real values" dev warning.
2. **iPhone variants.** Test SE (no notch, small kb), 15 Pro Max (Dynamic Island + large kb), 15 Pro (Dynamic Island). All three should see the composer land flush with the keyboard top.
3. **Dark keyboard / Emoji keyboard / Autocomplete accessory.** The keyboard height reported by the native module includes any accessory view in the standard iOS chrome but NOT QuickType predictive row if `spellCheck=false`. Our `AdvisorComposer` doesn't disable it, so the full height is reported and the composer sits above QuickType correctly.
4. **Tab bar fade-out.** `inputBottomPadding` drops to `THEME.spacing.sm` when `isKeyboardVisible` via the existing hook — unchanged. The composer's inner `paddingBottom` shrinks as the keyboard opens, so when it translates up there's no awkward home-indicator gap between composer and keyboard.
5. **Auto-scroll on keyboard open.** Verify with a scrolled-back chat (older message in view) that tapping the composer scrolls to end so the latest assistant reply isn't hidden behind the lifted composer.
6. **MemoryList Goals/Notes swap.** `key={activeTab}` on the composer is preserved — the sticky view remounts too, which is fine (it re-subscribes to the keyboard context cheaply).
7. **Android.** Android's default soft-input mode under Expo is `adjustResize`, so the window shrinks and the sibling `AdvisorComposer` moves up via native layout. `KeyboardStickyView` then adds `translateY: -keyboardHeight` ON TOP of that, which would double-compensate. The library-recommended fix is to call `useResizeMode()` (which `KeyboardStickyView` does internally via `useKeyboardAnimation`) — on Android it sets `adjustResize` but the hook's `height` value is still driven by the `WindowInsets.ime` dispatch, which is 0 until resize, then updates. Empirically this is fine because the library is designed for both platforms. If Android doubles up in practice, the fix is to set `enabled={Platform.OS !== "android"}` on the sticky view and rely on `adjustResize`. Verify on an Android emulator before merging.
8. **Dev warning check.** After the fix, `Keyboard.addListener("keyboardWillShow", ...)` usage in `useAdvisorComposerLayout` still fires for the `isKeyboardVisible` bool that drives `inputBottomPadding`. That's unchanged.

## Answers to the investigation questions

**Q1 — KAV math (library source).**
`src/components/KeyboardAvoidingView/index.tsx:101-116, 167-168`: `keyboardY = screenHeight - heightWhenOpened - keyboardVerticalOffset`, `relativeKeyboardHeight = max(frame.y + frame.height - keyboardY, 0)`, applied as `paddingBottom` when `behavior="padding"`. `frame` is the KAV's own onLayout frame — **parent-relative**. Stock RN KAV uses `this._frame` from `UIManager.measureInWindow` which is **screen-relative**; that's the semantic difference that makes the offset value mean different things between the two.

**Q2 — `HeaderHeightContext` in this screen.**
Populated correctly by react-navigation's `Screen` component (`node_modules/@react-navigation/elements/src/Screen.tsx:97-101`). The provider wraps the screen body, so `useContext(HeaderHeightContext)` inside `ChatView` returns the live tab-nav header height (~91 px on iPhone 15 Pro). That value is correct FOR THE HEADER, but `keyboardVerticalOffset` needs header + sub-tab row + any other chrome — that's the gap.

**Q3 — Extra components between screen and KAV.**
`app/advisor/index.tsx` renders `<View style={styles.tabBar}>` (the SubTabs row, ~80 px) and `<View style={styles.content}>` (flex: 1, hairline top border) before `<ChatView />`. The KAV is inside `styles.content`, so everything above `styles.content` (header + tabBar) contributes to the screen-Y offset that KAV's `frame.y = 0` doesn't encode. `OfflineBanner` in `app/_layout.tsx` is absolutely positioned per its component (no layout flow impact), and the outer `<View style={{ flex: 1, backgroundColor }}>` is a zero-Y wrapper so it doesn't add to the offset.

**Q4 — Library's own recommendation.**
The library's 1.21 guide (`docs/versioned_docs/version-1.21.0/guides/building-chat-app.mdx`) is explicit: *"You might be tempted to reach for `KeyboardAvoidingView` [...] while these components work well for forms [...], they weren't designed for the unique demands of a chat interface"* — citing frame drops, first-message rendering, double-scroll on interactive dismissal, and unnecessary animation. The recommended pattern is `KeyboardChatScrollView` (not yet in our 1.20.7) or at minimum `KeyboardStickyView` wrapping the composer. We're on 1.20.7 so `KeyboardStickyView` is the right choice today; we can upgrade to 1.21+ later if we want `KeyboardChatScrollView`.

**Q5 — Custom tab bar / header impact on Y position.**
The tab navigator's `<Tabs>` renders via `@react-navigation/bottom-tabs`'s `BottomTabView`, which calls `<Screen>` from `@react-navigation/elements` per-screen. `Screen.tsx:77-103` shows the header as a flex-flow `<View>` (not absolute unless `headerTransparent: true`), then the content as another `<View style={styles.content}>` BELOW it. Our `(tabs)/_layout.tsx` does NOT set `headerTransparent`, so the screen body's Y starts at `headerHeight`. `useHeaderHeight` returns that value correctly — but only that value. Any chrome INSIDE the screen (SubTabs) is below the content's Y=0 and must be added manually. That's the missing ~80 px.

**Q6 — Is the miscompensation calculable?**
Yes. Header ≈ 91 px, SubTabs row ≈ 80 px, hairline ≈ 0.33 px, total ~171 px. KAV is getting 91, needs 171, so it lifts the composer 80 px short. Matches the symptom. Rather than patch a brittle sum, replace with `KeyboardStickyView` which doesn't need the sum.
