# Sprint 2: Repository Layer + Async Foundation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all ~106 `supabase.table/rpc/storage` calls into repository classes, wrap blocking Supabase SDK calls with `run_in_executor` for async handlers, eliminate CreditLedger ad-hoc construction, and remove the duplicated default tier query.

**Architecture:** Repository-per-domain pattern following the existing `TierRepository` and `UsageRepository` conventions. Each repository takes a `Client` (Supabase) in its constructor. A shared `run_sync` helper wraps blocking calls for async contexts. Repositories are instantiated in `deps.py` dependency providers and injected via `Depends()`. The worker uses `get_supabase_service()` directly (no FastAPI DI).

**Tech Stack:** Python, FastAPI Depends(), Supabase Client, asyncio.run_in_executor, pytest

**Source spec:** `docs/superpowers/specs/2026-03-17-review-sweep-design.md` (Sprint 2)

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `app/db/async_helpers.py` | `run_sync()` wrapper for blocking calls in async contexts |
| Create | `app/repositories/user_repo.py` | User CRUD, auth admin ops, profile, account deletion |
| Create | `app/repositories/post_repo.py` | Post CRUD, comment queries, report creation |
| Create | `app/repositories/feed_repo.py` | Feed views, trending/biggest RPCs, reaction persistence |
| Create | `app/repositories/job_repo.py` | GlowUp job lifecycle, state transitions |
| Create | `app/repositories/image_repo.py` | Image row CRUD + storage bucket operations |
| Create | `app/repositories/subscription_repo.py` | Subscription CRUD, webhook event dedup |
| Create | `app/repositories/advisor_repo.py` | Conversations, messages, nudges, memories |
| Create | `app/repositories/analysis_repo.py` | Analysis CRUD |
| Create | `app/repositories/__init__.py` | Package init |
| Modify | `app/api/deps.py` | Add repository dependency providers |
| Modify | `app/api/auth.py` | Use UserRepository instead of inline queries |
| Modify | `app/api/users.py` | Use UserRepository + ImageRepository |
| Modify | `app/api/posts.py` | Use PostRepository |
| Modify | `app/api/social.py` | Use FeedRepository |
| Modify | `app/api/generation.py` | Use JobRepository + ImageRepository |
| Modify | `app/api/entitlement.py` | Use SubscriptionRepository |
| Modify | `app/api/webhooks.py` | Use SubscriptionRepository |
| Modify | `app/api/analyses.py` | Use AnalysisRepository |
| Modify | `app/api/public.py` | Use UserRepository + PostRepository |
| Modify | `app/api/health.py` | Use get_supabase (unchanged — single call) |
| Modify | `app/generation/worker.py` | Use JobRepository + ImageRepository |
| Modify | `app/image_pipeline/pipeline.py` | Use ImageRepository (2 inserts + 1 storage remove) |
| Modify | `app/image_pipeline/storage.py` | Use ImageRepository (upload + signed URL) |
| Modify | `app/services/public_url.py` | Use ImageRepository (download + upload + signed URL) |
| Modify | `app/face_analysis/service.py` | Use ImageRepository (storage download) |
| Modify | `app/advisor/service.py` | Use AdvisorRepository |
| Modify | `app/advisor/memory_manager.py` | Use AdvisorRepository |
| Modify | `app/advisor/nudge_eligibility.py` | Use AdvisorRepository |
| Modify | `app/advisor/nudge_scheduler.py` | Use AdvisorRepository |
| Modify | `app/main.py` | No changes needed (supabase/redis init stays) |

---

## Task 1: Create async helper + repository package

**Files:**
- Create: `app/db/async_helpers.py`
- Create: `app/repositories/__init__.py`

- [ ] **Step 1: Create `app/db/async_helpers.py`**

```python
"""Async helpers for blocking SDK calls.

The supabase-py SDK's .execute() is synchronous (blocking I/O).
When called from async def handlers, it blocks the asyncio event loop.
This module provides a wrapper to run blocking calls in a thread pool.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Callable, TypeVar

T = TypeVar("T")


async def run_sync(func: Callable[..., T], *args, **kwargs) -> T:
    """Run a blocking function in the default executor (thread pool).

    Usage:
        result = await run_sync(repo.get_user, username)
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(func, *args, **kwargs)
    )
```

