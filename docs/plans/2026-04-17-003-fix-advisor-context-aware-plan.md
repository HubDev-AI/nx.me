---
title: "fix: Advisor context-aware rewiring — nudges, glow-up photos, RAG, payload logging, smart nudge rotation"
type: fix
status: active
date: 2026-04-17
---

# fix: Advisor context-aware rewiring — nudges, glow-up photos, RAG, payload logging, smart nudge rotation

## Overview

Ada chat ignores most of what the app already knows about the user, and the nudge generator re-derives face shape from scratch on every run. When a user with a completed glow-up and a post-analysis nudge ("oval face, strong jaw, longer face…") asks "What hairstyle would suit me?", Ada replies "Hard to say without knowing your face shape — can you describe it?" — because the chat context is missing three signals the product already produces: nudges, the analysis-insight recommendations block, and the glow-up before/after photos. Vision also never fires on style questions because the trigger keyword list is too narrow. Separately, the post-analysis nudge has a 60-minute time cooldown and a prompt anchored on face shape / symmetry / top-3 recommendations, so repeat runs produce near-duplicate "oval face shapes are versatile…" clones — and the trigger is bound to the analysis endpoint rather than the more emotionally salient glow-up-completion moment. This plan closes the chat-context gaps, adds structured payload logging so regressions are debuggable without a paid re-run, promotes the first-analysis facts into a stable style profile the module reuses, rotates the nudge focus topic per generation, and moves the nudge trigger point to match the user's actual moment of peak attention.

## Problem Frame

Reproduction (screenshot 2026-04-17):
- User has a recent cleared upload, a completed glow-up (`after_image_url` present), and a post-analysis nudge that references face shape / proportions.
- User opens Chat tab and sends "What hairstyle would suit me?"
- Ada replies asking the user to describe their face shape.

Root-cause audit of `app/advisor/service.py:send_message` and `app/advisor/context_builder.py:build_context`:

1. **Nudges are absent from context.** `build_context()` takes `soul_md`, `user_data`, `memories`, `conversation`, `message`. Nudges are never threaded in — `AdvisorRepository.get_nudges` is only consumed by the `/v1/advisor/nudges` GET endpoint. Ada cannot reference the nudge the user just read.
2. **`_build_user_data` discards recommendations.** It reads `content.face_shape` and `content.symmetry_score` and returns `"oval face, symmetry 0.87, 4 analyses"`. The `recommendations` array and the `summary` field inside `analysis_insight.content` (written by `memory_manager.write_analysis_insight` — fix 2026-04-16) are dropped before they reach the system block.
3. **Visual trigger too narrow.** `VISUAL_TRIGGER_KEYWORDS = ("look at", "see my", "compare", "photo", "this picture", "my image")`. None match natural style prompts ("hairstyle", "beard", "glasses", "outfit", "brows"). Vision therefore never fires on the exact queries Ada is built for.
4. **No glow-up result in vision.** `_fetch_vision_content` reads `images` table where `status='cleared'` — that is the pre-upload moderation bucket (the source photo only). The generated `after_image_url` on the latest completed `jobs` row never reaches the model. Ada cannot "see" the glow-up the user is looking at on-screen.
5. **RAG can silently omit the latest analysis.** `_MIN_SIMILARITY = 0.60` floor drops analysis_insight candidates whose embedding similarity to "hairstyle" is below 0.6. For terse 3-item recommendations the cosine similarity to a one-noun query is often below threshold. The most-relevant memory goes uninjected.
6. **Zero payload logging.** `service.py` logs conversation creation, trim events, C-2 violations, and daily-threshold degradation. There is no log of the exact `system` / `messages` / `vision_content` / `model` sent to Claude. Debugging a bad response today requires re-running the paid API call with print statements locally — the user's memory rule `feedback_no_money_wasted_on_api_tests` is explicitly being violated.

7. **Nudge generator is blind to the actual image and anchors on re-derived face shape.** `build_post_analysis_prompt` in `app/advisor/nudge_templates.py` foregrounds `face_shape`, `symmetry_score`, and the top 3 `recommendations` on every invocation. Face shape is a stable trait — it does not change between runs — so anchoring the prompt there on each run is structurally guaranteed to produce clones. The 60-min `ADVISOR_POST_ANALYSIS_NUDGE_COOLDOWN_MINUTES` was added as a clone-suppression bandaid (comment at `nudge_scheduler.py:119-123` is explicit about this). More importantly, the nudge generator never looks at the actual before/after photo — the single richest signal the app has about what's interesting *this* time. The correct fix is to promote stable facts into a profile the module reads once, then let the vision-capable model look at *this* specific photo pair and decide what observation to make, with recent-nudge context threaded in so it structurally can't repeat itself. A server-side topic taxonomy (hair / brows / skin / etc.) is the wrong shape: it is culturally brittle on a women-primary audience, feature-coupled (breaks when make-up ships), and makes the server the author of interestingness when the model is better at that job.

8. **Nudge trigger is bound to analysis, not glow-up.** Today `POST /v1/analyses` (face analysis) enqueues `schedule_post_analysis_nudge`. Glow-up completion (the moment the user sees the before/after slider — the emotional peak of the flow) emits no nudge. User intent is "one nudge per glow-up event, landing right when the user is looking at the result." Analysis nudges remain useful (they fire before the glow-up, when the user has just seen the analysis breakdown), but the glow-up-completion moment is missing its own trigger.

## Requirements Trace

- R1. Ada chat must reference the user's analysis results (face shape + recommendations + symmetry) on the first turn without asking the user to re-describe them. (advisor-spec §4.5, §6.1)
- R2. Ada chat must surface the most recent nudges as context so chat and passive surfaces stay aligned. (advisor-spec §7)
- R3. Vision context must auto-attach the user's latest source photo and latest glow-up result whenever the message is about visible styling (hair, beard, brows, fit, skincare, outfit, glasses, makeup). (advisor-spec §6.4)
- R4. RAG retrieval must not silently drop the most recent `analysis_insight` row when the user has one. (advisor-spec §4.4)
- R5. Every Ada LLM call must be debuggable from backend logs alone: model, token counts, memory count, nudge count, vision-block count always at INFO; full system/messages payload at DEBUG behind a flag.
- R6. No regression of SOUL.md voice, content-filter, rate-limit, or per-user isolation. All pass unchanged.
- R7. Nudges must not re-derive face shape or any other stable trait on every generation. The stable user profile is written once per analysis and reused as silent context. Each nudge is grounded in the actual before/after image pair and contextualized against recent nudge bodies so outputs are structurally non-duplicate by the model's own judgment, not by a server-side taxonomy. (advisor-spec §7, §10 cost/safety intent)
- R8. A nudge fires once per completed glow-up (and any future generation feature — make-up next), in addition to the existing analysis-triggered nudge path. Dedup is self-dedup via vision + recent-context prompting; rapid-retry on the same source upload is server-side collapsed.
- R9. The nudge generator must be gender-, style-, and feature-agnostic. No hardcoded focus taxonomy (`hair` / `beard` / etc.). The model decides what is interesting in each specific image, which makes the system correct for a women-primary audience today and automatically correct for make-up when it ships.

## Scope Boundaries

- Not changing SOUL.md or the memory extraction path.
- Not changing the memory schema or embedding model (Ollama 768-dim stays). New memory type `style_profile` reuses the existing `user_memories` table (`type` column is `TEXT`, no enum migration needed).
- Not changing the chat API surface. Same route, same request/response shape.
- Not adding a batch vision endpoint or new image moderation. Reuses existing signed-URL helper.
- Not building a nudges-seen-in-chat "mark read" side effect. Nudges appear in context read-only.
- Not changing the weekly check-in, milestone, or re-engagement triggers. Only the post-analysis + new post-glow-up paths are rewired.
- Not deleting `ADVISOR_POST_ANALYSIS_NUDGE_COOLDOWN_MINUTES` — it is set to 0 and left in place so the setting is a rollback knob if per-topic dedup misbehaves in dev. Removal is a follow-up once the new scheme proves out.

