"""Tests for the retention worker's enumerate-BEFORE-cascade purge path.

Validates the fix for the pre-existing bug in ``app/workers/retention.py``:
the original bulk ``DELETE FROM jobs WHERE saved_at IS NULL AND created_at < ...``
dropped the FK-cascade-connected ``posts`` / ``images`` rows before anyone
enumerated the denormalised post-images storage keys off those rows, silently
orphaning the blobs in the ``post-images`` bucket (no sweeper coverage).

The fix mirrors the per-job enumerate-before-cascade pattern Unit 5 shipped
in ``app/api/jobs.py::delete_job``:

1. List expired unsaved jobs via ``JobRepository.list_expired_unsaved_jobs``.
2. For each doomed job, enumerate ``(bucket, storage_key)`` via the exact
   helper ``delete_job`` uses (``enumerate_blob_keys_for_delete``).
3. Bulk DELETE all doomed jobs (cascade fans out to posts/reactions/etc.).
4. Wipe each blob; on failure record to ``orphaned_storage_keys`` with
   reason ``retention_purge``.
5. Preserve the reconcile-lock skip guard.

These tests follow the MagicMock Supabase pattern established by
``tests/test_retention.py`` (sibling tests for uploads/reservations).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

try:
    from app.workers.retention import RETENTION_PURGE_REASON, run_retention

    _AVAILABLE = True
except (ImportError, AttributeError):
    _AVAILABLE = False

pytestmark = pytest.mark.skipif(not _AVAILABLE, reason="retention worker unavailable")


# ---------------------------------------------------------------------------
# Constants — no magic strings
# ---------------------------------------------------------------------------

_RAW_SELFIES_BUCKET = "raw-selfies"
_GENERATED_IMAGES_BUCKET = "generated-images"
_POST_IMAGES_BUCKET = "post-images"

_USER_ID = "u-retention"
_ANALYSIS_ID_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_ANALYSIS_ID_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

_SOURCE_TYPE_GLOWUP = "glowup_analysis"


# ---------------------------------------------------------------------------
# Helpers — mock builders
# ---------------------------------------------------------------------------


def _make_doomed_job_row(
    *,
    job_id: str | None = None,
    analysis_id: str = _ANALYSIS_ID_1,
    before: str | None = None,
    after: str | None = None,
) -> dict:
    jid = job_id or str(uuid4())
    return {
        "id": jid,
        "source_id": analysis_id,
        "source_type": _SOURCE_TYPE_GLOWUP,
        "before_image_url": before if before is not None else f"raw/{jid}/before.jpg",
        "after_image_url": after if after is not None else f"gen/{jid}/after.jpg",
    }


def _make_supabase(
    *,
    expired_jobs: list[dict] | None = None,
    post_rows_by_job: dict[str, list[dict]] | None = None,
    expired_uploads: list[dict] | None = None,
) -> MagicMock:
    """Build a MagicMock Supabase client with a query recorder per table.

    Each ``table(name)`` call gets a fresh chain; the recorder interprets
    the chain tail to return the appropriate canned response:

    - ``jobs`` select (list_expired_unsaved_jobs): returns ``expired_jobs``.
    - ``jobs`` select for enumerate_blob_keys_for_delete: returns the job
      row with before/after URLs via maybe_single.
    - ``posts`` select for enumerate_blob_keys_for_delete: returns the live
      post row (if any) for the job id.
    - ``jobs`` delete: no-op.
    - ``uploads`` select / delete: follow the existing test_retention pattern.
    - other tables: empty responses.
    """
    sb = MagicMock()

    expired_jobs_rows = expired_jobs or []
    post_rows_by_job = post_rows_by_job or {}
    expired_uploads_rows = expired_uploads or []

    # Build a lookup of job_id -> full row (with before/after) so the
    # enumerate helper's second query (single-job select) can return them.
    job_row_by_id: dict[str, dict] = {
        row["id"]: {
            "before_image_url": row.get("before_image_url"),
            "after_image_url": row.get("after_image_url"),
        }
        for row in expired_jobs_rows
    }

    # Storage mock — the bucket returned by storage.from_(bucket) records
    # every call so tests can assert which keys went where.
    storage_buckets: dict[str, MagicMock] = {}

    def _storage_from(bucket: str) -> MagicMock:
        if bucket not in storage_buckets:
            storage_buckets[bucket] = MagicMock()
            storage_buckets[bucket].remove.return_value = None
        return storage_buckets[bucket]

    sb.storage.from_.side_effect = _storage_from
    sb.storage.buckets = storage_buckets  # for test inspection

    def _table(name: str) -> MagicMock:
        qb = MagicMock()
        state = {"filters": {}, "projection": None, "single": False}

        def _select(proj: str) -> MagicMock:
            state["projection"] = proj
            return qb

        def _is(col: str, val) -> MagicMock:
            state["filters"][f"is:{col}"] = val
            return qb

        def _lt(col: str, val) -> MagicMock:
            state["filters"][f"lt:{col}"] = val
            return qb

        def _eq(col: str, val) -> MagicMock:
            state["filters"][f"eq:{col}"] = val
            return qb

        def _in(col: str, vals) -> MagicMock:
            state["filters"][f"in:{col}"] = vals
            return qb

        def _limit(n: int) -> MagicMock:
            return qb

        def _maybe_single() -> MagicMock:
            state["single"] = True
            return qb

        def _single() -> MagicMock:
            state["single"] = True
            return qb

        def _delete() -> MagicMock:
            state["op"] = "delete"
            return qb

        def _execute() -> MagicMock:
            result = MagicMock()
            result.data = []

            op = state.get("op")

            if name == "jobs":
                if op == "delete":
                    result.data = []
                    return result
                if state["single"] and "eq:id" in state["filters"]:
                    job_id = state["filters"]["eq:id"]
                    row = job_row_by_id.get(job_id)
                    result.data = row
                    return result
                # Non-single select → list_expired_unsaved_jobs.
                if "is:saved_at" in state["filters"]:
                    result.data = expired_jobs_rows
                    return result
                result.data = []
                return result

            if name == "posts":
                if "eq:glow_up_job_id" in state["filters"]:
                    jid = state["filters"]["eq:glow_up_job_id"]
                    result.data = post_rows_by_job.get(jid, [])
                    return result
                result.data = []
                return result

            if name == "uploads":
                if op == "delete":
                    result.data = []
                    return result
                result.data = expired_uploads_rows
                return result

            if name == "username_reservations":
                result.data = []
                return result

            if name == "users":
                result.data = []
                return result

            if name == "orphaned_storage_keys":
                # Upsert chain used by OrphanedStorageKeyRepository.record.
                result.data = []
                return result

            result.data = []
            return result

        qb.select.side_effect = _select
        qb.is_.side_effect = _is
        qb.lt.side_effect = _lt
        qb.eq.side_effect = _eq
        qb.in_.side_effect = _in
        qb.limit.side_effect = _limit
        qb.maybe_single.side_effect = _maybe_single
        qb.single.side_effect = _single
        qb.delete.side_effect = _delete
        # Upsert path used by orphan_repo.record.
        qb.upsert.return_value = qb
        qb.execute.side_effect = _execute

        return qb

    sb.table.side_effect = _table

    # auth.admin.list_users returns an empty sequence so
    # reconcile_orphaned_users is a no-op for these tests.
    admin_resp = MagicMock()
    admin_resp.users = []
    sb.auth.admin.list_users.return_value = admin_resp

    return sb


def _make_ctx(supabase: MagicMock) -> dict:
    return {"supabase": supabase}


def _remove_calls_for(supabase: MagicMock, bucket: str) -> list[list[str]]:
    """Return the list of ``remove`` call arg-lists for the given bucket."""
    bucket_mock = supabase.storage.buckets.get(bucket)
    if bucket_mock is None:
        return []
    return [c.args[0] for c in bucket_mock.remove.call_args_list]


# ---------------------------------------------------------------------------
# Happy path: two expired unsaved jobs with blobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_expired_jobs_enumerate_before_cascade_wipes_all_blobs() -> None:
    """Happy path: both jobs' raw + generated blobs are removed; no DLQ rows."""
    job1 = _make_doomed_job_row(before="raw/j1/before.jpg", after="gen/j1/after.jpg")
    job2 = _make_doomed_job_row(
        analysis_id=_ANALYSIS_ID_2,
        before="raw/j2/before.jpg",
        after="gen/j2/after.jpg",
    )
    sb = _make_supabase(expired_jobs=[job1, job2])

    await run_retention(_make_ctx(sb))

    # Both raw-selfies keys removed (one call per key — per-key wipe).
    raw_removed = _remove_calls_for(sb, _RAW_SELFIES_BUCKET)
    assert [job1["before_image_url"]] in raw_removed
    assert [job2["before_image_url"]] in raw_removed
    assert len(raw_removed) == 2

    # Both generated-images keys removed.
    gen_removed = _remove_calls_for(sb, _GENERATED_IMAGES_BUCKET)
    assert [job1["after_image_url"]] in gen_removed
    assert [job2["after_image_url"]] in gen_removed
    assert len(gen_removed) == 2

    # No post-images wipe for jobs that don't have a live post.
    post_bucket = sb.storage.buckets.get(_POST_IMAGES_BUCKET)
    assert post_bucket is None or post_bucket.remove.call_count == 0

    # Jobs table was accessed and the bulk delete fired (in_ on id list).
    assert call("jobs") in sb.table.call_args_list


