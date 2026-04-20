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

- Cut Haiku nudge spend to **one call per real user action** (a completed glow-up), down from five trigger paths.
- Make every generated nudge **actionable** — each one carries a next step the user can tap into.
- Give the chat surface its own dynamic entry points (**chat-open chips**) so the Ada tab is useful to users who never read the nudge feed.
- Close the dormant-user gap with a **templated, non-AI push** path rather than a Haiku call.

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
  "body": "<one warm sentence about the new look>",
  "observation_tag": "<1-3 words>",
  "next_step": {
    "label": "<short CTA copy, ≤ 24 chars>",
    "seed": "<one-sentence chat seed Ada will answer when tapped>"
  }
}
```

Prompt update in `build_vision_nudge_prompt`: after the existing observation sentence + tag, ask the model for one suggested next step the user could ask Ada about. The seed is a question in the user's voice (e.g. *"what makeup would play up this cheekbone shadow?"*) — not an instruction to Ada.

Storage: on `advisor_nudges` — add `next_step_label` and `next_step_seed` as `NOT NULL` columns and drop `observation_tag`, `trigger`, and any other columns that only existed to serve removed triggers. Pre-launch → wipe the table in place; no backfill, no nullable shim, no dual-contract window. Parse failure on `next_step` → drop the nudge pre-insert (same policy as malformed body today). No observation-only fallback path exists in code.

**Acceptance:**
- `POST /v1/advisor/nudges/{id}/next-step` (or equivalent — naming in planning) returns `{seed, conversation_id}` where the seed has been injected as the user's first chat message.
- Tapping a nudge with a `next_step` in `NudgeFeed` shows a CTA chip under the body; tapping the chip opens Ada chat with the seed already sent and Ada's reply loading.
- Nudges without a `next_step` (none in normal operation, only error-path rows if any slip through) render as today — no chip, tap opens the detail sheet only.
- Vision-prompt golden test updated to assert the prompt asks for all three fields.

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

Caching: server caches the last seed set per user keyed by `(user_id, latest_glowup_id)` in Redis for 24 h. Opening the tab when the key is warm returns cached seeds — zero Haiku spend. Only a fresh glow-up (new latest) or cache expiry triggers a new call.

Empty-state fallback (no completed glow-up yet): three static, non-AI seeds hard-coded in mobile (e.g. *"what should I try first?"*, *"how does Ada work?"*, *"can I upload a photo to start?"*). No backend call in that state.

**Acceptance:**
- Chat tab with at least one completed glow-up and an empty conversation shows a row of 2–3 tappable chips above the composer.
- Tapping a chip submits its `text` as the user's first message and starts the chat.
- Second tab-open within 24 h of the same glow-up fires zero additional Haiku calls (observed via `advisor.payload_logger`).
- Chat tab with conversation history (any message) renders as today — no chip row.
- Chat tab with no glow-ups shows the static fallback chips; tapping them still starts a chat; no backend call.
- Feature gated via the capabilities module (same gate as advisor today). No scattered `if`-checks.

### 4. Dormant-user re-engagement moves off Haiku

Dormant users (no activity ≥14 d, matching the old `RE_ENGAGEMENT_DAYS` threshold) get one push notification per dormancy window, copy drawn from a **static rotation of 3–5 templates** bundled in the worker. No AI call.

- Scheduler: a lightweight ARQ cron (`send_dormant_push`) scans users with push tokens whose latest activity is outside the window and who haven't received a dormant push in the same window. Idempotent per user per window.
- Templates live in `app/advisor/dormant_templates.py` as a tuple of strings picked by `hash(user_id) % len(templates)` so a given user sees the same template across retries but different users get variety.
- Pushed only if the user has opted in to push; otherwise skipped silently.
- No row written to `advisor_nudges` — this is not a nudge, it is a push. The user does not see a card on the feed.

**Acceptance:**
- A dormant user with a push token receives exactly one templated push within 24 h of hitting the threshold.
- The same user does not receive a second dormant push inside the same 14-day window.
- No Haiku call is made by this path.
- Users without push tokens are skipped; no retry, no fallback to a feed-only nudge.

### 5. Delete-account scope

Every new surface landed by this change must sweep cleanly on `delete_account` (napkin rule 5). The relevant surfaces:

- `advisor_nudges` rows — already wired; new columns travel with the row and need no extra cleanup.
- Redis seed cache `advisor:chat_seeds:{user_id}:{glowup_id}` — new; added to the delete-account flow's Redis-sweep step.
- Dormant-push dedup key `advisor:dormant_push:{user_id}:{window}` — new; added to the same sweep.

**Acceptance:** `delete_account` integration test asserts both new Redis key prefixes are gone post-delete.

## Cleanup (delete in place, this PR only)

All deletions happen in the same PR as the new contract. No "phase 1 / phase 2," no feature flag, no keep-for-now comments.

**Backend code**
- `app/advisor/nudge_eligibility.py` — delete the whole file; no eligibility scans remain.
- `app/advisor/nudge_policy.py` — drop `TRIGGER_POST_ANALYSIS`, `TRIGGER_WEEKLY_CHECKIN`, `TRIGGER_MILESTONE`, `TRIGGER_RE_ENGAGEMENT`, `MILESTONE_COUNTS`, `WEEKLY_CHECKIN_DAYS`, `RE_ENGAGEMENT_DAYS`. Keep only the constants the one remaining path uses.
- `app/advisor/nudge_templates.py` — drop `NUDGE_PROMPTS`, `get_prompt`, `_render_recent_nudges_block` (no more dedup block), and the recent-nudge / observation-tag scaffolding in `build_vision_nudge_prompt`. Rewrite the prompt for the new three-field contract.
- `app/advisor/nudge_scheduler.py` — delete `_generate_generic_nudge`, `_VISION_TRIGGERS` (single path now), `schedule_post_analysis_nudge`, `check_nudge_eligibility`, `_dispatch`, and the post-analysis insight scaffolding. Collapse `generate_nudge` to the single vision path. `_parse_vision_nudge_json` becomes `_parse_nudge_json` returning the three-field shape.
- `app/worker_settings.py` — deregister `schedule_post_analysis_nudge` and `check_nudge_eligibility`; remove the cron entry. Register the new `send_dormant_push` cron.
- `app/api/advisor.py` / `app/api/analyses.py` (or wherever the post-analysis enqueue lives) — delete the enqueue call; nothing replaces it.
- `app/repositories/advisor_repo.py` — delete `get_all_goal_user_ids`, `get_user_ids_with_nudge_since`, `count_insights_by_user`, `get_all_insights_with_timestamps`, `get_recent_nudge_context` (no longer needed — no dedup block). Add `get_latest_completed_glowup_id` for the chat-seed cache key.
- `app/advisor/dormant_templates.py` — new file, static template tuple.
- `app/api/advisor.py` — add `GET /v1/advisor/chat-seeds` and the nudge-CTA handoff endpoint.

**Database**
- `advisor_nudges`: `TRUNCATE` pre-launch (zero prod data), drop `observation_tag` and `trigger` columns, add `next_step_label TEXT NOT NULL`, `next_step_seed TEXT NOT NULL`. If `trigger` has FK references elsewhere, those go too.
- Drop any `advisor_nudge_focus` / topic-rotation tables if they still exist from the pre-Unit-8 era.

**Tests**
- Delete: `tests/test_advisor_nudge_post_analysis_grounded.py`, `tests/test_advisor_vision_nudge.py` (replaced by the new-contract variant), any eligibility-scan tests.
- Update: `tests/test_advisor_nudge_post_glowup.py` to the three-field contract; worker-settings test to reflect the new cron list.
- New: chat-seed endpoint test (cache hit / miss / empty-glowup fallback), dormant-push cron test, mobile chip-row integration test.

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

1. **Call-count reduction.** Per-user, per-week: Haiku nudge calls drop from up to `3 analysis + 3 glowups + 1 weekly = 7` in a busy week to `≤ glow-ups completed` + `≤ 1 chat-seed refresh per new glow-up`. Verified by counting `advisor.payload_logger` entries with `purpose ∈ {vision_nudge, chat_seeds}` over a scripted session.
2. **Every generated nudge is actionable.** 100% of `post_glowup` nudges persisted have non-null `next_step_label` and `next_step_seed` (else the row is dropped pre-insert per the parse-failure policy).
3. **Feed-to-chat handoff works.** Tapping a nudge CTA lands in Ada chat with the seed already sent, verified by a mobile integration test.
4. **Chat open without glow-up fires zero backend calls.** Verified by network log during an empty-glow-up cold start.
5. **Dormant push is AI-free.** Code review confirms `send_dormant_push` makes no LLM calls.

## Open questions

These go into planning, not brainstorming:

1. **Push rate limit.** Do we already have a per-user push rate limit? If not, dormant push + post-glow-up nudge push (if the latter pushes today — not verified on HEAD) could stack. Planning must check the push service and decide stacking policy.
2. **`next_step_seed` safety.** Seeds are model-generated user-voice questions injected as the first chat turn. Planning needs to confirm Ada's chat-request validation treats them as ordinary user input (no special path that trusts them more).
3. **Chat-seed cold start.** Very first glow-up of a brand-new user: is the latest-glow-up data available within the same transaction as the chat-tab open, or is there a race where the user opens the chat tab a few seconds after the glow-up finishes? Planning picks either "poll once" or "show fallback chips until first-ever nudge enqueues."
4. **Mobile empty-conversation detection.** Is "empty conversation" a backend flag or derived client-side? Planning wires the chip row to whichever source of truth already exists; no new flag introduced.
5. *(Resolved — `observation_tag` retired. See Cleanup.)*

## Risks

- **Mobile ↔ backend shape drift** (napkin rule, PR #190-ish pattern): `next_step` and `seeds` are new response shapes on two endpoints; their ports + tests must ship in the same PR.
- **Loss of marketing drip.** Removing weekly_checkin / milestone eliminates the "Ada sends you something" loop for users who don't glow up often. The dormant push partially replaces it but is less warm. Accept this — the removed nudges were low-value, and push is the right channel for passive drip anyway.
- **Empty glow-up history = empty Ada tab.** A new user who hasn't finished their first glow-up sees the static fallback chips and no nudges. Copy on the fallback chips must be inviting enough that this state still reads as "Ada is ready" not "Ada is empty." Planning writes the exact strings.

## Out of scope (deferred)

- Per-nudge thumbs-up / thumbs-down feedback.
- Multi-seed push (bundling > 1 dormant template into a richer card).
- AI-generated push copy (intentionally avoided — the whole point of Decision 4 is to keep it free).
- Bringing back milestone-shaped pushes (e.g. "you've done 5 glow-ups") — if we want that later, it's a push template, not a Haiku nudge.
