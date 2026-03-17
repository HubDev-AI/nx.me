# UI/UX Review
- Date: 2026-03-17
- Scope: mobile/**/*.tsx
- Auditor: AccessibilityAuditor
- Standard: WCAG 2.2 Level AA + React Native platform guidelines

## Findings

### Accessibility (Critical)

**A-1. Hardcoded `#F87171` error color used outside design tokens**
- WCAG Criterion: 1.4.3 Contrast (Minimum) (Level AA)
- Severity: Serious
- Location: `app/(auth)/login.tsx:210,353`, `app/(auth)/signup.tsx:376,559`
- Evidence: `color="#F87171"` (error icon and error text) is used directly instead of importing `ERROR_DARK` from color tokens. The color is the same value, but inline literals bypass token governance and risk divergence over time.
- Recommended Fix: Replace all inline `"#F87171"` with `ERROR_DARK` from `constants/colors.ts`.

**A-2. Tab bar labels hidden -- icon-only tabs without accessibilityLabel**
- WCAG Criterion: 1.1.1 Non-text Content (Level A)
- Severity: Serious
- Location: `app/(tabs)/_layout.tsx:46` -- `tabBarShowLabel: false`
- Evidence: Tab labels are hidden (`tabBarShowLabel: false`). While Expo Router's `<Tabs.Screen>` provides a `title` that maps to the screen's accessibility label, the individual `TabIcon` components rendered via `tabBarIcon` do not carry an `accessibilityLabel`. VoiceOver users navigating the tab bar rely on the system-provided tab button label derived from `title`, which is correctly set ("Home", "Search", etc.), so the core navigation works. However, the custom `TabIcon` view itself (the `View` wrapping the strip + icon) should be marked `accessibilityElementsHidden` or `importantForAccessibility="no"` to avoid VoiceOver announcing a redundant unlabeled element.
- Recommended Fix: Add `accessibilityElementsHidden={true}` (iOS) / `importantForAccessibility="no"` (Android) to the `<View style={styles.iconContainer}>` in `TabIcon`, or use `accessible={false}`.

**A-3. Onboarding "Not now" skip link is a Text with onPress, not a Pressable**
- WCAG Criterion: 4.1.2 Name, Role, Value (Level A)
- Severity: Serious
- Location: `app/onboarding.tsx:190-198`
- Evidence: `<Text ... onPress={() => setPushCompleted(true)} accessibilityRole="button">Not now</Text>`. Using `onPress` on `<Text>` is semantically incorrect for an interactive element. While `accessibilityRole="button"` is set (good), the component does not get native press feedback, focus ring, or `disabled` state management. The touch target is adequate (minHeight: 44), but keyboard/switch-control users may not receive proper button semantics on all platforms.
- Recommended Fix: Replace with `<Pressable>` wrapping a `<Text>`, matching the pattern used everywhere else in the codebase.

**A-4. Missing `accessibilityRole="alert"` on error banners in several components**
- WCAG Criterion: 4.1.3 Status Messages (Level AA)
- Severity: Moderate
- Location: `components/advisor/ChatView.tsx:291-303` (error banner), `components/comments/CommentsSheet.tsx:294-299` (post error toast), `components/paywall/PaywallModal.tsx:440-445` (purchase error banner)
- Evidence: Error banners that appear dynamically (without focus change) lack `accessibilityRole="alert"` or `accessibilityLiveRegion="assertive"`. Screen reader users will not be notified when these error messages appear.
- Recommended Fix: Add `accessibilityRole="alert"` (or `accessibilityLiveRegion="assertive"` on Android) to the error banner wrapper `<View>`.

**A-5. FeedCard images lack explicit width/height for accessibility tree**
- WCAG Criterion: 1.1.1 Non-text Content (Level A)
- Severity: Minor
- Location: `components/feed/FeedCard.tsx:146-169`
- Evidence: Before/after images have `accessibilityLabel="Before photo"` and `accessibilityLabel="After photo"` (good), but they are generic. The label does not include the post author's name, so a screen reader user viewing a list of cards hears "Before photo" repeatedly with no context about whose photo it is.
- Recommended Fix: Include the post username in the image label: `accessibilityLabel={\`Before photo by ${post.username}\`}`.