- [ ] **Step 2: Create `app/repositories/__init__.py`**

```python
"""Repository package — data access layer.

Each repository encapsulates supabase.table/rpc/storage calls for a domain.
Handlers import repositories and call methods instead of building queries inline.
"""
```

- [ ] **Step 3: Commit**

```bash
git add app/db/async_helpers.py app/repositories/__init__.py
git commit -m "feat: add run_sync async helper and repositories package

run_sync wraps blocking supabase-py SDK calls in asyncio.run_in_executor
so async handlers don't block the event loop."
```

---

## Task 2: UserRepository + update auth.py, users.py, public.py

**Files:**
- Create: `app/repositories/user_repo.py`
- Modify: `app/api/auth.py`
- Modify: `app/api/users.py`
- Modify: `app/api/public.py`

The UserRepository encapsulates all `supabase.table("users")` calls, plus `supabase.auth.admin` operations. Follow the existing `TierRepository` pattern (constructor takes `Client`).

- [ ] **Step 1: Read all three handler files to understand every user-related query**

Read `app/api/auth.py`, `app/api/users.py`, `app/api/public.py` fully. Identify every `supabase.table("users")` call and every `supabase.auth.admin.*` call.

- [ ] **Step 2: Create `app/repositories/user_repo.py`**

Define a `UserRepository` class with methods covering every user query found in step 1. Pattern:

```python
"""User repository — user CRUD, auth admin, profile operations."""
from __future__ import annotations

import logging
from uuid import UUID

from supabase import Client

logger = logging.getLogger(__name__)


class UserRepository:
    """Encapsulates all user-related database operations."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # --- Reads ---

    def get_by_username(self, username: str) -> dict | None:
        """Fetch user by username. Returns None if not found."""
        result = (
            self._sb.table("users")
            .select("*")
            .eq("username", username)
            .is_("deleted_at", "null")
            .maybe_single()
            .execute()
        )
        return result.data

    def check_username_available(self, username: str) -> bool:
        """Check if username is available (not taken, not reserved)."""
        # Copy exact logic from auth.py register()
        ...

    def get_by_id(self, user_id: str) -> dict | None:
        """Fetch user by ID."""
        ...

    # --- Writes ---

    def create(self, user_data: dict) -> dict:
        """Insert a new user row."""
        ...

    def upsert_social(self, user_data: dict) -> dict:
        """Upsert user for social login."""
        ...

    def update_profile(self, user_id: str, update_data: dict) -> dict:
        """Update user profile fields."""
        ...

    def soft_delete(self, user_id: str, reserved_until: str) -> dict | None:
        """Soft delete: set deleted_at, reserve username."""
        ...

    def update_email_verified(self, user_id: str) -> None:
        """Mark user as email verified."""
        ...

    # --- Auth admin ---

    def admin_create_user(self, email: str, password: str) -> dict:
        """Create auth user via admin API."""
        ...

    def admin_delete_user(self, user_id: str) -> None:
        """Delete auth user (best-effort)."""
        ...

    def admin_get_user(self, user_id: str) -> dict:
        """Get auth user by ID."""
        ...

    def admin_sign_out(self, token: str) -> None:
        """Revoke a session token."""
        ...

    # --- Credit reservations (for account deletion) ---

    def get_pending_reservations(self, user_id: str) -> list[dict]:
        """Fetch all 'reserved' credit reservations for user."""
        ...
```

**IMPORTANT:** Each method should contain the EXACT query logic currently inline in the handlers. Read the handler code and move it verbatim — don't simplify or change behavior.

- [ ] **Step 3: Update `app/api/auth.py`**

For each `supabase.table("users")` and `supabase.auth.admin.*` call:
1. Replace with the corresponding `UserRepository` method call
2. Since auth.py handlers are `async def`, wrap blocking repo calls with `await run_sync(repo.method, args)`
3. Add `user_repo: UserRepository = Depends(get_user_repo)` to handler parameters

