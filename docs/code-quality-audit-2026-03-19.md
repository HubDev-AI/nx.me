# Code Quality Audit — 2026-03-19

**Scope:** All source code across backend (`app/`), mobile (`mobile/`), card-web (`card-web/src/`), and config files.

---

## Backend (Python)

### B-1 | HIGH | Hardcoded model costs in fal.ai adapter
**File:** `app/generation/adapters/falai.py:120-127`
```python
def _estimate_cost(self, model: str) -> float:
    costs = {
        "fal-ai/flux-pulid": 0.035,
        "fal-ai/flux-general/image-to-image": 0.026,
        "fal-ai/instantid": 0.020,
    }
    return costs.get(model, 0.035)
```
**Problem:** Business-critical cost values hardcoded in adapter. Violates coding-conventions.md Rule 3 (all config in env/app config). Cannot adjust costs per environment without redeploying.

### B-2 | HIGH | Fragile exception detection via string matching
**File:** `app/entitlement/trial_grantor.py:50-58`
```python
except Exception as exc:
    exc_str = str(exc).lower()
    if "unique" in exc_str or "duplicate" in exc_str or "23505" in exc_str:
        logger.info("trial_grant already applied...")
        return
```
**Problem:** Relies on error message content for idempotency detection. PostgreSQL error messages can vary by locale. Should catch specific exception type or inspect structured error code attribute.

### B-3 | MEDIUM | Hardcoded Sonnet model string not in config
**File:** `app/advisor/service.py:39`
```python
_MODEL_SONNET = "claude-3-5-sonnet-20241022"
```
**Problem:** Haiku model was moved to config (A-5 fix), but Sonnet is still hardcoded. Inconsistent — both should be in config.

### B-4 | MEDIUM | Non-atomic concurrent counter cleanup
**File:** `app/generation/worker.py:517-532`
```python
new_val = await redis.decr(concurrent_key)
if new_val <= 0:
    await redis.delete(concurrent_key)
else:
    await redis.expire(concurrent_key, ...)
```
**Problem:** DECR and conditional DELETE/EXPIRE are separate Redis calls. If worker crashes between DECR and DELETE, key stays in inconsistent state. Should use Lua script for atomicity.

### B-5 | MEDIUM | Tier ID duplication across two files
**Files:** `app/constants/tiers.py` and `app/config/tiers.py`
**Problem:** Both define identical tier UUIDs. If migrations change a tier ID, `constants/tiers.py` must be manually updated. No enforcement that they stay in sync.

### B-6 | LOW | Inconsistent repository return patterns
**Files:** `app/repositories/user_repo.py`, `app/repositories/job_repo.py`
**Problem:** Some methods return `dict | None`, others return `dict` with empty fallback, others return `int` with `0` fallback. Callers must remember which pattern each method uses.

### B-7 | LOW | Redundant truthiness check
**File:** `app/entitlement/service.py:130-133`
```python
has_subscription = bool(sub_result.data)
if has_subscription and sub_result.data:
```
**Problem:** `sub_result.data` is checked twice — `has_subscription` already captures truthiness.

---

## Mobile (React Native / TypeScript)

### M-1 | HIGH | Placeholder "Coming Soon" UX shown to users
**File:** `mobile/app/result/[jobId].tsx:124-131`
```tsx
const handleShare = useCallback(() => {
    Alert.alert("Coming soon", "Sharing will be available in the next update.");
}, []);
const handleSave = useCallback(() => {
    Alert.alert("Coming soon", "Save to gallery will be available in the next update.");
}, []);
```
**Problem:** Share and Save buttons are visible and tappable but do nothing. Users discover broken features.

### M-2 | HIGH | Report button is a fake — no API call
**File:** `mobile/app/(tabs)/index.tsx:71-87`
```tsx
onPress: () => {
    // Report API call will be implemented in a future story
    Alert.alert("Reported", "Thank you for your feedback.");
},
```
**Problem:** Users think they reported content but nothing was submitted. This is deceptive UX and could have trust/legal implications.

### M-3 | HIGH | Two entire tabs are placeholder screens
**Files:** `mobile/app/(tabs)/search.tsx`, `mobile/app/(tabs)/notifications.tsx`
```tsx
/** Search tab — placeholder for future story */
export default function SearchScreen() {
    return (<View><Text>Search</Text><Text>Discover cards and creators</Text></View>);
}
```
**Problem:** Users can navigate to fully non-functional screens. Should either implement or hide the tabs.

### M-4 | MEDIUM | No-op callback passed to CommentsSheet
**File:** `mobile/app/(tabs)/index.tsx:64-69`
```tsx
const handleCommentPosted = useCallback((_postId: string) => {
    // ... this is a no-op placeholder ...
}, []);
```
**Problem:** Comment count doesn't update optimistically after posting. User sees stale count until next feed refresh.

### M-5 | MEDIUM | Silent error swallowing in pagination (6 locations)
**Files:** `mobile/components/feed/useFeed.ts:94`, `mobile/components/advisor/ChatView.tsx:139`, `mobile/components/advisor/NudgeFeed.tsx:140`, `mobile/components/advisor/MemoryList.tsx:523`, `mobile/components/comments/useComments.ts:95`, `mobile/app/onboarding.tsx:94`
```tsx
} catch (err) {
    console.warn("Feed loadMore error:", err);
}
```
**Problem:** Pagination failures are silently swallowed in 6 different locations. Users get no feedback that loading failed. Inconsistent with initial-load error handling which does show errors.

