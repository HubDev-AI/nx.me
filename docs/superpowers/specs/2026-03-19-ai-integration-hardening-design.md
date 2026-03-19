# AI Integration Production Hardening Design Spec

**Date:** 2026-03-19
**Source:** Debug audit — 10 AI integration findings
**Approach:** Single wave, single PR. All findings in the AI adapter/integration layer.

---

## #1: Add `compute_embedding` to LLMPort Protocol

**File:** `app/advisor/llm_port.py`

Both `AnthropicAdapter` and `MockLLMAdapter` implement `compute_embedding()`, and `MemoryManager` calls it. But the `LLMPort` Protocol doesn't declare it — new adapters can pass the Protocol check but fail at runtime.

**Change:** Add to `LLMPort`:
```python
async def compute_embedding(self, text: str) -> list[float]:
    """Compute a text embedding vector."""
    ...
```

---

## #2-3: Explicit retry config on Anthropic and OpenAI SDK clients

**Files:** `app/config/__init__.py`, `app/advisor/adapters/anthropic_adapter.py`

Both SDKs have built-in retry with exponential backoff, but the code relies on defaults that could change silently.

**Config additions:**
```python
LLM_MAX_RETRIES: int = 2
EMBEDDING_MAX_RETRIES: int = 2
```

**Adapter changes:**
```python
self._anthropic = anthropic.AsyncAnthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    timeout=httpx.Timeout(settings.ADVISOR_LLM_TIMEOUT_SECONDS),
    max_retries=settings.LLM_MAX_RETRIES,
)
self._openai = openai.AsyncOpenAI(
    api_key=openai_key,
    timeout=settings.ADVISOR_EMBEDDING_TIMEOUT_SECONDS,
    max_retries=settings.EMBEDDING_MAX_RETRIES,
)
```

---

## #4: Switch fal.ai to native async + timeout

**File:** `app/generation/adapters/falai.py`

Current code uses `fal_client.subscribe()` (sync) inside `loop.run_in_executor()`. fal_client has native async `run_async()`. The sync approach leaks threads on timeout.

**Change:** Replace executor-wrapped sync call with native async + timeout:

```python
async def generate(self, source_image_url, prompt, options):
    import fal_client
    start_ms = int(time.time() * 1000)
    request = self._build_request(source_image_url, prompt, options)

    result = await asyncio.wait_for(
        fal_client.run_async(options.model, arguments=request),
        timeout=settings.GENERATION_TIMEOUT_SECONDS,
    )
    ...
```

Remove `loop.run_in_executor()` entirely. The `__init__` lazy import of `fal_client` stays (but the instance-level `self._client` is no longer needed since `fal_client.run_async` is a module-level function).

---

## #5: Cache NSFW screener in worker context

**File:** `app/generation/worker.py`

Same pattern as M-7 (generator caching). The NSFW screener (especially `RekognitionAdapter`) creates a boto3 client on each instantiation.

**Change:** In `process_generation_job`, cache in `ctx`:
```python
if "nsfw_screener" not in ctx:
    ctx["nsfw_screener"] = _get_nsfw_screener()
screener = ctx["nsfw_screener"]
```

In `_generate_and_validate`, accept `screener` as a parameter instead of calling `_get_nsfw_screener()` directly.

---

## #6: Share httpx client across the generation job

**File:** `app/generation/worker.py`

Three separate `httpx.AsyncClient` context managers per job waste connection setup/teardown. Share one client.

**Change:** Create the client in `process_generation_job` and pass it through:

```python
async with httpx.AsyncClient(timeout=settings.GENERATION_HTTPX_TIMEOUT_SECONDS) as http_client:
    validate_result = await _generate_and_validate(
        ..., http_client=http_client, ...
    )
```

`_generate_and_validate` accepts `http_client` as a parameter and uses it for all 3 HTTP calls: generated image download (~line 257), source image download (~line 290), and retry image download (~line 355). Remove all three `async with httpx.AsyncClient(...)` blocks and replace with direct `http_client.get(url)` calls.

---

## #7: Deterministic trajectory hints in context builder

**Files:** `app/advisor/context_builder.py`, `app/advisor/service.py`

`maybe_add_trajectory` uses `random.random()` (global state) — non-deterministic. Same class of issue we fixed in the prompt builder (M-2).

**Change:** Add `rng` parameter to `build_context` and `maybe_add_trajectory`. Seed from conversation_id in `service.py` using `hashlib` (not `hash()` — Python's `hash()` is randomized per process via PYTHONHASHSEED):

```python
import hashlib
seed = int(hashlib.md5(conversation_id.encode()).hexdigest(), 16) % (2**32)
rng = random.Random(seed)
messages = build_context(..., rng=rng)
```

In `maybe_add_trajectory`:
```python
def maybe_add_trajectory(memories, rng=None):
    _rng = rng or random
    if len(accepted) < 2 or _rng.random() > _TRAJECTORY_CHANCE:
        return memories
```

---

## #8: Remove `_MODEL_SONNET` import-time alias

**File:** `app/advisor/service.py`

Line 39: `_MODEL_SONNET = settings.ADVISOR_MODEL_SONNET` captures at import time. Same pattern we fixed for `MODEL_HAIKU`.

**Change:** Remove the alias. Replace all `_MODEL_SONNET` references with `settings.ADVISOR_MODEL_SONNET` at call sites.

---

## #9: Downgrade Anthropic token logging to DEBUG

**File:** `app/advisor/adapters/anthropic_adapter.py`

Per-response token counts at INFO are noisy at scale (100+ messages/hour).

**Change:** `logger.info(...)` on line 92 becomes `logger.debug(...)`.

---

## #10: Fix mock embedding zero vector

**File:** `app/advisor/adapters/mock.py`

Zero vector `[0.0] * 1536` causes NaN in pgvector cosine similarity. Tests using the mock adapter get garbage memory retrieval results.

**Change:** Generate a deterministic non-zero unit vector from the input text hash:

```python
async def compute_embedding(self, text: str) -> list[float]:
    import hashlib
    seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.gauss(0, 1) for _ in range(1536)]
    norm = sum(x*x for x in vec) ** 0.5
    return [x / norm for x in vec]
```

Same input always produces the same embedding. Non-zero. Unit length. Cosine similarity works.

---

## Testing Strategy

- All existing tests must pass (78 currently)
- `python3 -m py_compile` on all modified files
- The fal.ai async switch (#4) can't be tested without the real API, but compilation + mock adapter tests verify the interface
- Mock embedding fix (#10) can be verified by checking `sum(x*x for x in embedding) ≈ 1.0` (unit vector)