### Deferred to Separate Tasks

- Prompt-caching of SOUL.md block (separate perf PR — this plan increases token count so caching becomes higher-value, but is additive).
- Richer per-memory provenance (link back to the job / nudge id) in the system block — UI-facing, not required for R1-R5.

## Context & Research

### Relevant code and patterns

- `app/advisor/service.py:85-226 send_message` — orchestration entry point. All changes thread through here or through `build_context`.
- `app/advisor/service.py:523-538 _build_user_data` — terse user_data assembly; expand to include `recommendations` and `summary`.
- `app/advisor/service.py:540-575 _fetch_vision_content` — image-block builder; add a glow-up variant that pulls `before_image_url` and `after_image_url` from the latest completed job.
- `app/advisor/context_builder.py:100-131 build_context` — signature extended to accept `nudges: list[dict]`; emit a 4th system block when non-empty.
- `app/advisor/context_builder.py:18-25 VISUAL_TRIGGER_KEYWORDS` — replace with a broader styling-aware matcher (see Key Decisions).
- `app/repositories/advisor_repo.py:519-531 get_latest_analysis_insight` — already returns full `content` dict including `recommendations` and `summary`; no repo change here.
- `app/repositories/advisor_repo.py:367-397 get_nudges_page` and `:get_nudges` — source for the new `get_recent_nudges_for_context` helper (read-only, cap 5, last 14 days).
- `app/repositories/job_repo.py:46-73` — `jobs` table access pattern; new helper `get_latest_completed_job_with_images(user_id)` returns the most recent completed job's `before_image_url` + `after_image_url`.
- `app/api/jobs.py:150-173` — canonical site for signing `before_image_url` (bucket `images`) and `after_image_url` (bucket `generated-images`). Mirror the two-bucket split in the new vision fetch.
- `app/advisor/memory_manager.py:203-256 get_relevant_memories` — hybrid scoring + similarity floor. Add a one-line "always include latest analysis_insight" merge before dedup (see Key Decisions).
- `app/config/__init__.py:64-93` — advisor settings live here; add `ADVISOR_DEBUG_LOG_PROMPT: bool = False`, `ADVISOR_CONTEXT_NUDGE_LIMIT: int = 5`, `ADVISOR_CONTEXT_NUDGE_AGE_DAYS: int = 14`.

### Institutional learnings

- `MEMORY.md` → `feedback_no_money_wasted_on_api_tests` — R5 directly addresses this: log enough that the next debug pass does not re-run the paid call.
- `MEMORY.md` → `feedback_no_hardcoded_urls` — the new trigger keyword list and thresholds land as named constants, not literals at the call site.
- `MEMORY.md` → `feedback_no_env_fallbacks` — new settings expose typed defaults, no silent fallbacks.
- Prior plan `docs/plans/2026-04-16-003-fix-advisor-wiring-and-caps-plan.md` wired the analysis-insight hook and enforced caps; this plan builds on the assumption that `analysis_insight` rows are now being written per analysis.

### External references

- Anthropic vision content block format — already established via `_fetch_vision_content`; no new research.

## Key Technical Decisions