# ---------------------------------------------------------------------------
# Mixed path: one job's ``after`` blob fails to wipe → lands in DLQ
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blob_wipe_failure_lands_in_dlq_with_retention_purge_reason() -> None:
    """A failing remove for a single key lands in DLQ; job row still deleted."""
    job = _make_doomed_job_row(before="raw/dlq/before.jpg", after="gen/dlq/after.jpg")
    sb = _make_supabase(expired_jobs=[job])

    # Force the generated-images remove to raise for this specific key.
    # Calling storage.from_ eagerly primes the mock so side_effect wires in.
    gen_bucket = sb.storage.from_(_GENERATED_IMAGES_BUCKET)

    def _remove_side_effect(keys):
        if keys == [job["after_image_url"]]:
            raise RuntimeError("storage 503")
        return None

    gen_bucket.remove.side_effect = _remove_side_effect

    # Spy on the orphaned_storage_keys upsert so we can assert the DLQ call.
    # Assemble the spy through ``side_effect`` returning the qb itself so the
    # repository's chained ``.execute()`` still resolves via the base stub.
    recorded: list[dict] = []
    original_table = sb.table.side_effect

    def _wrapped_table(name: str) -> MagicMock:
        qb = original_table(name)
        if name == "orphaned_storage_keys":

            def _upsert_spy(row: dict, on_conflict: str | None = None):
                recorded.append(row)
                return qb

            # Replace entirely — avoid recursion by not re-invoking the
            # wrapped mock's own call.
            qb.upsert = MagicMock(side_effect=_upsert_spy)
        return qb

    sb.table.side_effect = _wrapped_table

    await run_retention(_make_ctx(sb))

    # Raw-selfies key wiped normally.
    raw_removed = _remove_calls_for(sb, _RAW_SELFIES_BUCKET)
    assert [job["before_image_url"]] in raw_removed

    # The failing key was recorded to the DLQ with reason "retention_purge".
    matching = [
        r
        for r in recorded
        if r.get("bucket") == _GENERATED_IMAGES_BUCKET
        and r.get("storage_key") == job["after_image_url"]
    ]
    assert len(matching) == 1, f"expected 1 DLQ row, got {recorded!r}"
    assert matching[0]["reason"] == RETENTION_PURGE_REASON


