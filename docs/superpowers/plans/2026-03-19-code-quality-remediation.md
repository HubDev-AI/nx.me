# Code Quality Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 27 findings from the 2026-03-19 code quality audit — incomplete implementations, stub UX, hardcoded config, fragile error handling, resource leaks, and dead code across backend, mobile, and card-web.

**Deferred findings (not in this plan):**
- B-5 (tier ID duplication): Requires migration-aware approach — tracked separately
- B-6 (inconsistent repo return patterns): Codebase-wide refactor across all repos — tracked separately
- C-7 (type assertions in api.ts): Working correctly, cosmetic improvement — tracked separately
- M-9 (app.json _TODO_H6): Infrastructure prerequisite (AASA/assetlinks.json) — tracked separately
- M-10 (refresh token never retrieved): Needs investigation whether token refresh is planned — tracked separately
- M-12 (duplicate query param building): Convenience refactor — tracked separately

**Architecture:** Three independent workstreams: backend Python fixes (config extraction, atomic operations, exception handling), mobile React Native fixes (wire up report API, implement share/save, hide placeholder tabs, fix silent error handling), and card-web Next.js fixes (placeholder URLs, design token usage, event listener cleanup). Each task is self-contained and can be committed independently.

**Tech Stack:** Python/FastAPI/Supabase (backend), React Native/Expo Router (mobile), Next.js 14/Tailwind (card-web), Redis (caching/rate limiting)

**Source audit:** `docs/code-quality-audit-2026-03-19.md`

---

## File Map

### Backend (Python)
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/config/__init__.py` | Add model cost + Sonnet model config fields |
| Modify | `app/generation/adapters/falai.py` | Read costs from config instead of hardcoded dict |
| Modify | `app/advisor/service.py` | Read Sonnet model from config |
| Modify | `app/entitlement/trial_grantor.py` | Catch `postgrest.exceptions.APIError` by code instead of string matching |
| Modify | `app/generation/worker.py` | Atomic DECR+cleanup via Lua script |
| Modify | `app/api/posts.py` | Un-deprecate report endpoint, move rate limits to config |

### Mobile (React Native)
| Action | File | Responsibility |
|--------|------|----------------|
| Create | `mobile/lib/report.ts` | Report API client function |
| Modify | `mobile/app/(tabs)/index.tsx` | Wire report handler to API, implement comment count update |
| Modify | `mobile/app/(tabs)/_layout.tsx` | Hide search + notifications tabs |
| Delete | `mobile/app/(tabs)/search.tsx` | Remove placeholder screen |
| Delete | `mobile/app/(tabs)/notifications.tsx` | Remove placeholder screen |
| Modify | `mobile/app/result/[jobId].tsx` | Implement share via `Share.share()`, save via `expo-media-library` |
| Modify | `mobile/app/(tabs)/profile.tsx` | Remove stale TODO comment |
| Modify | `mobile/components/feed/FeedCard.tsx` | Use `AFTER_OVERLAY` color constant |
| Modify | `mobile/components/feed/useFeed.ts` | Surface pagination errors |
| Modify | `mobile/components/advisor/ChatView.tsx` | Surface pagination errors |
| Modify | `mobile/components/advisor/NudgeFeed.tsx` | Surface pagination errors |
| Modify | `mobile/components/advisor/MemoryList.tsx` | Surface pagination errors, fix rollback |
| Modify | `mobile/components/comments/useComments.ts` | Surface pagination errors |
| Modify | `mobile/app/onboarding.tsx` | Log entitlement fetch failure |

### Card-Web (Next.js)
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `card-web/src/config/constants.ts` | Remove placeholder App Store ID fallback, remove unused export |
| Modify | `card-web/src/components/card-view.tsx` | Use Tailwind design tokens for overlay colors |
| Modify | `card-web/src/app/[username]/opengraph-image.tsx` | Extract hardcoded colors to constants object |
| Modify | `card-web/src/components/cta-button.tsx` | Fix event listener leak, add error handling |
| Modify | `card-web/src/__tests__/smoke.test.ts` | Remove `void` no-op |

---

## Task 1: Backend — Extract model costs and Sonnet model to config

**Findings:** B-1 (hardcoded costs), B-3 (hardcoded Sonnet model)

**Files:**
- Modify: `app/config/__init__.py:91-102` (add new fields in generation section)
- Modify: `app/generation/adapters/falai.py:120-127` (read from config)
- Modify: `app/advisor/service.py:39` (read Sonnet from config)

- [ ] **Step 1: Add config fields**

In `app/config/__init__.py`, after the existing generation config block (after `GENERATION_HTTPX_TIMEOUT_SECONDS`), add:

```python
    # Model cost estimates (USD per generation, from provider pricing)
    FAL_COST_FLUX_PULID: float = 0.035
    FAL_COST_FLUX_DEV_IMG2IMG: float = 0.026
    FAL_COST_INSTANTID: float = 0.020
    FAL_COST_DEFAULT: float = 0.035

    # Advisor Sonnet model (chat responses)
    ADVISOR_MODEL_SONNET: str = "claude-3-5-sonnet-20241022"