- **Inject nudges as a dedicated system block, not as memories.** Nudges are product-authored content the user saw on a passive surface; blurring them into the memory corpus would distort the hybrid retrieval score. A separate `[system] nudges` block after `[system] memories` keeps provenance explicit and lets a reviewer see at a glance why Ada referenced a given nudge. Cap at 5 nudges, last 14 days, newest first. Budget impact ≈ 150-300 tokens, absorbed by the existing 5 000-token cap.
- **Expand `_build_user_data` to the full analysis fragment.** Render as a terse multi-line block: face shape, symmetry, analysis count, top 3 recommendations, summary (if present). Keeps the SOUL.md "no labels, no prefixes" voice by joining with commas / newlines rather than `Key: Value`.
- **Replace keyword-list vision trigger with a styling-topic matcher.** Keep the current literal triggers as one branch; add a styling-topic branch that matches common self-referential style queries (hair, hairstyle, haircut, beard, stubble, brows, eyebrows, mustache, skin, skincare, fit, outfit, clothes, glasses, frames, makeup, lips, smile) when the user also has at least one cleared image. Rationale: "What hairstyle would suit me?" is the canonical failure mode; any word-list extension that does not cover it is insufficient. Full keyword list lives in `context_builder.py` as a named constant and is covered by unit tests.
- **Vision = source photo + latest glow-up result, in that order.** When a glow-up is available, send `before_image_url` then `after_image_url` as two image blocks (advisor-spec §6.4 already allows two blocks; the current cap is `limit=2` on `get_cleared_images`). Fall back to `get_cleared_images` when no completed job exists. When both are available, prefer the glow-up pair because it tells Ada what the user is actually looking at.
- **Always merge the latest analysis_insight into retrieved memories.** Before dedup, if the user has an `analysis_insight` row that was not already picked by pgvector, splice it into position 0 of the memory list (still subject to the overall limit). Rationale: the analysis is the single most load-bearing memory for style advice; dropping it because embedding similarity is below 0.6 is a correctness bug, not a ranking tradeoff. Keeps the existing hybrid score for all other candidates unchanged.
- **Structured payload logging: one INFO line always, full DEBUG payload behind a flag.** INFO logs a single JSON-serializable dict: `model, user_id_hash, conversation_id, message_count, role_breakdown, system_block_count, system_block_tokens, memory_count, nudge_count, vision_block_count, user_message_length, total_input_tokens_est, trimmed, dropped`. DEBUG logs the full `system` string and `messages` array when `settings.ADVISOR_DEBUG_LOG_PROMPT=True`. Rationale: never log raw user content at INFO (PII risk); give on-demand payload visibility for debug sessions; keep the existing trim/C-2 logs intact.
- **Hash user_id in logs, never emit raw JWT claims.** Use `hashlib.sha256(str(user_id).encode()).hexdigest()[:12]` so logs are greppable across a session but not reversible. Repurposes the hashing helper already imported in `service.py`.
- **Promote stable facts to a `style_profile` memory (upsert, one per user).** Add `MemoryType.STYLE_PROFILE`. On every successful analysis, `write_analysis_insight_job` also upserts a `style_profile` row whose content dict holds the slowly-changing facts: `face_shape`, `symmetry_score`, `proportions_notes` (future), `dominant_traits` (future), `last_updated_at`. Existing `analysis_insight` rows stay — they capture the *event* (one per analysis, immutable). The profile captures the *current state* (one per user, mutable). This separation lets the nudge prompt reference a stable fact without anchoring new output on it: the face shape is in the profile slot, the focus topic is the fresh angle. Rationale: reusing `user_memories` avoids a schema migration; a single upsert is cheap; downstream readers (chat user_data block, nudge prompt) share the same source of truth.
- **Rotate nudge focus topic per generation.** Nudge focus topics live as a named ordered tuple in `app/advisor/nudge_policy.py`: `("hair", "beard", "brows", "skin", "fit", "accessories")`. The nudge scheduler inspects the user's last N post-analysis + post-glowup nudges, extracts the focus topic from each (stored as a new `focus` column on `advisor_nudges`), and picks the next untouched or longest-unused topic. `build_post_analysis_prompt` is renamed to `build_focus_nudge_prompt(profile, focus_topic, recommendations)` — the profile goes in as context, the focus topic is the subject the LLM is asked to address, and recommendations filter to items relevant to the focus. Rationale: structural variety beats a time cooldown. Each nudge is *about* something different, which is what the user actually wants to read.
- **Replace 60-min time cooldown with 48h per-topic dedup.** Set `ADVISOR_POST_ANALYSIS_NUDGE_COOLDOWN_MINUTES=0` in `.env.example`. Add `ADVISOR_NUDGE_TOPIC_DEDUP_HOURS: int = 48`. A nudge with focus topic `X` is skipped only if the last nudge with the same focus fired within 48h. This allows 3-6 distinct-topic nudges per day if the user is actually producing that many glow-ups, and blocks the clone scenario without blocking genuinely new content.
- **Add `post_glowup` trigger, fired from glow-up worker on job completion.** Generation worker (`app/generation/worker.py`) already owns the `jobs.status='completed'` transition. On the success branch, enqueue `generate_nudge` with trigger `TRIGGER_POST_GLOWUP`, no insight payload (the worker reads the user's `style_profile` via the scheduler). The analysis trigger stays — analysis and glow-up are distinct emotional moments and both earn a nudge, subject to the per-topic dedup. Rationale: the glow-up screen is where the user's attention peaks; a nudge landing there is the highest-signal moment for the passive surface.

## Open Questions

### Resolved During Planning

- **Should nudges in context be filtered to unread only?** Resolved → include both read and unread, last 14 days, cap 5. Read nudges may still be recent and relevant; filtering on read state creates a different-answer-if-you-opened-the-tab failure mode.
- **Should vision fire on every message once a user has cleared images?** Resolved → no. Styling-topic match OR explicit-trigger match is required. Sending vision on every "Hello" wastes tokens and invites `visual_trigger` false positives (e.g., "I love my job").
- **Should the logged payload include signed URLs?** Resolved → log URL host + expiry only at INFO; full URL only at DEBUG. Signed URLs are time-limited but still a leakable secret; the INFO line must stay safe to ship off-box.
- **Where does the new `get_latest_completed_job_with_images` live — advisor_repo or job_repo?** Resolved → `advisor_repo.py`. Keeps all advisor-side data access behind one repo (service-layer testability), adds a one-line Supabase query on `jobs` (same DB, no new dependency). The existing `images` access already lives there.
- **Should the new logging use a dedicated logger (`advisor.payload`)?** Resolved → yes, `logging.getLogger("app.advisor.payload")` so operators can `LOG_LEVEL_app_advisor_payload=DEBUG` without turning on debug globally. Logger name is a named constant.

### Deferred to Implementation

- **Exact trimming behavior when nudge block + expanded user_data push the system prefix over budget.** Current `trim_to_budget` protects all system messages; may need to introduce a soft cap on the nudge block specifically. Resolve by reading actual token counts during implementation; initial expectation is that with a 5 000-token budget this is not hit.
- **Token cost of 2 image blocks on style questions.** Anthropic bills vision per resized tile; may or may not push cost above the Haiku degradation threshold in practice. Watch in dev after flip; the 50-msg/day degradation gate already exists.

## High-Level Technical Design

> *This illustrates the intended message shape and is directional guidance for review, not implementation specification.*

```
system: SOUL.md                         (unchanged)
system: user_data                       (expanded: face shape, symmetry, count, recs, summary)
system: memories                        (hybrid-scored + pinned latest analysis_insight)
system: nudges                          (NEW — newest 5, last 14 days)
[conversation history up to token budget]
user: "<message>"
[vision: before_image_url, after_image_url]   (NEW — when styling-topic OR explicit trigger matches)
```

Payload log (INFO, one line per call):

```json
{
  "event": "advisor.llm_call",
  "model": "claude-sonnet-4-6",
  "user_id_hash": "a3f9b2c7d1e4",
  "conversation_id": "…",
  "system_block_count": 4,
  "memory_count": 5,
  "nudge_count": 3,
  "vision_block_count": 2,
  "user_message_length": 38,
  "total_input_tokens_est": 2140,
  "trimmed": false,
  "dropped": 0
}
```

Payload log (DEBUG, same line + `"payload": {"system": "…", "messages": [...]}`): only when `ADVISOR_DEBUG_LOG_PROMPT=True`.

## Implementation Units

- [ ] **Unit 1: Expand `_build_user_data` to the full analysis fragment**

**Goal:** Ada's user_data system block includes face shape, symmetry, count, top 3 recommendations, and summary. No more "oval face, symmetry 0.87, 4 analyses".

**Requirements:** R1

**Dependencies:** None.

**Files:**
- Modify: `app/advisor/context_builder.py` (`build_user_data_block` signature adds `recommendations: list[str] | None`, `summary: str | None`)
- Modify: `app/advisor/service.py` (`_build_user_data` passes the new fields through)
- Test: `tests/test_advisor_context_builder.py` (new or extended)

**Approach:**
- `build_user_data_block` emits a single comma-separated fragment when only basics exist (back-compat) and a two-line fragment when recommendations or summary exist. Stays label-free per SOUL.md.
- `_build_user_data` reads `content.recommendations` (list) and `content.summary` (str) from `get_latest_analysis_insight`.

**Patterns to follow:**
- `context_builder.py:format_memory` — raw fragment, no labels.
- `memory_manager.summarize_memory_content` — same joining style.

**Test scenarios:**
- Happy path: analysis_insight with face_shape, symmetry, recs, summary → block contains all five signals, no "face shape:" or similar labels.
- Happy path: analysis_insight with only face_shape → block matches the current terse output (back-compat).
- Edge case: `recommendations=[]` and `summary=""` → block emits only the terse line.
- Edge case: `analysis_count=0` → block omits the analyses clause.
- Edge case: `symmetry_score=None` → block omits the symmetry clause.

**Verification:**
- `tests/test_advisor_context_builder.py::test_user_data_block_includes_recommendations_and_summary` passes.
- Existing `build_user_data_block` tests pass unchanged.

- [ ] **Unit 2: Expose user photos via MCP-style tool surface — model fetches bytes, never signed URLs**

**Goal:** Replace eager `vision_content` attachment with a tool surface the model calls on demand. Named tools (`get_latest_photo`, `get_latest_glowup`) return image bytes as base64 blocks from server-held storage creds. No signed URL ever enters the LLM payload, prompt, or log stream.

**Requirements:** R3

**Dependencies:** None structurally. Unit 9 lands the tool registry; this unit wires the two photo tools + removes the eager `vision_content` path.

**Files:**
- Create: `app/advisor/mcp/tools_vision.py` (two tool handlers: `get_latest_photo`, `get_latest_glowup`)
- Modify: `app/advisor/service.py` — drop `_fetch_vision_content` eager path; pass registered tool schemas into the LLM adapter and loop on tool-use turns.
- Modify: `app/advisor/llm_port.py` — `create_message` signature adds `tools: list[dict] | None` and returns either a text response or a `tool_use` block list.
- Modify: `app/advisor/adapters/anthropic_adapter.py` — thread `tools` through `AsyncAnthropic.messages.create`; handle `stop_reason == "tool_use"`; redact tool-result image content in debug logs (extend existing `_redact_image_sources`).
- Modify: `app/advisor/adapters/mock.py` — mock must simulate a `tool_use` turn for tests.
- Modify: `app/repositories/advisor_repo.py` — new `get_latest_completed_job_with_images(user_id) -> dict | None`, `has_any_cleared_image(user_id) -> bool`, `fetch_image_bytes(storage_path, bucket) -> bytes`.
- Test: `tests/test_advisor_mcp_tools_vision.py`

**Approach:**
- The tool registry lives in Unit 9. This unit contributes the two vision tool handlers: `get_latest_photo(user_id)` returns the most recent cleared source image as a base64 Anthropic `image` content block; `get_latest_glowup(user_id)` returns a two-block list (before + after) from the latest completed `jobs` row.
- `user_id` is injected into every handler from the outer request context, NOT from LLM-provided arguments. The tool schema exposed to the model takes zero arguments (or only non-sensitive filters like `n`). This prevents cross-user requests even if the model hallucinates a user_id — the server ignores any `user_id` the LLM tries to pass.
- Handlers fetch bytes via Supabase storage `download()` (server-side, service-role key), not `create_signed_url()`. Signed URLs never exist in this code path.
- Tool-use loop cap: max 3 tool-use rounds per user turn (prevents a runaway "call every tool" chain). Named constant `ADVISOR_MAX_TOOL_ROUNDS: int = 3` in config.
- SOUL.md nudge: add one-line hint pointing the model at the vision tools when the user's question is about visible styling. Kept short to avoid voice drift — actual guidance is in tool descriptions.
- Explicit visual trigger keywords (`"look at"`, `"see my"`, etc.) go away as a prompt-level concern. Decision to fetch vision is now the model's, bounded by the tool-round cap.

**Patterns to follow:**
- `app/api/jobs.py:150-173` — two-bucket key convention (before → `images`, after → `generated-images`).
- `app/advisor/adapters/anthropic_adapter.py:_redact_image_sources` — extend to cover tool-result image content.

**Test scenarios:**
- Happy path: `get_latest_photo(user_id)` for a user with one cleared image → returns a single Anthropic image block with `source.type="base64"`, `media_type` set, bytes non-empty.
- Happy path: `get_latest_glowup(user_id)` for a user with one completed job → returns 2 blocks (before, after) in that order, both base64.
- Happy path: LLM tool-use loop — model responds with `tool_use` block; service invokes handler; tool_result appended; second model call returns final text.
- Edge case: user has no completed glow-up → `get_latest_glowup` returns a `tool_result` with `is_error=True` and a terse message the model can surface; no crash.
- Edge case: user has no cleared images → `get_latest_photo` returns `is_error=True` tool_result.
- Edge case: model requests 5 tool calls in one turn → first 3 execute; remainder replaced with "tool round cap exceeded" tool_results; final text produced from what was gathered.
- Security: LLM-provided `user_id` argument is silently ignored — handler uses authenticated user_id only. Test asserts cross-user call is refused.
- Security: adapter log records NEVER contain signed URLs or base64 image data (extend `_redact_image_sources` test coverage).
- Integration: full `send_message` — user asks "What hairstyle would suit me?" with a glow-up present → final payload log shows `tool_calls=1, tool_results=2` (before + after blocks) and 0 signed URLs in any recorded message.

**Verification:**
- `tests/test_advisor_mcp_tools_vision.py` passes (all scenarios above).
- `tests/test_advisor_service.py::test_tool_use_loop_with_glowup` passes.
- Redaction test asserts: grep of every captured log record for signed-URL fragments (`"/storage/v1/object/sign/"`, `"?token="`) returns zero hits even with `ADVISOR_DEBUG_LOG_PROMPT=True`.

- [ ] **Unit 3: Pin latest analysis_insight into retrieved memories**

**Goal:** When the user has an `analysis_insight` row, it is always present in the memories passed to `build_context`, regardless of pgvector similarity to the current message.

**Requirements:** R4

**Dependencies:** None (Unit 1 makes this doubly useful but not required).

**Files:**
- Modify: `app/advisor/memory_manager.py` (`get_relevant_memories` merges the latest analysis_insight before dedup + limit)
- Test: `tests/test_advisor_memory_manager.py`

**Approach:**
- After the hybrid-scored dedup pass, fetch the latest `analysis_insight` for the user (cheap — `get_latest_analysis_insight` already exists).
- If the dedup results do not already contain that row (compare by id or content fingerprint), prepend it and re-enforce the limit by dropping the last item.
- No change to the 0.60 similarity floor for other memory types — the floor is correct for noise suppression, wrong for this specific pin.

**Patterns to follow:**
- `memory_manager.py:244-256` existing dedup fingerprint via SHA-256.

**Test scenarios:**
- Happy path: user has analysis_insight, pgvector returns it with high similarity → single copy in output (no duplication from the pin).
- Happy path: user has analysis_insight, pgvector does NOT return it (similarity below floor) → pinned at position 0 of output, limit enforced by dropping the last scored memory.
- Edge case: user has no analysis_insight → no pin, behavior identical to current implementation.
- Edge case: `ADVISOR_CONTEXT_MEMORY_LIMIT=1` and pgvector returned a high-scoring non-analysis memory → output contains the pinned analysis_insight only (pin takes slot).

**Verification:**
- `tests/test_advisor_memory_manager.py::test_latest_analysis_insight_is_pinned` passes.
- Existing memory retrieval tests pass unchanged.

- [ ] **Unit 4: Thread nudges into `build_context` as a dedicated system block**

**Goal:** Ada sees the user's recent nudges in every chat turn. Block is separate from memories; provenance is explicit.

**Requirements:** R2

**Dependencies:** None.

**Files:**
- Modify: `app/advisor/context_builder.py` (`build_context` accepts `nudges: list[dict]`; emits a 4th system block when non-empty)
- Modify: `app/advisor/service.py` (`send_message` calls a new `_fetch_context_nudges(user_id)` and passes the result into `build_context`)
- Modify: `app/repositories/advisor_repo.py` (new `get_recent_nudges_for_context(user_id, limit, since)` → `list[dict]`)
- Modify: `app/config/__init__.py` (`ADVISOR_CONTEXT_NUDGE_LIMIT: int = 5`, `ADVISOR_CONTEXT_NUDGE_AGE_DAYS: int = 14`)
- Modify: `app/.env.example` (document the two new settings)
- Test: `tests/test_advisor_context_builder.py`, `tests/test_advisor_service.py`

**Approach:**
- `get_recent_nudges_for_context` selects `body, trigger, created_at` from `advisor_nudges` where `user_id = … AND created_at >= now() - interval …` ordered desc limit N. Read-only; no side effects on `read_at`.
- `build_context` emits the block as `"nudge (<trigger>): <body>"` joined by newlines. Keeps SOUL.md "no labels" spirit by using lowercase trigger as prefix rather than verbose label.
- Nudges block is token-counted and subject to the existing `trim_to_budget` logic. The trim function already protects system blocks; verify no regression.

**Patterns to follow:**
- `context_builder.py:100-131` build_context layering order.
- `advisor_repo.py:367-397` get_nudges_page shape.

**Test scenarios:**
- Happy path: user has 3 recent nudges → 4th system block present in output with 3 lines, newest first.
- Happy path: user has 0 nudges → no 4th block (existing 3-block shape preserved).
- Edge case: user has 10 nudges all within 14 days → 5 most recent present (cap honored).
- Edge case: user has 5 nudges older than 14 days → no block.
- Edge case: nudge body contains a newline → newline replaced with space before joining (preserves block structure).
- Integration: `send_message` end-to-end → nudge block appears in the `messages` passed to the LLM adapter (mock asserts on system[3]).

**Verification:**
- `tests/test_advisor_context_builder.py::test_build_context_includes_nudge_block` passes.
- `tests/test_advisor_service.py::test_send_message_threads_nudges_into_context` passes.
- Manual: open chat with a user that has a post-analysis nudge; Ada's first reply references the nudge facts without asking the user to repeat them.

- [ ] **Unit 5: Structured payload logging (INFO summary + DEBUG full payload)**

**Goal:** Every Ada LLM call emits one INFO log line with model + token/block counts + trim stats. When `ADVISOR_DEBUG_LOG_PROMPT=True`, the same call also emits a DEBUG line with the full system string and messages array.

**Requirements:** R5

**Dependencies:** Unit 4 ideally — so the nudge counter is populated. Functionally independent.

**Files:**
- Create: `app/advisor/payload_logger.py` (new module: `log_llm_call(logger, *, model, user_id, conversation_id, system, messages, vision_content, trimmed, dropped)`)
- Modify: `app/advisor/service.py` (`_call_llm_with_check` invokes `log_llm_call` before every `self._llm.create_message`)
- Modify: `app/config/__init__.py` (`ADVISOR_DEBUG_LOG_PROMPT: bool = False`)
- Modify: `app/.env.example` (document the new setting; explicitly note "dev only — do not enable in production")
- Test: `tests/test_advisor_payload_logger.py` (new)

**Approach:**
- `payload_logger.py` exports one function; no class, no state. Uses a dedicated logger `app.advisor.payload`.
- INFO line: build a `dict` with stable key order, `json.dumps(sort_keys=True)`-serialize, pass as `extra={"metric": "advisor.llm_call", ...}` plus a single human message so log aggregators index the `metric` field without re-parsing.
- User ID appears ONLY as `user_id_hash` (first 12 hex chars of sha256) — never raw.
- Signed URLs at INFO: host + expiry derived via `urllib.parse.urlsplit` — full URL NEVER appears at INFO.
- DEBUG line: when flag enabled, emit separate log record with full `system` string, full `messages` array (content included), and full vision URLs. Still with `user_id_hash`, never raw user_id.
- Token estimate: reuse `context_builder._count_tokens` for the INFO estimate — this sums across system + messages, same function the trim path uses.

**Patterns to follow:**
- `service.py:175-179` existing structured log with `extra` metric key.
- `app/config/__init__.py:64-93` — typed default, no fallback (per `feedback_no_env_fallbacks`).

**Test scenarios:**
- Happy path: `log_llm_call` with 4 system blocks, 2 memories, 3 nudges, 2 vision blocks → INFO record's `extra` has correct counts; no raw user_id or full URL.
- Happy path: `ADVISOR_DEBUG_LOG_PROMPT=False` → only one INFO record emitted; no DEBUG record.
- Happy path: `ADVISOR_DEBUG_LOG_PROMPT=True` → two records; DEBUG has full `system` + `messages` keys.
- Edge case: `vision_content=None` → `vision_block_count=0`, no URL fields emitted.
- Edge case: `trimmed=True, dropped=2` → both fields surface at INFO.
- Error path: serialization fails mid-call (e.g., non-JSON-serializable message part) → logger falls back to `repr()` on that field, never crashes the request path.
- Integration: `_call_llm_with_check` with mock LLM → log capture shows one INFO record per LLM call (two records when retry fires).

**Verification:**
- `tests/test_advisor_payload_logger.py` test suite passes.
- Manual: `ADVISOR_DEBUG_LOG_PROMPT=true make up`, send a chat message, observe one INFO + one DEBUG record in `docker compose logs api` (DEBUG gated by log level as well).
- `make lint` + `make test` clean.

- [ ] **Unit 7: Stable `style_profile` memory — written once per analysis, referenced by chat + nudge**

**Goal:** Introduce `MemoryType.STYLE_PROFILE`. One row per user. Upserted on every successful analysis. Chat user_data block and nudge prompt both read from this row instead of re-deriving from the most recent `analysis_insight`.

**Requirements:** R1, R7

**Dependencies:** Unit 1 (user_data block already consumes richer content — this swaps the data source from `analysis_insight` to `style_profile`).

**Files:**
- Modify: `app/advisor/models.py` — add `STYLE_PROFILE = "style_profile"` to `MemoryType`.
- Modify: `app/advisor/memory_manager.py` — new `upsert_style_profile(user_id, face_shape, symmetry_score, recommendations)`; reuses the existing embed + write path with an "upsert by (user_id, type='style_profile')" variant (one row per user).
- Modify: `app/repositories/advisor_repo.py` — `get_style_profile(user_id) -> dict | None`, `upsert_style_profile(row) -> dict` (uses Supabase `.upsert()` with `on_conflict="user_id,type"` assuming a partial-unique index exists; if not, read-then-insert-or-update fallback).
- Create: `app/migrations/0035_style_profile_unique.sql` — partial unique index `CREATE UNIQUE INDEX ... ON user_memories(user_id) WHERE type='style_profile'`. Allows upsert ergonomics without blocking multiple `analysis_insight` rows.
- Modify: `app/advisor/nudge_scheduler.py` — `write_analysis_insight_job` ALSO calls `upsert_style_profile` with the same facts (still fire-and-forget; independent failure).
- Modify: `app/advisor/service.py` — `_build_user_data` reads `style_profile` first; falls back to `get_latest_analysis_insight` for back-compat during rollout.
- Test: `tests/test_advisor_style_profile.py`

**Approach:**
- Content shape kept minimal in v1: `{face_shape, symmetry_score, recommendations, last_updated_at}`. Reserve space for `proportions_notes`, `dominant_traits`, `skin_tone`, `build` as nullable keys; future extraction passes can populate them without a schema change.
- Upsert semantics: on re-analysis, merge the new facts into the existing profile (new fields overwrite, absent fields preserved). Prevents regression if a later analysis returns a thinner payload.
- The existing `analysis_insight` rows stay — they remain the immutable per-event record. Only the *current state* lives in the profile.

**Patterns to follow:**
- `memory_manager.write_memory` — embed + insert pattern, extended with upsert.
- `nudge_scheduler.write_analysis_insight_job` — fire-and-forget, failure swallowed with structured log.

**Test scenarios:**
- Happy path: first analysis → new `style_profile` row written; face_shape and symmetry present.
- Happy path: second analysis with different facts → existing row updated (one row total per user), `last_updated_at` advanced.
- Happy path: `_build_user_data` reads from profile when present → block includes the expanded fields.
- Edge case: analysis write succeeds, profile upsert fails → `analysis_insight` still written; service falls back to reading latest `analysis_insight` for user_data (no user-visible regression).
- Edge case: profile lacks `recommendations` (null) → user_data block omits the recommendations clause gracefully (Unit 1 already handles this).
- Migration safety: `0035` uses a partial index; existing `analysis_insight` rows unaffected.

**Verification:**
- `tests/test_advisor_style_profile.py` passes.
- `make migrate` clean on a fresh DB.
- Manual: run two analyses for the same user; `select count(*) from user_memories where user_id=… and type='style_profile'` returns 1.

- [ ] **Unit 8: Vision-grounded post-generation nudge — the model sees the actual photo and decides what to say**

**Goal:** Replace the face-shape-parroting prompt (and my earlier deterministic focus-topic rotation) with vision-driven nudge generation. On every completed generation (glow-up today, make-up next, any future feature), the nudge worker calls the model with (a) the before/after images, (b) the user's stable `style_profile`, (c) the last N nudge bodies, and asks the model to write one warm sentence about whatever is actually most interesting in *this* specific image pair that hasn't been covered recently. No fixed topic taxonomy. No server-side rotation. Dedup is self-dedup via context. Gender-, style-, and feature-agnostic by construction; the app is women-primary and a preset list like `(hair, beard, brows, skin, fit, accessories)` is both culturally wrong and operationally brittle.

**Requirements:** R7, R8

**Dependencies:** Unit 2 + Unit 9 (the nudge worker uses `get_latest_glowup` / `get_latest_generation` as an internal MCP client so nudges and chat share the exact same image-fetch path). Unit 7 (stable `style_profile` is the context block; the model never re-derives face shape from the image).

**Files:**
- Modify: `app/advisor/nudge_policy.py` — add `TRIGGER_POST_GLOWUP = "post_glowup"`. Remove the `FOCUS_TOPICS` tuple entirely — it was my mistake.
- Rewrite: `app/advisor/nudge_templates.py` — delete `build_post_analysis_prompt`; replace with `build_vision_nudge_prompt(profile, recent_nudge_bodies, recent_observation_tags)`. Prompt body detailed in Approach below.
- Modify: `app/advisor/nudge_scheduler.py` — `generate_nudge` now branches into two paths: (1) `vision_nudge` for `post_analysis` and `post_glowup` — fetches images via the internal MCP client, calls the vision-capable Claude model, parses a strict JSON response `{"body": str, "observation_tag": str}`; (2) generic path for `weekly_checkin` / `milestone` / `re_engagement` unchanged. Removes the 60-min time cooldown and the focus-topic picker altogether.
- Modify: `app/repositories/advisor_repo.py` — `get_recent_nudge_context(user_id, limit=5)` returns `[{body, observation_tag, created_at}]` for the vision prompt's "don't repeat these" block.
- Create: `app/migrations/0036_advisor_nudges_observation.sql` — `ALTER TABLE advisor_nudges ADD COLUMN observation_tag TEXT`. Nullable, back-compat.
- Modify: `app/generation/worker.py` — on `jobs.status='completed'` success branch (both `before_image_url` and `after_image_url` populated), enqueue `generate_nudge(user_id, TRIGGER_POST_GLOWUP, job_id)`. Fire-and-forget; failure logged; never blocks completion.
- Modify: `app/config/__init__.py` — `ADVISOR_NUDGE_RECENT_CONTEXT_LIMIT: int = 5` (how many prior nudge bodies feed the "don't repeat" prompt); set `ADVISOR_POST_ANALYSIS_NUDGE_COOLDOWN_MINUTES: int = 0` default (kept as a rollback knob only, documented as deprecated).
- Modify: `app/.env.example` — document the new settings; mark the old cooldown as deprecated.
- Test: `tests/test_advisor_vision_nudge.py`, `tests/test_advisor_nudge_post_glowup.py`.
- Update: `tests/test_advisor_nudge_post_analysis_grounded.py` — existing test file; adjust to assert the new vision-based prompt shape and JSON output parsing.

**Approach:**
- **Prompt shape (`build_vision_nudge_prompt`):**
  - System: SOUL.md (unchanged; "no labels, no prefixes" voice).
  - User message: a short structured block —
    - "Stable facts about this user:" followed by the `style_profile` rendered compactly (same block the chat user_data uses).
    - "Recent nudges you already sent (do not repeat the same idea or phrasing):" a bulleted list of the last N bodies + their `observation_tag`s.
    - "Look at the attached before/after images. Pick the single most genuinely interesting specific thing about the new look — a detail that emerged, a contrast that reads well, a moment that lands. Write one warm sentence about that thing. Then emit a 1-3-word tag describing what you chose to focus on."
    - Output contract: strict JSON, single object, `{"body": "<one sentence>", "observation_tag": "<1-3 words>"}`. Parser validates; on parse failure the nudge is dropped and a `nudge_invalid_json` metric increments (no retry — next glow-up gets its own chance).
  - Vision content: the before + after image blocks fetched via the internal MCP client (same tool handler that chat uses — `get_latest_glowup` / `get_latest_generation`). Identical redaction + user-scoped safety as Unit 9.
- **Model:** the vision-capable Haiku model — `settings.ADVISOR_MODEL_HAIKU` is Claude Haiku 4.5 which supports vision. No Sonnet escalation (kept on cost; feedback from the prior Sonnet revert confirms Haiku voice is right for nudges).
- **Trigger surface:**
  - `post_glowup` fires from the worker on successful completion (success branch, both URLs populated).
  - `post_analysis` stays wired from `app/api/glowup.py:300-313` (existing callsite unchanged), but its code path now routes through `vision_nudge` too — the analysis screen has no generated "after" yet, so for this trigger the vision content is just the source photo. Prompt handles the degenerate 1-image case.
- **Rapid-retry dedup:** if another `post_glowup` for the same user fires within 5 minutes of the last one and the prior job was for a retry of the same source image (same `upload_id` on the source), skip. This is a narrow guard against the "user tapped Analyze, got a failure, tapped again" scenario producing back-to-back near-duplicate images. Any other case (user genuinely uploads a different photo and runs it) fires normally.
- **No cooldown, no rotation, no taxonomy.** Dedup emerges from the model's own access to prior bodies + tags. This is the whole point of the redesign.
- **Observation tag usage:** the tag is a model-authored short label ("softer jaw", "cleaner brows", "warmer undertone", "hair falls differently"). It is persisted alongside the body. Future nudges see it in the "recent context" block and naturally steer elsewhere. The server never interprets or filters on it — it is context for the model, not routing logic.

**Patterns to follow:**
- `app/advisor/service.py:540-575` existing `_fetch_vision_content` shape — but go through the MCP registry instead of duplicating the fetch.
- `app/advisor/memory_manager.py:280-304` — existing Haiku JSON-extraction prompt with parser + `json.loads` guard. Mirror the same robustness.
- `app/generation/worker.py:_fail_job` — canonical fire-and-forget shape on terminal state transitions. Mirror for the success branch.

**Test scenarios:**
- Happy path: user completes first glow-up → `post_glowup` nudge generated; body is one sentence; `observation_tag` is 1-3 words; both persisted.
- Happy path: user completes a second, visually-different glow-up 20 min later → second nudge's body has low word-overlap (<40%) with the first; observation_tag differs from the first.
- Happy path: post_analysis nudge with only a source image (no after yet) → prompt degrades gracefully; body stays grounded; no hallucinated "after" details.
- Edge case: model returns malformed JSON → nudge dropped; `advisor.nudge_invalid_json` metric increments; no partial row persisted.
- Edge case: user has no `style_profile` → nudge job skipped with structured log (same as pre-redesign).
- Edge case: rapid retry on the same `upload_id` within 5 min → second `post_glowup` skipped; log says `rapid_retry_dedup`.
- Edge case: model picks the same `observation_tag` as a recent one despite the prompt → the prompt does not currently force uniqueness; a duplicate tag is accepted. A follow-up can add a one-shot regenerate if the same tag appears twice in the recent list, but v1 keeps it simple.
- Edge case: `observation_tag` column is NULL on old rows → treated as "no tag" by the recent-context block (graceful forward compat).
- Security: the nudge worker calls the MCP registry with the *user's* context; cross-user image leakage impossible by the same 4-layer invariant in Unit 9 (unit test asserts nudge worker cannot fetch another user's images).
- Integration: two glow-ups back-to-back, same user, visually similar → two non-duplicate nudges emitted. Assert via word-overlap test that body-vs-body cosine / Jaccard stays below a sanity threshold. Not a golden test (model output varies) — a regression threshold.

