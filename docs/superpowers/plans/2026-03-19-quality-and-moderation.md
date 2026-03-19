# Code Quality & Moderation Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 27 code quality findings from the 2026-03-19 audit AND build a full content moderation pipeline (report → auto-hide → admin review, user blocking, admin bans).

**Architecture:** Four workstreams:
1. Backend code quality fixes (config extraction, atomic operations, exception handling)
2. Full moderation backend (report pipeline, blocking, bans, admin API)
3. Mobile fixes (moderation UI, share, remove stubs, infinite scroll, design system)
4. Card-web fixes (placeholder URLs, design tokens, event listener leak)

**Tech Stack:** Python/FastAPI/Supabase (backend), React Native/Expo Router (mobile), Next.js 14/Tailwind (card-web), Redis (rate limiting)

---

## Part I: Audit Findings

### Backend (Python) — 8 findings

| ID | Sev | File | Problem | Resolution |
|----|-----|------|---------|------------|
| B-1 | HIGH | `app/generation/adapters/falai.py:120-127` | Hardcoded model costs (`0.035`, `0.026`, `0.020`) in adapter | Task 1: Move to `app/config/__init__.py` as `FAL_COST_*` fields |
| B-2 | HIGH | `app/entitlement/trial_grantor.py:50-58` | Fragile string matching (`"unique" in exc_str`) for idempotency | Task 2: Check `getattr(exc, "code", None) == "23505"` first, narrow string fallback |
| B-3 | MED | `app/advisor/service.py:39` | Hardcoded `_MODEL_SONNET = "claude-3-5-sonnet-20241022"` (Haiku was moved to config, Sonnet wasn't) | Task 1: Add `ADVISOR_MODEL_SONNET` to config |
| B-4 | MED | `app/generation/worker.py:517-532` | Non-atomic DECR + DELETE/EXPIRE on concurrent counter — crash between ops leaks counter | Task 3: Lua script for atomic DECR+cleanup (same pattern as `entitlement/service.py:43`) |
| B-5 | MED | `app/constants/tiers.py` + `app/config/tiers.py` | Tier UUIDs duplicated in two files, no sync enforcement | Deferred: requires migration-aware approach |
| B-6 | LOW | `app/repositories/*.py` | Inconsistent return patterns (`dict|None` vs `dict` vs `int`) across repos | Deferred: codebase-wide refactor |
| B-7 | LOW | `app/entitlement/service.py:130-133` | Redundant `has_subscription and sub_result.data` double-check | Task 1b: Remove redundant variable |

### Mobile (React Native) — 12 findings

| ID | Sev | File | Problem | Resolution |
|----|-----|------|---------|------------|
| M-1 | HIGH | `mobile/app/result/[jobId].tsx:124-131` | Share and Save buttons show "Coming soon" alerts | Task 9: Implement share (universal link). Remove Save button (redundant — users save via share sheet or access from history) |
| M-2 | HIGH | `mobile/app/(tabs)/index.tsx:71-87` | Report button shows fake "Thank you" without API call | Task 6+7: Full report pipeline — create API client, wire handler, backend auto-hide |
| M-3 | HIGH | `mobile/app/(tabs)/search.tsx`, `notifications.tsx` | Two tabs are non-functional placeholder screens | Task 10: Delete files, remove tab entries from layout |
| M-4 | MED | `mobile/app/(tabs)/index.tsx:64-69` | `handleCommentPosted` is a no-op — count doesn't update | Task 11: Add `incrementCommentCount` to useFeed hook, rollback on API failure |
| M-5 | MED | 6 files (`useFeed.ts`, `ChatView.tsx`, `NudgeFeed.tsx`, `MemoryList.tsx`, `useComments.ts`, `onboarding.tsx`) | Silent error swallowing in pagination catch blocks | Task 12: Auto-retry with backoff (2s → 3s → inline message), no buttons |
| M-6 | MED | `mobile/app/(tabs)/profile.tsx:61` | Stale TODO comment — code already works | Task 11: Delete comment |
| M-7 | MED | `mobile/components/feed/FeedCard.tsx:254` | Hardcoded `rgba(244,63,94,0.72)` bypassing color system | Task 13: Add `AFTER_OVERLAY_STRONG` constant, use it |
| M-8 | MED | `mobile/app/result/[jobId].tsx` | Hardcoded spacing despite `SPACING = 8` constant | Task 13: Replace multiples of 8 with `SPACING * n` |
| M-9 | MED | `mobile/app.json:10` | `_TODO_H6` — custom URI scheme needs Universal Links migration | Deferred: requires AASA/assetlinks.json infrastructure |
| M-10 | LOW | `mobile/lib/api.ts:58` | Refresh token stored but never retrieved | Deferred: needs investigation |
| M-11 | LOW | `mobile/components/advisor/MemoryList.tsx:517-524` | Optimistic delete does full reload on failure instead of reinserting | Task 11: Capture item before delete, re-insert on failure |
| M-12 | LOW | Multiple files | Duplicate URLSearchParams + conditional append pattern | Deferred: convenience refactor |

### Card-Web (Next.js) — 7 findings

| ID | Sev | File | Problem | Resolution |
|----|-----|------|---------|------------|
| C-1 | HIGH | `card-web/src/config/constants.ts:49` | App Store URL fallback uses placeholder `id0000000000` | Task 14: Empty string fallback, guard in CTA button |
| C-2 | MED | `card-web/src/config/constants.ts:43-44` | `PUBLIC_API_BASE_URL` exported but never imported | Task 14: Delete dead export |
| C-3 | MED | `card-web/src/components/card-view.tsx:41,61,75` | 3 hardcoded rgba color values instead of Tailwind tokens | Task 15: Use CSS variables from design system |
| C-4 | MED | `card-web/src/app/[username]/opengraph-image.tsx` | 9+ hardcoded hex colors in OG image generator | Task 15: Extract to `OG` constants object |
| C-5 | MED | `card-web/src/components/cta-button.tsx:58-71` | Focus event listener added without cleanup on unmount | Task 15: Add safety cleanup timeout |
| C-6 | LOW | `card-web/src/__tests__/smoke.test.ts:43` | `void _username` no-op statement | Task 15: Use `_` destructuring |
| C-7 | LOW | `card-web/src/lib/api.ts:69-118` | `as` type assertions instead of type guards | Deferred: cosmetic, working correctly |

### Deferred (6 findings — tracked separately)

| ID | Reason |
|----|--------|
| B-5 | Tier ID sync requires migration-aware approach |
| B-6 | Repo return patterns is a codebase-wide refactor |
| C-7 | Type assertions work correctly, cosmetic improvement |
| M-9 | Infrastructure prerequisite (AASA/assetlinks.json) |
| M-10 | Needs investigation whether token refresh is planned |
| M-12 | Convenience refactor, no functional impact |

---

## Part II: Moderation System Design

### Report Pipeline

**Flow:** User reports → insert `reports` row → count unique reporters → if count >= `REPORT_AUTO_HIDE_THRESHOLD` (configurable, default 3) → set `posts.is_hidden = true` → post disappears from all feeds → admin reviews via `GET /admin/reports` → admin actions (keep hidden, un-hide, delete)

**Database changes:**
- Add `is_hidden BOOLEAN NOT NULL DEFAULT FALSE` to `posts` table
- Feed queries add `AND is_hidden = FALSE` filter (non-admin only)

**Config:** `REPORT_RATE_LIMIT = 5`, `REPORT_RATE_WINDOW_SECONDS = 3600`, `REPORT_AUTO_HIDE_THRESHOLD = 3`

### User-to-User Blocking

**Database:**
```sql
CREATE TABLE blocked_users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id UUID NOT NULL REFERENCES users(id),
    blocked_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(blocker_id, blocked_id),
    CHECK (blocker_id != blocked_id)
);
-- RLS: blocker_id = auth.uid()
-- Indexes on blocker_id and blocked_id
```

**Effects:** Bidirectional feed hiding, comment blocking, card visibility restriction.

**Mobile UI:**
- FeedCard long-press menu: Share, Block @username, Report, Cancel
- Profile page: three-dot menu → Block @username
- Settings → Blocked Users → Unblock

### Admin Bans

**Database:** Add `is_banned BOOLEAN DEFAULT FALSE`, `banned_at TIMESTAMPTZ`, `ban_reason TEXT` to `users`.

**Effects:** Auth rejected with `ACCOUNT_BANNED` at `get_current_user` dependency level. All posts set `is_hidden = true`.

### API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/posts/{postId}/report` | JWT | Submit report (un-deprecate existing endpoint + add auto-hide) |
| POST | `/v1/users/{userId}/block` | JWT | Block user (idempotent) |
| DELETE | `/v1/users/{userId}/block` | JWT | Unblock user |
| GET | `/v1/users/blocked` | JWT | List blocked users (paginated) |
| GET | `/admin/reports` | Admin key | List reports by status (paginated) |
| PATCH | `/admin/reports/{reportId}` | Admin key | Update status (reviewed/actioned/dismissed) |
| POST | `/admin/users/{userId}/ban` | Admin key | Ban user + hide all posts |
| DELETE | `/admin/users/{userId}/ban` | Admin key | Unban + un-hide posts |
| PATCH | `/admin/posts/{postId}` | Admin key | Manual show/hide post |

---

## Part III: Implementation Tasks

### Task 1: Backend — Extract model costs and Sonnet model to config

**Findings:** B-1, B-3

**Files:**
- Modify: `app/config/__init__.py`
- Modify: `app/generation/adapters/falai.py:120-127`
- Modify: `app/advisor/service.py:39`

- [ ] **Step 1:** Add config fields to `app/config/__init__.py` after generation config:
```python
    FAL_COST_FLUX_PULID: float = 0.035
    FAL_COST_FLUX_DEV_IMG2IMG: float = 0.026
    FAL_COST_INSTANTID: float = 0.020
    FAL_COST_DEFAULT: float = 0.035
    ADVISOR_MODEL_SONNET: str = "claude-3-5-sonnet-20241022"
```

- [ ] **Step 2:** Update `_estimate_cost` in `falai.py` to read `settings.FAL_COST_*` instead of hardcoded dict. Add `from app.config import settings` if missing.

- [ ] **Step 3:** Change `_MODEL_SONNET` in `service.py` to `settings.ADVISOR_MODEL_SONNET`.

- [ ] **Step 4:** Lint + syntax check. Commit.

---

### Task 1b: Backend — Fix redundant truthiness check

**Finding:** B-7

**Files:**
- Modify: `app/entitlement/service.py:130-133`

- [ ] **Step 1:** Remove `has_subscription` variable. Replace `if has_subscription and sub_result.data:` with `if sub_result.data:`. Verify `has_subscription` isn't used elsewhere in the function.

- [ ] **Step 2:** Commit.

---

### Task 2: Backend — Fix fragile exception handling in trial grantor

**Finding:** B-2

**Files:**
- Modify: `app/entitlement/trial_grantor.py:50-58`

- [ ] **Step 1:** Check what exception type Supabase PostgREST raises: `python -c "from postgrest.exceptions import APIError; print(APIError.__doc__)"`.

- [ ] **Step 2:** Replace lines 50-58 with structured check:
```python
        except Exception as exc:
            pg_code = getattr(exc, "code", None)
            if pg_code == "23505":
                logger.info("trial_grant already applied for user %s — skipping", user_id_str)
                return
            exc_str = str(exc).lower()
            if "23505" in exc_str or "unique_violation" in exc_str:
                logger.info("trial_grant already applied for user %s — skipping", user_id_str)
                return
            logger.error("grant_trial RPC failed for user %s: %s", user_id_str, exc)
            raise RuntimeError(f"Failed to grant trial for user {user_id_str}") from exc
```

- [ ] **Step 3:** Lint + compile check. Commit.

---

### Task 3: Backend — Atomic concurrent counter cleanup via Lua script

**Finding:** B-4

**Files:**
- Modify: `app/generation/worker.py`

- [ ] **Step 1:** Add Lua script constant at module level:
```python
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

- [ ] **Step 2:** Add SHA caching inside `process_generation_job` after Redis assignment:
```python
    cleanup_sha_key = "_concurrent_cleanup_sha"
    if cleanup_sha_key not in ctx:
        ctx[cleanup_sha_key] = await redis.script_load(_CONCURRENT_CLEANUP_SCRIPT)
    cleanup_sha = ctx[cleanup_sha_key]
```

- [ ] **Step 3:** Replace `finally` block to use `redis.evalsha(cleanup_sha, 1, key, ttl)`.

- [ ] **Step 4:** Lint check. Commit.

---

### Task 4: Backend — Migrations for moderation system

**Files:**
- Create: `app/migrations/0023_post_hidden.sql`
- Create: `app/migrations/0024_blocked_users.sql`
- Create: `app/migrations/0025_user_bans.sql`

- [ ] **Step 1:** Create `0023_post_hidden.sql`:
```sql
ALTER TABLE posts ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX idx_posts_hidden ON posts(is_hidden) WHERE is_hidden = TRUE;
```

- [ ] **Step 2:** Create `0024_blocked_users.sql`:
```sql
CREATE TABLE blocked_users (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id UUID NOT NULL REFERENCES users(id),
    blocked_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(blocker_id, blocked_id),
    CHECK (blocker_id != blocked_id)
);

ALTER TABLE blocked_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocked_users FORCE ROW LEVEL SECURITY;

CREATE POLICY blocked_users_own ON blocked_users
  FOR ALL TO authenticated
  USING (blocker_id = auth.uid())
  WITH CHECK (blocker_id = auth.uid());

CREATE INDEX idx_blocked_users_blocker ON blocked_users(blocker_id);
CREATE INDEX idx_blocked_users_blocked ON blocked_users(blocked_id);
```

- [ ] **Step 3:** Create `0025_user_bans.sql`:
```sql
ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN banned_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN ban_reason TEXT;
CREATE INDEX idx_users_banned ON users(is_banned) WHERE is_banned = TRUE;
```

- [ ] **Step 4:** Commit.

---

### Task 5: Backend — Report auto-hide and config

**Findings:** M-2 (backend portion)

**Files:**
- Modify: `app/config/__init__.py`
- Modify: `app/api/posts.py:359-398`
- Modify: `app/repositories/post_repo.py`

- [ ] **Step 1:** Add config fields:
```python
    REPORT_RATE_LIMIT: int = 5
    REPORT_RATE_WINDOW_SECONDS: int = 3600
    REPORT_AUTO_HIDE_THRESHOLD: int = 3
```

- [ ] **Step 2:** In `post_repo.py`, add `count_reports(post_id)` and `hide_post(post_id)` methods:
```python
def count_reports(self, post_id: str) -> int:
    result = (
        self._sb.table("reports")
        .select("reporter_user_id", count="exact")
        .eq("post_id", post_id)
        .execute()
    )
    return result.count or 0

def hide_post(self, post_id: str) -> None:
    self._sb.table("posts").update({"is_hidden": True}).eq("id", post_id).execute()

def unhide_post(self, post_id: str) -> None:
    self._sb.table("posts").update({"is_hidden": False}).eq("id", post_id).execute()
```

- [ ] **Step 3:** Update `report_post` in `posts.py`: remove `deprecated=True`, use config for rate limits, add auto-hide check after insert:
```python
    report = post_repo.insert_report(...)

    # Auto-hide: count unique reporters, hide if threshold reached
    report_count = post_repo.count_reports(str(post_id))
    if report_count >= settings.REPORT_AUTO_HIDE_THRESHOLD:
        post_repo.hide_post(str(post_id))
        logger.warning("Post %s auto-hidden: %d reports", post_id, report_count)
```

- [ ] **Step 4:** Update feed queries in `app/repositories/feed_repo.py` to filter `is_hidden = FALSE`. Add `.eq("is_hidden", False)` to `fetch_newest()` and update RPC functions if needed.

- [ ] **Step 5:** Lint check. Commit.

---

### Task 6: Backend — Block/unblock API

**Files:**
- Create: `app/repositories/block_repo.py`
- Create: `app/api/blocks.py`
- Modify: `app/main.py` (register router)

- [ ] **Step 1:** Create `app/repositories/block_repo.py`:
```python
class BlockRepository:
    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    def block(self, blocker_id: str, blocked_id: str) -> dict:
        result = self._sb.table("blocked_users").upsert(
            {"blocker_id": blocker_id, "blocked_id": blocked_id},
            on_conflict="blocker_id,blocked_id",
        ).execute()
        return (result.data or [{}])[0]

    def unblock(self, blocker_id: str, blocked_id: str) -> bool:
        result = (
            self._sb.table("blocked_users")
            .delete()
            .eq("blocker_id", blocker_id)
            .eq("blocked_id", blocked_id)
            .execute()
        )
        return len(result.data or []) > 0

    def get_blocked_ids(self, user_id: str) -> list[str]:
        result = (
            self._sb.table("blocked_users")
            .select("blocked_id")
            .eq("blocker_id", user_id)
            .execute()
        )
        return [r["blocked_id"] for r in (result.data or [])]

    def get_blocker_ids(self, user_id: str) -> list[str]:
        result = (
            self._sb.table("blocked_users")
            .select("blocker_id")
            .eq("blocked_id", user_id)
            .execute()
        )
        return [r["blocker_id"] for r in (result.data or [])]

    def list_blocked(self, user_id: str, limit: int, cursor: str | None) -> list[dict]:
        # Paginated list of blocked users with display names
        query = (
            self._sb.table("blocked_users")
            .select("id, blocked_id, created_at, users!blocked_id(display_name, username)")
            .eq("blocker_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if cursor:
            try:
                cursor_created_at, cursor_id = cursor.split("|", 1)
            except ValueError:
                raise ValueError(f"Malformed cursor: '{cursor}'")
            query = query.or_(
                f"created_at.lt.{cursor_created_at},"
                f"and(created_at.eq.{cursor_created_at},id.lt.{cursor_id})"
            )
        return query.execute().data or []
```

- [ ] **Step 2:** Create `app/api/blocks.py` with `POST /users/{userId}/block`, `DELETE /users/{userId}/block`, `GET /users/blocked`. Follow existing route patterns (deps, auth, Pydantic models). Validate `blocker_id != blocked_id`.

- [ ] **Step 3:** Register router in `app/main.py` under `/v1`.

- [ ] **Step 4:** Update feed queries in `feed_repo.py` to exclude blocked users' posts (bidirectional). The feed endpoints need to accept the requesting user's ID (or None for guests) and filter accordingly.

- [ ] **Step 5:** Update comment queries in `post_repo.py` to exclude blocked users' comments and reject comments from blocked users on blocker's posts.

- [ ] **Step 6:** Lint check. Commit.

---

### Task 7: Backend — Admin endpoints (reports, bans, post management)

**Files:**
- Create: `app/api/admin.py`
- Modify: `app/api/deps.py` (add admin auth dependency)
- Modify: `app/main.py` (register admin router)

- [ ] **Step 1:** Add admin auth dependency to `deps.py`:
```python
def require_admin(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")
```

- [ ] **Step 2:** Create `app/api/admin.py` with:
  - `GET /admin/reports?status=pending&limit=50` — paginated, ordered by created_at DESC
  - `PATCH /admin/reports/{reportId}` — update status (reviewed/actioned/dismissed). If dismissed and post was auto-hidden, call `unhide_post`.
  - `POST /admin/users/{userId}/ban` — set `is_banned=True`, `banned_at=NOW()`, `ban_reason=body.reason`. Hide all user's posts.
  - `DELETE /admin/users/{userId}/ban` — unban. Un-hide posts hidden by the ban (not those hidden by reports — use a `hidden_reason` field or check report counts).
  - `PATCH /admin/posts/{postId}` — manual show/hide toggle
  - `GET /admin/users?banned=true` — list banned users

- [ ] **Step 3:** Add ban check to `get_current_user` in `deps.py`:
```python
# After JWT validation, check ban status
user_row = supabase.table("users").select("is_banned").eq("id", claims["sub"]).maybe_single().execute()
if user_row.data and user_row.data.get("is_banned"):
    raise HTTPException(status_code=403, detail={"error": {"code": "ACCOUNT_BANNED", "message": "Your account has been suspended."}})
```

- [ ] **Step 4:** Register admin router in `main.py`. Lint check. Commit.

---

### Task 8: Mobile — Report API client and handler

**Finding:** M-2 (mobile portion)

**Files:**
- Create: `mobile/lib/report.ts`
- Modify: `mobile/app/(tabs)/index.tsx:71-87`

- [ ] **Step 1:** Create `mobile/lib/report.ts`:
```typescript
import { apiFetch } from "./api";

interface ReportResponse {
  report_id: string;
  status: string;
}

export async function reportPost(
  postId: string,
  reason?: string,
): Promise<ReportResponse> {
  return apiFetch<ReportResponse>(`/v1/posts/${postId}/report`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}
```

- [ ] **Step 2:** Replace stub `handleReport` in `index.tsx` with real API call. Show success message on 201. Handle 429 with "You've submitted several reports recently" message. Handle other errors with generic "Failed to submit report" message.

- [ ] **Step 3:** Commit.

---

### Task 8b: Mobile — Block API client and UI

**Files:**
- Create: `mobile/lib/block.ts`
- Modify: `mobile/components/feed/FeedCard.tsx` (add Block to long-press menu)
- Modify: `mobile/app/(tabs)/index.tsx` (add block handler, filter blocked from local state)
- Modify: `mobile/components/feed/useFeed.ts` (add removePostsByUser method)

- [ ] **Step 1:** Create `mobile/lib/block.ts`:
```typescript
import { apiFetch } from "./api";

export async function blockUser(userId: string): Promise<void> {
  await apiFetch(`/v1/users/${userId}/block`, { method: "POST" });
}

export async function unblockUser(userId: string): Promise<void> {
  await apiFetch(`/v1/users/${userId}/block`, { method: "DELETE" });
}

interface BlockedUser {
  id: string;
  blocked_id: string;
  display_name: string | null;
  username: string | null;
  created_at: string;
}

export async function getBlockedUsers(cursor?: string): Promise<{
  users: BlockedUser[];
  next_cursor: string | null;
}> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  const query = params.toString();
  return apiFetch(`/v1/users/blocked${query ? `?${query}` : ""}`);
}
```

- [ ] **Step 2:** Update FeedCard long-press menu. Current options: Share, Report, Cancel. New options: Share, Block @{username}, Report, Cancel. The `onBlock` callback is passed as a new prop.

- [ ] **Step 3:** Add `handleBlock` in `index.tsx`:
```typescript
const handleBlock = useCallback(async (userId: string, username: string) => {
  Alert.alert(
    `Block @${username}?`,
    "They won't be able to see your posts or comment on them.",
    [
      { text: "Cancel", style: "cancel" },
      {
        text: "Block",
        style: "destructive",
        onPress: async () => {
          try {
            await blockUser(userId);
            removePostsByUser(userId);  // From useFeed
          } catch {
            Alert.alert("Error", "Failed to block user. Please try again.");
          }
        },
      },
    ],
  );
}, [removePostsByUser]);
```

- [ ] **Step 4:** Add `removePostsByUser(userId)` to `useFeed.ts` — filters out all posts by that user from local state.

- [ ] **Step 5:** Add Block option to profile page three-dot menu (same API call + navigate back to feed).

- [ ] **Step 6:** Commit.

---

### Task 9: Mobile — Implement share on result screen + remove Save

**Finding:** M-1

**Files:**
- Modify: `mobile/app/result/[jobId].tsx`

- [ ] **Step 1:** Read `mobile/lib/analysis.ts` to confirm `JobResult` field names for post ID and image URL.

- [ ] **Step 2:** Check `UNIVERSAL_LINK_ORIGIN` availability: `grep -rn "UNIVERSAL_LINK_ORIGIN" mobile/`. Import if needed.

- [ ] **Step 3:** Replace `handleShare` stub with universal link share:
```typescript
const handleShare = useCallback(async () => {
  const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/posts/${result?.post_id ?? jobId}`;
  try {
    await Share.share(
      Platform.OS === "ios" ? { url: shareUrl } : { message: shareUrl },
    );
  } catch {
    // User cancelled — not an error
  }
}, [result, jobId]);
```

- [ ] **Step 4:** Delete `handleSave` callback and remove its Pressable button from the JSX. The CTA row becomes: Share + "This doesn't look like me".

- [ ] **Step 5:** Commit.

---

### Task 10: Mobile — Remove placeholder tabs

**Finding:** M-3

**Files:**
- Modify: `mobile/app/(tabs)/_layout.tsx`
- Delete: `mobile/app/(tabs)/search.tsx`
- Delete: `mobile/app/(tabs)/notifications.tsx`

- [ ] **Step 1:** Remove `<Tabs.Screen name="search">` and `<Tabs.Screen name="notifications">` from `_layout.tsx`.

- [ ] **Step 2:** Delete the two placeholder files.

- [ ] **Step 3:** TypeScript check: `cd mobile && npx tsc --noEmit`.

- [ ] **Step 4:** Commit.

---

### Task 11: Mobile — Comment count update + stale TODO + memory rollback

**Findings:** M-4, M-6, M-11

**Files:**
- Modify: `mobile/components/feed/useFeed.ts`
- Modify: `mobile/app/(tabs)/index.tsx:64-69`
- Modify: `mobile/app/(tabs)/profile.tsx:61`
- Modify: `mobile/components/advisor/MemoryList.tsx:517-524`

- [ ] **Step 1:** Add `incrementCommentCount` and `decrementCommentCount` to `useFeed.ts`:
```typescript
const incrementCommentCount = useCallback((postId: string) => {
  setPosts((prev) => prev.map((p) =>
    p.post_id === postId ? { ...p, comment_count: (p.comment_count ?? 0) + 1 } : p,
  ));
}, []);
```

- [ ] **Step 2:** Wire it in `index.tsx`. The comment posting caller should increment first, then call the API, and decrement on failure.

- [ ] **Step 3:** Delete stale TODO in `profile.tsx:61`.

- [ ] **Step 4:** Fix memory delete rollback — capture item before removal, re-insert on failure (sorted by `created_at` DESC).

- [ ] **Step 5:** Commit.

---

### Task 12: Mobile — Infinite scroll error handling (6 locations)

**Finding:** M-5

**Files:**
- Modify: `mobile/components/feed/useFeed.ts`
- Modify: `mobile/components/advisor/ChatView.tsx`
- Modify: `mobile/components/advisor/NudgeFeed.tsx`
- Modify: `mobile/components/advisor/MemoryList.tsx`
- Modify: `mobile/components/comments/useComments.ts`
- Modify: `mobile/app/onboarding.tsx`

- [ ] **Step 1:** In each hook/component, replace silent catch with auto-retry:
```typescript
const retryCountRef = useRef(0);
const [paginationFailed, setPaginationFailed] = useState(false);

// In the catch block:
} catch (err) {
  retryCountRef.current += 1;
  if (retryCountRef.current < 3) {
    const delay = retryCountRef.current === 1 ? 2000 : 3000;
    setTimeout(() => loadMore(), delay);
  } else {
    setPaginationFailed(true);
  }
}

// On successful load:
retryCountRef.current = 0;
setPaginationFailed(false);
```

- [ ] **Step 2:** Expose `paginationFailed` from hooks. In components, render inline text at list bottom:
```tsx
{paginationFailed && (
  <Text style={styles.paginationError}>
    Something went wrong. Pull down to refresh.
  </Text>
)}
```

- [ ] **Step 3:** For `onboarding.tsx` entitlement fetch: keep non-blocking, add descriptive `console.warn` message.

- [ ] **Step 4:** Commit.

---

### Task 13: Mobile — Design system compliance

**Findings:** M-7, M-8

**Files:**
- Modify: `mobile/constants/colors.ts`
- Modify: `mobile/components/feed/FeedCard.tsx:254`
- Modify: `mobile/app/result/[jobId].tsx`

- [ ] **Step 1:** Add `AFTER_OVERLAY_STRONG` to `colors.ts`:
```typescript
export const AFTER_OVERLAY_STRONG = "rgba(244, 63, 94, 0.72)";
```

- [ ] **Step 2:** Replace hardcoded rgba in `FeedCard.tsx:254` with `AFTER_OVERLAY_STRONG`.

- [ ] **Step 3:** In `result/[jobId].tsx`, replace hardcoded spacing values that are multiples of 8 with `SPACING * n`. Leave non-multiples as-is.

- [ ] **Step 4:** Commit.

---

### Task 14: Card-Web — Fix placeholder URL and dead export

**Findings:** C-1, C-2

**Files:**
- Modify: `card-web/src/config/constants.ts`
- Modify: `card-web/src/components/cta-button.tsx`

- [ ] **Step 1:** Change App Store URL fallback from `id0000000000` to empty string. Guard in `cta-button.tsx`: only redirect to store if `storeUrl` is non-empty.

- [ ] **Step 2:** Delete unused `PUBLIC_API_BASE_URL` export. Verify nothing imports it: `grep -rn "PUBLIC_API_BASE_URL" card-web/src/`.

- [ ] **Step 3:** ESLint + TypeScript check. Commit.

---

### Task 15: Card-Web — Design tokens, OG colors, CTA leak, test cleanup

**Findings:** C-3, C-4, C-5, C-6

**Files:**
- Modify: `card-web/src/components/card-view.tsx`
- Modify: `card-web/src/app/[username]/opengraph-image.tsx`
- Modify: `card-web/src/components/cta-button.tsx`
- Modify: `card-web/src/__tests__/smoke.test.ts`

- [ ] **Step 1:** Read `card-web/tailwind.config.ts` to find available design tokens. Replace 3 hardcoded rgba values in `card-view.tsx` with Tailwind classes or CSS variables.

- [ ] **Step 2:** Extract OG image colors to `const OG = { BG: '#080808', TEXT_PRIMARY: '#F8F8F8', ... } as const` at top of `opengraph-image.tsx`. Replace all inline hex values.

- [ ] **Step 3:** Fix CTA button listener leak — add safety cleanup `setTimeout` after `APP_OPEN_TIMEOUT_MS + 500`. Wrap `window.location.href = universalLink` in try/catch.

- [ ] **Step 4:** Replace `void _username` with `const { username: _, ...withoutUsername }` in test.

- [ ] **Step 5:** ESLint + TypeScript check. Commit.

---

### Task 16: Final verification

- [ ] **Step 1:** Backend lint: `flake8 app/ --max-line-length 120 --select E,F --ignore W503`
- [ ] **Step 2:** Card-web: `cd card-web && npx tsc --noEmit && npx eslint src/ --max-warnings 0`
- [ ] **Step 3:** Verify no remaining TODOs: `grep -rn "TODO\|FIXME\|HACK\|XXX" --include="*.py" --include="*.ts" --include="*.tsx" app/ mobile/ card-web/src/ | grep -v node_modules` (only `app.json:_TODO_H6` acceptable)
- [ ] **Step 4:** Create PR and merge.
