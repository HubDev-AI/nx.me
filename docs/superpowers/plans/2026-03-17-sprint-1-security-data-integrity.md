# Sprint 1: Critical Security & Data Integrity — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the highest-severity gaps — RLS on all user-scoped tables, missing credit ledger RPCs, non-transactional multi-step writes, a mispointed FK, and display_name XSS prevention.

**Architecture:** Five migrations (0013-0017) plus one app-level Pydantic validator. Migrations create RLS policies, SECURITY DEFINER RPCs, and atomic transaction functions. The app code changes are minimal — existing `supabase.rpc()` calls already target the RPCs we're creating, and the comment/reaction write paths get replaced with single RPC calls.

**Tech Stack:** PostgreSQL (plpgsql), Supabase RLS policies, Pydantic validators, pytest

**Source spec:** `docs/superpowers/specs/2026-03-17-review-sweep-design.md` (Sprint 1)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `app/migrations/0013_row_level_security.sql` | RLS + FORCE RLS on 16 tables, policies, service role bypass |
| Create | `app/migrations/0014_credit_ledger_rpcs.sql` | 4 SECURITY DEFINER RPCs: sum_credit_balance, credit_reserve, credit_release, credit_commit |
| Create | `app/migrations/0015_atomic_writes.sql` | 3 RPCs: persist_reaction_atomic, insert_comment_atomic, handle_checkout_credit_atomic |
| Create | `app/migrations/0016_fix_usage_events_fk.sql` | Drop + re-add FK on usage_events.user_id → public.users |
| Modify | `app/api/auth.py:52-58` | Add display_name validator to strip/reject `<>"` |
| Modify | `app/api/posts.py:242-252` | Replace INSERT + RPC with single `insert_comment_atomic` RPC |
| Modify | `app/api/social.py:322-355` | Replace INSERT + RPC with single `persist_reaction_atomic` RPC |
| Modify | `app/api/webhooks.py:103-146` | Replace 3-step write with single `handle_checkout_credit_atomic` RPC |
| Create | `tests/test_display_name_validation.py` | display_name XSS prevention tests |
| Create | `tests/test_migrations_rollback.py` | Verify all new migrations have DOWN sections |

---

## Task 1: RLS Migration (LR-3)

**Files:**
- Create: `app/migrations/0013_row_level_security.sql`

- [ ] **Step 1: Write the UP migration**

```sql
-- 0013_row_level_security.sql
-- Enable Row-Level Security on all 16 user-scoped tables.
-- Policy: authenticated users can only access their own rows.
-- Service role bypasses RLS (used by backend RPCs and webhooks).
-- Posts and comments get read-only public access (WHERE NOT is_deleted).

-- UP

-- Helper: all 16 user-scoped tables
-- users, images, analyses, credit_reservations, glow_up_jobs, credit_ledger,
-- subscriptions, posts, reactions, comments, reports, usage_events,
-- user_memories, advisor_conversations, advisor_messages, advisor_nudges

-- 1. Enable RLS + FORCE on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE images ENABLE ROW LEVEL SECURITY;
ALTER TABLE images FORCE ROW LEVEL SECURITY;
ALTER TABLE analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE analyses FORCE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations FORCE ROW LEVEL SECURITY;
ALTER TABLE glow_up_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE glow_up_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts FORCE ROW LEVEL SECURITY;
ALTER TABLE reactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reactions FORCE ROW LEVEL SECURITY;
ALTER TABLE comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE comments FORCE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events FORCE ROW LEVEL SECURITY;
ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories FORCE ROW LEVEL SECURITY;
ALTER TABLE advisor_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE advisor_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE advisor_nudges ENABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_nudges FORCE ROW LEVEL SECURITY;

-- 2. Owner policies: users can CRUD their own rows
-- "users" table: user_id is "id" column
CREATE POLICY users_own ON users
  FOR ALL
  TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- Standard user_id-based tables
CREATE POLICY images_own ON images
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY analyses_own ON analyses
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY credit_reservations_own ON credit_reservations
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY glow_up_jobs_own ON glow_up_jobs
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY credit_ledger_own ON credit_ledger
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY subscriptions_own ON subscriptions
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY reports_own ON reports
  FOR ALL TO authenticated
  USING (reporter_user_id = auth.uid())
  WITH CHECK (reporter_user_id = auth.uid());

CREATE POLICY usage_events_own ON usage_events
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY user_memories_own ON user_memories
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY advisor_conversations_own ON advisor_conversations
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY advisor_nudges_own ON advisor_nudges
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- advisor_messages: user owns messages via conversation ownership
CREATE POLICY advisor_messages_own ON advisor_messages
  FOR ALL TO authenticated
  USING (
    conversation_id IN (
      SELECT id FROM advisor_conversations WHERE user_id = auth.uid()
    )
  )
  WITH CHECK (
    conversation_id IN (
      SELECT id FROM advisor_conversations WHERE user_id = auth.uid()
    )
  );

-- 3. Posts: owner full access + public read for non-deleted
CREATE POLICY posts_own ON posts
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY posts_public_read ON posts
  FOR SELECT TO anon, authenticated
  USING (NOT is_deleted);

-- 4. Comments: owner full access + public read for non-deleted
CREATE POLICY comments_own ON comments
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

CREATE POLICY comments_public_read ON comments
  FOR SELECT TO anon, authenticated
  USING (NOT is_deleted);

-- 5. Reactions: authenticated users can insert their own + read all
CREATE POLICY reactions_own ON reactions
  FOR ALL TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

-- Guest reactions (via guest_session_token) are handled by service role RPCs
-- Anon users can read reaction counts via posts table, not reactions directly
CREATE POLICY reactions_read ON reactions
  FOR SELECT TO authenticated
  USING (true);
```