**A-6. GlowUpGrid cells have generic accessibility label**
- WCAG Criterion: 1.1.1 Non-text Content (Level A)
- Severity: Moderate
- Location: `components/profile/GlowUpGrid.tsx:139`
- Evidence: Every cell says `accessibilityLabel="Glow-up transformation"` -- no indication of which transformation, date, or index. Screen reader users navigating the grid hear identical labels.
- Recommended Fix: Include a date or ordinal: `accessibilityLabel={\`Glow-up transformation from ${item.created_at}\`}`.

**A-7. Lightbox close button touch target is 40x40 (below 44pt minimum)**
- WCAG Criterion: 2.5.8 Target Size (Minimum) (Level AA, WCAG 2.2)
- Severity: Serious
- Location: `components/result/BeforeAfterReveal.tsx:316-318`
- Evidence: `lightboxClose` style has `width: 40, height: 40`. The `hitSlop={12}` partially compensates but the visual target itself is below the 44pt minimum, and `hitSlop` does not count as target size under WCAG 2.2 Success Criterion 2.5.8.
- Recommended Fix: Increase to `width: 44, height: 44`.

**A-8. Advisor tab bar uses custom tabs without `tablist`/`tab` container role**
- WCAG Criterion: 4.1.2 Name, Role, Value (Level A)
- Severity: Moderate
- Location: `app/advisor/index.tsx:77`
- Evidence: The tab bar is a plain `<View>` without `accessibilityRole="tablist"`. The individual tabs correctly use `accessibilityRole="tab"` and `accessibilityState={{ selected }}`, but the container lacks the `tablist` role, which prevents assistive technologies from announcing the group as a tablist. (Compare with `SortTabs` which does have `accessibilityRole="tablist"` on its container -- good pattern.)
- Recommended Fix: Add `accessibilityRole="tablist"` to the `<View style={styles.tabBar}>`.

**A-9. PaywallModal does not trap focus or return focus on close**
- WCAG Criterion: 2.4.3 Focus Order (Level A)
- Severity: Serious
- Location: `components/paywall/PaywallModal.tsx`
- Evidence: The modal uses React Native's `<Modal>`, which on iOS does provide some focus containment. However, there is no explicit focus management: when the modal opens, focus does not programmatically move to the sheet content (e.g., the header title or close button). When the modal closes, focus does not return to the trigger element. This is a common React Native limitation but must be addressed for VoiceOver/TalkBack compliance.
- Recommended Fix: Use `AccessibilityInfo.announceForAccessibility()` when the modal opens, and/or set focus to the close button via a ref. On close, the calling component should restore focus to the trigger.

**A-10. CommentsSheet and EditProfileSheet share the same focus-on-open issue**
- Same as A-9 above. Applies to `CommentsSheet` and `EditProfileSheet`.

### Touch & Interaction (Critical)

**T-1. Memory type chips below 44pt minimum touch target**
- Severity: Serious
- Location: `components/advisor/MemoryList.tsx:352-358` (formStyles.typeChip)
- Evidence: `minHeight: 32, paddingVertical: 6`. The chip height is 32dp, well below the 44pt minimum. No `hitSlop` is applied.
- Recommended Fix: Increase `minHeight` to 44, or add `hitSlop={{ top: 6, bottom: 6 }}` and increase padding.

**T-2. NudgeCard icon container is 36x36 -- not a standalone target but contributes to mispress risk**
- Severity: Minor
- Location: `components/advisor/NudgeCard.tsx:122-130`
- Evidence: The icon container is 36x36. The entire card is the pressable, so the card itself exceeds 44pt (the card has minHeight: 44 plus padding). This is acceptable since the icon is not an independent target. No action required, noting for completeness.