```

- [ ] **Step 2: Update fal.ai adapter to read from config**

Replace `_estimate_cost` in `app/generation/adapters/falai.py:120-127`:

```python
def _estimate_cost(self, model: str) -> float:
    """Estimate cost per generation by model (from config)."""
    costs = {
        settings.FAL_MODEL_PRIMARY: settings.FAL_COST_FLUX_PULID,
        settings.FAL_MODEL_FALLBACK_1: settings.FAL_COST_FLUX_DEV_IMG2IMG,
        settings.FAL_MODEL_FALLBACK_2: settings.FAL_COST_INSTANTID,
    }
    return costs.get(model, settings.FAL_COST_DEFAULT)
```

Add `from app.config import settings` at the top if not already imported.

- [ ] **Step 3: Update advisor service to read Sonnet from config**

In `app/advisor/service.py:39`, change:

```python
# Before
_MODEL_SONNET = "claude-3-5-sonnet-20241022"

# After
_MODEL_SONNET = settings.ADVISOR_MODEL_SONNET
```

- [ ] **Step 4: Verify — syntax check + lint**

```bash
python -c "import ast; ast.parse(open('app/config/__init__.py').read()); ast.parse(open('app/generation/adapters/falai.py').read()); ast.parse(open('app/advisor/service.py').read()); print('OK')"
flake8 app/config/__init__.py app/generation/adapters/falai.py app/advisor/service.py --max-line-length 120 --select E,F --ignore W503
```

- [ ] **Step 5: Commit**

```bash
git add app/config/__init__.py app/generation/adapters/falai.py app/advisor/service.py
git commit -m "refactor: extract model costs and Sonnet model to config (B-1, B-3)"
```

---

## Task 1b: Backend — Fix redundant truthiness check

**Finding:** B-7

**Files:**
- Modify: `app/entitlement/service.py:130-133`

- [ ] **Step 1: Simplify the double check**

In `app/entitlement/service.py`, find the pattern:

```python
has_subscription = bool(sub_result.data)
# ...
if has_subscription and sub_result.data:
```

Replace with:

```python
if sub_result.data:
    end_str = sub_result.data[0].get("billing_period_end")
```

Remove the `has_subscription` variable if it's not used elsewhere in the function.

- [ ] **Step 2: Commit with Task 1**

Include in the Task 1 commit or commit separately:

```bash
git add app/entitlement/service.py
git commit -m "fix: remove redundant truthiness check in entitlement service (B-7)"
```

---

## Task 2: Backend — Fix fragile exception handling in trial grantor

**Finding:** B-2

**Files:**
- Modify: `app/entitlement/trial_grantor.py` (entire exception block)

**Context:** The Supabase Python client wraps PostgREST errors in `postgrest.exceptions.APIError` which has a `.code` attribute containing the PostgreSQL error code (e.g., `"23505"` for unique violation). The current code does string matching on the exception message which is fragile — error messages vary by locale and PostgreSQL version.

- [ ] **Step 1: Research the actual exception type**

Check what Supabase/PostgREST raises. The `postgrest` package exposes `APIError` with `.code`, `.message`, and `.details` attributes.

```bash
python -c "from postgrest.exceptions import APIError; print(APIError.__doc__)"
```

If `postgrest.exceptions.APIError` is not available, check `postgrest.types` or fall back to checking `hasattr(exc, 'code')`.

- [ ] **Step 2: Replace string matching with structured error check**

Replace lines 50-58 in `app/entitlement/trial_grantor.py`:

```python
        except Exception as exc:
            # Check for PostgreSQL unique violation (23505) via structured error code.
            # Supabase PostgREST wraps PG errors in APIError with a .code attribute.
            pg_code = getattr(exc, "code", None)
            if pg_code == "23505":
                logger.info("trial_grant already applied for user %s — skipping", user_id_str)
                return

            # Fallback: some Supabase client versions embed the code in the message
            exc_str = str(exc).lower()
            if "23505" in exc_str or "unique_violation" in exc_str:
                logger.info("trial_grant already applied for user %s — skipping", user_id_str)
                return

            logger.error("grant_trial RPC failed for user %s: %s", user_id_str, exc)
            raise RuntimeError(
                f"Failed to grant trial for user {user_id_str}"
            ) from exc