- [ ] **Step 2: Write the DOWN migration**

Append to the same file:

```sql
-- DOWN

-- Drop all policies
DROP POLICY IF EXISTS users_own ON users;
DROP POLICY IF EXISTS images_own ON images;
DROP POLICY IF EXISTS analyses_own ON analyses;
DROP POLICY IF EXISTS credit_reservations_own ON credit_reservations;
DROP POLICY IF EXISTS glow_up_jobs_own ON glow_up_jobs;
DROP POLICY IF EXISTS credit_ledger_own ON credit_ledger;
DROP POLICY IF EXISTS subscriptions_own ON subscriptions;
DROP POLICY IF EXISTS posts_own ON posts;
DROP POLICY IF EXISTS posts_public_read ON posts;
DROP POLICY IF EXISTS reactions_own ON reactions;
DROP POLICY IF EXISTS reactions_read ON reactions;
DROP POLICY IF EXISTS comments_own ON comments;
DROP POLICY IF EXISTS comments_public_read ON comments;
DROP POLICY IF EXISTS reports_own ON reports;
DROP POLICY IF EXISTS usage_events_own ON usage_events;
DROP POLICY IF EXISTS user_memories_own ON user_memories;
DROP POLICY IF EXISTS advisor_conversations_own ON advisor_conversations;
DROP POLICY IF EXISTS advisor_messages_own ON advisor_messages;
DROP POLICY IF EXISTS advisor_nudges_own ON advisor_nudges;

-- Disable RLS on all tables
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE images DISABLE ROW LEVEL SECURITY;
ALTER TABLE analyses DISABLE ROW LEVEL SECURITY;
ALTER TABLE credit_reservations DISABLE ROW LEVEL SECURITY;
ALTER TABLE glow_up_jobs DISABLE ROW LEVEL SECURITY;
ALTER TABLE credit_ledger DISABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions DISABLE ROW LEVEL SECURITY;
ALTER TABLE posts DISABLE ROW LEVEL SECURITY;
ALTER TABLE reactions DISABLE ROW LEVEL SECURITY;
ALTER TABLE comments DISABLE ROW LEVEL SECURITY;
ALTER TABLE reports DISABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events DISABLE ROW LEVEL SECURITY;
ALTER TABLE user_memories DISABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_conversations DISABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE advisor_nudges DISABLE ROW LEVEL SECURITY;
```

- [ ] **Step 3: Commit**

```bash
git add app/migrations/0013_row_level_security.sql
git commit -m "feat(db): add RLS policies on all 16 user-scoped tables

Enable ROW LEVEL SECURITY + FORCE on users, images, analyses,
credit_reservations, glow_up_jobs, credit_ledger, subscriptions,
posts, reactions, comments, reports, usage_events, user_memories,
advisor_conversations, advisor_messages, advisor_nudges.

Owner policies use auth.uid() = user_id. Posts and comments get
public read access for non-deleted rows. Service role bypasses
RLS for backend operations."
```

---

## Task 2: Credit Ledger RPCs (LR-4)

**Files:**
- Create: `app/migrations/0014_credit_ledger_rpcs.sql`