**T-3. Spacing between adjacent sort tabs is only 8dp**
- Severity: Moderate
- Location: `components/feed/SortTabs.tsx:88` -- `gap: 8`
- Evidence: The gap between sort tab pills is 8dp, which meets the 8dp minimum spacing requirement. However, the tabs are horizontally adjacent with rounded edges, so the actual inter-target gap may be slightly less than 8dp visually. Acceptable but borderline.

### Performance (High)

**P-1. FeedCard entrance animation runs on every re-render when `reactedPostIds` changes**
- Severity: Moderate
- Location: `components/feed/FeedCard.tsx:60-79`
- Evidence: The entrance animation `useEffect` depends on `[fadeAnim, translateAnim, index]`. While `fadeAnim` and `translateAnim` are refs (stable), the animation runs on mount which is correct. However, `renderItem` in the parent creates a new closure every time `reactedPostIds` changes (line 94-106), causing FeedCard to re-render. The animation values persist due to `useRef`, so re-animation does not occur, but the component tree is re-rendered unnecessarily.
- Recommended Fix: Memoize `FeedCard` with `React.memo` and pass `hasReacted` as a primitive prop (already done). The `reactedPostIds` set in the dependency of `renderItem` causes the callback to change, but since `hasReacted` is derived before passing, `React.memo` on `FeedCard` would prevent re-renders when only `reactedPostIds` changes for other posts.

**P-2. ChatView skeleton uses percentage widths cast to number incorrectly**
- Severity: Minor
- Location: `components/advisor/ChatView.tsx:56`
- Evidence: `{ width: \`${width * 80}%\` as unknown as number }` -- this is a type hack that will produce a string like `"48%"` cast to `number`, which may cause layout warnings or undefined behavior at runtime.
- Recommended Fix: Use `Dimensions.get('window').width * 0.48` or similar numeric calculation instead of percentage string casting.

**P-3. FlatList in GlowUpGrid has scrollEnabled={false} inside a ScrollView**
- Severity: Moderate
- Location: `components/profile/GlowUpGrid.tsx:118`, `app/(tabs)/profile.tsx:161-187`
- Evidence: `GlowUpGrid` uses a `FlatList` with `scrollEnabled={false}` nested inside a `ScrollView` in `ProfileScreen`. This disables FlatList's virtualization benefit -- all items are rendered at once since the FlatList never scrolls. For large histories, this will cause performance degradation.
- Recommended Fix: Either replace the outer `ScrollView` with a single `FlatList` using `ListHeaderComponent` for the profile header, or use `FlashList` / `SectionList`.

**P-4. Duplicate `formatTimeAgo` utility defined in two files**
- Severity: Minor
- Location: `components/feed/FeedCard.tsx:209-224`, `components/comments/CommentItem.tsx:82-98`
- Evidence: Identical `formatTimeAgo` function duplicated in two files. This is a code hygiene issue per the project's "no duplication" rule.
- Recommended Fix: Extract to a shared `lib/format.ts` utility.

**P-5. `NudgeFeed` and `MemoryList` use inline `ItemSeparatorComponent` arrow function**
- Severity: Minor
- Location: `components/advisor/NudgeFeed.tsx:243`, `components/advisor/MemoryList.tsx:593`
- Evidence: `ItemSeparatorComponent={() => <View style={styles.separator} />}` creates a new component reference on every render, causing unnecessary re-renders of separators.
- Recommended Fix: Extract to a named component: `const Separator = () => <View style={styles.separator} />;` outside the render.

### Style Consistency (High)

**S-1. Extensive use of hardcoded hex values outside token system**
- Severity: Serious
- Evidence: Across the codebase, `"#FFFFFF"`, `"#000000"`, `"#F87171"`, `"#4285F4"`, `"#DADCE0"`, `"#1F1F1F"`, `"#4ADE80"`, `"#F8F8F8"` are used as inline literals in approximately 60+ locations. While `#FFFFFF` (white text on CTA backgrounds) could be argued as universal, many of these should be design tokens.
- Specific concerns:
  - `"#F87171"` is `ERROR_DARK` -- should use the token (appears in login.tsx, signup.tsx)
  - `"#4ADE80"` is `SUCCESS_DARK` -- should use the token (appears in PaywallModal.tsx)
  - `"#FFFFFF"` for text-on-dark should have a token like `TEXT_ON_CTA` or `TEXT_INVERSE`
  - `"#4285F4"` (Google blue), `"#DADCE0"` (Google border), `"#1F1F1F"` (Google text) -- social button brand colors should be in a `SOCIAL_BRAND` token group
  - `"#000000"` for Apple button and scrim backdrops should use a token
