---
title: "Enumerate-before-cascade with CAS: the bulk-delete invariants"
date: 2026-04-19
category: best-practices
module: retention
problem_type: best_practice
component: background_job
severity: critical
related_components:
  - database
  - service_object
  - rails_controller
applies_when:
  - Bulk-deleting rows whose cascade drops join rows that reference external state (blobs, Redis, search indexes)
  - Adding or changing a retention / TTL / sweeper worker
  - Writing a per-resource DELETE endpoint where the resource owns blobs or secondary table rows reachable via join
  - Designing any mutation where the authoritative list of side-effect keys is lost the instant the DB op fires
  - Concurrent writers (save / publish / share) may mutate the target rows during the enumerate window
symptoms:
  - Blob storage orphaned indefinitely after bulk deletion of parent rows (no enumeration before delete)
  - Sweeper shows zero pending keys while storage bucket grows unboundedly
  - User save / publish race with retention worker results in loss of a just-saved job
  - Post-images survive after parent glowup_job deletion (FK cascade drops join, but blobs persist)
  - glowup_analyses rows orphaned when last referencing job is deleted with no ref-count check
root_cause: missing_workflow_step
resolution_type: code_fix
tags:
  - enumerate-before-cascade
  - compare-and-swap
  - retention-worker
  - blob-lifecycle
  - orphaned-storage
  - dlq
  - ref-count
  - bulk-delete
related_prs:
  - "HubDev-AI/nx.me#167"
related_docs:
  - docs/solutions/best-practices/account-delete-hard-reset-invariant-2026-04-18.md
---

# Enumerate-before-cascade with CAS: the bulk-delete invariants

## Context

The backend's retention worker had a silent-leak bug that predated this PR: `app/workers/retention.py::run_retention` issued a bulk `DELETE FROM jobs WHERE saved_at IS NULL AND created_at < cutoff` and leaned entirely on the FK cascade introduced by migrations 0044–0045 to fan out to `posts`, `reactions`, `comments`, `reports`, `credit_reservations`, and `prompt_experiments`. The cascade handled the DB rows correctly, but the storage side never did: `raw-selfies`, `generated-images`, and `post-images` blobs are referenced by columns (`jobs.before_image_url`, `jobs.after_image_url`, `posts.before_image_url`, `posts.after_image_url`) on rows that the cascade destroyed. Once the DELETE committed, there was nothing left in the DB to enumerate those keys from, so the worker never issued a single Supabase Storage delete for a purged job. Every blob of every unsaved job past the retention window leaked, and kept leaking every night.

Two structural facts made the leak worse:

1. **No FK cascade from `jobs.source_id` to `glowup_analyses`.** Migration 0034 rebuilds the jobs table with a polymorphic `source_type + source_id` pair (comment: *"PostgreSQL cannot express a polymorphic FK; integrity is enforced at the application layer."*). `source_id` is a plain UUID, so dropping a `jobs` row cannot drop the analysis it points at — app-layer ref-counting is the only way to safely delete the analysis.

2. **The bulk retention DELETE has a minutes-long window** between the "which rows are doomed" snapshot and the DELETE itself. In that window a user can save a row via `POST /v1/jobs/{id}/save`. Without a CAS guard, the DELETE hard-deletes the just-saved row anyway.

The plan-level risk was documented ("enumerate-before-cascade"; analysis orphan recoverability) but not fixed until PR #167. The same-day sibling doc [`account-delete-hard-reset-invariant-2026-04-18.md`](./account-delete-hard-reset-invariant-2026-04-18.md) already codified the 8-step per-user instance of this pattern (session history). This doc generalizes invariants 2 (step ordering) and 3 (compensating sweeper) to all cascade-bearing delete paths and adds the CAS rule for deferred/bulk paths.

## Guidance

Any DELETE (or UPDATE with side-effect triggers) that relies on FK cascade — or that has implicit side effects in external stores (object storage, caches, indexes) — must follow these five steps:

### 1. Read the side-effect keys BEFORE the DB op fires

After the DELETE, the cascade drops the join rows, and the join you needed to find storage keys or related IDs no longer exists. Enumerate first, always. Use a single helper so every delete path (retention worker, per-row endpoint, account delete) stays in lock-step on which keys count as "owned":

```python
blob_keys = job_repo.enumerate_blob_keys_for_delete(job_id)
# -> [(raw-selfies,        "{user}/{upload}.jpg"),
#     (generated-images,   "{user}/{job}.jpg"),
#     (post-images,        "{user}/before.jpg"),   # only if live post row exists
#     (post-images,        "{user}/after.jpg")]
```

