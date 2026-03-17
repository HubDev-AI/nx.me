# Python Review

- Date: 2026-03-17
- Scope: `app/**/*.py` (93 files)
- Reviewer: Automated via Claude Code (Sonnet 4.6)
- Static analysis: ruff/mypy not installed; findings from direct code inspection.

---

## Findings

### Critical

---

**CRITICAL-1: Missing HTTP response status check on downloaded provider image**
File: `app/generation/worker.py:175`

```python
async with httpx.AsyncClient() as client:
    resp = await client.get(gen_result.image_url)
    gen_image_bytes = resp.content
```

Issue: `resp.raise_for_status()` is never called. If fal.ai returns a non-2xx (403, 503, etc.) the worker silently writes an error HTML page as JPEG bytes into Supabase storage, passes it to identity checking (which will fail to detect a face), and then either fails the job or—if the HTML happens to pass the NSFW screen—writes garbage bytes as the output image.

The same pattern occurs at `worker.py:205` (source image download for identity check) and `worker.py:241` (retry image download).

Fix: Add `resp.raise_for_status()` immediately after each `await client.get(...)`.

---

**CRITICAL-2: Race condition in Redis rate-limit read + write (reactions)**
File: `app/api/social.py:257-294`

```python
current_rate = int(await redis_client.get(rate_key) or 0)   # read
if current_rate >= _REACTION_RATE_LIMIT:                     # check
    raise ...
# ... post existence check (DB round-trip) ...
pipe.incr(rate_key)
pipe.expire(rate_key, _REACTION_RATE_WINDOW_SECONDS)
await pipe.execute()                                          # write
```

Issue: The GET and the INCR are separated by several await points (including a DB query). Two concurrent requests from the same IP can both read `0`, both pass the check, and both INCR — meaning the rate limiter can be bypassed up to `_REACTION_RATE_LIMIT * number_of_concurrent_requests` times. This is the same pattern as the napkin note ("Treated the first X-Forwarded-For value as trustworthy").

Fix: Use `INCR` first (same atomic pipeline + `NX` EXPIRE pattern used correctly in `app/services/rate_limiter.py`), check the returned count, and decrement with `DECRBY` if over limit. Mirror the pattern from `check_registration_rate_limit`.

---

**CRITICAL-3: Broad `except Exception` swallows real webhook processing errors**
File: `app/api/webhooks.py:88-92`

```python
except Exception:
    logger.exception("Error processing webhook event %s (type=%s)", event_id, event_type)
    return {"status": "processing_error"}
```

Issue: Any runtime bug (e.g., `KeyError`, `AttributeError`, bad DB schema) is indistinguishable from a transient error. Stripe receives a `200` so it will **never retry**. The event is already recorded in `processed_webhook_events`, so manual recovery requires both finding the failure in logs AND deleting the idempotency record. Credit purchases and subscription activations can be silently lost.

Fix: Catch only expected transient exceptions (network errors, DB connectivity). Let programming errors propagate as `500` so Stripe retries. If returning `200` is intentional, add a dead-letter table insert inside the handler so no event is silently dropped.

---

**CRITICAL-4: `verify_email` endpoint is synchronous but calls async `TrialGrantor`**
File: `app/api/auth.py:246-302`

```python
@router.post("/verify-email", response_model=VerifyEmailResponse)
def verify_email(                          # sync def
    ...
) -> VerifyEmailResponse:
    grantor = TrialGrantor(supabase)
    grantor.grant(UUID(user_id_str))       # sync, fine
```

Issue: The handler itself is sync (`def`, not `async def`). While `TrialGrantor.grant` is sync, the endpoint also calls `supabase.auth.admin.get_user_by_id` synchronously inside an async FastAPI app running with an async event loop. Blocking sync IO in a sync FastAPI route runs in a thread pool (FastAPI handles this), but the function signature accepts `claims: dict = Depends(get_current_user)` while `get_current_user` returns `UserClaims`. The declared type annotation is wrong and will cause mypy failures. This is a type correctness issue at minimum.

Fix: Change `claims: dict` to `claims: UserClaims`. Also audit whether all sync Supabase calls inside `async` routes are intentionally blocking the thread pool.

