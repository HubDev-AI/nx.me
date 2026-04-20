# Nudges v2 — Actionable Nudges + Chat-Open Seeds

**Date:** 2026-04-20
**Owner:** @trifonov
**Status:** Ready for planning
**Scope:** Standard (backend deletions + one new nudge contract + one new mobile surface; pre-launch, destructive in-place changes — no legacy paths, no deprecation shims, no dual-write windows)
**Branch / worktree:** `feat/nudges-v2` at `../nxme-nudges-v2`

## Problem

The current advisor-nudge system burns Haiku calls on output users find low-value.

Concrete symptoms (verified against `app/advisor/nudge_scheduler.py`, `nudge_templates.py`, `nudge_policy.py`, `nudge_eligibility.py` on HEAD):

1. **Three triggers emit filler.** `weekly_checkin`, `milestone`, and `re_engagement` flow through `_generate_generic_nudge` with a prompt that is literally *"write a brief check-in nudge in your voice, one or two sentences, no greeting"* — no vision, no profile, no goal context. Output reads like SaaS marketing copy.
2. **Vision nudges fire per event with no novelty budget.** `post_analysis` and `post_glowup` each cost one Haiku vision call. A user who runs 10 glow-ups in a week produces 10 nudges of the same face; the model has access to recent-nudge bodies for dedup but not to whether the previous nudge was ever read.
3. **Observations without actions.** The vision-nudge contract is `{body, observation_tag}` — a sentence like "softer jaw in the new cut." Users finish reading with nothing to do next.
4. **Generated eagerly, surfaced passively.** Nudges live on the Ada tab's `NudgeFeed`. Users who never open the tab never see the generated content, but the Haiku call already fired.
5. **No feedback signal.** `read_at` is the only instrumentation. There is no way to learn which nudge shapes land vs. which are ignored, so the prompts cannot improve.

The resulting ROI is: **N triggers × Haiku cost per firing → feed impressions for users who open the tab → zero downstream action.** The spend is real; the return is near zero.

## Goals

Primary (value):
- **Every generated nudge produces downstream action.** Measurable as CTA tap-through rate on `post_glowup` nudges.
- **Every paid Haiku call serves something the user can tap.** No observation-only outputs.