### 2. Use compare-and-swap on the DELETE predicate when the op is deferred or long-running

A bulk retention purge has a minutes-long window between snapshot and DELETE. Re-assert the purge predicate on the DELETE itself so any row that no longer matches at commit time (user saved or published during the window) survives:

```python
# repository
def delete_by_ids(self, ids, *, cutoff_iso=None):
    q = self._sb.table("jobs").delete().in_("id", ids)
    if cutoff_iso is not None:
        q = q.is_("saved_at", "null").lt("created_at", cutoff_iso)
    q.execute()

# caller — pass the SAME cutoff used to build `ids`
doomed = job_repo.list_expired_unsaved_jobs(cutoff_iso)
job_repo.delete_by_ids([j["id"] for j in doomed], cutoff_iso=cutoff_iso)
```

Per-request endpoints (user-initiated, single-row) do not need CAS — the status gate + owner check + single-row DELETE are atomic enough. CAS is specifically for deferred/bulk paths. Nothing in prior sessions addresses the concurrent-user-save-racing-DELETE problem; the CAS predicate appears to be a genuinely new invariant from this work (session history).

### 3. Inline-wipe side effects AFTER the DB op, with DLQ fallback

Each `(bucket, key)` is attempted individually, not batched. A single storage 503 must land one key in the DLQ, not every key in the batch. Route through a shared helper so every delete site has the same wipe-or-record semantics:

```python
for bucket, key in blob_keys:
    wipe_blob_or_record_orphan_sync(
        image_repo, orphan_repo, bucket, key, RETENTION_PURGE_REASON,
    )
```

On exception, the helper calls `OrphanedStorageKeyRepository.record(bucket, key, reason)`; a nightly sweeper (`reclaim_orphaned_blobs`) drains the DLQ with a capped attempt budget.

### 4. Reason constants are server-side only

Every DLQ write tags the row with a reason that names the delete path. Reasons are module-level string constants (`DELETE_GLOWUP_REASON = "delete_glowup"`, `RETENTION_PURGE_REASON = "retention_purge"`, and the `"delete_account"` literal used by `wipe_deleted_user_blobs`) — never threaded through from user input. This keeps the DLQ's observability story audit-clean (no injection surface) and makes `WHERE reason = ?` sweeps cheap.

### 5. For DB rows that lack FK cascade, app-layer ref-count after the DB cascade, with its own DLQ

`jobs.source_id → glowup_analyses.id` is polymorphic, so the `DELETE FROM jobs` cascade leaves the analysis row behind. Before issuing the cascade, count peer jobs that share the same `source_id` (excluding cancelled peers, which have already released their reservation). Only delete the analysis when the count is zero:

```python
if source_type == SOURCE_TYPE_GLOWUP and source_id:
    peer_count = job_repo.count_peer_jobs_for_source(
        source_id, exclude_id=job_id, exclude_statuses={"cancelled"},
    )
    if peer_count == 0:
        delete_analysis = True

job_repo.delete_by_id(job_id)           # cascade fans out
if delete_analysis:
    try:
        job_repo.delete_analysis_by_id(source_id)
    except Exception:
        orphan_analyses_repo.record(source_id, DELETE_GLOWUP_REASON)  # DLQ
```

Record DLQ on failure; a dedicated sweeper (`app/workers/orphan_analysis_reclaim.py::reclaim_orphaned_analyses`) drains the `orphaned_analyses` table added by migration 0047.

### Ordering, in one line

Enumerate first → then CAS-DELETE (or plain DELETE for per-row endpoints) → then ref-count-cleanup for polymorphic references → then inline-wipe-or-DLQ → then analytics (swallow-wrapped). **If the DB DELETE itself raises, do NOT wipe the enumerated keys** — the row references they depend on are still alive.

## Why This Matters

Without this pattern, the failure mode is a silent, unbounded storage leak:

- **Pre-PR concrete damage.** Every unsaved glow-up past `RETENTION_JOB_DAYS` is DELETE-cascaded from `jobs` every night. The raw-selfie blob, the generated-image blob, and (for any posted-then-unsaved job) the two post-image blobs are all permanently orphaned in Supabase Storage. There is no join left to find them by, so they are unreachable — not just unlinked, but unfindable. The retention worker emits `"purged N jobs, N uploads, N storage objects"` on a clean run, so the log looks healthy while the storage bill climbs.
- **Class of bug.** This is the quietest category of regression. The API keeps serving 2xx. No user sees a 500. The only signal is your object-storage invoice, and invoices arrive monthly — by then the leak has been running for 30+ retention cycles. A prior session (2026-04-14 cross-layer audit, `fix/cross-layer-audit`) opened `retention.py` explicitly to fix a different cron-race issue and **did not catch the blob-orphan bug** (session history). That is exactly the methodology failure the pattern defends against: "we looked at the file and it looked fine."
- **CAS matters separately.** Without the CAS predicate on the bulk DELETE, a user who saves a job in the window between the retention snapshot and the DELETE commit has their just-saved row hard-deleted. They see the save succeed in the UI, then the job vanishes overnight. That is the kind of "I pressed save and it ate my work" bug that erodes trust permanently.
- **Polymorphic ref-count matters separately.** Without it, every deleted glow-up leaves its `glowup_analyses` row stranded. Storage on the analysis is cheap but the row can hold upload references; without cleanup you eventually grow an orphan graph that confuses later repair jobs and makes migrations risky.

**After the PR.** The retention worker enumerates per-job blobs before issuing the CAS-guarded DELETE, inline-wipes every blob, DLQs what fails, and the nightly reclaim worker drains the DLQ. The `DELETE /v1/jobs/{id}` endpoint uses the same helper, same reason-constant discipline, same ref-count-on-analysis logic. Two sweepers back both paths. The invoice stops climbing.

## When to Apply

**Apply this pattern when:**

- Any bulk or deferred DB DELETE/UPDATE triggers FK cascade on rows with implicit side effects in external stores (object storage, caches, full-text indexes, CDN paths).
- A per-row endpoint deletes a row whose side effects live in external stores (the enumerate-first + inline-wipe-with-DLQ shape still applies; CAS is optional because the op is user-initiated and short-lived).
- A polymorphic reference (no FK, plain UUID column) needs app-layer ref-count cleanup.
- The deletion path must be idempotent under retry — reason-constant DLQ + sweeper is the durable recovery handle when a single-request wipe fails mid-way.

**Do NOT apply this pattern when:**

- A simple row DELETE on a table has no side effects (pure metadata, no join dependents, no storage references, no cache keys). Adding enumerate-before-cascade + CAS + DLQ to a plain `DELETE FROM user_preferences WHERE id = ?` is pure overhead.
- The DELETE is inside a transaction that can atomically coordinate every side effect (rare in practice once object storage or Redis is involved — they are not in the DB transaction).
- The operation is already-atomic at the storage layer (e.g. a single object-storage delete with no DB representation).

## Examples

### Shared helper (single source of truth for wipe-or-record)

- `app/services/blob_cleanup.py` — exports `wipe_blob_or_record_orphan` (async) and `wipe_blob_or_record_orphan_sync`. Both never raise; both fall through to `OrphanedStorageKeyRepository.record(bucket, key, reason)` on storage failure. Retention worker uses the sync variant because it calls the sync Supabase client directly from inside an ARQ task.

### Call site 1 — bulk deferred (retention worker)

- `app/workers/retention.py::run_retention`
- Reason constant: `RETENTION_PURGE_REASON = "retention_purge"` (module-level).
- Steps: `list_expired_unsaved_jobs(cutoff)` → cap at `RETENTION_JOB_BATCH_LIMIT` → per-job `enumerate_blob_keys_for_delete` → CAS DELETE via `delete_by_ids(ids, cutoff_iso=cutoff_iso)` → per-key `wipe_blob_or_record_orphan_sync`. If the CAS DELETE raises, `doomed_blobs` is cleared to preserve the enumerate-before-cascade invariant (do not wipe keys whose DB references survived).

### Call site 2 — per-request user-initiated (DELETE glow-up endpoint)

- `app/api/jobs.py::delete_job`
- Reason constants: `DELETE_GLOWUP_REASON = "delete_glowup"` (module-level) for both the blob DLQ and the analysis DLQ.
- No CAS (user-initiated, single-row, owner-checked). Uses the polymorphic ref-count step: `count_peer_jobs_for_source(source_id, exclude_id=job_id, exclude_statuses={"cancelled"})` before the DELETE; `delete_analysis_by_id` only runs when peer count is zero. On analysis-delete failure, records to `orphaned_analyses` via `orphan_analyses_repo.record(source_id, DELETE_GLOWUP_REASON)` — the request still returns 204 (destructive ops must be idempotent).

### Call site 3 — bulk async fan-out (account delete blobs)