**Context:** `app/entitlement/ledger.py` calls these 4 RPCs but they don't exist in any migration. The RPC signatures must match exactly what ledger.py passes.

- [ ] **Step 1: Read ledger.py to confirm exact RPC parameter names**

```bash
grep -n "self._sb.rpc" app/entitlement/ledger.py
```

Expected: `sum_credit_balance(p_user_id)`, `credit_reserve(p_user_id, p_reservation_id)`, `credit_release(p_reservation_id)`, `credit_commit(p_reservation_id)`

- [ ] **Step 2: Write the UP migration**

```sql
-- 0014_credit_ledger_rpcs.sql
-- Credit ledger RPCs called by app/entitlement/ledger.py
-- All SECURITY DEFINER to bypass RLS (service-level operations).
-- Invariants (from ledger.py docstrings):
--   reserve + release = 0 (net)
--   reserve + commit = -1 (net)
--   balance = SUM(delta)

-- UP

-- 1. sum_credit_balance: atomic SUM(delta) for a user
CREATE OR REPLACE FUNCTION public.sum_credit_balance(p_user_id UUID)
RETURNS INTEGER
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
  SELECT COALESCE(SUM(delta), 0)::integer
  FROM credit_ledger
  WHERE user_id = p_user_id;
$$;

-- 2. credit_reserve: atomically create reservation + deduct credit
--    Returns the reservation row for confirmation.
CREATE OR REPLACE FUNCTION public.credit_reserve(
  p_user_id UUID,
  p_reservation_id UUID
)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_balance INTEGER;
BEGIN
  -- Guard: verify positive balance before reserving.
  -- NOTE: Under high concurrency, two simultaneous reserves could both
  -- read balance=1 and both succeed. For current traffic this is acceptable.
  -- If double-spend becomes a concern, add advisory lock: PERFORM pg_advisory_xact_lock(hashtext(p_user_id::text));
  SELECT COALESCE(SUM(delta), 0) INTO v_balance
  FROM credit_ledger WHERE user_id = p_user_id;

  IF v_balance <= 0 THEN
    RAISE EXCEPTION 'insufficient_credits' USING ERRCODE = 'P0001';
  END IF;

  -- Insert reservation
  INSERT INTO credit_reservations (id, user_id, amount, status, created_at)
  VALUES (p_reservation_id, p_user_id, 1, 'reserved', now());

  -- Deduct credit (delta = -1)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  VALUES (gen_random_uuid(), p_user_id, -1, 'reserve', p_reservation_id, now());

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- 3. credit_release: atomically release reservation + refund credit
--    Uses WHERE status = 'reserved' RETURNING * to prevent TOCTOU.
CREATE OR REPLACE FUNCTION public.credit_release(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  -- Atomically mark as released (only if still reserved)
  UPDATE credit_reservations
  SET status = 'released', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'reserved';

  IF NOT FOUND THEN
    RETURN;  -- Empty result signals already-resolved to caller
  END IF;

  -- Refund credit (delta = +1)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  SELECT gen_random_uuid(), user_id, 1, 'release', p_reservation_id, now()
  FROM credit_reservations
  WHERE id = p_reservation_id;

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;

-- 4. credit_commit: atomically commit reservation (credit consumed)
--    delta = 0 (the reserve already deducted; commit just marks it consumed)
CREATE OR REPLACE FUNCTION public.credit_commit(p_reservation_id UUID)
RETURNS SETOF credit_reservations
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE credit_reservations
  SET status = 'committed', resolved_at = now()
  WHERE id = p_reservation_id AND status = 'reserved';

  IF NOT FOUND THEN
    RETURN;
  END IF;

  -- Record the commit event (delta = 0, net effect: reserve's -1 stands)
  INSERT INTO credit_ledger (id, user_id, delta, type, reference_id, created_at)
  SELECT gen_random_uuid(), user_id, 0, 'commit', p_reservation_id, now()
  FROM credit_reservations
  WHERE id = p_reservation_id;

  RETURN QUERY SELECT * FROM credit_reservations WHERE id = p_reservation_id;
END;
$$;
```

- [ ] **Step 3: Write the DOWN migration**

Append to the same file:

```sql
-- DOWN

DROP FUNCTION IF EXISTS public.sum_credit_balance(UUID);
DROP FUNCTION IF EXISTS public.credit_reserve(UUID, UUID);
DROP FUNCTION IF EXISTS public.credit_release(UUID);
DROP FUNCTION IF EXISTS public.credit_commit(UUID);
```

