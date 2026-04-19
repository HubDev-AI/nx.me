---
title: "Partial UNIQUE index for re-publish after soft-delete"
date: 2026-04-19
category: best-practices
module: database
problem_type: best_practice
component: database
severity: medium
related_components:
  - rails_controller
  - service_object
applies_when:
  - Table has soft-delete (is_deleted, is_hidden, deleted_at) semantics
  - Business key would collide if a plain UNIQUE constraint were used across tombstones
  - User should be able to re-create a resource after their prior one was moderated or soft-deleted
  - POST handlers need to turn unique_violation into caller-idempotency
tags:
  - partial-unique-index
  - postgres
  - soft-delete
  - idempotent-post
  - unique-violation
  - is-deleted
related_prs:
  - "HubDev-AI/nx.me#167"
related_docs:
  - docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md
---

# Partial UNIQUE index for re-publish after soft-delete

## Context

Soft-deleted rows (`is_deleted`, `is_hidden`, `deleted_at`) stay in the
table. A plain `UNIQUE (business_key)` cannot tell live from tombstone —
once a user has a row with key K they can never insert another, even if
their first was moderated or they deleted it and legitimately want to
retry. UX is hostile: moderator soft-deletes a post, user taps Publish,
gets 500, silent feed lockout with no recovery path.

Postgres supports **partial unique indexes** — a `WHERE` predicate that
scopes uniqueness to "alive" rows only. Tombstones pile up harmlessly;
two live rows still collide. Pair with an idempotent POST handler that
catches `unique_violation` (SQLSTATE 23505), re-reads the live row, and
returns 200 — double-taps become caller-idempotent instead of 500s.

## Guidance

**Migration shape.** Match the `WHERE` predicate to the "alive"
definition used everywhere else in the code (same columns, same
booleans). Defensively de-duplicate first so the index can be created
even if legacy rows already violate it:

```sql
WITH ranked AS (
    SELECT id, row_number() OVER (
        PARTITION BY <business_key>
        ORDER BY created_at ASC, id ASC) AS rn
    FROM <table>
    WHERE is_deleted = FALSE AND is_hidden = FALSE
)
UPDATE <table> SET is_deleted = TRUE, updated_at = NOW()
 WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

CREATE UNIQUE INDEX idx_<table>_live_<key>
    ON <table> (<business_key>)
    WHERE is_deleted = FALSE AND is_hidden = FALSE;
```

**Handler shape (idempotent POST).** Detect 23505 via a shared helper,
look up the live row, re-check ownership, return 200. If the violation
fired but nothing live remains (peer soft-deleted between INSERT and
SELECT), retry once:

```python
try:
    row = insert(...)
    status_code = 201
except Exception as exc:
    if not is_unique_violation(exc):
        raise
    existing = get_live_by_key(...)
    if existing is None:
        row = insert(...)  # peer soft-deleted; partial predicate now permits
        status_code = 201
    else:
        if existing["user_id"] != caller_id:
            raise HTTPException(404, "Not found")  # never 403 — no oracle
        row, status_code = existing, 200
```

**Centralised violation detection.** Client libraries surface SQLSTATE
in different attributes — one helper checks `code`, `pgcode`, and
message fallbacks so wrapper drift never silently disables idempotency.

## Why This Matters

- **User-hostile vs legitimate re-try.** Plain `UNIQUE (col)` turns
  every soft-delete into a permanent lockout. Partial `UNIQUE WHERE alive`
  keeps the "at most one live row" invariant without breaking retry
  after moderation or user delete.
- **500s vs idempotent 200s.** Double-tap on Publish, offline retries,
  and back-then-resubmit naturally surface as 23505. Without an
  idempotent handler every one is a 500 and a scary error; with it the
  second call returns the first call's payload.
- **Enumeration safety.** The ownership re-check must 404 (not 403) on
  mismatch — otherwise the endpoint leaks "does this key exist?".

## When to Apply

Apply when the table has soft-delete columns, the business key must be
unique **among live rows only**, and users legitimately re-create the
resource after moderation or self-delete (posts, drafts, releasable
handles, nickname claims).

Do NOT apply when the column must be unique forever (content hash,
external ID, nonce) — use plain `UNIQUE`. Do NOT apply when the table
has no soft-delete; a trivially-true `WHERE` is just plain `UNIQUE` with
extra confusion.

## Examples

### Migration 0046 — `posts.glow_up_job_id`

`app/migrations/0046_unique_post_per_glowup_job.sql`:

```sql
WITH ranked AS (
    SELECT id, row_number() OVER (
        PARTITION BY glow_up_job_id
        ORDER BY created_at ASC, id ASC) AS rn
    FROM posts WHERE is_deleted = FALSE AND is_hidden = FALSE
)
UPDATE posts SET is_deleted = TRUE, updated_at = NOW()
 WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

CREATE UNIQUE INDEX idx_posts_live_glow_up_job_id
    ON posts (glow_up_job_id)
    WHERE is_deleted = FALSE AND is_hidden = FALSE;
```

### Handler — `app/api/posts.py::create_post`

```python
try:
    post = await run_sync(post_repo.insert_post, insert_row)
    response_status = status.HTTP_201_CREATED
except Exception as exc:
    if not is_unique_violation(exc):
        raise
    existing = await run_sync(post_repo.get_by_glow_up_job_id, body.glow_up_job_id)
    if existing is None:
        try:  # peer soft-deleted between INSERT and SELECT; partial permits retry
            post = await run_sync(post_repo.insert_post, insert_row)
            response_status = status.HTTP_201_CREATED
        except Exception as retry_exc:
            if not is_unique_violation(retry_exc):
                raise
            retry_existing = await run_sync(
                post_repo.get_by_glow_up_job_id, body.glow_up_job_id)
            if retry_existing is None:
                raise  # third-way race; escalate
            if retry_existing["user_id"] != user_id:
                raise HTTPException(status_code=404, detail="Job not found")
            # ... return existing as 200
```

### Helper — `app/utils/db_errors.py::is_unique_violation`

Single source of truth for 23505 detection across Supabase `APIError.code`,
psycopg `pgcode`, and bare message strings. Consolidated from three duplicated call sites (posts, advisor memories, trial grantor).

## Related

- `docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md`
- PR: HubDev-AI/nx.me#167
- Migration: `app/migrations/0046_unique_post_per_glowup_job.sql`
- Handler: `app/api/posts.py::create_post`
- Helper: `app/utils/db_errors.py::is_unique_violation`