**Verification:**
- `tests/test_advisor_vision_nudge.py` passes.
- `tests/test_advisor_nudge_post_glowup.py` passes.
- Existing `tests/test_advisor_nudge_post_analysis_grounded.py` passes with the new prompt shape.
- Dev smoke: log in, navigate to `/(tabs)/upload`, run two different glow-ups on two different uploads; open profile → confirm two distinct nudges; eyeball the bodies to verify they reference specific things visible in the respective images (not face-shape boilerplate).
- SQL check: `SELECT observation_tag, count(*) FROM advisor_nudges WHERE trigger IN ('post_glowup','post_analysis') GROUP BY observation_tag` shows diverse tags across runs, not one dominant repeat.

- [ ] **Unit 9: Advisor tool surface (MCP-style) — user-scoped, bytes-only, no signed URLs in prompts**

**Goal:** Ada chat operates via a tool surface the model invokes on demand. Named tools expose the user's glow-up images (the primary artifact advisor reasons about), style profile, recent nudges, and memory search. Handlers run server-side with full Supabase creds, enforce JWT-scoped `user_id`, and return bytes (base64) for images — signed URLs are never generated on this path. Registry is a **pluggable per-feature module** so the upcoming make-up feature (and any future visual feature) lands as a new `tools_<feature>.py` file with its own schemas, not as edits to the adapter or core service. Source photos (bare cleared uploads) remain available as a fallback tool but are not the advisor's primary image source.