```

**Why this approach:** We first check the structured `.code` attribute (clean path). We keep a narrow string fallback for `"23505"` and `"unique_violation"` only (not vague words like "unique" or "duplicate" which could match unrelated errors). The fallback protects against Supabase client version differences.

- [ ] **Step 3: Verify + lint**

```bash
python -m py_compile app/entitlement/trial_grantor.py
flake8 app/entitlement/trial_grantor.py --max-line-length 120 --select E,F --ignore W503
```

- [ ] **Step 4: Commit**

```bash
git add app/entitlement/trial_grantor.py
git commit -m "fix: use structured error code for trial grant idempotency check (B-2)"
```

---

## Task 3: Backend — Atomic concurrent counter cleanup via Lua script

**Finding:** B-4

**Files:**
- Modify: `app/generation/worker.py:517-532` (finally block)

**Context:** The existing code does DECR then conditionally DELETE or EXPIRE as two separate Redis calls. If the worker crashes between DECR and DELETE, the key is left in an inconsistent state. The codebase already uses Lua scripts for atomic Redis operations (see `app/entitlement/service.py:43-50` for the concurrent check script). Follow the same pattern.

- [ ] **Step 1: Add Lua script constant at module level**

After the existing `_ALLOWED_IMAGE_HOSTS` in `app/generation/worker.py`, add:

```python
# Atomic DECR + conditional cleanup (B-4: prevents leaked counter on crash)
_CONCURRENT_CLEANUP_SCRIPT = """
local val = redis.call('DECR', KEYS[1])
if val <= 0 then
    redis.call('DEL', KEYS[1])
    return 0
else
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
    return val
end
"""
```

- [ ] **Step 2: Add script SHA cache on the module or worker context**

After `process_generation_job` function's `supabase: Client = ctx["supabase"]` line, add SHA caching:

```python
    # Lazy-load Lua script SHA for atomic concurrent cleanup (B-4)
    cleanup_sha_key = "_concurrent_cleanup_sha"
    if cleanup_sha_key not in ctx:
        ctx[cleanup_sha_key] = await redis.script_load(_CONCURRENT_CLEANUP_SCRIPT)
    cleanup_sha = ctx[cleanup_sha_key]
```

- [ ] **Step 3: Replace the finally block**

Replace the existing finally block (lines 517-532) with:

```python
    finally:
        # B-4: Atomic DECR + conditional DELETE/EXPIRE via Lua script.
        # Prevents leaked counter if worker crashes between operations.
        if user_id_for_concurrent:
            try:
                await redis.evalsha(
                    cleanup_sha,
                    1,
                    f"concurrent:{user_id_for_concurrent}",
                    str(settings.GENERATION_TIMEOUT_SECONDS + 60),
                )
            except Exception:
                logger.error(
                    "Failed to cleanup concurrent counter for user %s",
                    user_id_for_concurrent,
                )
```

- [ ] **Step 4: Verify + lint**

```bash
python -m py_compile app/generation/worker.py
flake8 app/generation/worker.py --max-line-length 120 --select E,F --ignore W503
```

- [ ] **Step 5: Commit**

```bash
git add app/generation/worker.py
git commit -m "fix: atomic concurrent counter cleanup via Lua script (B-4)"
```

---

## Task 4: Backend — Un-deprecate report endpoint and move rate limits to config

**Finding:** B-1 (config), M-2 (report needs working backend)

**Files:**
- Modify: `app/config/__init__.py` (add report rate limit config)
- Modify: `app/api/posts.py:359-398` (remove deprecated flag, use config for rate limits)

**Context:** The report endpoint is fully functional but marked `deprecated=True`. The mobile app needs it active. The rate limit values (5 reports, 3600s window) are hardcoded at the top of the file.

- [ ] **Step 1: Add report config fields**

In `app/config/__init__.py`, in the rate limiting section (after login rate limits):

```python
    # Rate limiting — reports
    REPORT_RATE_LIMIT: int = 5
    REPORT_RATE_WINDOW_SECONDS: int = 3600