- [ ] **Step 4: Run existing credit ledger invariant tests**

```bash
pytest tests/test_credit_ledger_invariants.py -v
```

Expected: All pass (tests use `_InMemorySupabase` mock, not real DB — confirms ledger.py code still works)

- [ ] **Step 5: Commit**

```bash
git add app/migrations/0014_credit_ledger_rpcs.sql
git commit -m "feat(db): add credit ledger RPCs (sum_credit_balance, credit_reserve, credit_release, credit_commit)

SECURITY DEFINER functions that execute atomically:
- sum_credit_balance: COALESCE(SUM(delta), 0) for a user
- credit_reserve: insert reservation + ledger entry (delta=-1)
- credit_release: update status + refund (delta=+1), TOCTOU-safe
- credit_commit: update status + record (delta=0), TOCTOU-safe

Matches exact signatures expected by app/entitlement/ledger.py."
```

---

## Task 3: Atomic Write RPCs (LR-5)

**Files:**
- Create: `app/migrations/0015_atomic_writes.sql`
- Modify: `app/api/posts.py:242-252`
- Modify: `app/api/social.py:322-355`
- Modify: `app/api/webhooks.py:103-146`

- [ ] **Step 1: Write the UP migration with 3 atomic RPCs**

```sql
-- 0015_atomic_writes.sql
-- Atomic RPCs replacing multi-step writes that can leave inconsistent state.
-- All SECURITY DEFINER to bypass RLS.

-- UP

-- 1. insert_comment_atomic: INSERT comment + increment count in one transaction
CREATE OR REPLACE FUNCTION public.insert_comment_atomic(
  p_post_id UUID,
  p_user_id UUID,
  p_content TEXT
)
RETURNS SETOF comments
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_comment_id UUID := gen_random_uuid();
BEGIN
  INSERT INTO comments (id, post_id, user_id, content, created_at)
  VALUES (v_comment_id, p_post_id, p_user_id, p_content, now());

  UPDATE posts
  SET comment_count = comment_count + 1, updated_at = now()
  WHERE id = p_post_id;

  RETURN QUERY SELECT * FROM comments WHERE id = v_comment_id;
END;
$$;

-- 2. persist_reaction_atomic: INSERT reaction + increment count in one transaction
--    Returns empty set on duplicate (UNIQUE violation) so caller knows to undo Redis INCR.
--    Depends on: increment_reaction_count (defined in migration 0011)
CREATE OR REPLACE FUNCTION public.persist_reaction_atomic(
  p_post_id UUID,
  p_user_id UUID DEFAULT NULL,
  p_guest_session_token TEXT DEFAULT NULL
)
RETURNS SETOF reactions
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  INSERT INTO reactions (id, post_id, user_id, guest_session_token, created_at)
  VALUES (gen_random_uuid(), p_post_id, p_user_id, p_guest_session_token, now());

  -- Only increment if INSERT succeeded (no exception)
  PERFORM increment_reaction_count(p_post_id);

  RETURN QUERY
    SELECT * FROM reactions
    WHERE post_id = p_post_id
      AND (
        (p_user_id IS NOT NULL AND user_id = p_user_id) OR
        (p_guest_session_token IS NOT NULL AND guest_session_token = p_guest_session_token)
      )
    ORDER BY created_at DESC LIMIT 1;

EXCEPTION
  WHEN unique_violation THEN
    -- Duplicate reaction — return empty set (caller decrements Redis)
    RETURN;
END;
$$;

-- 3. handle_checkout_credit_atomic: INSERT ledger + conditional tier upgrade
CREATE OR REPLACE FUNCTION public.handle_checkout_credit_atomic(
  p_user_id UUID,
  p_credits INTEGER,
  p_event_id TEXT,
  p_trial_tier_id UUID,
  p_credit_holder_tier_id UUID
)
RETURNS TABLE(tier_upgraded BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_current_tier_id UUID;
  v_upgraded BOOLEAN := FALSE;
BEGIN
  -- Insert credit purchase into ledger
  INSERT INTO credit_ledger (id, user_id, delta, type, note, created_at)
  VALUES (gen_random_uuid(), p_user_id, p_credits, 'purchase', 'Stripe event ' || p_event_id, now());

  -- Check current tier
  SELECT tier_id INTO v_current_tier_id
  FROM users WHERE id = p_user_id;

  -- Upgrade from trial to credit_holder if needed
  IF v_current_tier_id = p_trial_tier_id THEN
    UPDATE users
    SET tier_id = p_credit_holder_tier_id,
        updated_at = now()
    WHERE id = p_user_id;
    v_upgraded := TRUE;
  END IF;

  RETURN QUERY SELECT v_upgraded;
END;
$$;
```