**Requirements:** R3, R5 (and enables R1, R2 richer fetches on demand)

**Dependencies:** Unit 2 (consumer of the vision tools), Unit 4 (nudge primer block; tool fetches deeper), Unit 7 (profile tool reads the stable row).

**Files:**
- Create: `app/advisor/mcp/__init__.py`
- Create: `app/advisor/mcp/registry.py` — `ToolRegistry`, schema export, dispatch by name.
- Create: `app/advisor/mcp/context.py` — per-request context object carrying `user_id`, `supabase` client, `advisor_repo`; injected into every handler.
- Create: `app/advisor/mcp/tools_vision.py` — `get_latest_photo`, `get_latest_glowup` (moved from Unit 2 skeleton to here).
- Create: `app/advisor/mcp/tools_profile.py` — `get_style_profile` (returns `face_shape`, `symmetry_score`, `recommendations`, `last_updated_at`).
- Create: `app/advisor/mcp/tools_nudges.py` — `get_recent_nudges(limit, since_days)` returning structured list.
- Create: `app/advisor/mcp/tools_memories.py` — `search_memories(query, limit)` wrapping `memory_manager.get_relevant_memories`.
- Create: `app/advisor/mcp/tools_jobs.py` — cross-feature tools: `get_latest_generation` (returns latest completed `jobs` row as images + `feature` metadata, regardless of `source_type`) and `get_latest_job_status` (status-only, no URLs). Hook point for future features.
- Rename (from Unit 2): `app/advisor/mcp/tools_vision.py` → `app/advisor/mcp/tools_glowup.py`. Same handlers, feature-explicit name so `tools_makeup.py` can land parallel in a future PR without confusion.
- Modify: `app/advisor/llm_port.py` — `create_message` accepts `tools: list[dict] | None` and returns `LLMResponse | ToolUseResponse`.
- Modify: `app/advisor/adapters/anthropic_adapter.py` — attach tools to the Anthropic call; handle `stop_reason == "tool_use"`; loop until final text or round cap.
- Modify: `app/advisor/adapters/mock.py` — mock handles tool-use for tests.
- Modify: `app/advisor/service.py` — build registry per turn with user-scoped context; pass schemas to adapter; surface `tool_call_count` and `tool_names` to the payload logger.
- Modify: `app/config/__init__.py` — `ADVISOR_MAX_TOOL_ROUNDS: int = 3`, `ADVISOR_TOOLS_ENABLED: bool = True` (kill switch).
- Modify: `app/advisor/payload_logger.py` (from Unit 5) — extra fields `tool_call_count`, `tool_names`, `tool_errors`.
- Modify: `app/advisor/persona.py` / SOUL.md — add a one-paragraph tools section (brief; real guidance lives in tool descriptions).
- Test: `tests/test_advisor_tool_registry.py`, `tests/test_advisor_tool_security.py`, `tests/test_advisor_tool_roundtrip.py`.