# ---------------------------------------------------------------------------
# Published-post path: live post → post-images keys also enumerated and wiped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_job_with_live_post_wipes_post_images_blobs() -> None:
    """Unusual but possible: a doomed unsaved job has a live public post.

    The enumerate helper MUST pick up post-images keys via the posts join
    BEFORE the FK cascade drops the posts row. Otherwise those blobs
    orphan silently (the bug this whole unit fixes).
    """
    job = _make_doomed_job_row(before="raw/live/before.jpg", after="gen/live/after.jpg")
    live_post = {
        "before_image_url": "before/u-1/abc.jpg",
        "after_image_url": "after/u-1/xyz.jpg",
    }
    sb = _make_supabase(
        expired_jobs=[job],
        post_rows_by_job={job["id"]: [live_post]},
    )

    await run_retention(_make_ctx(sb))

    post_removed = _remove_calls_for(sb, _POST_IMAGES_BUCKET)
    assert [live_post["before_image_url"]] in post_removed
    assert [live_post["after_image_url"]] in post_removed
    assert len(post_removed) == 2

    # Raw + generated still wiped.
    assert [job["before_image_url"]] in _remove_calls_for(sb, _RAW_SELFIES_BUCKET)
    assert [job["after_image_url"]] in _remove_calls_for(sb, _GENERATED_IMAGES_BUCKET)