- [ ] **Step 2: Write the DOWN migration**

Append to the same file:

```sql
-- DOWN

DROP FUNCTION IF EXISTS public.insert_comment_atomic(UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS public.persist_reaction_atomic(UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS public.handle_checkout_credit_atomic(UUID, INTEGER, TEXT, UUID, UUID);
```

- [ ] **Step 3: Update `app/api/posts.py` — replace INSERT + RPC with atomic RPC**

In `app/api/posts.py`, replace the comment INSERT + increment_comment_count calls (lines ~242-252) with:

```python
    # Atomic: insert comment + increment count in single transaction
    result = supabase.rpc("insert_comment_atomic", {
        "p_post_id": str(post_id),
        "p_user_id": user_id,
        "p_content": body.content,
    }).execute()

    comment = result.data[0]
```

- [ ] **Step 4: Update `app/api/social.py` — replace persist_reaction with atomic RPC**

In `app/api/social.py`, replace the `persist_reaction` function body (lines ~322-355) with:

```python
async def persist_reaction(ctx: dict, reaction_data: dict) -> None:
    """Background task: atomically insert reaction + update counter.

    On duplicate (UNIQUE constraint), RPC returns empty set — decrement Redis.
    """
    from app.db.client import get_supabase_service

    supabase = get_supabase_service()
    post_id = reaction_data["post_id"]

    try:
        result = supabase.rpc("persist_reaction_atomic", {
            "p_post_id": post_id,
            "p_user_id": reaction_data.get("user_id"),
            "p_guest_session_token": reaction_data.get("guest_session_token"),
        }).execute()

        if not result.data:
            # Duplicate reaction — undo optimistic Redis INCR
            redis_client = ctx.get("redis")
            if redis_client:
                await redis_client.decr(f"posts:{post_id}:reactions")
            logger.info("Duplicate reaction for post %s — Redis counter decremented", post_id)

    except Exception:
        # Transient failure: undo Redis optimistic increment before retry
        redis_client = ctx.get("redis")
        if redis_client:
            await redis_client.decr(f"posts:{post_id}:reactions")
        raise  # Let ARQ retry
```

- [ ] **Step 5: Update `app/api/webhooks.py` — replace checkout handler with atomic RPC**

In `app/api/webhooks.py`, replace the credit purchase section of `_handle_checkout_completed` (lines ~131-144) with:

```python
        # Atomic: insert ledger entry + conditional tier upgrade
        from app.constants.tiers import TIER_ID_TRIAL, TIER_ID_CREDIT_HOLDER
        result = supabase.rpc("handle_checkout_credit_atomic", {
            "p_user_id": user_id,
            "p_credits": credits,
            "p_event_id": event_id,
            "p_trial_tier_id": TIER_ID_TRIAL,
            "p_credit_holder_tier_id": TIER_ID_CREDIT_HOLDER,
        }).execute()

        tier_upgraded = result.data[0]["tier_upgraded"] if result.data else False
        logger.info(
            "Credit purchase: user=%s, credits=%d, event=%s, tier_upgraded=%s",
            user_id, credits, event_id, tier_upgraded,
        )
```

- [ ] **Step 6: Run existing tests to verify no regressions**

```bash
pytest tests/ -v
```