**Approach:**
- **Two-phase delivery, this plan only ships phase 1.** Phase 1: in-process tool registry consumed via Anthropic `tools` in the Messages API. Phase 2 (separate follow-up): expose the same registry as an MCP server (StreamableHTTP transport) for reuse by Claude Desktop / Code. Phase 1 achieves the user's security ask (no URLs in prompts) and is cheaper than spinning up a standalone server. Phase 2 is additive.
- **Registry shape:** each tool module exports `TOOL_SCHEMA` (Anthropic-compatible `{name, description, input_schema}`) and `async def handle(ctx: McpContext, **inputs)`. Registry composes them at advisor-service init time.
- **Pluggable per-feature modules — designed for make-up next.** The `app/advisor/mcp/tools_<feature>.py` convention is the public extension point. Glow-up ships with `tools_glowup.py` (renamed from `tools_vision.py` in Unit 2 — make the feature name explicit from day one). Make-up lands as `tools_makeup.py` whose handlers resolve against the `makeup_sessions` table (already anticipated by the polymorphic `jobs.source_type CHECK IN ('glowup_analysis','makeup_session')` in `app/migrations/0034_glowup_tier3_restructure.sql:82-83`; see `docs/research/ai-makeup-mapping.md` for feature framing). The registry auto-discovers every `tools_*.py` in `app/advisor/mcp/` at init time; no adapter or service changes are required to register a new feature's tools. SOUL.md is the only cross-feature surface that needs a one-line touch ("Ada can work with glow-ups and make-up looks") when make-up ships.
- **Feature-agnostic cross-cutting tool: `get_latest_generation`.** Since `jobs` is polymorphic, Ada often does not know which feature the user is referencing ("what do you think of this look?"). One cross-feature tool queries the most recent completed `jobs` row regardless of `source_type`, returns the before/after images as base64 blocks, AND returns `feature="glowup"` / `feature="makeup"` metadata so the model can frame its reply correctly. Feature-specific tools (`get_latest_glowup`, future `get_latest_makeup`) remain for when the model wants a specific feature's output; the cross-feature tool is the fallback when the question does not name a feature. This pattern survives adding N more feature modules without changing Ada's core behavior.
- **Each feature module owns its own schema, description, and region semantics.** For example, `tools_glowup.py` describes "AI-generated styling edits (hair, beard, grooming, glasses) on the user's face"; a future `tools_makeup.py` would describe "AI-applied make-up looks (Clean Girl, Soft Glam, Smokey Eye, preset × intensity variants)." Same base contract (`TOOL_SCHEMA` + `async def handle(ctx, **inputs)`); different descriptive language so the model picks the right one. Cross-feature tool is the neutral default that always works.
- **Glow-up is the primary visual anchor, not cleared uploads.** `get_latest_glowup` is the tool Ada reaches for first when the question is visual. `get_latest_photo` (source cleared image) remains registered but its description explicitly de-prioritizes it: "Use this ONLY when the user has no glow-up and a source photo is needed for a grooming question that predates any generation." Rationale: advisor's value is styling advice grounded in what the user is considering — the glow-up result is that thing.
- **Cross-user isolation (non-negotiable):** four layers stack.
  1. `McpContext.user_id` is set ONCE, from JWT `claims["sub"]` at request entry in `app/api/advisor.py`. Context is immutable (frozen dataclass). No code path mutates it.
  2. Every tool handler's signature is `async def handle(ctx: McpContext, **model_args)`. `model_args` is filtered by the registry against the tool's declared `input_schema` — unknown keys (including `user_id`, `uid`, `account`, any variant) are dropped BEFORE the handler sees them. Test: `TOOL_SCHEMAS_NEVER_ACCEPT_USER_ID` asserts the string "user_id" (case-insensitive) appears in no tool schema's `input_schema.properties`.
  3. Every repository query invoked by a tool handler passes `ctx.user_id` as the filter. Supabase RLS (already `ENABLE + FORCE` on `user_memories`, `advisor_*`, `images`, `jobs` per migration `0013`) is a belt-and-suspenders backstop; the app layer is the authoritative control.
  4. Request-scoped context is invalidated when the chat turn ends. Reusing a stale `McpContext` from a prior request (e.g. via a leaked reference) is impossible because the registry is constructed per-turn and dropped after `send_message` returns.