Pattern for converting:
```python
# BEFORE (inline in handler):
result = supabase.table("users").select("*").eq("username", username).maybe_single().execute()

# AFTER (via repository + run_sync):
from app.db.async_helpers import run_sync
user_data = await run_sync(user_repo.get_by_username, username)
```

**For the duplicated default tier query (LE-3):** Both `register()` and `social_login()` have identical `supabase.table("tiers").select("id").eq("is_default", True)...` queries. Use `TierRepository.get_default()` (which already exists with Redis caching) instead of adding a duplicate method to UserRepository. Inject `TierRepository` via `get_entitlement_service` or a dedicated `get_tier_repo` dependency. Both handlers should call `tier = await tier_repo.get_default()` and use `str(tier.id)` as the tier_id.

- [ ] **Step 4: Update `app/api/users.py`**

Replace all `supabase.table("users")` calls with `user_repo` methods. `app/api/users.py` also queries analyses, images, glow_up_jobs, and storage — those will be handled in later tasks. For now, only extract the `users` table queries.

- [ ] **Step 5: Update `app/api/public.py`**

Replace `supabase.table("users")` calls with `user_repo` methods.

- [ ] **Step 6: Add `get_user_repo` to `app/api/deps.py`**

```python
def get_user_repo(request: Request) -> UserRepository:
    from app.repositories.user_repo import UserRepository
    return UserRepository(request.app.state.supabase)
```

- [ ] **Step 7: Run tests**

```bash
pytest tests/ -v
```

- [ ] **Step 8: Commit**

```bash
git add app/repositories/user_repo.py app/api/auth.py app/api/users.py app/api/public.py app/api/deps.py
git commit -m "refactor: extract UserRepository from auth/users/public handlers

Move all supabase.table('users') and auth.admin calls into
UserRepository. Wrap blocking calls with run_sync for async handlers.
Eliminates duplicated default tier query (LE-3)."
```

---

## Task 3: PostRepository + update posts.py

**Files:**
- Create: `app/repositories/post_repo.py`
- Modify: `app/api/posts.py`
- Modify: `app/api/deps.py`

- [ ] **Step 1: Read `app/api/posts.py` to identify all post/comment/report queries**

- [ ] **Step 2: Create `app/repositories/post_repo.py`**

Methods needed (extract from handler code):
- `get_by_id(post_id)` — fetch post by ID
- `create(post_data)` — insert post row
- `soft_delete(post_id)` — set is_deleted=True
- `insert_comment_atomic(post_id, user_id, content)` — RPC call
- `get_comments(post_id, cursor, limit)` — paginated comments
- `create_report(report_data)` — insert report row
- `get_commenter_profile(user_id)` — fetch display_name + avatar for comment author

- [ ] **Step 3: Update `app/api/posts.py` to use PostRepository**

Replace all `supabase.table("posts")`, `supabase.table("comments")`, `supabase.table("reports")`, and `supabase.rpc("insert_comment_atomic")` calls with repo methods. Add `post_repo: PostRepository = Depends(get_post_repo)` to handlers. Wrap with `run_sync`.

- [ ] **Step 4: Add `get_post_repo` to `app/api/deps.py`**

- [ ] **Step 5: Run tests + commit**

---

## Task 4: FeedRepository + update social.py

**Files:**
- Create: `app/repositories/feed_repo.py`
- Modify: `app/api/social.py`
- Modify: `app/api/deps.py`

- [ ] **Step 1: Read `app/api/social.py` to identify all feed/reaction queries**

- [ ] **Step 2: Create `app/repositories/feed_repo.py`**

Methods needed:
- `get_newest(cursor, limit)` — query `v_feed_posts` view
- `get_trending(cursor_score, cursor_created, cursor_id, limit)` — RPC `feed_trending`
- `get_biggest_improvements(cursor_reactions, cursor_created, cursor_id, limit)` — RPC
- `get_post_for_reaction(post_id)` — fetch post (for reaction validation)
- `persist_reaction_atomic(post_id, user_id, guest_token)` — RPC
- `check_rate_limit(...)` — rate limit helpers (if they query supabase)

- [ ] **Step 3: Update `app/api/social.py` to use FeedRepository**

