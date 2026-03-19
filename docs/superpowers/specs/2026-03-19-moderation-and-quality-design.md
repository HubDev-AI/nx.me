# Moderation Pipeline & Code Quality Remediation Design

**Date:** 2026-03-19
**Scope:** Full moderation system (report → auto-hide → admin review), user blocking, admin bans, plus remaining code quality fixes from audit

---

## 1. Report Pipeline

### Current State
- `reports` table exists with `id`, `post_id`, `reporter_user_id`, `reason`, `status` (pending/reviewed/actioned/dismissed), `created_at`
- RLS: users see only their own reports
- Indexes on `post_id` and `status`
- Backend endpoint `POST /v1/posts/{postId}/report` exists (functional, marked deprecated)
- Mobile has the UI flow (FeedCard long-press → Report) but the handler is a stub — shows fake success alert without calling API

### Design

**Submission flow:**
1. User long-presses FeedCard → taps Report → confirmation dialog → calls `POST /v1/posts/{postId}/report`
2. Backend: rate-limit check (configurable, default 5/hour), verify post exists, insert report row
3. Backend: after insert, count distinct reporters for this post. If count >= `REPORT_AUTO_HIDE_THRESHOLD` (configurable, default 3), set `posts.is_hidden = true`
4. Return `{report_id, status: "pending"}` to mobile
5. Mobile: show "Report submitted — we'll review this post"

**Auto-hide mechanism:**
- Add `is_hidden BOOLEAN NOT NULL DEFAULT FALSE` column to `posts` table (migration)
- Feed queries already filter `is_deleted = FALSE`; extend to also filter `is_hidden = FALSE` for non-admin users
- When auto-hide triggers, update the post row immediately. Post becomes invisible in all feeds.
- Admin can un-hide via `PATCH /admin/posts/{postId}` with `{is_hidden: false}`

**Admin review:**
- `GET /admin/reports?status=pending&limit=50` — paginated list of pending reports, ordered by created_at DESC
- `PATCH /admin/reports/{reportId}` — update status to `reviewed`, `actioned`, or `dismissed`
- `actioned` status: post stays hidden (or gets deleted if admin chooses)
- `dismissed` status: if auto-hidden, un-hide the post automatically
- All admin endpoints require `ADMIN_API_KEY` header (existing pattern in the codebase)

**Config additions (`app/config/__init__.py`):**
```
REPORT_RATE_LIMIT: int = 5
REPORT_RATE_WINDOW_SECONDS: int = 3600
REPORT_AUTO_HIDE_THRESHOLD: int = 3
```

---

## 2. User-to-User Blocking

### Database

