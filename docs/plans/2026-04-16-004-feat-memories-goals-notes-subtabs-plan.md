---
title: "feat: Memories tab — Goals / Notes subtabs"
type: feat
status: active
date: 2026-04-16
deepened: 2026-04-16
origin: docs/brainstorms/2026-04-16-memories-goals-notes-subtabs-requirements.md
---

# feat: Memories tab — Goals / Notes subtabs

## Overview

Replace the single flat memory list + in-composer Goal/Note chip picker with two top-level subtabs (Goals · Notes), each with an independent input draft and a list filtered to user-authored memories of that type only. Ada's internal memories (`analysis_insight`, `accepted_suggestion`, `dismissed_suggestion`) are hidden from both tabs while remaining in the DB to feed advisor context and nudges.

## Problem Frame

Current UX has three pain points (see origin):
1. Draft text carries across Goal↔Note chip flips because a single `content` state backs both — switching the chip carries whatever was typed along with it.
2. Insights/Accepted/Dismissed crowd the list (one currently renders as a raw JSON blob).
3. Classifying every added memory as "Goal" vs "Note" puts cognitive load on the user even though the distinction is really about stickiness (GOAL is cap-exempt and weighted higher during retrieval in `app/advisor/memory_manager.py:40,182`).

Note: the existing `TypeChips` component already sits *above* the `FlatList` in `mobile/components/advisor/MemoryList.tsx` (lines 517, 532) — not inside `AdvisorComposer`. The change here is a semantic one (flip the chips from "composer type picker" to "list filter + per-tab composer binding"), not a relocation.

The user picked subtabs with independent inputs and hiding system-authored memories entirely (see origin).

## Requirements Trace