- `app/workers/delete_account_blobs.py::wipe_deleted_user_blobs`
- Reason literal: `"delete_account"` (used directly in `orphan_repo.record(bucket, key, "delete_account")`). Worth promoting to a module-level `DELETE_ACCOUNT_REASON` constant for consistency with the other two sites — it is the only reason string still inlined.
- Pattern: chunks each bucket's keys into batches of `_CHUNK_SIZE=250`; on batch failure, per-key fan-out into the DLQ (not a batch-level record — same "one failing key does not DLQ the whole batch" discipline as the retention + delete_job per-key loops). Uses `asyncio.to_thread` to keep the ARQ event loop free across the sync Supabase round-trips.

### DLQ tables + sweepers

- `orphaned_storage_keys` — migration `app/migrations/0036_orphaned_storage_keys.sql`. Drained by `app/workers/orphan_reclaim.py::reclaim_orphaned_blobs`. Unique on `(bucket, storage_key)`; `(attempts, inserted_at)` index so the sweeper can filter exhausted rows DB-side. Bounded retries via `ORPHAN_RECLAIM_MAX_ATTEMPTS`.
- `orphaned_analyses` — migration `app/migrations/0047_orphaned_analyses.sql` (shape mirrors 0036 one-to-one, swapping `(bucket, storage_key)` for a single `analysis_id`). Drained by `app/workers/orphan_analysis_reclaim.py::reclaim_orphaned_analyses`. Bounded retries via `ORPHAN_ANALYSIS_RECLAIM_MAX_ATTEMPTS`; WARN-logs when a row crosses the ceiling so exhausted rows surface for operator review.

### Before/after on the retention worker

Before (silent-leak; pre-PR code path):

```python
supabase.table("jobs").delete() \
    .is_("saved_at", "null") \
    .lt("created_at", cutoff) \
    .execute()
# Cascade drops posts/images. Blobs orphan forever.
```

After (PR #167):

```python
doomed = job_repo.list_expired_unsaved_jobs(cutoff_iso)[:RETENTION_JOB_BATCH_LIMIT]
ids = [j["id"] for j in doomed]
keys_per_job = {j["id"]: job_repo.enumerate_blob_keys_for_delete(j["id"]) for j in doomed}
job_repo.delete_by_ids(ids, cutoff_iso=cutoff_iso)         # CAS re-asserts predicate
for job_id, keys in keys_per_job.items():
    for bucket, key in keys:
        wipe_blob_or_record_orphan_sync(
            image_repo, orphan_repo, bucket, key, RETENTION_PURGE_REASON,
        )
```

## What Didn't Work (session history)

Evolution across prior sessions on this repo that informed this pattern:

- **Soft-delete + 72-hour async cleanup story** (auth design, early March 2026). Cleanup story was never written; every blob orphaned forever. Root enabling decision for the entire leak family.
- **Scrubbing just UNIQUE columns** (PR #162, 2026-04-18 morning). Re-signup worked after email + tiktok_open_id were NULLed on soft-delete, but device-local state and four other surfaces still leaked. Abandoned in favor of full hard-delete.
- **`KEYS` instead of `SCAN` for Redis cleanup.** Documented as a leak in [account-delete invariants](./account-delete-hard-reset-invariant-2026-04-18.md); fixed in PR #166 via `scan_iter`.
- **`blocked_users` SET NULL on delete** (reviewed in PR #166). Combined with existing UNIQUE(blocker_id, blocked_id) + RLS policy `USING (blocker_id = auth.uid())`, NULL rows became unreadable orphans. Changed to CASCADE both sides.
- **Cross-layer audit (`fix/cross-layer-audit`, 2026-04-14) missed the retention blob leak.** The audit inspected `retention.py` directly and fixed a different cron-race issue. The leak sat for four more days. This pattern's WARN-log-at-ceiling, DLQ observability, and single-helper-per-path design defend against "looked fine" audits.

## Related

- [`account-delete-hard-reset-invariant-2026-04-18.md`](./account-delete-hard-reset-invariant-2026-04-18.md) — original per-user instance of this pattern. This doc generalizes invariants 2 (step ordering) and 3 (compensating sweeper) to all cascade-bearing delete paths.
- PR #167 — introduces `DELETE /v1/jobs/{id}`, retention refactor, `orphaned_analyses` DLQ.
- PR #166 — prior per-user instance (`delete_account` hard-reset).
- Migrations: 0036 (`orphaned_storage_keys`), 0045 (cascade completeness), 0047 (`orphaned_analyses`).
- Sweepers: `app/workers/orphan_reclaim.py`, `app/workers/orphan_analysis_reclaim.py`.
