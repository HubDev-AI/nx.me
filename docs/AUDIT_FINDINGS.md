# NXME Mobile App Audit Findings
**Date:** 2026-03-23
**Total Issues:** 58

## Critical (4)
1. **PaywallModal.tsx:226,277** — TODO: Stripe integration incomplete, uses Checkout Session URL not PaymentIntent
2. **notifications.ts:17** — Push token registration not wired (backend endpoint missing)
3. **blocked-users.tsx:84-92** — Blocked user profiles show UUID not names (backend now fixed, verify frontend uses new fields)
4. **_layout.tsx:117** — TypeScript `as any` cast on AnimatedStyle losing type safety

## Major - Functionality (10)
1. **index.tsx:231** — FlatList ref cast `as any`
2. **create.tsx:173** — router.push cast `as any`
3. **DropdownMenu.tsx:171** — Icon name cast without validation
4. **RadialMenu.tsx:414** — Same icon cast issue
5. **FeedCard.tsx:125** — Unsafe `(global as any).innerWidth`, should use Dimensions API
6. **CommentInput.tsx:173** — @ts-ignore for web outlineStyle
7. **AuthInput.tsx:142** — Same @ts-ignore issue
8. **subscription.tsx:287** — `theme.accentMuted` may not be defined
9. **api.ts** — Token refresh uses module-level variables (race condition risk)
10. **result/[jobId].tsx:88** — Hard-coded setTimeout for CTA visibility

## Major - Navigation (3)
1. **advisor tab** — `href: "/advisor"` + `name="advisor"` creates ambiguity
2. **card/[username].tsx:51** — Username regex doesn't match AUTH_VALIDATION constant
3. **blocked-users.tsx** — Endpoint URL may not match backend pagination

## Major - UI/UX (5)
1. **_layout.tsx:174** — Tab bar `position: absolute` may overlap content on some screens
2. **CommentsSheet** — No keyboard avoidance on Android
3. **Alert dialogs** — No accessibility attributes
4. **No loading skeleton** for profile first load
5. **No character count** on comment input

## Major - API/Data (5)
1. **Coming soon features** — UI shows them but no backend
2. **blocked-users.tsx:79-92** — Profile resolution incomplete
3. **Multiple `.catch(() => {})** — Silent error swallowing (12+ locations)
4. **subscription.tsx** — `theme.accentMuted` not defined on theme context
5. **Advisor components** — No pagination, load everything at once

## Minor (15)
1. No image caching/optimization
2. Missing error boundary at app root
3. No analytics tracking
4. Inconsistent error messages
5. Feed dropdown may render off-screen
6. Settings version fallback
7. No advisor empty state guidance
8. Tab bar scroll-to-top doesn't sync header
9. Onboarding has no error state for entitlement fetch
10. Multiple hardcoded colors outside THEME
11. ReactionButton animations not memoized
12. No max-length visual feedback on comment input
13. No alt text on many images
14. Color contrast issues on overlays
15. Tab order not optimized for screen readers

## Technical Debt (8)
1. Consolidate all colors to THEME (some still inline)
2. Centralized error handling (useApiError hook)
3. Memoize animation components
4. Paginate advisor components
5. Add expo-image with cache + blurhash
6. Error boundary at app root
7. Analytics integration
8. Header sync with scroll position

## Not Implemented Yet
1. Push notification device registration
2. Native Stripe payment sheet (uses web redirect)
3. Refund API endpoint (backend doesn't expose it)
4. Token refresh endpoint (backend doesn't expose it)
5. Password reset flow
6. Terms of service / privacy policy links
