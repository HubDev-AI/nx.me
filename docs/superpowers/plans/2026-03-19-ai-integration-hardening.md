# AI Integration Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 10 AI integration findings — missing Protocol method, explicit retry config, native async fal.ai, resource pooling, deterministic context, and mock correctness.

**Architecture:** Single wave, single PR. All changes are in the AI adapter/integration layer — advisor adapters, generation pipeline, and context builder.

**Tech Stack:** Python/FastAPI, Anthropic SDK, OpenAI SDK, fal_client, httpx, pgvector

**Spec:** `docs/superpowers/specs/2026-03-19-ai-integration-hardening-design.md`

---

### Task 1: LLM Protocol + retry config + logging + mock fix (#1, #2-3, #9, #10)

**Files:**
- Modify: `app/advisor/llm_port.py`
- Modify: `app/config/__init__.py`
- Modify: `app/advisor/adapters/anthropic_adapter.py`
- Modify: `app/advisor/adapters/mock.py`

- [ ] **Step 1: Add `compute_embedding` to LLMPort Protocol**

In `app/advisor/llm_port.py`, add after the `create_message` method:

```python
    async def compute_embedding(self, text: str) -> list[float]:
        """Compute a text embedding vector."""
        ...
```

- [ ] **Step 2: Add retry config constants**

In `app/config/__init__.py`, after `ADVISOR_EMBEDDING_TIMEOUT_SECONDS`, add:

```python
    # SDK retry config (explicit — do not rely on SDK defaults)
    LLM_MAX_RETRIES: int = 2
    EMBEDDING_MAX_RETRIES: int = 2
```

- [ ] **Step 3: Pass retry config + downgrade logging in Anthropic adapter**

In `app/advisor/adapters/anthropic_adapter.py`:

Add `max_retries=settings.LLM_MAX_RETRIES` to the `anthropic.AsyncAnthropic()` constructor call.

Add `max_retries=settings.EMBEDDING_MAX_RETRIES` to the `openai.AsyncOpenAI()` constructor call.

Change line ~92 from `logger.info(` to `logger.debug(` for the per-response token count log.

- [ ] **Step 4: Fix mock embedding zero vector**

In `app/advisor/adapters/mock.py`, add `import hashlib` at top. Replace the `compute_embedding` method:

```python
    async def compute_embedding(self, text: str) -> list[float]:
        """Return a deterministic non-zero unit vector seeded from input text.

        Zero vectors cause NaN in pgvector cosine similarity.
        """
        import hashlib
        seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vec = [rng.gauss(0, 1) for _ in range(1536)]
        norm = sum(x * x for x in vec) ** 0.5
        return [x / norm for x in vec]
```

Add `import random` at top of the file if not already present.

- [ ] **Step 5: Verify compilation**

```bash
python3 -m py_compile app/advisor/llm_port.py
python3 -m py_compile app/config/__init__.py
python3 -m py_compile app/advisor/adapters/anthropic_adapter.py
python3 -m py_compile app/advisor/adapters/mock.py
```

- [ ] **Step 6: Run tests**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -p asyncio --tb=short -q
```

- [ ] **Step 7: Commit**

```bash
git add app/advisor/llm_port.py app/config/__init__.py app/advisor/adapters/anthropic_adapter.py app/advisor/adapters/mock.py
git commit -m "fix(advisor): LLM Protocol gap, explicit retry config, mock embedding, log level (#1,#2-3,#9,#10)"
```

---

### Task 2: Switch fal.ai to native async (#4)

**Files:**
- Modify: `app/generation/adapters/falai.py`

- [ ] **Step 1: Rewrite FalAiAdapter to use run_async**

Replace the `__init__` and `generate` methods:

```python
class FalAiAdapter:
    """Real fal.ai generation adapter — native async."""

    async def generate(
        self,
        source_image_url: str,
        prompt: str,
        options: GenerationOptions,
    ) -> GenerationResult:
        """Call fal.ai API for image generation using native async client."""
        import fal_client

        start_ms = int(time.time() * 1000)

        # Build request based on model
        if "flux-pulid" in options.model:
            request = self._build_pulid_request(source_image_url, prompt, options)
        elif "flux-general" in options.model:
            request = self._build_flux_dev_request(source_image_url, prompt, options)
        elif "instantid" in options.model:
            request = self._build_instantid_request(source_image_url, prompt, options)
        else:
            raise ValueError(f"Unknown model: {options.model}")

        # Native async call with timeout protection
        result = await asyncio.wait_for(
            fal_client.run_async(options.model, arguments=request),
            timeout=settings.GENERATION_TIMEOUT_SECONDS,
        )

        elapsed_ms = int(time.time() * 1000) - start_ms

        # Extract image URL from result
        image_url = self._extract_image_url(result)

        logger.info(
            "fal.ai generation complete: model=%s, time=%dms",
            options.model, elapsed_ms,
        )

        return GenerationResult(
            image_url=image_url,
            seed=result.get("seed"),
            inference_time_ms=elapsed_ms,
            estimated_cost_usd=self._estimate_cost(options.model),
        )
```

Remove the old `__init__` method (which did `import fal_client; self._client = fal_client`). Remove the `loop = asyncio.get_running_loop()` and `loop.run_in_executor()` lines. Keep all the `_build_*_request`, `_extract_image_url`, and `_estimate_cost` methods unchanged.

- [ ] **Step 2: Verify compilation**

```bash
python3 -m py_compile app/generation/adapters/falai.py
```

- [ ] **Step 3: Commit**

```bash
git add app/generation/adapters/falai.py
git commit -m "perf(generation): switch fal.ai to native async run_async + timeout (#4)"
```

---

### Task 3: Cache NSFW screener + share httpx client (#5, #6)

**Files:**
- Modify: `app/generation/worker.py`

- [ ] **Step 1: Cache NSFW screener in ctx**

In `process_generation_job`, after the generator caching block (~line 485-487), add:

```python
    if "nsfw_screener" not in ctx:
        ctx["nsfw_screener"] = _get_nsfw_screener()
    nsfw_screener = ctx["nsfw_screener"]