---

### High

---

**HIGH-1: `build_prompt` has no type annotation on `analysis_result` parameter**
File: `app/generation/prompt_builder.py:146`

```python
def build_prompt(
    analysis_result,           # missing type annotation
    face_ratio: float = 0.30,
) -> tuple[str, str, dict]:
```

Issue: Missing `AnalysisResult` annotation means static analysers and IDE tooling cannot validate the call sites. The return type `dict` for the third element should be `dict[str, float | int]`.

Fix: `analysis_result: AnalysisResult` (import from `app.face_analysis.models`).

---

**HIGH-2: `AdvisorService.__init__` accepts `llm_adapter: Any`**
File: `app/advisor/service.py:57`

```python
def __init__(
    self,
    supabase: Client,
    redis_client: aioredis.Redis,
    llm_adapter: Any,           # should be LLMPort
) -> None:
```

Issue: The `LLMPort` Protocol is defined in `app/advisor/llm_port.py`. Using `Any` disables all type-checking on adapter calls. Same pattern in `MemoryManager.__init__` (`llm_adapter: Any`).

Fix: Import and use `LLMPort` from `app.advisor.llm_port`.

---

**HIGH-3: `_handle_checkout_completed` is `async` but all sub-handlers are sync — mixing sync Supabase I/O inside an async route without await**
File: `app/api/webhooks.py:102`

```python
async def _handle_checkout_completed(supabase: Client, session: dict, event_id: str) -> None:
    ...
    supabase.table("credit_ledger").insert({...}).execute()   # blocking sync call
```

Issue: `_handle_checkout_completed` is declared `async` but contains only blocking sync Supabase calls with no `await`. The call is `await`ed in the route handler. This is not an error at runtime (the coroutine completes), but it misleads readers into thinking these calls are non-blocking and prevents the event loop from scheduling other work during the I/O. It also means the other handlers (`_handle_subscription_created`, etc.) are plain sync functions called without `await` — inconsistency that will cause confusion.

Fix: Either make all handlers `async` and use an async Supabase client, or make all handlers sync and call them without `await`.

---

**HIGH-4: `reaction_count` Redis counter can drift below zero or go stale permanently**
File: `app/api/social.py:284-293`

```python
cached = await redis_client.get(redis_counter_key)
if cached is None:
    await redis_client.set(redis_counter_key, post.data["reaction_count"], ex=60)  # 60s TTL
new_count = await redis_client.incr(redis_counter_key)
```

Issue: The TTL is set only on cache miss (`set(..., ex=60)`). After the key expires and is re-seeded, the INCR adds to the fresh value. However, between the `SET` and the `INCR`, another concurrent request can `INCR` on the freshly-set value without going through the cache miss path. More importantly, the nightly `reconcile_reaction_counts` ARQ task deletes Redis keys by post ID, but the `SET` in the react endpoint does **not** reset the TTL if the key already exists. This means a popular post's key can live indefinitely in Redis, accumulating drift if `persist_reaction` ARQ jobs fail silently.

Fix: Use `redis_client.incrbyfloat` / `incr` exclusively (no `set` for warm-up). On cache miss, read from DB and use `SET NX` to avoid overwriting an existing counter.

---

**HIGH-5: `_forbidden_output_terms` has a duplicate entry**
File: `app/advisor/content_filter.py:18-33`

```python
_FORBIDDEN_OUTPUT_TERMS: frozenset[str] = frozenset([
    ...
    "ranking",
    ...
    "ranking",       # duplicated
    ...
])
```

Issue: `"ranking"` appears twice in the list literal. While `frozenset` deduplicates, this is a latent maintenance issue indicating the list is manually managed without validation. A missing forbidden term (e.g., "ugly" variants like "not pretty") could slip through.

Fix: Remove the duplicate. Add a test that asserts no duplicates in the raw list before `frozenset()` conversion. Consider loading forbidden terms from a config file for auditability.

---

**HIGH-6: `_sign_url` nested function defined inside a loop-adjacent block with silent exception swallowing**
File: `app/api/users.py:242-249`

