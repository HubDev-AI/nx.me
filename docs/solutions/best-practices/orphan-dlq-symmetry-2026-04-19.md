---
title: "Orphan DLQ symmetry: blobs, DB rows, and pre-record-before-op"
date: 2026-04-19
category: best-practices
module: workers
problem_type: best_practice
component: background_job
severity: high
related_components:
  - database
  - service_object
applies_when:
  - Adding a new DLQ for orphaned resources (blobs, rows, external IDs)
  - External side effect happens BEFORE the durable commit (upload, signal, webhook)
  - Polymorphic reference without FK cascade needs app-layer cleanup + sweeper
  - Request interruption must leave reconcilable state, not silent orphans
tags:
  - orphan-dlq
  - dead-letter-queue
  - pre-record
  - sweeper
  - polymorphic-reference
  - ref-count
  - cron-stagger
related_prs:
  - "HubDev-AI/nx.me#167"
related_docs:
  - docs/solutions/best-practices/enumerate-before-cascade-with-cas-2026-04-19.md
  - docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md
---

# Orphan DLQ symmetry: blobs, DB rows, and pre-record-before-op

## Context

Migration `0036_orphaned_storage_keys.sql` introduced a DLQ for blobs
whose primary DB insert failed AND inline cleanup delete also failed;
nightly `reclaim_orphaned_blobs` drains it. PR #167 extended the pattern
along two new axes:

1. **DB rows can also orphan.** `jobs.source_id → glowup_analyses.id` is
   polymorphic with no FK cascade — app-layer ref-count deletes the
   analysis explicitly. When that best-effort delete fails after
   `DELETE FROM jobs` committed, the analysis is unreferenced forever.
   `0047_orphaned_analyses.sql` mirrors 0036's shape;
   `OrphanedAnalysesRepository` mirrors `OrphanedStorageKeyRepository`;
   `reclaim_orphaned_analyses` mirrors `reclaim_orphaned_blobs`.

2. **Pre-record-before-op.** `POST /v1/posts` uploads two blobs to
   `PUBLIC_BUCKET` *before* inserting the `posts` row. If the request
   dies between (TOCTOU 409, retry exhaust, crash, disconnect), blobs
   orphan with no sweeper path — `reclaim_orphaned_blobs` drains only
   rows already in the DLQ. Fix: pre-record upload keys with
   `PUBLISH_PENDING_REASON = "publish_pending"` before the insert;
   delete DLQ rows on successful commit.

## Guidance

Six symmetry rules for every new orphan DLQ.

### 1. Shape mirror

```sql
CREATE TABLE orphaned_<entity> (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    <entity_ref> <type> NOT NULL,
    reason TEXT NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    CONSTRAINT orphaned_<entity>_unique UNIQUE (<entity_ref>)
);
CREATE INDEX orphaned_<entity>_attempts_idx ON orphaned_<entity> (attempts, inserted_at);
```

The `(attempts, inserted_at)` index lets the sweeper filter exhausted rows
**DB-side**. A pure client-side filter over oldest-first `ORDER BY` pins
exhausted rows at the batch head and starves the sweeper.

### 2. Repo symmetry

Exactly four methods: `record / list_pending / delete / mark_attempt`.
`record()` uses UPSERT with `on_conflict=<entity_ref>` so first-insert is
race-free and idempotent. `mark_attempt()` is the **only** path that bumps
`attempts` — never bump from `record()`. An app re-recording an
already-known orphan must not erase the sweeper's increment.

### 3. Reason constants are server-side only

Grepped and alerted on — never user-derived. Current:
`DELETE_GLOWUP_REASON` (`app/api/jobs.py`), `RETENTION_PURGE_REASON`
(`app/workers/retention.py`), `PUBLISH_PENDING_REASON` (`app/api/posts.py`),
and `"delete_account"` (`app/api/auth.py` + `app/workers/delete_account_blobs.py`;
promote to `DELETE_ACCOUNT_REASON` for consistency).

### 4. One sweeper per DLQ, stagger crons

DLQ drains read the same tables as retention/reconcile — parallel runs
contend for row locks. Stagger in `app/worker_settings.py`:
`reclaim_orphaned_blobs` at 03:45 UTC, `reclaim_orphaned_analyses` at
04:00 UTC. Never co-schedule a new DLQ drain at the same minute as
retention or reconcile — pick the next 15-minute slot.

### 5. Attempt ceiling with operator signal

`MAX_ATTEMPTS = 5`. Above ceiling the sweeper skips (DB-side filter +
client-side defence-in-depth). On the crossing attempt emit
`logger.warning("Orphan X hit attempt ceiling — manual cleanup required")`
so rows don't rot silently.

