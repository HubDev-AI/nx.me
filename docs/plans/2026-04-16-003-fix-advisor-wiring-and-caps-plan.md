---
title: "fix: Advisor audit — wire analysis-insight hook, align prompts, enforce caps"
type: fix
status: active
date: 2026-04-16
origin: docs/advisor-spec.md
---

# fix: Advisor audit — wire analysis-insight hook, align prompts, enforce caps

## Overview

End-to-end audit of the advisor feature against `docs/advisor-spec.md`. Three independent agents swept security, wiring, and prompts. Security is clean. Wiring has one high-severity gap (the analysis-insight memory hook is defined but never invoked, so Ada has no memory of a user's face-analysis results), plus four medium gaps: nudge and summary prompts don't use SOUL.md, and the spec's memory-cap (500/user) and context-token cap (5 000) are not enforced. This plan fixes the gaps without re-architecting the module.

## Problem Frame

The spec defines Ada as an advisor that "knows each user's face analysis results, remembers their goals, and checks in with styling tips." Two behaviors in the spec are currently non-functional or misaligned:

1. After a face analysis, the spec says to persist an `analysis_insight` memory row via an event hook (spec §4.5, §16). The hook function exists in `app/advisor/memory_manager.py` but is orphaned — no caller. Consequence: Ada treats every user as first-time on every turn, even after they ran several analyses. This directly undermines the product's core promise.
2. SOUL.md governs Ada's voice. Chat uses the full SOUL.md system prompt (correctly). Nudges and conversation summaries use short generic prompts — nudges say only "You are Ada, a warm personal style advisor. Keep responses brief." This produces voice drift: chat Ada has taste, opinions, anti-patterns; nudge Ada is a generic assistant.

Additionally, two cost/safety caps from §10 are not enforced (memory-per-user and context-token). Security review found no cross-user exposure — all routes resolve `user_id` from the JWT and every repo query filters by it, RLS is force-enabled, vision-context images are user-scoped.

## Requirements Trace

- R1. Ada must have persistent memory of each user's analysis results (spec §4.5 — `analysis_insight` rows written after every face analysis, guarded by `ADVISOR_ENABLED`).
- R2. Ada's voice must be consistent across chat, nudges, and summary (SOUL.md as the single persona source, spec §1, §12).
- R3. Per-user memory count must be bounded (spec §10 — 500/user cap).
- R4. LLM input context must be bounded (spec §10 — 5 000-token cap).
- R5. Per-user data isolation must remain intact (spec §14 — already verified clean; this plan must not regress).

## Scope Boundaries

- Not changing the memory schema, RPC signature, or embedding model (Ollama 768-dim is already landed).
- Not adding new nudge triggers or new memory types.
- Not reworking content-filter patterns or rate-limit keys — both already per-user and enforced.
- Not addressing the pre-existing `test_config.test_adapter_defaults_are_mock` failure — that comes from a local `.env` override and is unrelated to advisor code.

### Deferred to Separate Tasks

- Prompt-caching on Anthropic calls (SOUL.md is a perfect cache candidate): separate perf PR, not in scope for correctness audit.
- Push-notification delivery for nudges (spec §7 open question 2): product decision, not plumbing.
- Memory promotion/expiry policy beyond the hard 500 cap (LRU vs. importance-weighted): product decision.

## Context & Research

### Security audit (verified clean — for the record)

- Every `/v1/advisor/*` and `/v1/memories*` route resolves `user_id` from `claims["sub"]` in `app/api/advisor.py`; no user_id is read from path or body.
- `advisor_repo` filters every query by `user_id` (`get_nudges_page`, `get_nudge_by_id(nudge_id, user_id)`, `delete_memory(memory_id, user_id)`, cursor-safe pagination).
- RPC `match_user_memories(p_user_id, ...)` takes the authenticated user_id from the service layer only.
- RLS policies on `user_memories`, `advisor_*` tables are `ENABLE + FORCE` (migration `0013`). Service-role key bypasses RLS; app layer is the authoritative control.
- Vision content: `_fetch_vision_content` → `advisor_repo.get_cleared_images(user_id)` filters by user_id before signing URLs.
- Guest lockdown (PR #101): `require_feature("advisor_chat")` rejects guests with 402 on `POST /v1/advisor/messages`.

### Relevant code and patterns

- Hook invocation pattern: `app/api/glowup.py:276-286` already enqueues `schedule_post_analysis_nudge` after analysis completes, guarded by `ADVISOR_ENABLED`. Add the insight write alongside it using the same guard and the same site.
- SOUL.md access: `app/advisor/service.py:49-56` loads `_SOUL_MD` at import. Expose it (or a getter) for nudge and summary call sites so they share the same persona text.
- Memory write pattern: `memory_manager.write_memory()` already handles embed-then-insert with failure logging; `write_analysis_insight` follows the same shape and can reuse it.
- Context budget pattern: no helpers yet. Closest reference is the existing `_MAX_TOKENS_CHAT = 256` constant on the output side.

### Institutional learnings

- `docs/solutions/` is empty — no prior advisor learnings recorded.
- Memory `MEMORY.md` — `feedback_no_env_fallbacks` (fail fast on missing env), `feedback_no_hardcoded_urls` (constants, not magic numbers), `feedback_pre_launch_destructive_ok` (no migrations/backfills needed — can edit DB in place). Relevant to implementation choices below.

## Key Technical Decisions

- **Wire the hook from the analysis-completion site, not from the worker.** `app/api/glowup.py` already sits at the correct seam and already calls `enqueue(schedule_post_analysis_nudge, …)` behind `ADVISOR_ENABLED`. Adding the synchronous `write_analysis_insight` call right there keeps the integration one-liner and keeps the advisor module self-contained (spec §16). Rationale: generation worker would couple background-job timing to the insight; the API-level hook fires deterministically once per successful analysis.
- **Share `_SOUL_MD` across chat, nudge, and summary.** Promote it from a private module constant to an exported helper `get_soul_md()` in a shared location (or keep as module attribute and import from `app.advisor.service` — whichever keeps imports acyclic). Rationale: SOUL.md is the product's persona; duplication invites drift.
- **Enforce the 500-cap on write, not on retrieval.** When `write_memory` inserts, if count ≥ cap delete the oldest low-importance row (or reject with a logged warning for user-created goals). Rationale: cheaper than pruning on retrieval; keeps retrieval fast.
- **Enforce the 5 000-token context cap by trimming oldest conversation turns after assembly.** Keep SOUL.md, user_data, and memories inviolate; drop oldest user/advisor turn pairs until under budget. Rationale: history is the only expandable input; SOUL.md + memories are bounded by design.
- **Use `tiktoken` for token counting** (already an indirect dependency via OpenAI SDK paths) OR a cheap heuristic (chars ÷ 4) behind a single helper so it's swappable. Rationale: correctness > perfection; the cap exists to prevent a runaway, not to squeeze the last 200 tokens.

## Open Questions

### Resolved During Planning

- Should the analysis-insight hook be sync or async? Sync — it writes one row with one embedding call (same cost profile as the existing nudge enqueue), and the user isn't blocked on the response (analysis is already a background job that resolves later). The service already does fire-and-forget memory extraction using `asyncio.create_task`, same pattern applies.
- Should nudges get the full SOUL.md? Yes. Nudges are user-visible Ada voice; generic-assistant-tone defeats the feature. The extra ~600 tokens per nudge is negligible (Haiku, one-shot, no history).
- Should we enforce the cap on user-added goals too, or just on system-extracted memories? Both. User-added `goal` and `user_note` memories count toward the cap. But prefer deleting `dismissed_suggestion` / older `user_note` before ever touching a `goal` (importance-weighted eviction).

### Deferred to Implementation

- Exact token-count helper (tiktoken vs. heuristic): decide once we confirm `tiktoken` is already importable in the backend container; fall back to `len(text) // 4` heuristic otherwise.
- Eviction query shape: single-RPC vs. app-side select-delete. Depends on whether a small Postgres function is worth the migration cost versus an app-layer SELECT + DELETE.

## Implementation Units

- [ ] **Unit 1: Wire the analysis-insight hook from the analysis-completion site**

**Goal:** After every successful face analysis, persist an `analysis_insight` memory row so Ada's chat context carries face shape, symmetry, and recommendations on the user's next message.

**Requirements:** R1.

**Dependencies:** none.

**Files:**
- Modify: `app/api/glowup.py` (alongside the existing `schedule_post_analysis_nudge` enqueue — call `memory_manager.write_analysis_insight` under `ADVISOR_ENABLED`).
- Modify: `app/advisor/memory_manager.py` (if `write_analysis_insight` needs a small DI tweak to accept the injected embedding port / repo handle — otherwise untouched).
- Test: `tests/test_advisor_analysis_insight_hook.py` (new).

**Approach:**
- At the existing `if settings.ADVISOR_ENABLED:` block in `app/api/glowup.py`, call `write_analysis_insight(user_id, analysis_result, image_id)` as a fire-and-forget task using the same `_background_tasks` pattern already used in `service.send_message`.
- Keep `write_analysis_insight` signature stable; only refactor if needed to accept the same ports the rest of the module already injects.
- Log success/failure with the existing `advisor.memory_extraction_failure` metric naming convention.

**Execution note:** Add a failing integration test for the hook firing first, then wire the call site.

**Patterns to follow:**
- Fire-and-forget with structured logging: `app/advisor/service.py:199-222`.
- Guard site: existing `schedule_post_analysis_nudge` block in `app/api/glowup.py`.

**Test scenarios:**
- Happy path: successful analysis → one new row in `user_memories` with `type='analysis_insight'` and `user_id` matching the caller, plus a non-null embedding.
- Error path: `write_analysis_insight` raises → analysis response still returns 2xx (fire-and-forget must not block the user path); a warning is logged with the standard `advisor.memory_extraction_failure` metric.
- Feature flag: `ADVISOR_ENABLED=False` → no memory row is written, no background task is created.
- Per-user isolation: two concurrent analyses for different users write two rows with distinct `user_id` values; neither sees the other.
- Integration: after the hook fires, a subsequent `send_message` call pulls the inserted row back via `get_relevant_memories` when the query is semantically close to the recommendations text.

**Verification:**
- Running an analysis in dev creates exactly one new `user_memories` row of type `analysis_insight` for the caller.
- Immediately after, a chat message like "what should I focus on next" retrieves that row among the top-3 memories.

---

- [ ] **Unit 2: Share SOUL.md across chat, nudge, and summary**

**Goal:** Eliminate persona drift by making every Anthropic call that speaks as Ada use the same SOUL.md system prompt.

**Requirements:** R2.

**Dependencies:** none.

**Files:**
- Modify: `app/advisor/service.py` (expose SOUL.md via a simple helper — `get_soul_md()` or similar — and use it in `_summarize_conversation`).
- Modify: `app/advisor/nudge_scheduler.py` (swap the short mini-persona for SOUL.md + a role-specific one-line instruction appended via a second `system` message, e.g. "Write a brief check-in nudge. One to two sentences.").
- Test: `tests/test_advisor_persona_consistency.py` (new).

**Approach:**
- Move SOUL.md loading to a tiny helper (`app/advisor/persona.py` if the concern deserves its own module, otherwise keep in `service.py` and export).
- Nudge call: `system=<SOUL.md>` top-level, with the trigger-specific instruction passed as the first `user` message (or as an extra `system` parts list — the adapter already collapses multiple system parts into one combined system).
- Summary call: same shape. Instruction "Summarise in 2-3 sentences, styling preferences and goals only." goes in the user message, SOUL.md stays in `system`. The summary is never shown verbatim to the user, but keeping it in Ada's voice preserves continuity when it's re-injected into future context.

**Patterns to follow:**
- System-parts collapsing: `app/advisor/adapters/anthropic_adapter.py:48-63`.

**Test scenarios:**
- Happy path (nudge): `generate_nudge` is called for a known trigger → the adapter receives `system` containing SOUL.md content (assert a distinctive SOUL.md phrase appears in the captured `system` argument).
- Happy path (summary): `_summarize_conversation` → adapter `system` contains SOUL.md content.
- Edge case: SOUL.md missing at import time → service fails fast (spec: already `raise RuntimeError`); confirm nudge and summary paths surface the same failure, not a silent generic fallback.
- Persona-drift regression: a snapshot test over the first 200 chars of captured `system` for chat/nudge/summary should show they all start with the same SOUL.md preamble.

**Verification:**
- In dev with the mock adapter swapped out for a capture-only double, the `system` field on chat, nudge, and summary calls all contain SOUL.md content.

---

- [ ] **Unit 3: Enforce the 500-memory-per-user cap on write**

**Goal:** Prevent unbounded growth of `user_memories` per user; keep retrieval cost predictable.

**Requirements:** R3.

**Dependencies:** Unit 1 (analysis-insight writes add one more code path that must respect the cap).

**Files:**
- Modify: `app/advisor/memory_manager.py` — add a `_enforce_cap(user_id)` call inside `write_memory` (and inside `write_analysis_insight` if it doesn't already go through `write_memory`).
- Modify: `app/repositories/advisor_repo.py` — add `count_memories(user_id)` and `delete_oldest_low_importance(user_id, keep_types=("goal",))`.
- Modify: `app/config/__init__.py` — add `ADVISOR_MEMORY_CAP: int = 500` (no fallback; fail fast if caller overrides to invalid value).
- Test: `tests/test_advisor_memory_cap.py` (new).

**Approach:**
- On every write, if `count_memories(user_id) >= ADVISOR_MEMORY_CAP`, delete the single oldest memory whose type is not `goal` (preserve user-declared intent above all else). Tie-break on `created_at ASC`, then `importance ASC`.
- Both `count_memories` and `delete_oldest_low_importance` must filter by `user_id` (no cross-user eviction — same discipline as the rest of the repo).
- Importance weights already exist in `memory_manager` — reuse them for eviction ordering.

**Test scenarios:**
- Happy path: 499 existing memories → insert succeeds, count is 500.
- Boundary: 500 existing → insert triggers eviction of one oldest non-goal row, final count is 500.
- Goal preservation: 500 where all are `goal` → new insert evicts nothing (document behavior: write is accepted, count goes to 501) and a warning is logged with metric `advisor.memory_cap_goal_only`. This is deliberate: we never silently delete a user's stated intent.
- Error path: eviction query fails → the write is still attempted; if write succeeds count goes to 501, warning logged.
- Per-user isolation: 500 memories for user A + 1 write for user B → no eviction happens on A's table.

**Verification:**
- Seeding a test user to 500 rows and sending one more message → exactly 500 rows remain for that user, the oldest non-goal is gone.

---

- [ ] **Unit 4: Enforce the 5 000-token context cap on assembly**

**Goal:** Prevent the Anthropic call from exceeding the model's context window on long conversations.

**Requirements:** R4.

**Dependencies:** none.

**Files:**
- Modify: `app/advisor/context_builder.py` — add `trim_to_budget(messages, max_tokens)` that preserves system messages and the current user message and drops oldest user/advisor pairs until under budget.
- Modify: `app/advisor/service.py` — call `trim_to_budget` after `build_context`, before `create_message`.
- Modify: `app/config/__init__.py` — add `ADVISOR_CONTEXT_TOKEN_BUDGET: int = 5000`.
- Test: `tests/test_advisor_context_budget.py` (new).

**Approach:**
- Single helper for token counting: `_count_tokens(text) -> int` using `tiktoken` when importable, else `len(text) // 4` heuristic (documented as approximate at ≥20% headroom from the 5 000 cap).
- Trim policy: never drop SOUL.md, user_data, memories, or the incoming user message. Drop oldest conversation turns in pairs (user + matching advisor response) to keep dialog coherence.
- Return the trimmed list plus a trim-count for logging (`advisor.context_trimmed` metric).

**Test scenarios:**
- Happy path: short conversation → no trimming; `messages` returned unchanged.
- Trim triggered: fabricate 100 long turns → assembly trims oldest pairs, final token estimate ≤ budget, most recent 4 turns preserved, system messages preserved, incoming user message preserved.
- Edge case: budget is less than SOUL.md alone → trim returns SOUL.md + user_data + incoming user message (no history, no memories); metric logged.
- Integration: send a chat message against a seeded 100-turn conversation → `create_message` is called with ≤5 000 tokens of input (assert via captured adapter args).

**Verification:**
- Loading a test user with 100 messages and sending one more → the Anthropic adapter receives ≤5 000 tokens.

---

- [ ] **Unit 5: Regression lock for per-user isolation**

**Goal:** Turn the security audit's "clean" finding into an enforced invariant, so a future careless repo change cannot silently leak cross-user data.

**Requirements:** R5.

**Dependencies:** none.

**Files:**
- Test: `tests/test_advisor_isolation.py` (new).

**Approach:**
- Integration-level tests that seed two users (A, B), create memories, nudges, and conversations for each, then assert every list/delete/mark-read endpoint called as user A returns no rows owned by B, and returns 404 (not 403 — spec prefers 404 to avoid confirming existence) when a B-owned resource id is supplied.
- Also assert `_fetch_vision_content` called with A's user_id returns no B-owned images.

**Execution note:** Pure characterization — no behavior changes. Locks current correct behavior.

**Test scenarios:**
- Happy path: A calls `GET /v1/memories` → returns only A's memories.
- Cross-user read: A calls `DELETE /v1/memories/{B's_id}` → 404, B's row untouched.
- Cross-user nudge: A calls `POST /v1/advisor/nudges/{B's_id}/read` → 404, B's nudge not marked.
- Cross-user conversation: A calls `GET /v1/advisor/messages` with no cursor → only A's conversation returned; crafting a cursor from B's ids does not leak rows.
- Vision: A's advisor message with "look at my photo" → `_fetch_vision_content(A)` does not return B's images even if B's image id is injected into the message text.

**Verification:**
- The new test file runs green against the current code and would fail loudly if a future PR forgets a `user_id` filter.

## System-Wide Impact

- **Interaction graph:** Unit 1 adds one call from `app/api/glowup.py` into `app/advisor/memory_manager.py`, using the existing `ADVISOR_ENABLED` guard — keeps the spec's "nothing outside `app/advisor/` imports *from* it except at one event hook" rule intact.
- **Error propagation:** All four functional units use fire-and-forget with structured logging where the user is not waiting; synchronous failures (summary, nudge) are already logged and skipped.
- **State lifecycle risks:** Unit 3's eviction and Unit 4's trimming are both deterministic and idempotent. Eviction is per-write, not a background sweep, so no concurrent-sweep race.
- **API surface parity:** No endpoint contracts change. Adding `ADVISOR_MEMORY_CAP` and `ADVISOR_CONTEXT_TOKEN_BUDGET` to settings needs the usual `.env.example` mirror (per project convention).
- **Integration coverage:** Units 1, 3, 4 each ship at least one integration scenario that mocks alone would not catch (hook → retrieval roundtrip; cap triggers on the real repo path; budget capping measured at the adapter call site).
- **Unchanged invariants:** Route signatures, memory schema, embedding model (768-dim Ollama), RPC signature, RLS policies, rate-limit keys, guest-lockdown gates — all untouched.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Unit 1 doubles write load on the generation-success path (nudge enqueue + insight write + embedding call). | Fire-and-forget; embedding call already runs for memory-extraction on every chat turn, capacity proven. Log latency of the hook behind `advisor.analysis_insight_ms` metric. |
| Unit 2 increases per-nudge token spend (SOUL.md ≈ 600 tokens × daily nudges). | Haiku pricing makes this ~$0.0003 per nudge extra; well inside the cost model in spec §10. If it matters later, prompt-caching (deferred) reclaims it. |
| Unit 3's "preserve goals" rule can let malicious or confused users balloon past 500 by repeatedly inserting `goal` memories. | Input sanitization already caps message length; a follow-up product decision can add a per-type sub-cap. Out of scope here. |
| Unit 4's heuristic token count is approximate — a real payload could overshoot by 10–15%. | Budget is set at 5 000 against a 200 000-token Sonnet window, so overshoot is harmless. If the heuristic path is taken (tiktoken unavailable), log once per process so ops notice. |
| Pre-existing `test_config.test_adapter_defaults_are_mock` failure could mask a real failure during CI. | Note in PR description; do not fix as part of this plan (scope). |

## Documentation / Operational Notes

- Update `app/.env.example` with the two new settings (`ADVISOR_MEMORY_CAP`, `ADVISOR_CONTEXT_TOKEN_BUDGET`). Per `feedback_env_example_sync.md`.
- Spec §10 is accurate — no spec changes needed; the plan closes the implementation gap against what's already written.
- No migrations. No backfill of existing users' analysis-insights (pre-launch — per `feedback_pre_launch_destructive_ok.md`, fine to let them start fresh).

## Sources & References

- **Origin document:** [docs/advisor-spec.md](../advisor-spec.md)
- Current code: `app/advisor/service.py`, `app/advisor/memory_manager.py`, `app/advisor/context_builder.py`, `app/advisor/nudge_scheduler.py`, `app/advisor/content_filter.py`, `app/advisor/adapters/anthropic_adapter.py`, `app/api/advisor.py`, `app/api/glowup.py`, `app/repositories/advisor_repo.py`.
- Related recent PRs: #99 (advisor request field fix), #100 (guest-friendly history), #101 (prod guest lockdown), #104 (role-mapping fix landed today).
- Migrations: `app/migrations/0007_advisor_tables.sql`, `0013_advisor_rls.sql`, `0037_ollama_embeddings.sql`.