- **Prescriptive tool descriptions — the model must know when to call what.** Every `TOOL_SCHEMA.description` follows a three-part contract: **(1) what it returns**, **(2) when to call it**, **(3) when NOT to call it**. Example (`get_latest_glowup`):
  ```
  Returns the user's most recent completed glow-up as two images: the
  before photo and the AI-generated after photo, in that order.

  Call this when the user asks about their glow-up result, compares
  their current look to the generated one, asks what changed, or
  asks a styling question ("what hairstyle would suit me?", "does
  this beard work?") where seeing both images would ground the
  answer. Prefer this over get_latest_photo whenever a glow-up is
  available — the after image shows what the user is thinking about.

  Do NOT call this when the user has not run a glow-up (the tool
  will return is_error=True), when the user is asking about general
  grooming advice not tied to their own face, or when the prior
  turn already fetched the same images. Never pass user_id — the
  server uses the authenticated user only.
  ```
  Each tool description is reviewed in code review against this template. Vague descriptions ("returns the user's photo") are rejected — the model must have enough signal to decide *when* without guessing.
- **Image tools return Anthropic `image` content blocks with `source.type="base64"`**, not URLs. Bytes come from `supabase.storage.from_(bucket).download(path)`.
- **Text tools return plain text summaries** sized to fit within a single tool_result block; never paginate via URL.
- **Rate limiting inside the loop:** `ADVISOR_MAX_TOOL_ROUNDS` caps how many tool-use turns the model can do per user message. On cap exhaustion, remaining tool calls return "tool round cap exceeded" as `is_error=True` tool_result so the model can still finalize its text.
- **Observability:** each tool invocation emits a structured log with `tool=<name>`, `user_id_hash`, `duration_ms`, `success=bool`, `error_class` if any. No raw payloads.
- **Kill switch:** `ADVISOR_TOOLS_ENABLED=False` reverts to the eager-vision path (Unit 2 keeps its fallback branch gated on this flag) so a bad tool deploy does not brick the advisor. Planning expects this to be retired once the tool surface proves stable.

**Patterns to follow:**
- `app/advisor/adapters/anthropic_adapter.py:_redact_image_sources` — same redaction pattern extended to tool-result image content.
- `app/api/deps.py` — DI pattern for building request-scoped objects; `McpContext` follows this style.
- Anthropic Messages API `tools` parameter (2026-current SDK) — attach tools on the outgoing call; process `stop_reason == "tool_use"` loop client-side.