- Recommended Fix: Add to `constants/colors.ts`:
  ```ts
  export const TEXT_INVERSE = "#FFFFFF";
  export const SCRIM_BG = "#000000";
  export const SOCIAL_GOOGLE_BLUE = "#4285F4";
  export const SOCIAL_GOOGLE_BORDER = "#DADCE0";
  export const SOCIAL_GOOGLE_TEXT = "#1F1F1F";
  ```

**S-2. Inline rgba values not centralized as tokens**
- Severity: Moderate
- Evidence: 18+ inline `rgba(...)` values across components. Some are already tokenized in `colors.ts` (FEED_DIVIDER, BEFORE_OVERLAY, etc.), but many are not:
  - `"rgba(248,113,113,0.1)"` (error background) -- used in 5 files
  - `"rgba(244,63,94,0.08)"` (coral tint) -- used in 4 files
  - `"rgba(244,63,94,0.12)"` (coral tint stronger) -- SortTabs
  - `"rgba(255,255,255,0.05)"` (skeleton shimmer) -- NudgeFeed, MemoryList
  - `"rgba(74,222,128,0.1)"` (success background) -- PaywallModal
  - `"rgba(0,0,0,0.6)"` and `"rgba(0,0,0,0.95)"` (overlays) -- BeforeAfterReveal
- Recommended Fix: Add these as named tokens in `colors.ts`.

**S-3. PremiumCard defines its own CTA colors outside the design token system**
- Severity: Moderate
- Location: `components/paywall/PremiumCard.tsx:31-32`
- Evidence: `const CTA_SUBSCRIBE = "#E11D48"` and `const CTA_SUBSCRIBE_PRESSED = "#BE123C"` are defined locally. These values happen to match `COLORS.after[600]` and `COLORS.after[700]` respectively, but are not imported from the token system.
- Recommended Fix: Use `COLORS.after[600]` and `COLORS.after[700]` from the token file.

**S-4. Social login button styling duplicated between login.tsx, signup.tsx, and SocialLoginButtons.tsx**
- Severity: Moderate
- Location: `app/(auth)/login.tsx:374-408`, `app/(auth)/signup.tsx:580-614`, `components/auth/SocialLoginButtons.tsx:97-131`
- Evidence: The social button styles (googleButton, appleButton, socialButton, etc.) are defined identically in three files. The `SocialLoginButtons` component exists as a reusable component but is NOT used in either login.tsx or signup.tsx -- each screen implements its own inline social buttons.
- Recommended Fix: Refactor login.tsx and signup.tsx to use the `SocialLoginButtons` shared component, eliminating ~70 lines of duplicated styles.

**S-5. Icon family consistency is maintained (Ionicons throughout) -- POSITIVE**
- All icons use `@expo/vector-icons` Ionicons family consistently. No mixing of icon families.

### Layout (High)

**L-1. Root layout uses `<View>` without SafeAreaView -- relies on child screens**
- Severity: Moderate
- Location: `app/_layout.tsx:81`
- Evidence: `<View style={{ flex: 1, backgroundColor: BG_PAGE }}>` -- the root layout does not use `SafeAreaView`. Safe area insets are handled individually by each screen that needs them (profile.tsx uses `useSafeAreaInsets`, upload.tsx uses `SafeAreaView edges=["bottom"]`, etc.). This is an acceptable pattern with Expo Router, but it means any screen that forgets to handle safe areas will have content under the notch/home indicator.
- Screens that correctly handle safe areas: profile, upload, result, card, onboarding, login (via insets), signup (via insets), advisor (via insets).
- Screens that may be missing safe area handling: search.tsx, notifications.tsx (placeholder screens with centered content -- likely OK since they use flex centering, but header overlap is possible on devices with large notches).