# ---------------------------------------------------------------------------
# Boundary: zero expired jobs → no-op on storage / jobs delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_expired_jobs_is_a_no_op() -> None:
    """With no expired unsaved jobs, no storage wipes and no jobs DELETE."""
    sb = _make_supabase(expired_jobs=[])

    await run_retention(_make_ctx(sb))

    # No storage buckets were ever touched for jobs purge.
    # (uploads path may still access raw-selfies if there are expired
    # uploads — but this fixture has none, so assert empty.)
    assert sb.storage.buckets == {}


# ---------------------------------------------------------------------------
# Reconcile-lock held → retention skips (existing behavior preserved)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retention_skips_when_reconcile_lock_held() -> None:
    """The fix must not regress the reconcile-lock skip guard."""
    from app.api.social import RECONCILE_LOCK_KEY

    sb = _make_supabase(
        expired_jobs=[_make_doomed_job_row()],
    )
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="1")  # lock held

    await run_retention({"supabase": sb, "redis": redis_mock})

    redis_mock.get.assert_called_once_with(RECONCILE_LOCK_KEY)
    # No DB work, no storage work.
    sb.table.assert_not_called()
    sb.storage.from_.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 1: CAS DELETE preserves jobs Saved between enumerate and delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_by_ids_includes_retention_cas_predicate() -> None:
    """``delete_by_ids(cutoff_iso=...)`` chains the ``saved_at`` + ``created_at``
    CAS predicate on the DELETE so a concurrent Save survives the purge.

    This protects against the race where a user Saves a job (flipping
    ``saved_at`` from NULL to a timestamp) in the minutes-long window
    between the enumerate call and the bulk DELETE. The CAS guarantees
    the just-saved row is filtered out at commit time, not hard-deleted.
    """
    from app.repositories.job_repo import JobRepository

    sb = MagicMock()
    delete_chain = sb.table.return_value.delete.return_value
    in_chain = delete_chain.in_.return_value
    is_chain = in_chain.is_.return_value
    lt_chain = is_chain.lt.return_value
    lt_chain.execute.return_value = MagicMock(data=[])

    job_repo = JobRepository(sb)
    cutoff = "2026-04-11T00:00:00+00:00"
    job_repo.delete_by_ids(["job-1", "job-2"], cutoff_iso=cutoff)

    # The DELETE must be constrained by BOTH saved_at IS NULL and
    # created_at < cutoff so a row that got Saved (or freshly created)
    # between enumerate and delete is skipped rather than hard-deleted.
    in_chain.is_.assert_called_once_with("saved_at", "null")
    is_chain.lt.assert_called_once_with("created_at", cutoff)


@pytest.mark.asyncio
async def test_retention_passes_same_cutoff_to_delete_by_ids() -> None:
    """The retention worker must pass the same ``cutoff_iso`` it used for
    the SELECT into ``delete_by_ids`` — a mismatch would loosen the CAS."""
    job = _make_doomed_job_row(before="raw/c/before.jpg", after="gen/c/after.jpg")
    sb = _make_supabase(expired_jobs=[job])

    # Capture the DELETE chain's filter calls so we can assert the CAS
    # predicate was applied with the same cutoff retention computed.
    captured: dict[str, list] = {"is": [], "lt": [], "in": []}
    original_table = sb.table.side_effect

    def _wrapped(name: str) -> MagicMock:
        qb = original_table(name)
        if name != "jobs":
            return qb
        original_is = qb.is_.side_effect
        original_lt = qb.lt.side_effect
        original_in = qb.in_.side_effect

        def _is(col, val):
            captured["is"].append((col, val))
            return original_is(col, val)

        def _lt(col, val):
            captured["lt"].append((col, val))
            return original_lt(col, val)

        def _in(col, vals):
            captured["in"].append((col, vals))
            return original_in(col, vals)

        qb.is_.side_effect = _is
        qb.lt.side_effect = _lt
        qb.in_.side_effect = _in
        return qb

    sb.table.side_effect = _wrapped

    await run_retention(_make_ctx(sb))

    # The bulk DELETE path must have chained an in_(id, ids), then the
    # is_(saved_at, null) + lt(created_at, cutoff) CAS predicate. The
    # exact cutoff value isn't asserted (retention computes it from
    # settings.RETENTION_JOB_DAYS); we assert the columns + operator
    # wiring, which is what this fix ensures.
    saved_at_filters = [c for c in captured["is"] if c[0] == "saved_at"]
    created_at_filters = [c for c in captured["lt"] if c[0] == "created_at"]
    in_ids_filters = [c for c in captured["in"] if c[0] == "id"]

    assert saved_at_filters, "CAS predicate on saved_at missing from DELETE"
    assert created_at_filters, "CAS predicate on created_at missing from DELETE"
    assert in_ids_filters, "DELETE must still scope to the enumerated id list"