- [ ] **Step 4: Add `get_feed_repo` to deps.py, run tests, commit**

---

## Task 5: JobRepository + ImageRepository + update generation.py, worker.py, image pipeline

**Files:**
- Create: `app/repositories/job_repo.py`
- Create: `app/repositories/image_repo.py`
- Modify: `app/api/generation.py`
- Modify: `app/generation/worker.py`
- Modify: `app/image_pipeline/pipeline.py`
- Modify: `app/image_pipeline/storage.py`
- Modify: `app/services/public_url.py`
- Modify: `app/face_analysis/service.py`
- Modify: `app/api/deps.py`

This is the largest task — generation.py has ~12 supabase calls, worker.py has ~14, and the image pipeline/services add ~9 more (all storage operations).

- [ ] **Step 1: Read `app/api/generation.py` and `app/generation/worker.py` fully**

- [ ] **Step 2: Create `app/repositories/job_repo.py`**

Methods needed:
- `get_by_id(job_id)` — fetch job
- `get_by_idempotency_key(key)` — idempotency check
- `create(job_data)` — insert job
- `update_status(job_id, status, extra_fields)` — update job state
- `claim(job_id)` — set status=PROCESSING
- `get_stuck_jobs(cutoff)` — watchdog query
- `log_usage_event(event_data)` — insert usage_events row
- `refund_usage_event(job_id)` — update usage_events on cancel

- [ ] **Step 3: Create `app/repositories/image_repo.py`**

Methods needed:
- `get_by_id(image_id)` — fetch image row
- `get_by_ids(image_ids)` — batch fetch
- `create(image_data)` — insert image row
- `create_signed_url(bucket, key, expires)` — storage signed URL
- `upload(bucket, key, data, content_type)` — storage upload
- `remove(bucket, keys)` — storage remove
- `download(bucket, key)` — storage download

- [ ] **Step 4: Update `app/api/generation.py`**

Replace all supabase calls with repo methods. Add `job_repo` and `image_repo` as Depends. Wrap with `run_sync`.

- [ ] **Step 5: Update `app/generation/worker.py`**

The worker is NOT a FastAPI handler — it's an ARQ background task. It uses `get_supabase_service()` directly. Create repos at the start of the function:

```python
from app.repositories.job_repo import JobRepository
from app.repositories.image_repo import ImageRepository
from app.db.client import get_supabase_service

supabase = get_supabase_service()
job_repo = JobRepository(supabase)
image_repo = ImageRepository(supabase)
```

Worker functions are `async def` but all supabase calls are sync — wrap with `run_sync`.

- [ ] **Step 6: Add dependency providers to deps.py, run tests, commit**

---

## Task 6: SubscriptionRepository + update entitlement.py, webhooks.py

**Files:**
- Create: `app/repositories/subscription_repo.py`
- Modify: `app/api/entitlement.py`
- Modify: `app/api/webhooks.py`
- Modify: `app/api/deps.py`

- [ ] **Step 1: Read `app/api/entitlement.py` and `app/api/webhooks.py`**

- [ ] **Step 2: Create `app/repositories/subscription_repo.py`**

Methods needed:
- `get_active_for_user(user_id)` — check active subscription
- `create(sub_data)` — insert subscription
- `update_by_provider_id(provider_sub_id, update_data)` — update subscription
- `get_by_provider_id(provider_sub_id)` — fetch for deletion handling
- `check_webhook_processed(provider, event_id)` — idempotency check
- `mark_webhook_processed(provider, event_id)` — insert processed event

- [ ] **Step 3: Update handlers, add deps, run tests, commit**

---

## Task 7: AnalysisRepository + update analyses.py

**Files:**
- Create: `app/repositories/analysis_repo.py`
- Modify: `app/api/analyses.py`
- Modify: `app/api/deps.py`

- [ ] **Step 1: Read `app/api/analyses.py`**

- [ ] **Step 2: Create `app/repositories/analysis_repo.py`**

Methods needed:
- `get_by_id(analysis_id)` — fetch analysis
- `get_for_user(user_id, cursor, limit)` — paginated history
- `create(analysis_data)` — insert analysis

- [ ] **Step 3: Update handler, add deps, run tests, commit**