- **R1** — Two subtabs (Goals · Notes) at the top of the Memories tab; no chip inside the composer (origin §Decisions).
- **R2** — Each tab has its own session-scoped composer draft that is preserved when switching tabs and cleared on successful send (origin §Inputs).
- **R3** — Goals tab lists only `type=goal` rows; Notes tab lists only `type=user_note` rows; insights/accepted/dismissed never render in either tab (origin §List rendering, §What's hidden).
- **R4** — Default tab on first open: Goals. Subsequent opens within a session: last-used tab (origin §Shape).
- **R5** — Per-tab empty state text (origin §List rendering).
- **R6** — Swipe-to-delete, row timestamp, keyboard offset all still work (origin §Success criteria 5).
- **R7** — `ruff`/`pytest`/`expo lint` suites stay green (origin §Success criteria 7).

## Scope Boundaries

- No AI auto-classification of Goal vs Note.
- No "Pin to keep forever" reframing.
- No dedicated "Ada memories" tab this release.
- No draft persistence across app restarts.
- No search/sort/bulk actions.
- No data migration — hiding system-authored memories is done by the request-time type filter, not a DB change.
- No change to cap eviction policy (GOAL remains cap-exempt).

### Deferred to Separate Tasks

- Mobile memory-list pagination wiring — the backend has been paginated since day one but `fetchMemories()` in `mobile/lib/advisor.ts` currently fetches a single page and ignores `next_cursor` / `has_more`. Adding true infinite scroll is orthogonal to subtabs and tracked separately.
- A "What Ada knows about me" screen for inspecting system-authored memories.

## Context & Research

### Relevant Code and Patterns

- `mobile/components/advisor/MemoryList.tsx` — main surface. Contains `TypeChips` (the composer-level chip picker being removed), `SwipeableMemoryRow`, `useAdvisorComposerLayout`, and state for `content` / `selectedType`.
- `mobile/components/advisor/AdvisorComposer.tsx` — shared composer component reused on chat + memories tabs; unchanged by this plan.
- `mobile/lib/advisor.ts` — typed API client. `fetchMemories`, `addMemory`, `deleteMemory`.
- `mobile/constants/config.ts` — `ADVISOR_ENDPOINTS.MEMORIES`.
- `app/api/advisor.py` — `list_memories` handler (line 363) + `add_memory` (316) + `delete_memory` (404).
- `app/advisor/service.py` — `AdvisorService.list_memories_page` (line 415). Does **not** currently accept a `type_filter` kwarg; repo does.
- `app/repositories/advisor_repo.py` — `get_memories_page(..., type_filter=None)` (line 300) already accepts a type filter and applies it as `.eq("type", type_filter)` (line 319–320).
- `app/advisor/models.py` — `MemoryListPageResponse` (line 106).

### Institutional Learnings

- All pagination must be **infinite scroll** (not a "load more" button) per `CLAUDE.md` convention. The current `MemoryList` does not paginate; this plan does not add pagination (deferred) but keeps the door open — client types should be widened so a follow-up can wire `next_cursor`.
- **Feature gating** lives in `useCapabilities()` (mobile) and `require_app_feature()` (backend) per `app/features/README.md`. Memories CRUD is tier-open; no gating touched here.
- **No magic strings**: tab values (`"goal"` / `"user_note"`) must come from the existing `MemoryType` union, not hard-coded strings.
- **Pre-launch destructive OK** — DB has no real user data to preserve, but nothing destructive is required by this plan anyway.

### External References

None — codebase has strong local patterns for React Native tab chips (existing `TypeChips` component, profile tabs); no external research warranted.

## Key Technical Decisions

- **Server-side type filter (not client-side).** Add `?type=` query param to `GET /v1/memories`; pipe it through the service to the repo's existing `type_filter` arg. Rationale: hides system-authored rows at the data layer so the wire payload is already clean, and lets the follow-up pagination work just add a `cursor` param without changing the tab wiring. Client-side filtering would overfetch and pay for rows the user can never see.
- **Param type is `Literal["goal", "user_note"] | None`.** Using the full `MemoryType` enum would let callers ask for `analysis_insight`/`accepted_suggestion`/`dismissed_suggestion` (all valid enum values) and silently bypass the UX-level hiding of Ada memories. A two-value `Literal` gives FastAPI free 422 rejection on anything else, matches the High-Level Design diagram, and keeps the `MemoryType` enum free for internal use. Mirrors the explicit two-value check already used by `add_memory` (`app/api/advisor.py:328-337`).
- **Two subtabs only, no "All".** Goals and Notes only — matches the origin decision to hide Ada memories. Visually the row is rendered as a **chip pair** (not a full tab bar) to stay consistent with the existing `TypeChips` look; the component is called `SubTabs` semantically but styled as chips. Throughout this doc "subtabs" and "the chip pair" refer to the same element.
- **Per-tab drafts, per-tab `error`, per-tab `isAdding`.** Submitting a Goal must not lock the Notes composer; a failed Goals fetch must not paint a "Could not load" overlay on top of Notes. Keep three isolated sub-states: `goalDraft / noteDraft`, `goalError / noteError`, `goalAdding / noteAdding` (or, equivalently, two `{draft, error, isAdding}` records keyed by tab — implementer's choice).
- **Default tab = Goals; last-used tab persists via a ref.** Expo Router's bottom-tab navigator keeps `MemoryList` mounted across tab visits (default `lazy: false` on this project), so the ref survives switches between the app's top-level tabs. It does reset on full app restart — accepted tradeoff per origin.
- **No full-screen skeleton on tab-switch refetch.** The initial-mount skeleton (`isLoading` true) stays. On tab change, keep the previous list rendered and show a subtle list-area indicator (e.g., `ActivityIndicator`) while the new type's fetch resolves. Avoids the jarring full-screen collapse on every tap.
- **Remove the row type-label text, keep the icon container.** The flag / doc icon gives the card a visual anchor on the left; removing it reflows the whole row. Drop only the `"Goal" / "Note"` label text beside the timestamp — each tab's content is uniform so the textual label is the redundant chrome.
- **Backend defaults `type=None`** to preserve any existing consumer (no other caller of `GET /v1/memories` besides mobile, verified via grep). The mobile client always passes the active type, so the unfiltered path effectively dies on this surface.

## Open Questions

### Resolved During Planning

- **Server-side vs client-side filter** → server-side. See decisions.
- **Default-tab persistence** → session-only, no AsyncStorage.
- **Counts in tab labels** (e.g., "Goals (3)") → not v1. Evaluate after ship.
- **What happens to existing analysis_insight rows that were previously visible** → nothing; they remain in DB and are hidden by the server filter.

### Deferred to Implementation

- Whether to memoize the filtered fetcher via a key derived from `activeTab` so `useCallback` dependencies stay clean (pure hook hygiene decision).
- Whether swipe-delete confirmation that's left open during a tab switch should dismiss the Alert or keep it — minor edge; accept current `Alert.alert` behavior unless QA flags it.

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification. The implementing agent should treat it as context, not code to reproduce.*

```
┌────────────────────────── MemoryList.tsx ───────────────────────────┐
│ state: {                                                             │
│   activeTab: "goal" | "user_note",                                   │
│   memories:  UserMemory[],                     (for active tab)      │
│   byTab: {                                                           │
│     goal:      { draft: string, error: string|null, isAdding: bool },│
│     user_note: { draft: string, error: string|null, isAdding: bool },│
│   },                                                                 │
│   initialLoading: bool,                        (skeleton on mount)   │
│   refetching:     bool,                        (subtle spinner)      │
│ }                                                                    │
│                                                                      │
│ ┌─ SubTabs — styled as chip pair ──────────────┐                     │
│ │ [ ⚑ Goals ]  [ 📝 Notes ]                    │  setActiveTab(t)    │
│ │  role=tab    role=tab                         │       │             │
│ │  container role=tablist                       │       │             │
│ └──────────────────────────────────────────────┘       │             │
│                                                         │             │
│   onTabChange(t):                                       │             │
│     • setActiveTab(t)                                   │             │
│     • refetching=true; fetchMemories({type: t}) ────────┘             │
│     • composer binds to byTab[t].draft                               │
│                                                                      │
│ ┌─ FlatList (current tab only) ────────────────┐                     │
│ │ SwipeableMemoryRow × N                       │                     │
│ │   (icon container kept; type-label dropped)  │                     │
│ │   refetching ? <ActivityIndicator/> overlay  │                     │
│ └──────────────────────────────────────────────┘                     │
│                                                                      │
│ ┌─ AdvisorComposer ────────────────────────────┐                     │
│ │ key           = activeTab                    │  ← forces remount   │
│ │ value         = byTab[activeTab].draft       │    to clear         │
│ │ disabled      = byTab[activeTab].isAdding    │    internal height  │
│ │ placeholder   = per-tab                      │                     │
│ │ a11yLabel     = "Goal content" | "Note content"                    │
│ │ onSubmit: addMemory(activeTab, {text})       │                     │
│ │           then clear only byTab[t].draft     │                     │
│ └──────────────────────────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────────┘

                 │                                    ▲
                 │ GET /v1/memories?type=…            │ POST /v1/memories
                 ▼                                    │
┌──────────────────────────── backend ────────────────┴────────────────┐
│ list_memories(type: Literal["goal","user_note"] | None = None, …)    │
│   → svc.list_memories_page(user_id, type_filter=type, …)             │
│     → repo.get_memories_page(..., type_filter=type_filter)  (exists) │
└──────────────────────────────────────────────────────────────────────┘
```

## Implementation Units

- [ ] **Unit 1: Backend — `type` query param on list memories**

**Goal:** Teach `GET /v1/memories` and its service layer to filter by memory type, reusing the repo's existing `type_filter` support.

**Requirements:** R3

**Dependencies:** None

**Files:**
- Modify: `app/api/advisor.py` (handler `list_memories`)
- Modify: `app/advisor/service.py` (`AdvisorService.list_memories_page`)
- Test: `tests/test_advisor_memories_type_filter.py` (new)

**Approach:**
- Add a `type: Literal["goal", "user_note"] | None = Query(None)` param on `list_memories`. FastAPI auto-validates against the two allowed values and returns 422 for anything else — no manual guard needed. Using the full `MemoryType` enum here would admit `analysis_insight`/`accepted_suggestion`/`dismissed_suggestion` as valid values and let a caller bypass the "hide Ada memories" UX contract; keep the enum for internal use only on this endpoint.
- Plumb `type_filter=type` (already a plain string when present) into `svc.list_memories_page`.
- Extend `list_memories_page` signature with `type_filter: str | None = None`; pass through to `repo.get_memories_page`.
- Leave `type_filter=None` behaving exactly as today (unfiltered) so any latent caller is unaffected.

**Patterns to follow:**
- Query param typing follows `cursor: str | None = Query(None, …)` already on the same handler.
- Service layer kwargs mirror repo kwargs one-to-one (see `list_memories_page` body).

**Test scenarios:**
- Happy path — `GET /v1/memories?type=goal` returns only goal-type rows (seed 2 goals + 1 note + 1 insight; expect 2).
- Happy path — `GET /v1/memories?type=user_note` returns only user_note rows (expect 1 from the seed).
- Edge case — `GET /v1/memories` with no `type` param returns all types, unchanged from today.
- Error path — `GET /v1/memories?type=analysis_insight` returns **422** (FastAPI's auto-validation of `Literal["goal", "user_note"]`).
- Error path — `GET /v1/memories?type=bogus` returns 422.
- Edge case — `GET /v1/memories?type=goal&cursor=...` composes correctly with the existing cursor path (pass a known cursor, expect the next page to respect both constraints).
- Integration — the returned pagination envelope (`next_cursor`, `has_more`) remains well-formed when a filtered query exhausts its rows.

**Verification:**
- New pytest file passes; existing `tests/test_advisor_*` suite stays green; `make lint` clean.

---

- [ ] **Unit 2: Mobile API client — widen types and accept `type` / `cursor`**

**Goal:** Update `mobile/lib/advisor.ts` so the client passes a type filter on list and exposes the paginated response shape (even though pagination wiring is deferred).

**Requirements:** R3

**Dependencies:** Unit 1

**Files:**
- Modify: `mobile/lib/advisor.ts`

**Approach:**
- Extend `fetchMemories(opts?: { type?: "goal" | "user_note"; cursor?: string })` (options object to keep call sites readable).
- Build the URL with `URLSearchParams` mirroring `fetchMessages` / `fetchNudges`.
- Change `MemoriesResponse` to match the backend envelope: `{ memories, next_cursor: string | null, has_more: boolean }`. This is a breaking type change for `MemoryList` (sole caller) — Unit 3 updates the consumer.
- Do not add a pagination hook here — the goal is to align types, not wire infinite scroll.

**Patterns to follow:**
- `fetchMessages` (same file) for the URLSearchParams + optional cursor idiom.

**Test scenarios:**
- None at the client-library level — this file has no unit tests today. Type correctness is validated by Unit 3's consumer and `tsc`.

**Verification:**
- `cd mobile && npx tsc --noEmit` passes.
- `cd mobile && npx expo lint` clean.

---

- [ ] **Unit 3: Mobile — subtabs, per-tab state, and list refetch**

**Goal:** Flip the existing `TypeChips` (which already sits above the `FlatList`) from a composer type-picker into a subtab switcher: per-tab drafts, per-tab error/isAdding, active-tab-scoped fetch, and list filtered by type via the new server-side param.

**Requirements:** R1, R2, R3, R4, R5, R6

**Dependencies:** Unit 2

**Files:**
- Modify: `mobile/components/advisor/MemoryList.tsx`
- (optional) Create: `mobile/components/advisor/MemorySubTabs.tsx` — only if extracting the chip pair makes the diff clearer; inline in `MemoryList` is acceptable.

**Approach:**
- Repurpose the current `TypeChips` row (already above the `FlatList`): rename semantically to `SubTabs`, keep the position, and reuse the pill chip styling (`activeBg`, `border`, `THEME.radius.pill`, `PressableScale`). Match the existing `paddingHorizontal: THEME.spacing.md`; do not make the row sticky (v1).
- State shape (see High-Level Technical Design):
  - `activeTab: "goal" | "user_note"` (default `"goal"`)
  - `byTab: { goal: {draft, error, isAdding}, user_note: {draft, error, isAdding} }` — per-tab so one tab's failure or in-flight submit never bleeds into the other.
  - `memories: UserMemory[]` — always the active tab's current page (no need to cache per tab in v1).
  - `initialLoading: boolean` — true only on first mount; drives the `MemorySkeleton`.
  - `refetching: boolean` — true while a tab-switch fetch is in flight; drives a list-area `ActivityIndicator`, **not** the full-screen skeleton.
- Composer binding: `value = byTab[activeTab].draft`; `disabled = byTab[activeTab].isAdding`. Pass `key={activeTab}` to `AdvisorComposer` so its internal height state resets cleanly on tab switch (prevents a long note's expanded height from bleeding into a shorter goal draft).
- Placeholder is tab-scoped (per origin Decisions §Inputs): Goals → `"e.g. Grow out my hair to shoulder length"`; Notes → `"e.g. I prefer minimal jewelry"`.
- `accessibilityLabel` on `AdvisorComposer` is tab-scoped: `"Goal content"` / `"Note content"`. Submit a11y label stays `"Add memory"`.
- On tab change: `setActiveTab(t)`; set `refetching = true`; call `fetchMemories({ type: t })` (from Unit 2); on resolve, write `memories` and clear `refetching`. Do **not** clear drafts on tab switch — that's the whole point.
- On successful `addMemory`: clear only `byTab[activeTab].draft` and prepend the new row to `memories`. Leave the other tab's draft intact.
- On `addMemory` error: set `byTab[activeTab].error`, surface via `showToast` (existing pattern), leave the draft intact so the user can retry.
- Empty state per tab (inside the list area — SubTabs stay visible and interactive above):
  - Goals → `"No goals yet. Tell Ada what you're working toward."`
  - Notes → `"No notes yet. Jot anything Ada should know about you."`
- List errors: render `AdvisorEmptyOverlay` scoped to the list area when `byTab[activeTab].error` is set and `memories.length === 0`. SubTabs stay interactive so the user can switch tabs instead of being trapped on the failed one.
- `SwipeableMemoryRow`: keep the left `iconContainer` + `memoryTypeIcon` (flag / doc). Drop the `typeLabel` text element next to the timestamp — each tab is uniform so the label is redundant. The icon gives the card its visual anchor.
- Accessibility: the chip pair uses `accessibilityRole="tablist"` on the container and `accessibilityRole="tab"` + `accessibilityState={{ selected: isActive }}` on each chip (upgrading from `"button"`). Optional polish — on tab change, set `accessibilityLiveRegion="polite"` on the list area so VoiceOver announces the refresh.
- Retain `useAdvisorComposerLayout`, `KeyboardAvoidingView`, `keyboardVerticalOffset`, and `showToast` flow unchanged.

**Patterns to follow:**
- Existing `TypeChips` component in `MemoryList.tsx` for chip styling tokens.
- `fetchMessages` / `fetchNudges` in `mobile/lib/advisor.ts` for the URLSearchParams-with-optional-params idiom Unit 2 mirrors.
- `useCapabilities()` usage pattern — not needed here but don't introduce scattered if-checks.

**Test scenarios:**
- Manual (simulator): Goals tab, type `"grow hair"`, switch to Notes — composer empty. Switch back — `"grow hair"` still there. Submit on Goals — composer clears; new row appears; Notes draft untouched.
- Manual: Notes tab, type something, switch to Goals, submit a goal, switch back — Notes draft still there.
- Manual: Goals tab shows only goal rows; Notes tab shows only note rows; neither shows any insight row even after triggering a fresh analysis (verifies Unit 1's server-side filter).
- Manual: swipe-to-delete a row on Goals tab — row disappears; switch to Notes and back — deletion persists.
- Manual: Empty state shows correct copy per tab.
- Manual: Tab-switch refetch shows a subtle list-area indicator, **not** the full-screen skeleton flashing on every tap.
- Manual: Type a 3-line note on Notes, switch to Goals — composer shrinks to the empty goal draft's natural height (verifies the `key={activeTab}` remount).
- Manual: Start a Goals submit (observe composer disabled), immediately tap Notes — Notes composer is **not** disabled.
- Manual: Force a Goals fetch error (e.g., kill the API); switch to Notes — Notes loads normally without inheriting the Goals error overlay.
- Manual: VoiceOver — each chip is announced as a tab with selected-state; the list area announces on tab change.
- Regression: keyboard offset unchanged on both tabs (`inputBottomPadding`).

**Verification:**
- `cd mobile && npx expo lint` clean.
- `cd mobile && npx tsc --noEmit` clean.
- Manual checklist above exercised on iOS simulator with a fresh guest account.

---

- [ ] **Unit 4: Polish + regression pass**

**Goal:** Sweep leftover references to the old design, align docs, and update the Maestro flow (which is already out of sync — see below).

**Requirements:** R6, R7

**Dependencies:** Unit 3

**Files:**
- Modify: `mobile/components/advisor/MemoryList.tsx` (any leftover dead code from the `TypeChips` semantic change — old `selectedType` references, unused `ADDABLE_TYPES`, stale comments).
- Modify: `mobile/UI_MAP.md` — update any reference to the composer chip picker to reflect the subtabs.
- Modify: `mobile/.maestro/flows/80-advisor-memory-add.yaml` — the flow already uses the obsolete placeholder string `"Add a goal or note"` (doesn't match current or new placeholders) and is silently passing via `runFlow.when.visible` guards. Update selectors to tap a subtab (e.g., `"Goals"`) then type into the current placeholder.

**Approach:**
- Grep the mobile tree for `selectedType`, `TypeChips`, `ADDABLE_TYPES` — delete anything that still references the old composer-picker model.
- Update the Maestro flow to: tap the Memories tab, tap the `"Goals"` subtab, tap the composer (targeting the real placeholder), type, submit, assert the new row. Remove the stale `"Add a goal or note"` selector.
- Verify `UI_MAP.md` mentions the subtabs layout, not the composer chip picker.

**Test scenarios:**
- Test expectation: none — this unit is mechanical cleanup plus one targeted Maestro flow update. Verification lives in the downstream lint + `expo lint` + Maestro dry-run, plus a manual exercise of the updated flow.

**Verification:**
- `make format && make lint && make test` green.
- `cd mobile && npx expo lint` green.
- Maestro flow `80-advisor-memory-add.yaml` actually exercises the add-goal path end-to-end (no silent skip via `when.visible`).

## System-Wide Impact

- **Interaction graph:** Only `MemoryList.tsx` and the three advisor memory endpoints touched. No nudge / chat paths affected.
- **Error propagation:** Unchanged — `addMemory`, `deleteMemory`, `fetchMemories` all continue to throw `ApiError`; toast surface stays the same.
- **State lifecycle risks:** Per-tab drafts live in component state; unmounting the Memories tab discards both drafts (intentional). No persisted partial writes.
- **API surface parity:** `GET /v1/memories` gains an optional `type` query param. No other callers exist; backward-compatible. `POST` / `DELETE` unchanged.
- **Integration coverage:** Unit 1's integration test exercises the full handler → service → repo path; mobile side is manual since the project has no RN test harness for this surface.
- **Unchanged invariants:** `GOAL` remains cap-exempt (`_enforce_memory_cap`); retrieval weighting unchanged; system-authored memories continue to be written and consumed by the advisor context/nudge paths.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Hidden consumer of `GET /v1/memories` (e.g., a web surface) relying on the unfiltered response | Keep `type=None` path intact and unchanged. Defaults to today's behavior. |
| Users with existing `analysis_insight` rows expect to see them somewhere | Origin explicitly accepts this tradeoff ("cleanest UI … user can't inspect"); call it out in the PR description in case QA surfaces it. |
| Drafts lost when user backgrounds the app briefly | Acceptable — drafts are session-scoped per origin. If regretted post-ship, trivial follow-up with `AsyncStorage`. |
| Maestro flow `80-advisor-memory-add.yaml` assumes in-composer chips | Unit 4 checks and updates the selector if needed. |
| Request fan-out on tab switch (refetch) feels slow on a large list | Backend already supports pagination + is indexed on `(user_id, created_at desc, id desc)`; a 50-row first page is fast. Revisit with pagination wiring in the deferred follow-up if needed. |

## Documentation / Operational Notes

- Update `mobile/UI_MAP.md` if it documents the old chip composer.
- No runbook or monitoring change. No rollout flag — change is small and reversible by a single revert commit per unit.

## Sources & References

- **Origin document:** [docs/brainstorms/2026-04-16-memories-goals-notes-subtabs-requirements.md](../brainstorms/2026-04-16-memories-goals-notes-subtabs-requirements.md)
- Related code:
  - `mobile/components/advisor/MemoryList.tsx`
  - `mobile/lib/advisor.ts`
  - `app/api/advisor.py::list_memories` (line 363)
  - `app/advisor/service.py::AdvisorService.list_memories_page` (line 415)
  - `app/repositories/advisor_repo.py::get_memories_page` (line 300)
- Related PRs: #107 (guest memory CRUD + 204 patch), #108 (review follow-ups)
- Spec: `docs/advisor-spec.md` §10 (cap), §6 (context assembly)