Secondary (cost as consequence, not driver):
- Haiku calls are bounded to user-initiated events: at most one `post_glowup` vision call per completed glow-up, plus at most one `chat-seeds` call per user per hour (enforced by rate limit + single-flight).
- Dormant-user re-engagement is cut from this PR (push subsystem doesn't exist; app pre-launch). Picked up in a later PR if push lands.

Framing note: the original user brief paired "not very helpful" with "waste AI calls." Pre-launch there is no production spend to cut, so "value first, cost as consequence" is the load-bearing frame. Instrumentation (tap-through, seed submission rate, parse-drop rate) is P1 scope, not deferred.

## Non-goals

- Changing Ada's `SOUL.md` persona or the chat request shape.
- Redesigning the advisor tab layout, theming, or navigation beyond adding the chat-open chips row.
- Adding a per-nudge rating UI (good/bad thumbs). Deferred — if we need a feedback loop later, add it after the new contract has baseline data.
- Server-side A/B or prompt variants. One contract, one prompt.
- Any paid-tier / entitlement change — nudges remain ledger-gated per the existing Ada rule.

## Decisions

### 1. Trigger set shrinks to one: `post_glowup`

Delete the following triggers in place (pre-launch, destructive OK per repo policy):

- `TRIGGER_POST_ANALYSIS` — no longer fires after face analysis.
- `TRIGGER_WEEKLY_CHECKIN` — `_generate_generic_nudge` path removed entirely.
- `TRIGGER_MILESTONE` — milestone counts (5, 10) no longer trigger anything.
- `TRIGGER_RE_ENGAGEMENT` — dormant-user path covered by Decision 4.

Keep only `TRIGGER_POST_GLOWUP`. The daily cron `check_nudge_eligibility` and its three eligibility-scan functions in `nudge_eligibility.py` are deleted along with their repository methods (`get_all_goal_user_ids`, `get_user_ids_with_nudge_since`, `count_insights_by_user`, `get_all_insights_with_timestamps`). The ARQ job signatures `schedule_post_analysis_nudge` and `check_nudge_eligibility` are removed from `worker_settings.py`; the analysis endpoint loses its nudge-enqueue call.

**Acceptance:**
- Running `check_nudge_eligibility` no longer exists as a cron; no job emits weekly / milestone / re-engagement nudges.
- Running an analysis does not enqueue any nudge.
- Running a successful glow-up enqueues exactly one `generate_nudge` with `trigger=post_glowup`.
- Tests `test_advisor_nudge_post_analysis_grounded.py` is deleted; `test_advisor_nudge_post_glowup.py` updated for the new contract; no new tests reference removed triggers.

### 2. `post_glowup` nudge becomes actionable

New response contract for the vision-grounded Haiku call:

```json
{
  "body": "<one warm sentence about the new look, ≤ 160 chars>",
  "next_step": {
    "label": "<short CTA copy, ≤ 24 chars>",
    "seed": "<one-sentence user-voice question, ≤ 140 chars, must end with '?'>"
  }
}
```

Prompt update in `build_vision_nudge_prompt`: ask the model for one warm sentence about the new look, plus one next-step question the user could ask Ada about. The seed is a question in the user's voice (e.g. *"what makeup would play up this cheekbone shadow?"*) — not an instruction to Ada. Prompt must include voice/tone guardrails: female-coded language only, no SaaS filler ("Learn more", "Explore", "Try this"), first-person curious register, no imperatives to the assistant. Prompt must also instruct the model to ignore any text visible in the attached image (image-injection guard).

Storage: on `advisor_nudges` — drop `observation_tag`, `trigger`, and any other columns that only existed to serve removed triggers; add `next_step_label VARCHAR(24) NOT NULL` and `next_step_seed VARCHAR(140) NOT NULL`. `body` column gets a `VARCHAR(160)` constraint added. Pre-launch → `TRUNCATE advisor_nudges` in place; no backfill, no nullable shim, no dual-contract window. Parse failure or length-bound failure on any field → drop the nudge pre-insert. No observation-only fallback path exists in code.

**Parse-failure observability.** Log `advisor.nudge_parse_drop` with the failure kind (`json`, `length`, `shape`, `seed_not_question`). Dashboard alert if drop rate over a rolling 200-call window exceeds 15% — that is the threshold at which the paid call is silently failing.

**Nudge CTA handoff endpoint.** `POST /v1/advisor/nudges/{nudge_id}/next-step`. Ownership: server loads the nudge row and requires `nudge.user_id == auth.user_id`; 404 (not 403 — do not leak existence) on mismatch. Behavior: mints a new conversation owned by the caller, writes the `next_step_seed` as the first user message **as a prefilled draft** (see Decision 2a), returns `{conversation_id, seed_text}`. No Ada call is started server-side until the client confirms submission.

**Decision 2a — User reviews seed before send (security + UX).** Tapping the CTA does **not** auto-submit the seed to Ada. The client opens the chat with the seed prefilled in the composer; the user taps send. Applies identically to chat-seed chips in Decision 3. Rationale: the seed is model-generated from a user-uploaded image, so auto-submit is an image-mediated prompt-injection surface. Prefill + confirm closes that surface while preserving the tap-to-start feel. The user also sees "Ada suggested this question — edit or send" as microcopy above the composer on seed prefill.

**NudgeCard chrome.** With `trigger` gone, `NudgeCard` loses `nudgeLabel()` / `nudgeIcon()`. Replacement: static constant `POST_GLOWUP_LABEL = "After your glow-up"` + static icon (planning picks from existing theme set). No per-nudge icon variation.

**Novelty / anti-repetition (user requirement: "don't want same nudges every time").** Run repeated glow-ups for the same user must produce visibly different nudges — not paraphrases of the last one.

Two-layer defence:

1. **Prompt-side "don't repeat" block.** Keep `get_recent_nudge_context` (was scheduled for deletion — reinstated) and feed the **last 5** nudge rows for this user into `build_vision_nudge_prompt` as a "previously said, pick a different angle" section. The block lists each prior `{body, next_step.label, next_step.seed}`. The model is instructed to (a) pick a visibly different body subject than any prior body, (b) not reuse any prior CTA label verbatim, (c) not paraphrase a prior seed question.
2. **Storage-side uniqueness guard.** Before insert, compute `body_hash = sha256(lowercase(body))`. If a row exists for this `user_id` with the same `body_hash` within the last 30 days → drop the new row with a `advisor.nudge_duplicate_body` metric and log the collision for prompt tuning. Add a `body_hash VARCHAR(64) NOT NULL` column + a `(user_id, body_hash)` index on `advisor_nudges` to make the check cheap.

The prompt-side block is the normal path; the storage guard is the backstop for when the model ignores the instruction.

**Acceptance:**
- `POST /v1/advisor/nudges/{nudge_id}/next-step` returns `{conversation_id, seed_text}` for nudges owned by the caller; returns 404 on mismatch or unknown ID.
- Tapping a nudge CTA in `NudgeFeed` opens Ada chat with the seed **prefilled in the composer** + microcopy; the user taps send to start the conversation.
- Nudges without a `next_step` never persist (parse-fail drop). No card renders without a CTA.
- Vision-prompt golden test asserts the prompt asks for `body` + `next_step.{label, seed}`, includes the voice/tone guardrails, and the image-injection guard.
- Parse-drop rate metric wired and alerting threshold (15% rolling 200-call) documented.

### 3. Chat-open chips (new mobile surface)

When the user opens the Ada chat tab on an empty-conversation state, call a new endpoint (e.g. `GET /v1/advisor/chat-seeds`) that returns 2–3 one-line suggested questions the user could ask. The endpoint is backed by a single Haiku call using the **latest** completed glow-up + `style_profile`, same pattern as the nudge, but returning an array:

```json
{
  "seeds": [
    {"label": "Why does this angle work?", "text": "why did this angle land better than the front-on shot?"},
    {"label": "What to try next", "text": "what's one small change I should try in the next glow-up?"},
    {"label": "Hair color pairing", "text": "would a warmer hair color read better with this lipstick?"}
  ]
}
```

**Caching + rate limit + single-flight.**
- Cache key: `advisor:chat_seeds:{user_id}:{latest_glowup_id}`, TTL 24 h, value = the full seeds JSON.
- Per-user rate limit on cache-miss Haiku calls: **one call per user per hour**, enforced by a secondary Redis key `advisor:chat_seeds:cooldown:{user_id}` with 1 h TTL. Rate-limited requests return the most recent cached seeds for that user (even against a stale glow-up) rather than firing a fresh call.
- Single-flight: lock key `advisor:chat_seeds:lock:{user_id}:{latest_glowup_id}` with 30 s TTL so simultaneous tab-opens against a cold key produce one Haiku call, not N.

**Chip display contract (resolved).**
- Chip **displays `label`** (short, scannable, ≤ 24 chars).
- On tap, `text` is **prefilled in the composer** (Decision 2a) — not auto-submitted. User taps send.
- Max chips rendered: **3** per empty-state open; chat-tab never shows more than 3 chips at once.
- Seeded-chat CTA on a nudge card is subject to the same "only most recent 5 nudges show an active CTA" cap (older nudges render as read-only observations).

**Empty-state fallback (no completed glow-up yet).** Three fallback seeds fetched from a **remote-config endpoint** (`GET /v1/advisor/chat-seeds`; server returns fallback seeds when no glow-up exists) — kept server-side so copy iterates without an app store release. Mobile falls back to a hard-coded tuple only on network failure.

**Empty-conversation detection.** The client is the source of truth: the chip row renders when the current conversation has zero persisted messages. No new backend flag.

**Acceptance:**
- Chat tab with ≥1 completed glow-up and an empty conversation shows up to 3 tappable chips above the composer.
- Tapping a chip prefills the composer with `text` and focuses the input; user-initiated send triggers the normal `POST /v1/advisor/messages` path.
- Second tab-open with unchanged `latest_glowup_id` fires zero Haiku calls.
- Tab-open after a new glow-up fires exactly one chat-seeds Haiku call (subject to the 1 h per-user rate limit).
- Tab-open within the 1 h cooldown against a new glow-up returns cached seeds without a Haiku call.
- Simultaneous cold-key tab-opens (two devices, same user) produce exactly one Haiku call (single-flight lock).
- Chat tab with any conversation history renders as today — no chip row.
- Chat tab with no glow-ups shows the remote-config fallback seeds; tapping them prefills the composer; no Haiku call in that path.
- Feature gated via the capabilities module. No scattered `if`-checks.

### 4. Dormant-user re-engagement — **dropped pre-launch**

Originally: templated push to users inactive ≥14 d. **Cut from scope** because:
- The repo has no push-notification subsystem (no token table, no `expo-notifications` mobile integration, no worker push adapter). Building it is 3× the work of the rest of this PR.
- The app is pre-launch — there is no dormant-user cohort to re-engage with.
- Re-engaging dormant users before the app is live solves a non-problem.

If and when a push subsystem lands for other reasons (new-glow-up-ready pushes, friend activity, etc.), add a `send_dormant_push` cron as a follow-up PR. Until then: `TRIGGER_RE_ENGAGEMENT` is deleted from code per Decision 1 and nothing replaces it on this PR.

No acceptance criteria — nothing ships on this line item.

### 5. Delete-account scope

Every new surface landed by this change must sweep cleanly on `delete_account` (napkin rule 5). The current sweep at `app/api/auth.py:1518-1527` is a mixed list + single `scan_iter` pattern; new variable-suffix keys must be added as **wildcard `scan_iter` patterns**, not literal key deletes.

**Redis patterns to add to the sweep (all via `scan_iter` unless noted):**
- `advisor:chat_seeds:{user_id}:*` — seed cache per glow-up.
- `advisor:chat_seeds:cooldown:{user_id}` — per-user cache-miss cooldown (literal, not wildcard).
- `advisor:chat_seeds:lock:{user_id}:*` — single-flight locks.
- `advisor:nudge:post_glowup:{user_id}:*` — **pre-existing leak** (`_RAPID_RETRY_KEY_FMT` in `nudge_scheduler.py:81` is not in today's sweep). Fold in as part of this PR.

**Table-level cleanup:** `advisor_nudges` rows already cascade on `user_id` — no change needed.

**Acceptance:** `delete_account` integration test asserts all four Redis key prefixes are gone post-delete, including the pre-existing rapid-retry key.

## Cleanup (delete in place, this PR only)

All deletions happen in the same PR as the new contract. No "phase 1 / phase 2," no feature flag, no keep-for-now comments.

**Backend code**
- `app/advisor/nudge_eligibility.py` — delete the whole file; no eligibility scans remain.
- `app/advisor/nudge_policy.py` — drop `TRIGGER_POST_ANALYSIS`, `TRIGGER_WEEKLY_CHECKIN`, `TRIGGER_MILESTONE`, `TRIGGER_RE_ENGAGEMENT`, `MILESTONE_COUNTS`, `WEEKLY_CHECKIN_DAYS`, `RE_ENGAGEMENT_DAYS`. Keep only the constants the one remaining path uses.
- `app/advisor/nudge_templates.py` — drop `NUDGE_PROMPTS` and `get_prompt`. **Keep** `_render_recent_nudges_block` (novelty/dedup block is now a product requirement — see Decision 2 Novelty section). Rewrite `build_vision_nudge_prompt` to the new `{body, next_step.{label, seed}}` contract and the stronger anti-repetition instructions.
- `app/advisor/nudge_scheduler.py` — delete `_generate_generic_nudge`, `_VISION_TRIGGERS` (single path now), `schedule_post_analysis_nudge`, `check_nudge_eligibility`, `_dispatch`, and the post-analysis insight scaffolding. Collapse `generate_nudge` to the single vision path. `_parse_vision_nudge_json` becomes `_parse_nudge_json` returning the new shape. Add body-hash dedup check + `advisor.nudge_duplicate_body` metric before insert.
- `app/worker_settings.py` — deregister `schedule_post_analysis_nudge` and `check_nudge_eligibility`; remove the cron entry. No new cron registered (dormant push deferred).
- `app/api/advisor.py` / `app/api/analyses.py` (or wherever the post-analysis enqueue lives) — delete the enqueue call; nothing replaces it.
- `app/repositories/advisor_repo.py` — delete `get_all_goal_user_ids`, `get_user_ids_with_nudge_since`, `count_insights_by_user`, `get_all_insights_with_timestamps`. **Keep** `get_recent_nudge_context` (needed for the novelty block). Add `get_latest_completed_glowup_id` for the chat-seed cache key and `find_duplicate_body` for the storage-side dedup guard.
- `app/api/advisor.py` — add `GET /v1/advisor/chat-seeds` and `POST /v1/advisor/nudges/{nudge_id}/next-step`.

**Database**
- `advisor_nudges`: `TRUNCATE` pre-launch (zero prod data). Drop columns `observation_tag`, `trigger`. Add columns: `next_step_label VARCHAR(24) NOT NULL`, `next_step_seed VARCHAR(140) NOT NULL`, `body_hash VARCHAR(64) NOT NULL`. Add `VARCHAR(160)` constraint to `body`. Create index `ix_advisor_nudges_user_body_hash (user_id, body_hash)` for the duplicate-body check. If `trigger` has FK references elsewhere, those go too.
- Drop any `advisor_nudge_focus` / topic-rotation tables if they still exist from the pre-Unit-8 era.

**Tests**
- Delete: `tests/test_advisor_nudge_post_analysis_grounded.py`, `tests/test_advisor_vision_nudge.py` (replaced by the new-contract variant), any eligibility-scan tests.
- Update: `tests/test_advisor_nudge_post_glowup.py` to the new contract (`{body, next_step}`), including novelty-block presence + body-hash dedup path; worker-settings test to reflect the new cron list (no new crons added).
- New: chat-seed endpoint test (cache hit / miss / rate-limit / single-flight / remote-config fallback); nudge-CTA handoff endpoint test (ownership 404, prefill contract); body-hash dedup test (insert-then-retry identical body → dropped + metric emitted); mobile chip-row integration test (label render + prefill, no auto-send).

**Mobile**
- `mobile/components/advisor/NudgeCard.tsx` — add CTA chip row; remove any `observation_tag` rendering.
- `mobile/components/advisor/NudgeFeed.tsx` — no shape changes beyond the new `next_step` field on `Nudge`.
- `mobile/lib/advisor.ts` — update `Nudge` type: drop `observation_tag`, add `next_step`; add `fetchChatSeeds()`.
- New: `ChatSeedChips.tsx` mounted above the composer on empty-conversation state.
- `mobile/constants/config.ts` — drop any legacy nudge trigger enums if present.

**Env / config**
- Drop `ADVISOR_POST_GLOWUP_RAPID_RETRY_MINUTES` if it was only used by the rapid-retry guard and no longer applies (or keep if the guard stays — planning calls it). Drop `ADVISOR_MILESTONE_DEDUP_HOURS`, `ADVISOR_NUDGE_RECENT_CONTEXT_LIMIT`. Update `.env.example` and any other env-example files the napkin requires.

**Docs**
- Delete or update `docs/plans/2026-04-17-003-fix-advisor-context-aware-plan.md` sections that describe the removed triggers (planning call — either mark superseded by this brainstorm or excise the dead sections).
- Update `app/features/README.md` if it lists advisor nudges by trigger.

## Success criteria

Pre-launch we cannot measure production impact, so these are observable via local runs + logged metrics:

**Value metrics (primary):**
1. **Nudge CTA tap-through** — instrumented on the nudge CTA tap; reported in `advisor.payload_logger` with `event=nudge_cta_tapped`. Baseline established on TestFlight; target set after first week of data.
2. **Seed submission rate** — of prefilled seeds (both nudge CTA and chat-seed chips), percent actually sent to Ada. Instrumented as `event=seed_sent` with source tag.
3. **Parse-drop rate** — rolling 200-call window on `advisor.nudge_parse_drop`; alerts over 15%.

**Correctness metrics:**
4. **Every persisted nudge is actionable.** 100% of `post_glowup` rows have non-null `next_step_label` and `next_step_seed` (rows without are dropped pre-insert).
5. **Cost is bounded.** `advisor.payload_logger` entries with `purpose=vision_nudge` ≤ count of completed glow-ups in the session; `purpose=chat_seeds` ≤ 1 per user per hour and ≤ count of new glow-ups in the session.
6. **Feed-to-chat handoff works.** Tapping a nudge CTA lands in Ada chat with the seed prefilled in the composer (not auto-sent), verified by a mobile integration test.
7. **Chat open without glow-up fires exactly one call** to the fallback-seeds endpoint and zero Haiku calls, verified by network log.
8. **Novelty holds.** Running 5 back-to-back glow-ups for the same user against the same reference photo yields 5 distinct nudge bodies (no exact hash collision, no verbatim CTA label repeats) — verified by a scripted integration test.

**Security metrics:**
9. **IDOR gate.** Integration test: user A cannot call `/nudges/{id}/next-step` for a nudge owned by user B — 404 returned.
10. **Rate limit.** Simulated burst of 10 simultaneous chat-seed cache-miss requests from one user produces exactly 1 Haiku call.

## Open questions (for planning)

1. *(Resolved — push subsystem out of scope; Decision 4 cut.)*
2. *(Resolved — Decision 2a: seeds are prefilled, not auto-sent; user reviews before submit. Length + shape validated server-side; seeds must end in `?`. Image-injection guard added to vision prompt.)*
3. *(Resolved — chat-seed empty-conversation detection is client-side: chip row renders iff the current conversation has zero persisted messages.)*
4. *(Resolved — same as #3.)*
5. *(Resolved — `observation_tag` retired.)*
6. **Parse-drop baseline.** Alert threshold is 15% rolling-200-call, but we have no baseline for the new 3-field nested JSON on Haiku. Planning runs a 100-call synthetic benchmark against real glow-ups and reports the observed drop rate; if materially higher than 5%, revisit contract (e.g. split into two calls).
7. **Novelty-block size.** Feeding last 5 nudge rows is a starting number. If prompt cost climbs or dedup still feels weak after TestFlight, planning can tune (3 rows lighter, 8 rows stricter) without changing the contract.

## Resolved scope calls (from document review)

- **One PR, all at once.** No split, no phase 1 / phase 2. All decisions below ship together.
- **Decision 3 chips + Decision 2 nudge consolidated where it makes sense.** `GET /v1/advisor/chat-seeds` still exists (separate surface), but the post_glowup nudge Haiku call and the chat-seeds Haiku call both draw from the same shared "stable facts + latest glow-up image" context. The per-user 1h rate limit keeps total cost bounded regardless.
- **Decision 4 (push) is cut from this PR.** Pre-launch, no push subsystem exists, no dormant users exist. Picked up in a later PR if/when push lands for other reasons.
- **Milestone push also cut** for the same reason.
- **Identity framing owned explicitly:** Ada is a response-to-action advisor on this surface, not an ambient companion. That is the product position for v2.

## Risks

- **Mobile ↔ backend shape drift** (napkin rule, recurring P0 pattern): `next_step`, `body_hash`, and `seeds` touch two endpoints + the mobile `Nudge` type. Ports + tests must ship in the same PR.
- **Silent-Ada window.** With all non-glow-up triggers cut, a user who signs up and doesn't complete a glow-up sees no nudges ever. The remote-config fallback chips carry the whole new-user experience on the Ada tab. Copy iteration budget needs to be real — a dull fallback is the new activation bottleneck.
- **Body-hash dedup is too strict.** Two genuinely different observations could collapse to the same lowercased body by coincidence. Start with a 30-day window; if we see > 1% false-positive drops in metrics, shorten the window or switch to a fuzzier similarity check.
- **Novelty still fails at high volume.** A user running 20+ glow-ups of visually similar outputs may exhaust plausible angles. Accept that after the last 5 rows are all about the same face, the model will paraphrase — the hash guard catches verbatim repeats but not thematic ones. Not a fix for this PR; revisit if we see the pattern.

## Out of scope (deferred)

- Per-nudge thumbs-up / thumbs-down feedback.
- Push notification subsystem (tokens, Expo integration, worker adapter) — deferred until there's a real driver for pushes.
- Dormant-user re-engagement (any channel) — deferred with the push subsystem.
- Milestone reinforcement pushes — same.
- Prompt variants / server-side A/B.