---

## Task 8: AdvisorRepository + update advisor/*.py

**Files:**
- Create: `app/repositories/advisor_repo.py`
- Modify: `app/advisor/service.py`
- Modify: `app/advisor/memory_manager.py`
- Modify: `app/advisor/nudge_eligibility.py`
- Modify: `app/advisor/nudge_scheduler.py`
- Modify: `app/api/deps.py`

This is the second-largest task — the advisor module has ~25 supabase calls.

- [ ] **Step 1: Read all advisor files**

- [ ] **Step 2: Create `app/repositories/advisor_repo.py`**

Methods needed (grouped by sub-domain):

Conversations:
- `get_or_create_conversation(user_id)` — get active or create new
- `get_conversation(conversation_id)` — fetch single
- `update_conversation_timestamp(conversation_id)` — touch updated_at
- `summarize_conversation(conversation_id, summary)` — update summary + summarised_at

Messages:
- `get_messages(conversation_id, limit)` — fetch messages
- `insert_message(message_data)` — insert message
- `delete_messages(conversation_id)` — delete all messages (for summarization)

Nudges:
- `get_nudges(user_id, limit)` — fetch nudges
- `get_nudge_by_id(nudge_id)` — fetch single
- `mark_nudge_read(nudge_id)` — update read_at
- `insert_nudge(nudge_data)` — create nudge
- `find_last_nudge(user_id, trigger)` — for eligibility checks
- `find_recent_nudges(user_id, trigger, since)` — for cooldown checks

Memories:
- `get_memories(user_id, type_filter)` — fetch memories
- `insert_memory(memory_data)` — create memory with embedding
- `match_memories(user_id, embedding, limit)` — pgvector similarity RPC
- `check_duplicate(user_id, type, content_key)` — dedup check
- `update_memory(memory_id, update_data)` — update existing
- `get_analysis_insights(user_id)` — for milestone eligibility

- [ ] **Step 3: Update all advisor files to use AdvisorRepository**

The advisor service/manager classes take `supabase` in constructor. Change to take `AdvisorRepository` instead. Update all callers.

- [ ] **Step 4: Add deps, run tests, commit**

---

## Task 9: CreditLedger injection (ME-4) + final wiring

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/api/webhooks.py` (if CreditLedger still ad-hoc)
- Modify: `app/api/auth.py` (if CreditLedger still ad-hoc)
- Modify: `app/generation/worker.py` (if CreditLedger still ad-hoc)

- [ ] **Step 1: Search for all `CreditLedger(supabase)` instantiations**

```bash
grep -rn "CreditLedger(" app/
```

- [ ] **Step 2: Add `get_credit_ledger` to deps.py**

```python
def get_credit_ledger(request: Request) -> CreditLedger:
    from app.entitlement.ledger import CreditLedger
    return CreditLedger(request.app.state.supabase)
```

- [ ] **Step 3: Replace all ad-hoc `CreditLedger(supabase)` with dependency injection**

In API handlers: `ledger: CreditLedger = Depends(get_credit_ledger)`
In worker: construct once at function start (same as repos)

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor: inject CreditLedger via DI instead of ad-hoc construction (ME-4)"
```

---

## Task 10: Final verification

- [ ] **Step 1: Verify no remaining inline supabase calls in handlers**

```bash
grep -rn "supabase\.table\|supabase\.rpc\|supabase\.storage\|supabase\.auth\.admin" app/api/ app/advisor/ app/generation/worker.py
```

Expected: Only `app/api/health.py` (single readiness check) and `app/api/deps.py` (provider functions). All other handler files should be clean.

- [ ] **Step 2: Verify no ad-hoc CreditLedger construction**

```bash
grep -rn "CreditLedger(" app/ --include="*.py" | grep -v "test\|__pycache__\|repo\|deps"
```

Expected: Only `app/entitlement/ledger.py` (class definition), `app/api/deps.py` (DI provider), and `app/entitlement/service.py` (inside EntitlementService.__init__, which is already DI'd via get_entitlement_service).

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

- [ ] **Step 4: Review commit history**

```bash
git log --oneline HEAD~10..HEAD
```