### 6. Never-raises repo contract

`record()` must not throw — the caller is already on a failure path. Both
repos wrap the upsert in `try/except Exception` + `logger.exception`.
Masking the primary error behind a DLQ-insert failure is the worst outcome.

### Pre-record-before-op code shape

```python
published = await run_sync(publish_post_images, ...)                        # 1. side effect
await run_sync(orphan_repo.record, BUCKET, published.before_key, PUBLISH_PENDING_REASON)  # 2. pre-record
await run_sync(orphan_repo.record, BUCKET, published.after_key,  PUBLISH_PENDING_REASON)
fresh = await run_sync(job_repo.get_jobs_for_post, job_id)                  # 3. TOCTOU re-verify
if not fresh or fresh["status"] != "completed":
    raise HTTPException(status_code=409, ...)
post = await run_sync(post_repo.insert_post, insert_row)                    #    durable commit
try:                                                                        # 4. best-effort DLQ cleanup
    await run_sync(orphan_repo.delete_by_key, BUCKET, published.before_key)
    await run_sync(orphan_repo.delete_by_key, BUCKET, published.after_key)
except Exception:
    logger.warning("DLQ cleanup failed — sweeper will retry, safe", exc_info=True)
```

If step 4 fails, the sweeper does a spurious re-delete of blobs the posts
row now owns — no-op 404, not data loss.

## Why This Matters

- **No shape mirror**: divergent sweeper queries; without `(attempts,
  inserted_at)` the oldest exhausted row blocks the whole batch.
- **No race-free upsert**: concurrent first-writers overwrite the
  sweeper's `attempts=3` with `attempts=1`, silently resetting the ceiling.
- **User-derived reasons**: attackers poison alerting; typos hide rows.
- **No cron stagger**: DLQ drains + retention contend for row locks, can
  deadlock.
- **No ceiling+WARN**: permanent failures retry forever disguised as
  transient, or vanish after the filter.
- **Raising `record()`**: inline `except` swallows a different exception
  than the one it was logging — root-cause stack lost.
- **No pre-record-before-op**: any failure between side effect and commit
  orphans the resource permanently — a leak *class*, not a single bug.

## When to Apply

- New DLQ for orphaned resources (blobs, rows, external IDs).
- External side effect (upload, signal, webhook) happens BEFORE the durable
  commit.
- Polymorphic reference without FK cascade needs app-layer cleanup.
- Request interruption must leave reconcilable state, not silent orphans.

## When NOT to Apply

- Side effect is idempotent and cheap to redo next request (Redis INCR+TTL).
- Orphan has FK cascade the DB enforces — rely on the DB.
- Single-table transaction covers side effect and commit.
- Retention sweeper already discovers key-without-row orphans for this
  bucket — reconcile covers it.

## Examples

**Blob DLQ (0036 + `reclaim_orphaned_blobs`).** `app/image_pipeline/pipeline.py`
uploads a blob; on image-insert failure `except` calls
`orphan_repo.record(bucket, key, reason)`. Sweeper drains 03:45 UTC.

**Analysis DLQ (0047 + `reclaim_orphaned_analyses`).** `DELETE /v1/jobs/{job_id}`
issues `DELETE FROM jobs`, then best-effort deletes the unreferenced
`glowup_analyses` row. On failure calls
`orphan_analyses_repo.record(source_id, DELETE_GLOWUP_REASON)`. Sweeper
retries 04:00 UTC, `MAX_ATTEMPTS=5`, WARN on ceiling crossing.

**Publish-pending pre-record (`POST /v1/posts`).** `create_post` uploads
both images to `PUBLIC_BUCKET`, pre-records both keys to
`orphaned_storage_keys` with `reason=PUBLISH_PENDING_REASON`, then runs
M-5 TOCTOU re-verify and `insert_post` (with 23505 retry). On success,
two `delete_by_key` calls remove the pending rows. On ANY failure between
upload and insert, DLQ rows stay; `reclaim_orphaned_blobs` drains them.

Three workers drain: `reclaim_orphaned_blobs` (03:45 UTC),
`reclaim_orphaned_analyses` (04:00 UTC), and retention
(`app/workers/retention.py`, which itself records to the blob DLQ on
purge failures with `RETENTION_PURGE_REASON`).

## Related

- `enumerate-before-cascade-with-cas-2026-04-19.md` — delete-path discipline that feeds this DLQ
- `account-delete-hard-reset-invariant-2026-04-18.md` — account delete uses the blob DLQ with `reason="delete_account"`
- PR #167 — save / share / publish / delete, introduced 0047 + publish-pending