```

- [ ] **Step 2: Add httpx client + pass both through**

Wrap the main try block in `process_generation_job` with a shared httpx client. Add `nsfw_screener` and `http_client` to the `_generate_and_validate` call:

```python
    async with httpx.AsyncClient(timeout=settings.GENERATION_HTTPX_TIMEOUT_SECONDS) as http_client:
        validate_result = await _generate_and_validate(
            job_repo, image_repo, cost_tracker, generator,
            job_id, job_data, options, source_url, adaptive_params,
            prompt, options.negative_prompt, storage_key, user_id, supabase,
            redis_client=redis, concurrent_key=concurrent_key,
            nsfw_screener=nsfw_screener, http_client=http_client,
        )
```

- [ ] **Step 3: Update `_generate_and_validate` signature**

Add `nsfw_screener=None` and `http_client=None` parameters to `_generate_and_validate`. Replace:

1. `screener = _get_nsfw_screener()` → `screener = nsfw_screener or _get_nsfw_screener()`

2. All three `async with httpx.AsyncClient(timeout=...) as client:` blocks → use `http_client` directly:

```python
# Generated image download (was ~line 257)
resp = await http_client.get(gen_result.image_url)
resp.raise_for_status()
gen_image_bytes = resp.content

# Source image download (was ~line 290)
resp = await http_client.get(source_url)
resp.raise_for_status()
source_image_bytes = resp.content

# Retry image download (was ~line 355)
resp = await http_client.get(retry_result.image_url)
resp.raise_for_status()
retry_image_bytes = resp.content
```

Remove the three `async with httpx.AsyncClient(...)` context manager blocks.

- [ ] **Step 4: Verify compilation and tests**

```bash
python3 -m py_compile app/generation/worker.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -p asyncio --tb=short -q
```

- [ ] **Step 5: Commit**

```bash
git add app/generation/worker.py
git commit -m "perf(generation): cache NSFW screener + share httpx client per job (#5, #6)"
```

---

### Task 4: Deterministic context builder + remove import-time alias (#7, #8)

**Files:**
- Modify: `app/advisor/context_builder.py`
- Modify: `app/advisor/service.py`

- [ ] **Step 1: Add rng parameter to context_builder functions**

In `app/advisor/context_builder.py`:

Update `build_context` signature to accept `rng`:
```python
def build_context(
    soul_md: str,
    user_data: str,
    memories: list[dict[str, Any]],
    conversation: list[dict[str, str]],
    message: str,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
```

Pass `rng` through to `maybe_add_trajectory`:
```python
    enhanced_memories = maybe_add_trajectory(memories, rng=rng)
```

Update `maybe_add_trajectory` to accept and use `rng`:
```python
def maybe_add_trajectory(
    memories: list[dict[str, Any]],
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    _rng = rng or random
    accepted = [m for m in memories if m.get("type") == "accepted_suggestion"]
    if len(accepted) < 2 or _rng.random() > _TRAJECTORY_CHANCE:
        return memories
    ...
```

- [ ] **Step 2: Remove `_MODEL_SONNET` alias and seed rng in service.py**

In `app/advisor/service.py`:

Delete line 42: `_MODEL_SONNET = settings.ADVISOR_MODEL_SONNET`

Add `import hashlib` at the top with other stdlib imports.

Replace all references to `_MODEL_SONNET` with `settings.ADVISOR_MODEL_SONNET`. Check these locations:
- In `_select_model` return statement
- Any other reference (grep for `_MODEL_SONNET`)

In `send_message`, before the `build_context` call, seed the RNG from conversation_id:

```python
        # Deterministic RNG for context assembly (hashlib, not hash() — cross-process safe)
        _seed = int(hashlib.md5(conversation_id.encode()).hexdigest(), 16) % (2**32)
        _rng = random.Random(_seed)

        # Step 7: Build LLM context
        messages = build_context(
            soul_md=_SOUL_MD,
            user_data=user_data_block,
            memories=memories,
            conversation=history,
            message=message,
            rng=_rng,
        )
```

Add `import random` at top if not present.

- [ ] **Step 3: Verify compilation and tests**

```bash
python3 -m py_compile app/advisor/context_builder.py
python3 -m py_compile app/advisor/service.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -p asyncio --tb=short -q
```

- [ ] **Step 4: Commit**

```bash
git add app/advisor/context_builder.py app/advisor/service.py
git commit -m "fix(advisor): deterministic context builder + remove import-time model alias (#7, #8)"
```

---

### Task 5: Final verification + PR

- [ ] **Step 1: Full compilation check**

```bash
python3 -m py_compile app/advisor/llm_port.py
python3 -m py_compile app/advisor/adapters/anthropic_adapter.py
python3 -m py_compile app/advisor/adapters/mock.py
python3 -m py_compile app/advisor/context_builder.py
python3 -m py_compile app/advisor/service.py
python3 -m py_compile app/config/__init__.py
python3 -m py_compile app/generation/adapters/falai.py
python3 -m py_compile app/generation/worker.py
```

- [ ] **Step 2: Full test suite**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -p asyncio --tb=short -q
```

- [ ] **Step 3: PR and merge**

Create PR targeting `dev`, merge after checks pass.