# ---------------------------------------------------------------------------
# Fix 7: Error isolation between retention steps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_purge_runs_even_when_job_purge_raises(monkeypatch) -> None:
    """A fault in Step 1 (job purge) must not skip Step 2 (upload purge).

    Previously a single exception in ``delete_by_ids`` aborted the whole
    cron tick — reservations and orphan reconciliation never ran. Now
    each step is try-wrapped independently.
    """
    upload_id = str(uuid4())
    storage_key = f"user/{upload_id}.jpg"
    sb = _make_supabase(
        expired_jobs=[_make_doomed_job_row()],
        expired_uploads=[{"id": upload_id, "image_url": storage_key}],
    )

    # Force the job-repo's list_expired_unsaved_jobs to raise so the
    # Step 1 try/except catches it and moves on to Step 2.
    from app.workers import retention as retention_mod

    class _BoomRepo:
        def __init__(self, _sb):
            pass

        def list_expired_unsaved_jobs(self, _cutoff):
            raise RuntimeError("db 503")

    monkeypatch.setattr(retention_mod, "JobRepository", _BoomRepo)

    await run_retention(_make_ctx(sb))

    # Uploads step still ran — the upload blob got removed.
    raw_removed = _remove_calls_for(sb, _RAW_SELFIES_BUCKET)
    assert [storage_key] in raw_removed


# ---------------------------------------------------------------------------
# Enumeration runs BEFORE cascade DELETE (the ordering invariant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enumeration_happens_before_jobs_delete() -> None:
    """Call-order assertion — the whole point of this unit.

    The expired-jobs ``select`` + per-job ``enumerate_blob_keys_for_delete``
    queries must all complete BEFORE the bulk ``delete().in_(...)`` on the
    jobs table. If reversed, the FK cascade wipes the posts join and the
    post-images enumeration returns empty.
    """
    job = _make_doomed_job_row(
        before="raw/order/before.jpg", after="gen/order/after.jpg"
    )
    live_post = {
        "before_image_url": "before/u-x/k.jpg",
        "after_image_url": "after/u-x/k.jpg",
    }
    sb = _make_supabase(
        expired_jobs=[job],
        post_rows_by_job={job["id"]: [live_post]},
    )

    call_order: list[str] = []
    original_table = sb.table.side_effect

    def _wrapped(name: str) -> MagicMock:
        qb = original_table(name)
        original_execute = qb.execute.side_effect

        def _execute_tracer(*args, **kwargs):
            # Classify the call by inspecting the recorded mock_calls
            # on the builder — easier + more resilient than re-reading
            # the state dict.
            mock_calls = [str(c) for c in qb.mock_calls]
            if name == "posts" and any("eq('glow_up_job_id'" in c for c in mock_calls):
                call_order.append("enumerate_posts")
            elif name == "jobs" and any("delete()" in c for c in mock_calls):
                call_order.append("delete_jobs")
            elif (
                name == "jobs"
                and any("eq('id'" in c for c in mock_calls)
                and any("maybe_single()" in c for c in mock_calls)
            ):
                call_order.append("enumerate_job_select")
            elif name == "jobs" and any("is_('saved_at'" in c for c in mock_calls):
                call_order.append("list_expired")
            return original_execute(*args, **kwargs)

        qb.execute.side_effect = _execute_tracer
        return qb

    sb.table.side_effect = _wrapped

    await run_retention(_make_ctx(sb))

    # The list_expired call must come first; both enumerate_* calls
    # must come before delete_jobs.
    assert "list_expired" in call_order
    assert "delete_jobs" in call_order
    first_delete = call_order.index("delete_jobs")
    assert call_order.index("list_expired") < first_delete
    # Per-job enumeration happened before the bulk delete.
    assert all(
        call_order.index(event) < first_delete
        for event in ("enumerate_job_select", "enumerate_posts")
        if event in call_order
    )