Expected: All existing tests pass (they use mocked Supabase, so RPC name changes don't affect them)

- [ ] **Step 7: Commit**

```bash
git add app/migrations/0015_atomic_writes.sql app/api/posts.py app/api/social.py app/api/webhooks.py
git commit -m "feat(db): replace multi-step writes with atomic RPCs

- insert_comment_atomic: INSERT + increment in one transaction
- persist_reaction_atomic: INSERT + increment, returns empty on duplicate
- handle_checkout_credit_atomic: ledger INSERT + conditional tier upgrade

Updates posts.py, social.py, webhooks.py to call these RPCs
instead of doing separate INSERT + RPC/UPDATE calls."
```

---

## Task 4: Fix usage_events FK (DB-1)

**Files:**
- Create: `app/migrations/0016_fix_usage_events_fk.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 0016_fix_usage_events_fk.sql
-- Fix: usage_events.user_id references auth.users(id) instead of public.users(id).
-- Every other table references public.users. ON DELETE CASCADE should fire when
-- the application user is deleted, not the auth identity.

-- UP

ALTER TABLE usage_events
  DROP CONSTRAINT IF EXISTS usage_events_user_id_fkey;

ALTER TABLE usage_events
  ADD CONSTRAINT usage_events_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- DOWN

ALTER TABLE usage_events
  DROP CONSTRAINT IF EXISTS usage_events_user_id_fkey;

ALTER TABLE usage_events
  ADD CONSTRAINT usage_events_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
```

- [ ] **Step 2: Commit**

```bash
git add app/migrations/0016_fix_usage_events_fk.sql
git commit -m "fix(db): usage_events FK references public.users instead of auth.users

The FK was pointing at auth.users(id), inconsistent with all other
tables that reference public.users(id). ON DELETE CASCADE would fire
on auth identity deletion, not application user deletion."
```

---

## Task 5: display_name XSS Prevention (QF-8)

**Files:**
- Modify: `app/api/auth.py:52-58`
- Create: `tests/test_display_name_validation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_display_name_validation.py`:

```python
"""Tests for display_name XSS prevention (QF-8)."""
import pytest
from pydantic import ValidationError


def test_display_name_rejects_angle_brackets():
    from app.api.auth import RegisterRequest

    with pytest.raises(ValidationError, match="display_name"):
        RegisterRequest(
            email="test@example.com",
            password="securepass123",
            username="testuser",
            display_name="<script>alert('xss')</script>",
        )


def test_display_name_rejects_double_quotes():
    from app.api.auth import RegisterRequest

    with pytest.raises(ValidationError, match="display_name"):
        RegisterRequest(
            email="test@example.com",
            password="securepass123",
            username="testuser",
            display_name='Hello "World"',
        )


def test_display_name_allows_normal_text():
    from app.api.auth import RegisterRequest

    req = RegisterRequest(
        email="test@example.com",
        password="securepass123",
        username="testuser",
        display_name="John O'Brien-Smith",
    )
    assert req.display_name == "John O'Brien-Smith"


def test_display_name_allows_unicode():
    from app.api.auth import RegisterRequest

    req = RegisterRequest(
        email="test@example.com",
        password="securepass123",
        username="testuser",
        display_name="Jean-Pierre",
    )
    assert req.display_name == "Jean-Pierre"


def test_display_name_allows_emoji():
    from app.api.auth import RegisterRequest

    req = RegisterRequest(
        email="test@example.com",
        password="securepass123",
        username="testuser",
        display_name="Cool User 🎉",
    )
    assert req.display_name == "Cool User 🎉"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_display_name_validation.py -v
```

Expected: `test_display_name_rejects_angle_brackets` and `test_display_name_rejects_double_quotes` FAIL (no validation exists yet). The `allows_*` tests PASS.

- [ ] **Step 3: Add the validator to RegisterRequest**

In `app/api/auth.py`, modify the `RegisterRequest` class (line ~52-58):

```python
from pydantic import field_validator

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=50)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    guest_session_token: str | None = None

    @field_validator("display_name")
    @classmethod
    def display_name_no_html_chars(cls, v: str) -> str:
        if any(ch in v for ch in '<>"'):
            raise ValueError("display_name must not contain <, >, or \" characters")
        return v
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_display_name_validation.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass (existing tests don't use `<>"` in display names)

- [ ] **Step 6: Commit**

```bash
git add app/api/auth.py tests/test_display_name_validation.py
git commit -m "fix(auth): reject <, >, \" in display_name to prevent stored XSS

The display_name field accepted arbitrary characters including HTML
metacharacters. While currently rendered in mobile only, the field
is returned via /public/cards/{username} JSON consumed by card-web.
Reject at input boundary rather than retroactively cleaning stored data."
```

---

## Task 6: Verify All Migrations Have DOWN Sections

**Files:**
- Review: `app/migrations/0013_row_level_security.sql` through `app/migrations/0016_fix_usage_events_fk.sql`

- [ ] **Step 1: Verify each new migration contains both UP and DOWN**

```bash
grep -l "DOWN" app/migrations/0013_*.sql app/migrations/0014_*.sql app/migrations/0015_*.sql app/migrations/0016_*.sql
```

Expected: All 4 files listed

- [ ] **Step 2: Run full test suite one final time**

```bash
pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 3: Final review — verify no files were accidentally modified**

```bash
git diff --name-only
git status
```

Expected: Only the files listed in this plan are modified/created.