**L-2. 8dp spacing rhythm is well maintained -- POSITIVE**
- Evidence: The codebase consistently uses `SPACING = 8` constant and multiples thereof (8, 16, 24, 32, 48). Padding and gap values align to the 8dp grid throughout.

**L-3. No horizontal scroll detected -- POSITIVE**
- No component uses horizontal ScrollView or horizontal FlatList. All layouts are vertical-scrolling or static.

**L-4. Bottom tab bar has 5 items (Home, Search, Create, Notifications, Profile) -- POSITIVE**
- Exactly 5 items, meeting the maximum recommendation.

### Animation (Medium)

**AN-1. BeforeAfterReveal and SuggestionPills correctly respect `prefers-reduced-motion` -- POSITIVE**
- Both components check `AccessibilityInfo.isReduceMotionEnabled()` and fall back to simple `FadeIn.duration(150)` when reduced motion is enabled.

**AN-2. FeedCard entrance animation does NOT respect reduced motion**
- Severity: Moderate
- Location: `components/feed/FeedCard.tsx:60-78`
- Evidence: The stagger entrance animation (fadeAnim + translateAnim, 300ms duration) runs unconditionally with no `isReduceMotionEnabled` check.
- Recommended Fix: Check `AccessibilityInfo.isReduceMotionEnabled()` and skip the stagger animation (set values immediately to final state) when enabled.

**AN-3. TypingIndicator animation does not respect reduced motion**
- Severity: Minor
- Location: `components/advisor/TypingIndicator.tsx:17-40`
- Evidence: The bouncing dot animation runs in a loop unconditionally. Should use a static "..." display when reduced motion is enabled.

**AN-4. Animation durations are within recommended range -- POSITIVE**
- All animation durations fall within 150-300ms: AuthButton (150ms), FeedCard (300ms), PaywallModal (200-300ms), CommentsSheet (200-300ms), SuggestionPills (250ms), BeforeAfterReveal (150-300ms). The TypingIndicator dots use 400ms per cycle, which is acceptable for a looping indicator.

**AN-5. Animations use transform and opacity only (native driver compatible) -- POSITIVE**
- All `Animated.timing` calls use `useNativeDriver: true`, and animations are limited to `opacity`, `scale`, `translateX`, `translateY`. No layout property animations.

### Forms (Medium)

**F-1. AuthInput uses visible labels above fields -- POSITIVE**
- All form fields in login.tsx, signup.tsx, and EditProfileSheet use visible `<Text>` labels above inputs, not placeholder-only labels.

**F-2. Error messages are placed below fields -- POSITIVE**
- `AuthInput` renders errors below the input with an icon + text pattern.

**F-3. KeyboardAvoidingView is used in all form screens -- POSITIVE**
- login.tsx, signup.tsx, CommentsSheet, ChatView, and EditProfileSheet all use `KeyboardAvoidingView` with platform-appropriate behavior.

**F-4. CommentInput uses placeholder-only label pattern**
- Severity: Moderate
- Location: `components/comments/CommentInput.tsx:67`
- Evidence: `placeholder="Add a comment..."` with `accessibilityLabel="Comment input"`. While the accessibility label is present for screen readers, there is no visible label for sighted users. This is acceptable for a chat-style input (convention in messaging UIs), but strictly speaking fails WCAG 3.3.2 Labels or Instructions for form inputs.
- Note: This is an industry-standard pattern for comment/chat inputs and the risk is low.

**F-5. ChatView message input uses placeholder-only label**
- Same pattern as F-4. `placeholder="Message Ada..."` with `accessibilityLabel="Message input"`. Acceptable for chat UI convention.

**F-6. Memory add form input uses placeholder-only label**
- Severity: Minor
- Location: `components/advisor/MemoryList.tsx:301-314`
- Evidence: Dynamic placeholder based on selected type, with `accessibilityLabel="Memory content"`. No visible label. The type chip selector above provides some context.

### Navigation (High)

**N-1. Bottom nav has exactly 5 items -- POSITIVE**

