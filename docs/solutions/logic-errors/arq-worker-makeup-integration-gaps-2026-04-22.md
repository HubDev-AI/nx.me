---
title: ARQ Worker Integration Gaps in Makeup Feature
date: 2026-04-22
category: docs/solutions/logic-errors
module: makeup
problem_type: logic_error
component: background_job
symptoms:
  - All makeup generation jobs silently dropped — enqueue succeeds, worker never picks up
  - Fair-use quota never refunded when makeup generation fails terminally
  - Makeup advisor nudges never fire after job completion
root_cause: incomplete_setup
resolution_type: code_fix
severity: critical
related_components:
  - service_object
  - assistant
tags:
  - arq
  - worker
  - makeup
  - background-job
  - integration
  - stub
---

# ARQ Worker Integration Gaps in Makeup Feature

## Problem

The makeup feature was built unit-by-unit across multiple PRs, leaving three ARQ worker integration wires incomplete by the time they were reviewed together: the enqueue call used the wrong function name (silently dropped all jobs), the fair-use decrement stub was never wired to the real Lua implementation, and the makeup nudge function was never registered in `WorkerSettings.functions`.

## Symptoms

- All makeup generation jobs silently dropped — `enqueue_job` returned success but the ARQ worker never executed anything
- Fair-use quota consumed on terminal failures and never refunded — users hit their daily cap prematurely
- `generate_nudge_makeup` defined in `nudge_scheduler.py` but post-makeup nudges never delivered

## What Didn't Work

- The pre-record step (`job_repo.pre_record_makeup_job`) and the `202 ACCEPTED` response both succeeded, so API-level smoke tests showed no error
- Log monitoring showed jobs entering `QUEUED` status but never transitioning — initially mistaken for a worker slowness issue

## Solution

Three separate fixes, all in `app/`:

**1. Wrong ARQ function name in `app/api/makeup.py`**

```python
# Before — silently enqueues to a name no worker listens for
await request.app.state.arq_pool.enqueue_job(
    "makeup_generate",
    str(job_id),
)

# After — matches the registered function name in worker.py
await request.app.state.arq_pool.enqueue_job(
    "process_generation_job",
    str(job_id),
)
```

**2. Stub fair-use decrement wired in `app/generation/makeup_pipeline.py`**

```python
# Before — explicit no-op stub, never refunded quota on terminal failures
async def _decrement_fair_use(redis_client, user_id, namespaced_key):
    """Stub — Unit 6 replaces with Lua-backed DECR + marker DEL."""
    pass

# After — delegates to the Lua-backed implementation
async def _decrement_fair_use(redis_client, user_id, namespaced_key):
    if not namespaced_key:
        return
    from app.api.rate_limiters.makeup_fair_use import fair_use_decr
    try:
        await fair_use_decr(redis_client, user_id, namespaced_key)
    except Exception:
        logger.warning(
            "fair_use_decr failed for user=%s key=%s", user_id, namespaced_key
        )
```

**3. Missing function in `app/worker_settings.py`**

```python
# Before
from app.advisor.nudge_scheduler import (
    generate_nudge,
    write_analysis_insight_job,
)
functions = [process_generation_job, generate_nudge, write_analysis_insight_job, ...]

# After
from app.advisor.nudge_scheduler import (
    generate_nudge,
    generate_nudge_makeup,
    write_analysis_insight_job,
)
functions = [process_generation_job, generate_nudge, generate_nudge_makeup, write_analysis_insight_job, ...]
```

**Bonus: wrong failure code in `app/generation/makeup_pipeline.py`**

```python
# Before — "config" adapter errors incorrectly classified as retryable
failure_code = (
    MAKEUP_FAILURE_NON_RETRYABLE
    if exc.kind == "non_retryable"
    else MAKEUP_FAILURE_RETRYABLE   # BUG: "config" errors should also be non_retryable
)

# After
failure_code = MAKEUP_FAILURE_NON_RETRYABLE  # both non_retryable and config are terminal
```

## Why This Works

ARQ dispatches by string function name — `enqueue_job("X", ...)` silently no-ops if no registered function is named `"X"`. The correct name is `"process_generation_job"` (the Python function name of the handler in `app/generation/worker.py`).

The fair-use Lua scripts (`makeup_fair_use_incr.lua` / `makeup_fair_use_decr.lua`) were implemented in the same PR batch but the pipeline stub was never updated to call them — leaving quota permanently consumed on terminal failures.

ARQ only dispatches to functions listed in `WorkerSettings.functions`. A function that is imported but not listed in `functions` is unreachable by the worker.

## Prevention

**1. Grep-check for unresolved stubs before merging makeup-related PRs:**

```bash
grep -rn "Stub\|No-op until\|TODO.*Unit" app/generation/ app/api/
```

Any comment matching this pattern in a production code path is a blocking review comment.

**2. Integration smoke test for each new ARQ function:**

```python
async def test_makeup_generate_enqueues_correct_function(mock_arq_pool):
    await generate_makeup(...)
    mock_arq_pool.enqueue_job.assert_called_once_with(
        "process_generation_job", ANY
    )
```

**3. Verify `WorkerSettings.functions` covers every function dispatched via `enqueue_job` in the codebase:**

```bash
# Find all enqueue_job call strings
grep -rn 'enqueue_job("' app/ | grep -oP '(?<=enqueue_job\(")[^"]+' | sort -u

# Compare against registered function names
python -c "
from app.worker_settings import WorkerSettings
print([f.__name__ for f in WorkerSettings.functions])
"
```

**4. When adding a new feature that uses ARQ, checklist:**

- [ ] `enqueue_job` call uses the Python function `__name__` exactly
- [ ] Function added to `WorkerSettings.functions`
- [ ] Any stub functions replaced before the PR merges (not in a follow-up PR)
- [ ] Fair-use / quota hooks wired if the feature has a rate limit

## Related Issues

- PR #216: `feat+ai-makeup` — makeup feature integration review where these issues were caught
- `app/generation/worker.py` — `process_generation_job` is the registered entry point for all generation types dispatched by `source_type`
- `app/api/rate_limiters/makeup_fair_use.py` — Lua-backed fair-use scripts (`fair_use_incr` / `fair_use_decr`)