**Test scenarios:**
- Happy path: registry exposes 6 tools (vision ×2, profile, nudges, memories, job status). All schemas validate against the Anthropic tool schema spec.
- Happy path: model requests `get_latest_glowup` → handler returns 2 base64 image blocks; next turn's adapter call includes them; final text references the glow-up.
- Happy path: model requests `get_style_profile` then `get_latest_glowup` in sequence → both satisfied within `ADVISOR_MAX_TOOL_ROUNDS`.
- Security: LLM attempts to pass `user_id="<other>"` to any tool → argument silently stripped; handler uses authenticated user. Test asserts cross-user data never returned.
- Security: assert no registered tool schema includes `user_id` as an allowable input parameter (introspection test).
- Security: logs captured across a full test turn contain zero substrings matching `supabase.co/storage/v1/object/sign` or `?token=`.
- Edge case: tool handler raises → registry returns `tool_result` with `is_error=True` and terse message; model completes its turn with an apology rather than crashing.
- Edge case: registry receives unknown tool name → returns `is_error=True` tool_result; counter increments.
- Kill switch: `ADVISOR_TOOLS_ENABLED=False` → `create_message` never includes tools; eager-vision fallback (Unit 2 gate) still produces vision_content; no regression against pre-tool behavior.
- Roundtrip: full chat turn with 2 tool calls → payload logger shows `tool_call_count=2, tool_names=["get_style_profile","get_latest_glowup"], tool_errors=0`, `vision_block_count=2` from tool results rather than eager attachment.

**Verification:**
- `tests/test_advisor_tool_registry.py` passes.
- `tests/test_advisor_tool_security.py` passes (cross-user, log-leak, schema-introspection assertions).
- `tests/test_advisor_tool_roundtrip.py` passes (full model → tool → model → text loop against the mock adapter).
- Manual: `ADVISOR_DEBUG_LOG_PROMPT=true make up`, chat "what hairstyle would suit me?" with a glow-up present; confirm log records contain zero signed URLs and contain the base64 redaction marker at the expected points.

- [ ] **Unit 6: End-to-end reproduction test + dev-env smoke**

**Goal:** A regression test asserts the canonical failure mode is fixed: given a user with analysis_insight + a post-analysis nudge + a completed glow-up, `send_message("What hairstyle would suit me?")` builds a message payload that contains all four signals, and vision_content is a two-block list. Dev-env smoke confirms Ada no longer asks the user to describe their face shape.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** Units 1, 2, 3, 4, 5.

**Files:**
- Create: `tests/test_advisor_context_integration.py`
- Manual: dev smoke steps added to `docs/plans/2026-04-17-003-fix-advisor-context-aware-plan.md` verification section below.

**Approach:**
- Fixture: insert one `analysis_insight` memory with recommendations + summary; insert 2 advisor_nudges (post_analysis + weekly_checkin); insert one completed `jobs` row with both image URLs; insert one cleared image.
- Inject a stubbed LLM adapter that captures the `messages` / `system` / `vision_content` args on call.
- Assert: `system` string contains the analysis_insight summary, user_data block has the recommendations, nudges block has both nudge bodies, and vision_content has 2 blocks.
- Assert: one INFO log record per call with the expected counts.

**Patterns to follow:**
- Existing integration-style tests under `tests/` use Supabase test client + stubbed adapters.

**Test scenarios:**
- Happy path (the canonical case): all four signals present → all four reach the payload; log counts match.
- Happy path: user with only analysis_insight, no nudges → 3 system blocks, vision absent (no styling keyword OR no cleared image).
- Edge case: feature flag `ADVISOR_ENABLED=False` → route returns 402 before this flow fires (sanity check; no regression).
- Error path: stubbed LLM raises mid-turn → payload logged once before the raise, no partial message persisted.

**Verification:**
- `pytest tests/test_advisor_context_integration.py -x -q` passes.
- Dev smoke: fresh account (log in via Google/Apple), run one analysis + one glow-up, then open Chat tab and send "What hairstyle would suit me?" — Ada's first reply must reference the user's face shape OR one of the recommendations. Capture simulator screenshot for the PR.

## System-Wide Impact

- **Interaction graph:** `build_context` signature change ripples into every caller (today: only `send_message`; tests mock it). All callers updated in the same PR.
- **Error propagation:** New repo calls (`get_recent_nudges_for_context`, `get_latest_completed_job_with_images`, `has_any_cleared_image`) must fail-soft — on exception, log warning and fall through with an empty list / no-vision behavior. Existing `_fetch_vision_content` already models this.
- **State lifecycle risks:** None. All reads; no writes.
- **API surface parity:** `/v1/advisor/messages` request/response shape unchanged. The nudge API (`/v1/advisor/nudges`) is untouched — it still returns the full paginated nudge feed; the context path uses a narrower read for a different purpose.
- **Integration coverage:** Unit 6 covers the cross-layer assembly. Unit 5 covers logging at the call boundary.
- **Unchanged invariants:**
  - SOUL.md loaded at module import; still the only system persona source.
  - Content filter + rate limit still run before memory retrieval.
  - Per-user isolation: every new repo helper filters by `user_id` from JWT claims. RLS policies unchanged.
  - Memory cap + token budget enforcement (prior plan) still applies.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Token budget breach: new nudge block + expanded user_data + two image blocks may push context above 5 000 tokens on chatty users | `trim_to_budget` already drops oldest conversation turns; Unit 6 logs `total_input_tokens_est` so we can see budget usage empirically in dev. If breaches appear, add a nudge-block-specific soft cap in a follow-up. |
| Vision cost regression: every hairstyle-type question now ships 2 image blocks | Existing 50-msg/day Haiku degradation already caps runaway cost per user. Log line exposes `vision_block_count` so a follow-up dashboard can measure the delta. |
| Logging leak: raw user content in INFO logs | INFO logs only counts + hashed user_id + URL host/expiry. Tests assert no raw URL or raw content in the INFO record. |
| Test fragility: existing `build_context` tests break on new signature | Add `nudges=None` as an optional parameter with a default so signature is back-compat for tests that did not pass it; existing tests still pass. Update the tests that must assert the new block. |
| Dev `ADVISOR_DEBUG_LOG_PROMPT=True` accidentally shipped to prod | Documented in `.env.example` as "dev only". Not toggled by default. A separate follow-up can add a CI assertion that the prod env template has it off. |

## Documentation / Operational Notes

- Update `app/.env.example` with `ADVISOR_DEBUG_LOG_PROMPT`, `ADVISOR_CONTEXT_NUDGE_LIMIT`, `ADVISOR_CONTEXT_NUDGE_AGE_DAYS`.
- Update `app/AGENTS.md` advisor section (if present) with the one-paragraph description of the new context layering: SOUL.md → user_data → memories (with analysis pin) → nudges → conversation → user message.
- No runbook change required — nothing new to monitor beyond existing advisor metrics.
- No migration. Nothing new to store.

## Sources & References

- Reproduction: user screenshot 2026-04-17 18:56 — Ada asks "can you describe your face shape" despite analysis + nudge + glow-up in state.
- Related plan: `docs/plans/2026-04-16-003-fix-advisor-wiring-and-caps-plan.md` — wired the analysis_insight write path this plan depends on.
- Related plan: `docs/plans/2026-04-17-001-feat-glowup-ux-polish-and-advisor-nudges-plan.md` — ships the grounded post-analysis nudge this plan threads into context.
- Code: `app/advisor/service.py`, `app/advisor/context_builder.py`, `app/advisor/memory_manager.py`, `app/repositories/advisor_repo.py`, `app/repositories/job_repo.py`, `app/api/jobs.py`.
- Memory rules enforced: `feedback_no_hardcoded_urls`, `feedback_no_env_fallbacks`, `feedback_no_money_wasted_on_api_tests`, `feedback_verify_before_claiming_fixed`, `feedback_pr_workflow`.