```python
def _sign_url(bucket: str, storage_key: str) -> str | None:
    try:
        return supabase.storage.from_(bucket).create_signed_url(
            storage_key, settings.SIGNED_URL_EXPIRY_SECONDS
        )["signedURL"]
    except Exception:           # bare except, no logging of the actual exc
        logger.warning("Failed to sign URL: bucket=%s key=%s", bucket, storage_key)
        return None
```

Issue: The exception object is swallowed entirely; the warning log doesn't include `exc_info=True`. Diagnosing systematic signing failures (wrong bucket name, revoked service key) will require adding logging retroactively under production pressure.

Fix: `logger.warning("...", bucket, storage_key, exc_info=True)`.

---

**HIGH-7: `compute_adaptive_params` uses chained `elif` with redundant conditions**
File: `app/generation/prompt_builder.py:76-80`

```python
elif keyword_count == 3 or keyword_count == 4:
```

Issue: Minor but the expression should be `keyword_count in (3, 4)` per Pythonic idioms. More importantly, the function has no type annotation for its return value (`dict` is declared but not the dict's value types), and the `timedelta` import at line 12 is unused.

Fix: Remove the unused `from datetime import timedelta` import. Annotate return as `dict[str, float | int]`. Change `== 3 or == 4` to `in (3, 4)`.

---

**HIGH-8: `Optional` used from `typing` instead of `X | None` syntax**
File: `app/api/users.py:12, 38, 44, 49, 51, 62, 66`

```python
from typing import Optional
...
class ProfileResponse(BaseModel):
    avatar_url: Optional[str]
```

Issue: The project uses Python 3.10+ syntax elsewhere (`str | None`) but reverts to the legacy `Optional[str]` form exclusively in `app/api/users.py`. This is a consistency violation and the `Optional` import can be removed.

Fix: Replace all `Optional[X]` with `X | None`, remove the `typing.Optional` import.

---

**HIGH-9: `(ValueError, Exception)` catch pattern is redundant**
File: `app/api/auth.py:572`

```python
except (ValueError, Exception) as release_exc:  # noqa: BLE001
```

Issue: `Exception` is a supertype of `ValueError`, so the `ValueError` in the tuple is unreachable dead code. The real intent appears to be "catch anything" (the `BLE001` noqa confirms this), but the comment-suppression approach hides intent. The same issue exists conceptually at `trial_grantor.py:77` where `except Exception: # noqa: BLE001` silently degrades to a fallback without re-raising.

Fix: Replace with `except Exception as release_exc:` and add a comment explaining why broad-catch is intentional here (account deletion — best-effort release).

---

**HIGH-10: `identity_checker.py` acquires ArcFace lock twice with no exception guard between releases**
File: `app/generation/identity_checker.py:67-78`

```python
with _arcface_lock:
    source_faces = _arcface_app.get(source_img)
if not source_faces:
    ...
    return IdentityCheckResult(...)

with _arcface_lock:
    gen_faces = _arcface_app.get(gen_img)
```

Issue: Two separate lock acquisitions with a return between them is correct, but since `_arcface_app.get()` can raise (e.g., OOM, corrupt image), an unhandled exception between the two `with` blocks will propagate without the lock being held — which is fine, but the outer caller (`worker.py`) wraps the entire thing in `loop.run_in_executor`, and an exception there goes to the outer `except Exception` handler that calls `_fail_job` — which is correct. However, the current behaviour discards the exception traceback from within the executor. This should be logged before re-raising.

Fix: Wrap the `run_in_executor` call with explicit exception logging so the identity check failure reason is captured.

---

### Medium

---

**MEDIUM-1: Magic numbers in `cost_tracker.py` without named constants**
File: `app/generation/cost_tracker.py:41, 66, 122, 135, 153`

Examples:
- `pipe.expire(key, 90000)` — 90000 = "25 hours", not self-documenting
- `return total_cost / max(bucket_count * 10, 1)` — the `10` is undocumented (implied: 10 requests per hour bucket)
- `if failures >= 5:` — circuit breaker threshold, not configurable
- `await self._redis.set("gen:circuit:open", "1", ex=120)` — 120s cooldown not in config

Fix: Define named constants at the module top:
```python
_COST_BUCKET_TTL_SECONDS = 90_000   # 25h
_REQUESTS_PER_HOUR_ESTIMATE = 10
_CIRCUIT_BREAKER_THRESHOLD = 5
_CIRCUIT_BREAKER_COOLDOWN_SECONDS = 120
```

---

**MEDIUM-2: `check_queue_depth` has a `max_depth` parameter but the caller always uses `settings.MAX_QUEUE_DEPTH`; the default parameter value `15000` duplicates the config default**
File: `app/generation/cost_tracker.py:91`

```python
async def check_queue_depth(self, max_depth: int = 15000) -> bool:
```

Issue: The default `15000` is a duplicate of `MAX_QUEUE_DEPTH` in `config.py`. If the config default is changed, this local default silently stays at `15000`.

Fix: Remove the default value and require the caller to pass `settings.MAX_QUEUE_DEPTH` explicitly, or remove the parameter entirely and read from config directly.

---

**MEDIUM-3: Inline `import re` inside route handler**
File: `app/api/social.py:241`

```python
elif x_guest_token:
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", x_guest_token):
```

Issue: `import re` is a standard library module. Placing it inside a hot path (called on every reaction) forces a module lookup on every request, even though `re` is cached after the first import. More importantly, the pattern `r"[0-9a-f]{64}"` is not pre-compiled. For a hot endpoint this should be a module-level compiled pattern.

Fix: Move `import re` to the top of the file. Add a module-level `_GUEST_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")` and use `_GUEST_TOKEN_RE.fullmatch(x_guest_token)`.

---

**MEDIUM-4: `logger.info` call at profile view is noisy for a high-traffic public endpoint**
File: `app/api/users.py:122`

```python
logger.info("Profile viewed for user %s", user_id)
```

Issue: This logs on every public profile view with no rate limiting. In production with a social feed, this will generate millions of log entries per day, masking real INFO-level events.

Fix: Downgrade to `logger.debug` or remove.

---

**MEDIUM-5: `datetime` imported inside function body**
File: `app/api/users.py:332-334`

```python
if updates:
    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
```

Issue: `datetime` and `timezone` are already available at the module level elsewhere in the file (they should be imported at the top). This is a deferred import inside a hot path with no benefit.

Fix: Add `from datetime import datetime, timezone` to the module-level imports.

---

**MEDIUM-6: `_seven_days_ago_iso` imports `timedelta` inside a module where it is already imported at the top**
File: `app/advisor/memory_manager.py:331`

```python
def _seven_days_ago_iso() -> str:
    from datetime import timedelta     # already imported at line 10
    return (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat()
```

Issue: `timedelta` is already imported at the module top (`from datetime import datetime, timezone`). The inner import is redundant.

Fix: Remove the inner `from datetime import timedelta` — it is already available.

---

**MEDIUM-7: `_build_user_data` in `AdvisorService` re-imports `build_user_data_block` inside the method body**
File: `app/advisor/service.py:381`

```python
from app.advisor.context_builder import build_user_data_block
return build_user_data_block(...)
```

Issue: `build_user_data_block` is already imported at the top of the file (`from app.advisor.context_builder import build_context, build_user_data_block, has_visual_trigger`). The in-method import is a duplicate that suggests the top import is not being relied upon.

Fix: Remove the in-method import; the symbol is already in scope from the top-level import.

---

**MEDIUM-8: PEP 8 import ordering violations**
File: `app/api/auth.py:24-34`

```python
from app.api.deps import get_current_user, get_redis, get_supabase
from app.api.middleware.auth import UserClaims
from app.config import settings
from app.entitlement.trial_grantor import TrialGrantor
from app.services.disposable_email import is_disposable_email
from slugify import slugify                   # third-party between first-party
from app.services.rate_limiter import (
    check_ip_registration_rate_limit,
    ...
)
```

Issue: `from slugify import slugify` is a third-party import placed between first-party `app.*` imports. PEP 8 / isort requires: stdlib → third-party → first-party, each group separated by a blank line.

Fix: Move `from slugify import slugify` to the third-party import group above the `app.*` imports.

---

**MEDIUM-9: `_post_check` in `advisor/service.py` has weak repetition detection**
File: `app/advisor/service.py:476`

```python
last_words = " ".join(recent_messages[-1].split()[:3]).lower()
this_words = " ".join(response.split()[:3]).lower()
if last_words and last_words == this_words:
    return "Start differently."
```

Issue: Checking only the first 3 words is a very narrow repetition signal. Two completely different messages can share a 3-word opener (e.g., "I think you"). More importantly, `recent_messages[-1]` is the **last** advisor message, not the one immediately before the current response. If the conversation had 5 back-and-forth turns, this only checks against the most recent one.

This is a functional/product issue, not purely a code quality issue, but flagged because the simplistic implementation may produce a false sense of correctness.

---

**MEDIUM-10: `extract_memories_from_turn` catches `(json.JSONDecodeError, Exception)` — redundant since `Exception` is the supertype**
File: `app/advisor/memory_manager.py:253`

```python
except (json.JSONDecodeError, Exception) as exc:
    logger.warning("Memory extraction failed: %s", exc)
    return
```

Same pattern as HIGH-9. `json.JSONDecodeError` is a subclass of `ValueError` which is a subclass of `Exception`. The explicit listing of `json.JSONDecodeError` is dead code.

Fix: Use `except Exception as exc:` with a comment that `json.JSONDecodeError` is the expected common case.

---

**MEDIUM-11: `advisor/content_filter.py` rate-limit check reads THEN writes — same TOCTOU race as CRITICAL-2**
File: `app/advisor/content_filter.py:80-88`

```python
count = int(await redis_client.get(key) or 0)
if count >= settings.ADVISOR_CHAT_RATE_LIMIT:
    raise ValueError("RATE_LIMIT_EXCEEDED")
pipe = redis_client.pipeline()
pipe.incr(key)
pipe.expire(key, 3600)
await pipe.execute()
```

Issue: Same read-then-write pattern as CRITICAL-2. Two concurrent requests will both read the same count, both pass the check, and both INCR. This is less severe here than in CRITICAL-2 (chat messages vs. reactions) but advisors can overshoot their rate limit under concurrent load.

Fix: INCR first, then check the returned value, DECRBY if over limit (atomic pattern from `check_registration_rate_limit`).

---

**MEDIUM-12: `MAX_PROMPT_KEYWORDS` is used as a cap, but `prepare_keywords` can exceed it by adding a style theme after capping**
File: `app/generation/prompt_builder.py:118-125`

```python
if len(ordered) > settings.MAX_PROMPT_KEYWORDS:
    ordered = ordered[:settings.MAX_PROMPT_KEYWORDS]

if len(ordered) <= 4:
    ordered.append(random.choice(_STYLE_THEMES))  # can push past MAX_PROMPT_KEYWORDS
```

Issue: If `MAX_PROMPT_KEYWORDS = 4` and the input is exactly 4 keywords, the cap does not trim them. Then the style theme is appended because `len(ordered) <= 4`, producing 5 keywords — exceeding the configured maximum.

Fix: Move the style theme injection before the cap, or apply the cap after injection:
```python
if len(ordered) <= 4:
    ordered.append(random.choice(_STYLE_THEMES))
return ordered[:settings.MAX_PROMPT_KEYWORDS]
```

---

### Low

---

**LOW-1: `_SOUL_MD` is read at import time — `FileNotFoundError` will crash the worker at startup without a clear message**
File: `app/advisor/service.py:46`

```python
_SOUL_MD: str = _SOUL_MD_PATH.read_text(encoding="utf-8")
```

Fix: Wrap in a try/except at import time with a clear `RuntimeError` message, or check for the file in a startup health check.

---

**LOW-2: Hardcoded model names in `advisor/service.py` and `memory_manager.py` instead of config constants**
Files: `app/advisor/service.py:37-38`, `app/advisor/memory_manager.py:247`

```python
_MODEL_SONNET = "claude-3-5-sonnet-20241022"
_MODEL_HAIKU = "claude-3-haiku-20240307"
```

These are module-level constants (acceptable), but `memory_manager.py:247` uses a raw string literal:
```python
model="claude-3-haiku-20240307",
```

Fix: Import `_MODEL_HAIKU` from `advisor/service.py` or define a shared `app/advisor/models.py` constant and import from there.

---

**LOW-3: `_AVG_SECONDS_PER_JOB = 15` is a magic number with no config backing**
File: `app/api/generation.py:60`

Issue: The constant is undocumented and cannot be tuned without a code change. As fal.ai performance changes, estimated wait times will silently be wrong.

Fix: Either back it with a config value or at minimum add a comment explaining how `15` was derived.

---

**LOW-4: `supabase.table("v_feed_posts")` references a DB view by name string — no validation**
File: `app/api/social.py:152`

Issue: If the view is renamed or dropped, the failure will be a runtime 500. This is structural and hard to avoid with Supabase PostgREST, but worth noting.

---

**LOW-5: `app/advisor/service.py:136` uses `asyncio.create_task` without error handling**
File: `app/advisor/service.py:136`

```python
asyncio.create_task(
    self._memory_manager.extract_memories_from_turn(...)
)
```

Issue: An unhandled exception in the task will result in a "Task exception was never retrieved" warning in the event loop. The task result is never awaited.

Fix: Add a callback or wrap the coroutine in a helper that logs exceptions:
```python
task = asyncio.create_task(self._memory_manager.extract_memories_from_turn(...))
task.add_done_callback(lambda t: t.exception() and logger.warning("Memory extraction task failed", exc_info=t.exception()))
```

---

**LOW-6: Inconsistency: `delete_account` is `def` (sync) but reads reservation data synchronously inside a sync handler, while `social_login` is correctly `async`**
File: `app/api/auth.py:534`

Issue: `delete_account` performs multiple Supabase queries (reservations, soft-delete, auth deletion) synchronously. This is valid since FastAPI runs sync handlers in a thread pool, but it is inconsistent with the other auth endpoints and could cause confusion.

---

**LOW-7: `prompts/keyword_allowlist.py` is imported from two different paths**
File: `app/generation/prompt_builder.py:110, 159`

```python
from prompts.keyword_allowlist import HAIR_KEYWORDS   # in prepare_keywords()
from prompts.keyword_allowlist import ALLOWED_KEYWORDS # in build_prompt()
```

Issue: `prompts` is imported as a top-level package (relative to the working directory), not as `app.prompts`. This will break if the working directory is not the repo root. The imports are inside functions (deferred), masking the breakage until the function is called.

Fix: Move the `prompts` package under `app/`, or add the repo root to `sys.path` explicitly in the worker entry point. At minimum, move the imports to the module top so they fail at import time rather than at generation time.

---

**LOW-8: `app/api/users.py` extra blank line between `_lookup_user` and the comment block**
File: `app/api/users.py:93`

Issue: Double blank line after `_lookup_user` (line 91 is the end of the function, line 92 is blank, line 94 is another blank, line 95 is the section comment). PEP 8 allows two blank lines between top-level definitions, but three is non-standard.

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 4 |
| High | 10 |
| Medium | 12 |
| Low | 8 |
| **Total** | **34** |

## Verdict

**BLOCK** — 4 Critical and 10 High issues found.

### Must-fix before merge

| # | File | Issue |
|---|------|-------|
| CRITICAL-1 | `generation/worker.py` | Missing `raise_for_status()` on downloaded provider image — silent data corruption |
| CRITICAL-2 | `api/social.py` | TOCTOU race in reaction rate limiter — bypassed under concurrency |
| CRITICAL-3 | `api/webhooks.py` | Broad except on webhook handler returns 200 — credit purchases silently lost |
| CRITICAL-4 | `api/auth.py` | Wrong type annotation on `verify_email` (`dict` vs `UserClaims`) |
| HIGH-2 | `advisor/service.py` | `Any` type on LLM adapter disables all type safety |
| HIGH-4 | `api/social.py` | Redis reaction counter drift — unbounded stale values |
| HIGH-6 | `api/users.py` | Silent exception swallowing in `_sign_url` with no exc_info |
| MEDIUM-11 | `advisor/content_filter.py` | Same TOCTOU race as CRITICAL-2 in advisor rate limiter |
| MEDIUM-12 | `generation/prompt_builder.py` | Cap applied before theme injection — can exceed `MAX_PROMPT_KEYWORDS` |