```

- [ ] **Step 2: Update the report endpoint**

In `app/api/posts.py`:

1. Remove `deprecated=True` from the `@router.post` decorator (line 363)
2. Replace hardcoded `_REPORT_RATE_LIMIT` and `_REPORT_RATE_WINDOW` references with `settings.REPORT_RATE_LIMIT` and `settings.REPORT_RATE_WINDOW_SECONDS`
3. Add `from app.config import settings` if not already imported

```python
@router.post(
    "/posts/{post_id}/report",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_post(
    post_id: UUID,
    body: ReportRequest,
    claims: UserClaims = Depends(get_current_user),
    post_repo: PostRepository = Depends(get_post_repo),
    redis_client: aioredis.Redis = Depends(get_redis),
) -> ReportResponse:
    """Report a post for review. Auth required, rate-limited."""
    user_id = claims["sub"]

    rate_key = f"report_rate:{user_id}"
    count = await redis_client.incr(rate_key)
    if count == 1:
        await redis_client.expire(rate_key, settings.REPORT_RATE_WINDOW_SECONDS)
    if count > settings.REPORT_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many reports. Please slow down.")

    post = post_repo.get_active_post(str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    report = post_repo.insert_report(
        post_id=str(post_id),
        reporter_user_id=user_id,
        reason=body.reason,
    )
    logger.info("Report %s on post %s by user %s", report["id"], post_id, user_id)

    return ReportResponse(report_id=report["id"], status="pending")
```

- [ ] **Step 3: Remove the old hardcoded constants** if they exist at the top of `posts.py`

Search for `_REPORT_RATE_LIMIT` and `_REPORT_RATE_WINDOW` module-level constants and delete them.

- [ ] **Step 4: Verify + lint**

```bash
flake8 app/api/posts.py app/config/__init__.py --max-line-length 120 --select E,F --ignore W503
```

- [ ] **Step 5: Commit**

```bash
git add app/config/__init__.py app/api/posts.py
git commit -m "fix: un-deprecate report endpoint, move rate limits to config (B-1, M-2)"
```

---

## Task 5: Mobile — Wire up report handler to real API

**Finding:** M-2 (fake report button)

**Files:**
- Create: `mobile/lib/report.ts`
- Modify: `mobile/app/(tabs)/index.tsx:71-87`

**Context:** The backend `POST /v1/posts/{postId}/report` endpoint already exists and works (Task 4 un-deprecates it). The mobile app already has the UI flow (confirmation dialog in the feed screen). We just need to: (1) create an API client function, (2) call it from the handler, (3) handle success/error states properly.

The existing `apiFetch` pattern (in `mobile/lib/api.ts`) auto-attaches the JWT. The report endpoint requires auth and returns `{ report_id, status }`.

- [ ] **Step 1: Create report API client**

Create `mobile/lib/report.ts`:

```typescript
/**
 * Report API — POST /v1/posts/{postId}/report
 *
 * Rate limited to 5 reports per hour per user (server-enforced).
 * Returns { report_id, status: "pending" } on success.
 */
import { apiFetch } from "./api";

interface ReportResponse {
  report_id: string;
  status: string;
}

interface ReportOptions {
  reason?: string;
}

/**
 * Submit a content report for a post.
 *
 * @throws ApiError on 404 (post not found), 429 (rate limited), or auth errors
 */
export async function reportPost(
  postId: string,
  options: ReportOptions = {},
): Promise<ReportResponse> {
  return apiFetch<ReportResponse>(`/v1/posts/${postId}/report`, {
    method: "POST",
    body: JSON.stringify({ reason: options.reason ?? null }),
  });
}
```

- [ ] **Step 2: Wire up the report handler in the feed screen**

Replace the stub handler in `mobile/app/(tabs)/index.tsx:71-87`:

```typescript
import { reportPost } from "../../lib/report";

// ... inside FeedScreen component:

const handleReport = useCallback((postId: string) => {
  Alert.alert(
    "Report Post",
    "Are you sure you want to report this post as inappropriate?",
    [
      { text: "Cancel", style: "cancel" },
      {
        text: "Report",
        style: "destructive",
        onPress: async () => {
          try {
            await reportPost(postId);
            Alert.alert(
              "Report Submitted",
              "Thanks for helping keep NXME safe. We'll review this post.",
            );
          } catch (err: unknown) {
            const status = (err as { status?: number }).status;
            if (status === 429) {
              Alert.alert(
                "Slow Down",
                "You've submitted several reports recently. Please try again later.",
              );
            } else {
              Alert.alert("Error", "Failed to submit report. Please try again.");
            }
          }
        },
      },
    ],
  );
}, []);
```

**Why this approach:** We show the real success state ("We'll review this post") vs the current lie ("Thank you for your feedback" with no API call). Rate limit 429s get a specific user-friendly message. Other errors get a generic retry message. No silent swallowing.

- [ ] **Step 3: Commit**

```bash
git add mobile/lib/report.ts mobile/app/\(tabs\)/index.tsx
git commit -m "feat: wire report handler to real API with error handling (M-2)"
```

---

## Task 6: Mobile — Implement share and save on result screen

**Finding:** M-1 (Coming Soon stubs)

**Files:**
- Modify: `mobile/app/result/[jobId].tsx:124-132`
- Modify: `mobile/package.json` (add `expo-media-library` if needed)

**Context:** The result screen has Share and Save buttons that show "Coming soon" alerts. Share should use React Native's built-in `Share.share()` API (already used in FeedCard for the long-press menu). Save should download the after-image to the device gallery via `expo-media-library`.

The result screen already has the job data in state as `result: JobResult` which contains `after_image_url` (the public URL of the generated image).

- [ ] **Step 1: Read JobResult type to confirm field names**

Read `mobile/lib/analysis.ts` and find the `JobResult` type/interface. Note the exact field names for: the after/generated image URL, and any post_id field. All code in subsequent steps must use these exact field names.

- [ ] **Step 2: Check if expo-media-library is installed**

```bash
cd mobile && grep "expo-media-library" package.json
```

If not present:
```bash
npx expo install expo-media-library
```

- [ ] **Step 3: Implement handleShare**

Replace the stub in `mobile/app/result/[jobId].tsx:124-127`:

```typescript
import { Share, Platform } from "react-native";
// (Share is already imported from react-native on line 17)

const handleShare = useCallback(async () => {
  if (!result?.after_image_url) return;

  const shareUrl = `${UNIVERSAL_LINK_ORIGIN ?? "https://nxme.ai"}/posts/${result.post_id ?? jobId}`;

  try {
    if (Platform.OS === "ios") {
      await Share.share({ url: shareUrl });
    } else {
      await Share.share({ message: shareUrl });
    }
  } catch {
    // User cancelled share sheet — not an error
  }
}, [result, jobId]);
```

**Note:** Check what fields `JobResult` actually has. Read `mobile/lib/analysis.ts` for the `JobResult` type to determine the correct field names for the share URL and image URL. If `post_id` isn't available on `JobResult`, construct the URL from the job result's card URL or use the after_image_url directly.

- [ ] **Step 4: Implement handleSave**

Replace the stub in `mobile/app/result/[jobId].tsx:129-132`:

```typescript
import * as MediaLibrary from "expo-media-library";
import * as FileSystem from "expo-file-system";

const handleSave = useCallback(async () => {
  if (!result?.after_image_url) return;

  try {
    // Request permissions
    const { status } = await MediaLibrary.requestPermissionsAsync();
    if (status !== "granted") {
      Alert.alert(
        "Permission Required",
        "Please allow access to your photo library to save images.",
      );
      return;
    }

    // Download to temp file, then save to gallery
    const fileUri = `${FileSystem.cacheDirectory}nxme-glowup-${jobId}.jpg`;
    const download = await FileSystem.downloadAsync(result.after_image_url, fileUri);
    await MediaLibrary.saveToLibraryAsync(download.uri);

    Alert.alert("Saved", "Your glow-up has been saved to your photo library.");
  } catch {
    Alert.alert("Error", "Failed to save image. Please try again.");
  }
}, [result, jobId]);
```

**Important:** Verify `expo-file-system` is already a dependency (it's part of Expo SDK, should be available). If not, `npx expo install expo-file-system`.

- [ ] **Step 5: Check UNIVERSAL_LINK_ORIGIN is available**

```bash
grep -rn "UNIVERSAL_LINK_ORIGIN" mobile/
```

If it doesn't exist in the result screen's scope, import it from `mobile/constants/config.ts` or `mobile/lib/api.ts` (wherever the feed uses it).

- [ ] **Step 6: Commit**

```bash
git add mobile/app/result/\[jobId\].tsx mobile/package.json
git commit -m "feat: implement share and save-to-gallery on result screen (M-1)"
```

---

## Task 7: Mobile — Hide placeholder tabs

**Finding:** M-3 (non-functional Search and Notifications tabs)

**Files:**
- Modify: `mobile/app/(tabs)/_layout.tsx:67-105` (hide both tabs)
- Delete: `mobile/app/(tabs)/search.tsx`
- Delete: `mobile/app/(tabs)/notifications.tsx`

**Context:** Expo Router allows hiding a tab from the tab bar while keeping the route file (for future use) by setting `href: null`. However, since these screens are completely non-functional and exist only as "future story" placeholders, we should delete the files entirely to avoid confusion. The tab entries in `_layout.tsx` should be removed too.

- [ ] **Step 1: Remove search and notifications tab entries from layout**

In `mobile/app/(tabs)/_layout.tsx`, delete the `<Tabs.Screen name="search" .../>` block (lines 67-79) and the `<Tabs.Screen name="notifications" .../>` block (lines 93-105).

- [ ] **Step 2: Delete placeholder screen files**

```bash
rm mobile/app/\(tabs\)/search.tsx mobile/app/\(tabs\)/notifications.tsx
```

- [ ] **Step 3: Verify the app still builds**

```bash
cd mobile && npx expo export --platform ios --dump-sourcemap false 2>&1 | tail -5
```

Or at minimum verify TypeScript:
```bash
cd mobile && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
git add mobile/app/\(tabs\)/_layout.tsx
git rm mobile/app/\(tabs\)/search.tsx mobile/app/\(tabs\)/notifications.tsx
git commit -m "fix: remove non-functional search and notifications tabs (M-3)"
```

---

## Task 8: Mobile — Fix silent pagination errors (6 locations)

**Finding:** M-5

**Files:**
- Modify: `mobile/components/feed/useFeed.ts:94`
- Modify: `mobile/components/advisor/ChatView.tsx:139`
- Modify: `mobile/components/advisor/NudgeFeed.tsx:140`
- Modify: `mobile/components/advisor/MemoryList.tsx:523`
- Modify: `mobile/components/comments/useComments.ts:95`
- Modify: `mobile/app/onboarding.tsx:94`

**Context:** All 6 locations catch pagination errors and silently swallow them with `console.warn`. The user gets no feedback that "load more" failed. The fix should not be aggressive (no modal alerts for pagination) — instead, expose a `loadMoreError` state that the consuming component can use to show a subtle retry prompt.

- [ ] **Step 1: Fix useFeed.ts — expose loadMore error state**

In `mobile/components/feed/useFeed.ts`, add a `loadMoreError` state:

```typescript
const [loadMoreError, setLoadMoreError] = useState(false);
```

In the catch block (~line 94), set the error state instead of silently swallowing:

```typescript
} catch (err) {
  setLoadMoreError(true);
  logger.warn("Feed loadMore error:", err);
} finally {
```

Clear it on the next successful load:

```typescript
// At the start of loadMore:
setLoadMoreError(false);
```

Return `loadMoreError` from the hook. The consuming component (`index.tsx`) can render a small "Tap to retry" footer when `loadMoreError` is true.

- [ ] **Step 2: Apply the same pattern to the other 4 hooks/components**

For each file, add a `loadMoreError` boolean state (or equivalent), set it on catch, clear it on retry, and expose it for the consuming component.

- `ChatView.tsx:139` — set error state, show a small "Couldn't load older messages. Tap to retry." text
- `NudgeFeed.tsx:140` — same pattern
- `MemoryList.tsx:523` — same pattern
- `useComments.ts:95` — same pattern

- [ ] **Step 3: Fix onboarding.tsx entitlement error**

In `mobile/app/onboarding.tsx:94-98`, the entitlement fetch failure is silently swallowed. This is acceptable (user can still attempt upload), but should log properly:

```typescript
getEntitlement()
  .then(setEntitlement)
  .catch((err) => {
    console.warn("Entitlement fetch failed — proceeding without entitlement data:", err);
  });
```

This is intentionally NOT surfaced to the user (entitlement is non-blocking for the upload flow).

- [ ] **Step 4: Commit**

```bash
git add mobile/components/feed/useFeed.ts mobile/components/advisor/ChatView.tsx mobile/components/advisor/NudgeFeed.tsx mobile/components/advisor/MemoryList.tsx mobile/components/comments/useComments.ts mobile/app/onboarding.tsx
git commit -m "fix: surface pagination errors instead of silent swallowing (M-5)"
```

---

## Task 9: Mobile — Comment count optimistic update + stale TODO cleanup

**Findings:** M-4 (no-op comment handler), M-6 (stale TODO), M-11 (optimistic delete rollback)

**Files:**
- Modify: `mobile/app/(tabs)/index.tsx:64-69`
- Modify: `mobile/app/(tabs)/profile.tsx:61`
- Modify: `mobile/components/advisor/MemoryList.tsx:517-524`

- [ ] **Step 1: Implement optimistic comment count update**

In `mobile/app/(tabs)/index.tsx:64-69`, the `handleCommentPosted` callback is a no-op. The feed data lives in `useFeed` which doesn't expose a setter. The proper fix is to add a `updatePostField` method to `useFeed` (or a dedicated `incrementCommentCount`) and call it from the handler.

In `mobile/components/feed/useFeed.ts`, add a method to the hook's return:

```typescript
const incrementCommentCount = useCallback((postId: string) => {
  setPosts((prev) =>
    prev.map((p) =>
      p.post_id === postId
        ? { ...p, comment_count: (p.comment_count ?? 0) + 1 }
        : p,
    ),
  );
}, []);

// Return it from the hook:
return { posts, ..., incrementCommentCount };
```

Then in `index.tsx`:

```typescript
const { posts, ..., incrementCommentCount } = useFeed(...);

const handleCommentPosted = useCallback((postId: string) => {
  incrementCommentCount(postId);
}, [incrementCommentCount]);
```

- [ ] **Step 2: Remove stale TODO from profile.tsx**

In `mobile/app/(tabs)/profile.tsx:61`, delete the comment:

```typescript
// Before:
// TODO: Get username from auth context once available

// After: (line deleted entirely)
```

- [ ] **Step 3: Fix optimistic delete rollback in MemoryList**

In `mobile/components/advisor/MemoryList.tsx:517-524`, instead of full-reload on failure, re-insert the deleted item:

```typescript
const handleDelete = useCallback(async (memoryId: string) => {
  // Capture the item before removing for potential rollback
  const deletedItem = memories.find((m) => m.id === memoryId);
  setMemories((prev) => prev.filter((m) => m.id !== memoryId));

  try {
    await deleteMemory(memoryId);
  } catch {
    // Rollback: re-insert the deleted item at its original position
    if (deletedItem) {
      setMemories((prev) => [...prev, deletedItem].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ));
    }
    Alert.alert("Error", "Failed to delete memory. Please try again.");
  }
}, [memories, deleteMemory]);
```

- [ ] **Step 4: Commit**

```bash
git add mobile/app/\(tabs\)/index.tsx mobile/app/\(tabs\)/profile.tsx mobile/components/feed/useFeed.ts mobile/components/advisor/MemoryList.tsx
git commit -m "fix: optimistic comment count, stale TODO, memory delete rollback (M-4, M-6, M-11)"
```

---

## Task 10: Mobile — Fix hardcoded color and spacing

**Findings:** M-7 (hardcoded color), M-8 (hardcoded spacing)

**Files:**
- Modify: `mobile/components/feed/FeedCard.tsx:254`
- Modify: `mobile/app/result/[jobId].tsx` (spacing values)

- [ ] **Step 1: Fix hardcoded color in FeedCard**

In `mobile/components/feed/FeedCard.tsx:254`, replace:

```typescript
// Before:
backgroundColor: "rgba(244, 63, 94, 0.72)",

// After:
backgroundColor: AFTER_OVERLAY,
```

Check that `AFTER_OVERLAY` is imported from `../../constants/colors`. The existing value `"rgba(244, 63, 94, 0.08)"` in `constants/colors.ts` has opacity `0.08`, but the FeedCard uses `0.72`. These are different values. Check if there's a higher-opacity after-overlay constant. If not, add one to `constants/colors.ts`:

```typescript
/** After-state reveal overlay — 72% opacity for strong overlay on feed labels */
export const AFTER_OVERLAY_STRONG = "rgba(244, 63, 94, 0.72)";
```

Then use `AFTER_OVERLAY_STRONG` in FeedCard.

- [ ] **Step 2: Fix hardcoded spacing in result screen**

In `mobile/app/result/[jobId].tsx`, audit all inline spacing values and replace with `SPACING * n` where `SPACING = 8` is already defined. Only replace values that are exact multiples of 8 (8, 16, 24, 32). Leave non-multiples (12, 20, etc.) as-is — they may be intentional.

- [ ] **Step 3: Commit**

```bash
git add mobile/components/feed/FeedCard.tsx mobile/app/result/\[jobId\].tsx mobile/constants/colors.ts
git commit -m "fix: use design system colors and spacing constants (M-7, M-8)"
```

---

## Task 11: Card-Web — Fix placeholder App Store URL and remove dead export

**Findings:** C-1 (fake App Store ID), C-2 (unused export)

**Files:**
- Modify: `card-web/src/config/constants.ts:43-44,49`

- [ ] **Step 1: Fix App Store URL fallback**

Replace the placeholder `id0000000000` with a fail-fast approach — if the env var is missing in production, the CTA button should not render a broken link:

```typescript
// Before:
export const APP_STORE_URL =
  process.env.NEXT_PUBLIC_APP_STORE_URL ??
  'https://apps.apple.com/app/nxme/id0000000000';

// After:
export const APP_STORE_URL =
  process.env.NEXT_PUBLIC_APP_STORE_URL ?? '';
```

Then in `cta-button.tsx`, guard against empty store URLs:

```typescript
// Only redirect to store if URL is configured
if (storeUrl) {
  const timer = setTimeout(() => {
    window.location.href = storeUrl;
  }, APP_OPEN_TIMEOUT_MS);
  // ...
}
```

- [ ] **Step 2: Remove unused PUBLIC_API_BASE_URL**

Delete lines 43-44 in `card-web/src/config/constants.ts`:

```typescript
// Delete this:
export const PUBLIC_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
```

Verify nothing imports it:

```bash
grep -rn "PUBLIC_API_BASE_URL" card-web/src/
```

- [ ] **Step 3: Commit**

```bash
git add card-web/src/config/constants.ts card-web/src/components/cta-button.tsx
git commit -m "fix: remove placeholder App Store URL, remove dead export (C-1, C-2)"
```

---

## Task 12: Card-Web — Use design tokens, fix event listener leak, cleanup

**Findings:** C-3 (hardcoded colors in card-view), C-4 (hardcoded OG colors), C-5 (event listener leak), C-6 (void no-op)

**Files:**
- Modify: `card-web/src/components/card-view.tsx:41,61,75`
- Modify: `card-web/src/app/[username]/opengraph-image.tsx` (top of file)
- Modify: `card-web/src/components/cta-button.tsx:58-71`
- Modify: `card-web/src/__tests__/smoke.test.ts:43`

- [ ] **Step 1: Fix card-view hardcoded colors**

In `card-web/src/components/card-view.tsx`, the three inline styles should use Tailwind classes or CSS variables. Check what classes are available in `tailwind.config.ts` for `glow`, `before-overlay`, `after-overlay`.

If Tailwind classes exist (e.g., `bg-before-overlay`), use them directly. If not, use CSS custom properties from the design system tokens (`var(--color-before-overlay)`, etc.).

Replace:
```tsx
// Line 41: style={{ backgroundColor: 'rgba(15, 23, 42, 0.72)' }}
// → use class: bg-[var(--color-before-overlay)] or the Tailwind token

// Line 61: style={{ backgroundColor: 'rgba(244, 63, 94, 0.08)' }}
// → use class: bg-[var(--color-after-overlay)]

// Line 75: style={{ boxShadow: '0 0 0 2px rgba(255, 140, 66, 0.40)' }}
// → use class: ring-2 ring-[var(--color-glow-ring)]
```

Read `card-web/tailwind.config.ts` first to check what design tokens are available as Tailwind theme extensions.

- [ ] **Step 2: Extract OG image colors to constants**

At the top of `card-web/src/app/[username]/opengraph-image.tsx`, before the component, add:

```typescript
/** Colors for OG image generation — mirrors design tokens but inline for Satori. */
const OG = {
  BG: '#080808',
  TEXT_PRIMARY: '#F8F8F8',
  TEXT_SECONDARY: '#A0A0A0',
  ACCENT: '#F43F5E',
  GLOW: '#FF8C42',
  BORDER: '#2A2A2A',
} as const;
```

Then replace all hardcoded hex values in the component with `OG.BG`, `OG.TEXT_PRIMARY`, etc.

- [ ] **Step 3: Fix event listener leak in CTA button**

In `card-web/src/components/cta-button.tsx`, the focus listener needs cleanup. Use `useEffect` cleanup or wrap in a ref:

```typescript
const handleClick = useCallback(() => {
  // ... existing universal link logic ...

  if (isMobile) {
    const timer = setTimeout(() => {
      if (storeUrl) window.location.href = storeUrl;
    }, APP_OPEN_TIMEOUT_MS);

    const clearOnFocus = () => {
      clearTimeout(timer);
      window.removeEventListener('focus', clearOnFocus);
    };
    window.addEventListener('focus', clearOnFocus);

    // Safety cleanup: if focus never fires (e.g., app not installed),
    // the timer handles redirect. Remove listener after timeout fires.
    setTimeout(() => {
      window.removeEventListener('focus', clearOnFocus);
    }, APP_OPEN_TIMEOUT_MS + 500);
  }
}, [username, storeUrl, isMobile]);
```

Also wrap the initial `window.location.href` in try/catch:

```typescript
try {
  window.location.href = universalLink;
} catch {
  // Invalid URL — fall through to store redirect
}
```

- [ ] **Step 4: Remove void no-op in test**

In `card-web/src/__tests__/smoke.test.ts:43`, replace:

```typescript
// Before:
const { username: _username, ...withoutUsername } = VALID_CARD
void _username

// After:
const { username: _, ...withoutUsername } = VALID_CARD
```

Or use object rest without destructuring the unused field:

```typescript
const { username, ...withoutUsername } = VALID_CARD  // eslint-disable-line @typescript-eslint/no-unused-vars
```

- [ ] **Step 5: Lint check**

```bash
cd card-web && npx eslint src/ --max-warnings 0 2>&1 | head -20
cd card-web && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 6: Commit**

```bash
git add card-web/src/components/card-view.tsx card-web/src/app/\[username\]/opengraph-image.tsx card-web/src/components/cta-button.tsx card-web/src/__tests__/smoke.test.ts
git commit -m "fix: design tokens in card-view, OG color constants, CTA listener leak, test cleanup (C-3 to C-6)"
```

---

## Task 13: Final verification

- [ ] **Step 1: Full backend lint**

```bash
flake8 app/ --max-line-length 120 --select E,F --ignore W503
python -c "import ast, pathlib; [ast.parse(f.read_text()) for f in pathlib.Path('app').rglob('*.py')]; print('OK')"
```

- [ ] **Step 2: Full card-web check**

```bash
cd card-web && npx tsc --noEmit && npx eslint src/ --max-warnings 0
```

- [ ] **Step 3: Verify no remaining TODOs/FIXMEs in source**

```bash
grep -rn "TODO\|FIXME\|HACK\|XXX" --include="*.py" --include="*.ts" --include="*.tsx" app/ mobile/ card-web/src/ | grep -v node_modules | grep -v __pycache__
```

The only acceptable remaining item is `mobile/app.json:_TODO_H6` (tracked infrastructure debt requiring AASA/assetlinks.json hosting).

- [ ] **Step 4: Create PR and merge**

```bash
git push -u origin fix/code-quality-remediation
gh pr create --base dev --title "fix: remediate all code quality findings" --body "..."
gh pr merge --merge --delete-branch
```