New `blocked_users` table:
```sql
CREATE TABLE blocked_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    blocker_id    UUID NOT NULL REFERENCES users(id),
    blocked_id    UUID NOT NULL REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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

### Backend API

- `POST /v1/users/{userId}/block` — create block relationship (idempotent — ignore if exists)
- `DELETE /v1/users/{userId}/block` — remove block relationship
- `GET /v1/users/blocked` — list blocked users (paginated)

### Feed Filtering

Modify feed queries to exclude posts by users the requesting user has blocked AND posts by users who have blocked the requesting user (bidirectional hiding):

```sql
-- In feed_trending, feed_newest, etc.:
WHERE p.user_id NOT IN (
    SELECT blocked_id FROM blocked_users WHERE blocker_id = p_requesting_user_id
    UNION
    SELECT blocker_id FROM blocked_users WHERE blocked_id = p_requesting_user_id
)
```

For unauthenticated feed (guest users), no block filtering applies.

### Comment Filtering

Blocked users' comments are hidden from the blocker's view. Comments query adds same exclusion. Blocked users cannot create comments on the blocker's posts (return 403).

### Card Visibility

Blocked users cannot view the blocker's card page. Card-web fetches from the backend; backend returns 404 for blocked relationships (requires auth check in the card data endpoint).

### Mobile UI

**FeedCard long-press menu** (existing, add "Block" option):
- iOS ActionSheet: Share, Block @username, Report, Cancel
- Android Alert: same options
- Block confirmation: "Block @username? They won't be able to see your posts or comment on them."
- On confirm: `POST /v1/users/{userId}/block`, then remove their posts from local feed state

**Profile page** (other user's profile):
- Three-dot menu → "Block @username"
- Same confirmation dialog and API call
- After blocking: navigate back to feed

**Unblock:**
- Settings → Blocked Users → list with Unblock buttons
- Or from the blocked user's profile (if navigated to directly via link)

---

## 3. Admin Bans

### Database

Add columns to `users` table:
```sql
ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN banned_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN ban_reason TEXT;
```

### Backend API (Admin)

- `POST /admin/users/{userId}/ban` — set `is_banned = true`, `banned_at = NOW()`, `ban_reason = body.reason`. Hide all user's posts (`UPDATE posts SET is_hidden = true WHERE user_id = ...`).
- `DELETE /admin/users/{userId}/ban` — unban. Un-hide posts that were hidden by the ban (not those hidden by reports).
- `GET /admin/users?banned=true` — list banned users

### Auth Check

Banned users attempting to authenticate get a 403 with `{"code": "ACCOUNT_BANNED", "message": "Your account has been suspended."}`. Check at the `get_current_user` dependency level — if user row has `is_banned = true`, reject.

### Feed Filtering

Banned users' posts are already hidden via `is_hidden = true`. No additional feed query changes needed beyond what report auto-hide already adds.

---

## 4. Result Screen Changes

### Remove Save Button

Delete `handleSave` callback and its "Save" `Pressable` from the result screen JSX. The CTA row becomes: Share, "This doesn't look like me" (refund).

### Share Implementation

Use universal link share (same pattern as FeedCard):
```typescript
const handleShare = useCallback(async () => {
  const shareUrl = `${UNIVERSAL_LINK_ORIGIN}/posts/${postId}`;
  try {
    await Share.share(
      Platform.OS === "ios" ? { url: shareUrl } : { message: shareUrl }
    );
  } catch {
    // User cancelled — not an error
  }
}, [postId]);
```

Card-web's OG image renderer handles the visual preview when the link is shared.

---

## 5. Comment Count Optimistic Update

Add `incrementCommentCount(postId)` to the `useFeed` hook. Updates local state immediately. On comment API failure, decrement back:

```typescript
// In CommentsSheet or wherever the comment is posted:
incrementCommentCount(postId);
try {
  await postComment(postId, content);
} catch {
  decrementCommentCount(postId);  // Rollback
  // Show error
}
```

Both increment and decrement are state updates on the feed's posts array — no API calls.

---

## 6. Infinite Scroll Error Handling

Replace all 6 silent catch blocks with auto-retry pattern:

**On pagination failure:**
1. Wait 2 seconds, retry automatically
2. If retry fails, wait 3 seconds, retry again
3. After 3 total failures: show inline text at list bottom — "Something went wrong. Pull down to refresh."
4. No buttons, no modals, no interruption to scroll

**Implementation:** Each hook/component that does pagination gets a `retryCount` ref. On catch, increment and schedule retry via `setTimeout`. On success, reset to 0. After 3 failures, set a `paginationFailed` state that renders the inline message.

For `onboarding.tsx` entitlement fetch: keep silent (non-blocking), but log with context.

---

## 7. Remaining Code Quality Fixes (from audit)

These are unchanged from the original plan and are mechanical fixes:

| Finding | Fix |
|---------|-----|
| B-1 | Move hardcoded model costs to config |
| B-2 | Structured exception handling in trial grantor |
| B-3 | Move Sonnet model to config |
| B-4 | Atomic concurrent counter cleanup via Lua script |
| B-7 | Remove redundant truthiness check |
| M-3 | Delete placeholder Search/Notifications tabs |
| M-6 | Remove stale TODO comment |
| M-7 | Use design system color constant in FeedCard |
| M-11 | Optimistic memory delete with proper rollback |
| C-1 | Remove placeholder App Store URL fallback |
| C-2 | Remove dead `PUBLIC_API_BASE_URL` export |
| C-3 | Use Tailwind design tokens in card-view |
| C-4 | Extract OG image colors to constants |
| C-5 | Fix event listener leak in CTA button |
| C-6 | Remove void no-op in test |

---

## Migration Summary

New migrations needed:
1. `ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE ON posts`
2. `CREATE TABLE blocked_users` with RLS, indexes, constraints
3. `ADD COLUMNS is_banned, banned_at, ban_reason ON users`

---

## API Endpoint Summary

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/posts/{postId}/report` | JWT | Submit report (existing, un-deprecate) |
| POST | `/v1/users/{userId}/block` | JWT | Block a user |
| DELETE | `/v1/users/{userId}/block` | JWT | Unblock a user |
| GET | `/v1/users/blocked` | JWT | List blocked users |
| GET | `/admin/reports` | Admin key | List reports (filterable by status) |
| PATCH | `/admin/reports/{reportId}` | Admin key | Update report status |
| POST | `/admin/users/{userId}/ban` | Admin key | Ban user + hide all posts |
| DELETE | `/admin/users/{userId}/ban` | Admin key | Unban user + un-hide posts |
| PATCH | `/admin/posts/{postId}` | Admin key | Show/hide post manually |