### M-6 | MEDIUM | Stale TODO comment
**File:** `mobile/app/(tabs)/profile.tsx:61`
```tsx
// TODO: Get username from auth context once available
```
**Problem:** Code already works via `loadProfile("me")`. The TODO is stale and misleading.

### M-7 | MEDIUM | Hardcoded color bypassing design system
**File:** `mobile/components/feed/FeedCard.tsx:254`
```tsx
backgroundColor: "rgba(244, 63, 94, 0.72)",  // hardcoded coral
```
**Problem:** Should use `AFTER_OVERLAY` or equivalent from `constants/colors.ts`. Other overlays in the same file correctly use the color system.

### M-8 | MEDIUM | Hardcoded spacing values despite SPACING constant
**File:** `mobile/app/result/[jobId].tsx`
**Problem:** Defines `const SPACING = 8` but many style values still use hardcoded `8`, `12`, `16`, `24` instead of `SPACING * n`.

### M-9 | MEDIUM | `_TODO_H6` tracking comment in app.json
**File:** `mobile/app.json:10`
```json
"_TODO_H6": "Remove custom URI scheme ('scheme: nxme') once all deep links use Universal Links"
```
**Problem:** Tracked infrastructure debt. The custom URI scheme is a security concern (H-6 audit finding). Requires AASA/assetlinks.json hosting before removal.

### M-10 | LOW | Refresh token stored but never retrieved
**File:** `mobile/lib/api.ts:58`
```tsx
await SecureStore.setItemAsync("nxme_refresh_token", response.refresh_token);
```
**Problem:** Token is stored but there's no corresponding retrieval function. Either dead code or incomplete token refresh implementation.

### M-11 | LOW | Optimistic delete with full-reload rollback
**File:** `mobile/components/advisor/MemoryList.tsx:517-524`
```tsx
setMemories((prev) => prev.filter((m) => m.id !== memoryId));
try { await deleteMemory(memoryId); }
catch { loadMemories(); }  // Full reload instead of re-adding the item
```
**Problem:** On delete failure, the entire memory list is reloaded instead of reinserting the deleted item. Causes visual flash.

### M-12 | LOW | Duplicate query param building pattern
**Files:** `mobile/lib/advisor.ts`, `mobile/components/feed/useFeed.ts`, `mobile/components/comments/useComments.ts`
**Problem:** Same URLSearchParams + conditional append pattern repeated 4+ times. Should be a shared `buildQueryString()` utility.

---

## Card-Web (Next.js / TypeScript)

### C-1 | HIGH | Placeholder App Store URL with fake ID
**File:** `card-web/src/config/constants.ts:49`
```typescript
export const APP_STORE_URL =
    process.env.NEXT_PUBLIC_APP_STORE_URL ??
    'https://apps.apple.com/app/nxme/id0000000000';
```
**Problem:** Fallback uses `id0000000000` (placeholder). If env var is missing in production, users get a broken App Store link.

### C-2 | MEDIUM | Unused export `PUBLIC_API_BASE_URL`
**File:** `card-web/src/config/constants.ts:43-44`
```typescript
export const PUBLIC_API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
```
**Problem:** Defined but never imported anywhere. Dead code.

### C-3 | MEDIUM | Hardcoded colors in card-view component
**File:** `card-web/src/components/card-view.tsx:41,61,75`
```tsx
style={{ backgroundColor: 'rgba(15, 23, 42, 0.72)' }}
style={{ backgroundColor: 'rgba(244, 63, 94, 0.08)' }}
style={{ boxShadow: '0 0 0 2px rgba(255, 140, 66, 0.40)' }}
```
**Problem:** Three hardcoded color values that should use Tailwind theme tokens (`glow.ring`, `before-overlay`, `after-overlay`). Design system violation.

### C-4 | MEDIUM | 9+ hardcoded colors in OG image generator
**File:** `card-web/src/app/[username]/opengraph-image.tsx`
**Problem:** All color values in the OG image route are hardcoded hex strings. While Satori can't use Tailwind, these should be extracted to constants at the top of the file for maintainability.

### C-5 | MEDIUM | Event listener leak in CTA button
**File:** `card-web/src/components/cta-button.tsx:58-71`
```tsx
window.addEventListener('focus', clearOnFocus);
```
**Problem:** Focus listener added in click handler without cleanup on component unmount. If component unmounts before focus event fires, listener leaks.

### C-6 | LOW | Useless `void` statement in test
**File:** `card-web/src/__tests__/smoke.test.ts:43`
```typescript
const { username: _username, ...withoutUsername } = VALID_CARD;
void _username;
```
**Problem:** No-op statement to suppress unused variable warning. Should use `_` destructuring or eslint ignore.

### C-7 | LOW | Type assertions (`as`) instead of type guards
**File:** `card-web/src/lib/api.ts:69,84,91,107-118`
**Problem:** Heavy use of `as` type casts in parsing function. Runtime validation exists but TypeScript doesn't see it. Should use type predicates or `satisfies`.

---

## Summary

| Severity | Backend | Mobile | Card-Web | Total |
|----------|---------|--------|----------|-------|
| HIGH     | 2       | 3      | 1        | **6** |
| MEDIUM   | 4       | 6      | 4        | **14**|
| LOW      | 2       | 3      | 2        | **7** |
| **Total**| **8**   | **12** | **7**    | **27**|