**N-2. Deep linking supported via card/[username] route -- POSITIVE**
- Universal link handling is implemented. The `deep-link-guard.ts` rejects custom URI schemes.

**N-3. Back navigation is predictable -- POSITIVE**
- Auth screens use `Stack` navigation with system back button. Upload and result screens use Stack with header back. Modal sheets have close buttons.

**N-4. Advisor screen is not reachable from the tab bar**
- Severity: Moderate
- Location: `app/advisor/index.tsx` exists at route `/advisor`, but there is no tab or visible navigation entry point in the tab bar to reach it.
- Evidence: The advisor screen is a standalone route. Users must navigate to it programmatically or via deep link. There is no tab bar item, no profile screen link, and no create screen link pointing to `/advisor`.
- Recommended Fix: Either add a navigation entry point (button in profile, or replace one of the placeholder tabs), or document this as intentionally hidden behind a feature gate.

**N-5. No loading/splash transition from RootLayout to tabs**
- Severity: Minor
- Location: `app/_layout.tsx:71-73`
- Evidence: When `isReady` is false, the component returns `null`, causing a blank frame. The splash screen is shown over this, but there may be a brief flash between splash hide and first screen render depending on initialization speed. This is handled by `SplashScreen.hideAsync()` in `onLayoutReady`, which is the correct pattern.

## Pre-Delivery Checklist

- [ ] Extract `"#F87171"` to `ERROR_DARK` token in login.tsx and signup.tsx (A-1)
- [ ] Add `accessible={false}` to TabIcon container View (A-2)
- [ ] Replace onboarding "Not now" Text with Pressable wrapper (A-3)
- [ ] Add `accessibilityRole="alert"` to dynamic error banners in ChatView, CommentsSheet, PaywallModal (A-4)
- [ ] Add `accessibilityRole="tablist"` to Advisor tab bar container (A-8)
- [ ] Increase lightbox close button to 44x44 (A-7)
- [ ] Add reduced-motion check to FeedCard entrance animation (AN-2)
- [ ] Increase MemoryList type chip minHeight to 44 (T-1)
- [ ] Extract `formatTimeAgo` to shared utility (P-4)
- [ ] Refactor login.tsx and signup.tsx to use SocialLoginButtons component (S-4)
- [ ] Add missing design tokens for inline hex/rgba values (S-1, S-2)
- [ ] Use `COLORS.after[600]`/`[700]` in PremiumCard instead of local constants (S-3)
- [ ] Replace FlatList-in-ScrollView pattern in ProfileScreen with single FlatList (P-3)
- [ ] Fix ChatView skeleton percentage width type hack (P-2)
- [ ] Extract inline ItemSeparatorComponent to named components (P-5)

## Summary

| Category | Critical | Serious | Moderate | Minor | Positive |
|---|---|---|---|---|---|
| Accessibility | 0 | 5 | 3 | 2 | -- |
| Touch & Interaction | 0 | 1 | 1 | 1 | -- |
| Performance | 0 | 0 | 2 | 3 | -- |
| Style Consistency | 0 | 1 | 3 | 0 | 1 |
| Layout | 0 | 0 | 1 | 0 | 3 |
| Animation | 0 | 0 | 1 | 1 | 3 |
| Forms | 0 | 0 | 1 | 1 | 3 |
| Navigation | 0 | 0 | 1 | 1 | 3 |
| **Total** | **0** | **7** | **13** | **9** | **13** |

**Overall Assessment**: The codebase demonstrates strong foundational accessibility awareness -- most interactive elements have `accessibilityLabel`, `accessibilityRole`, and `accessibilityState`. Touch targets consistently use `minHeight: 44` or `MIN_TOUCH_TARGET`. The design token system is well-structured but undermined by widespread inline hex/rgba values. The most impactful issues to address before release are: (1) focus management in modal sheets for screen reader users, (2) missing reduced-motion support in FeedCard animations, (3) consolidating hardcoded color values into the token system, and (4) eliminating the duplicated SocialLoginButtons code. No critical blockers were found.
