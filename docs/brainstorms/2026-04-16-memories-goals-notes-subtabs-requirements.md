# Memories Tab — Goals / Notes subtabs

**Date:** 2026-04-16
**Status:** Requirements (pre-planning)
**Scope:** Lightweight → Standard (mobile + small backend)

## Problem

The Memories tab currently shows one flat list and a single input with two chip-toggles (Goal / Note). Three pain points:

1. Typed text persists across chip flips — user changes type and their draft unexpectedly carries over.
2. System-authored memories (`analysis_insight`, `accepted_suggestion`, `dismissed_suggestion`) appear alongside user memories in the feed and dominate it — the screenshot shows an insight rendered as raw JSON crowding a user goal.
3. "Goal vs Note" is a classification the user has to make up front, even though the two serve very different mental tasks (long-term intention vs. passing fact about me).

The type tag is not cosmetic — `GOAL` is cap-exempt and weighted higher during retrieval (`app/advisor/memory_manager.py:40, 182`). Hiding it entirely would cost retention semantics.

## Goal

Give users a Memories tab that serves both planner and journaler modes, without forcing them to share mental space with Ada's internal bookkeeping memories.

## Decisions

### Shape

**Two subtabs at the top of the Memories tab: Goals · Notes.**

- Each tab shows user-authored memories of that type only.
- Insights / Accepted / Dismissed memories are hidden from this UI (they continue to exist in the DB and feed the advisor's context).
- Default tab on first open: **Goals**. Subsequent opens: **last-used tab** within the session.

### Inputs

**One composer per tab, with independent drafts.**

- Goals tab: placeholder `"e.g. Grow out my hair to shoulder length"`.
- Notes tab: placeholder `"e.g. I prefer minimal jewelry"`.
- Draft text is held per-tab in component state; switching tabs never carries the draft across. Drafts live for the session and are discarded on successful send or when the Memories tab unmounts.
- Submit button adds a memory of the active tab's type (`goal` vs `user_note`) — API payload unchanged.

### List rendering

- Each row drops the per-row type badge (icon + "Goal" / "Note" label) — redundant when the whole tab is one type.
- Keep the row layout otherwise (content summary, timestamp, swipe-to-delete).
- Empty state per tab:
  - Goals: `"No goals yet. Tell Ada what you're working toward."`
  - Notes: `"No notes yet. Jot anything Ada should know about you."`

### What's hidden

- `analysis_insight`, `accepted_suggestion`, `dismissed_suggestion` rows do not render in either tab. They remain in the DB and continue to feed the advisor context builder and nudge generator.
- Rationale: user asked for the cleanest UI. They accept that Ada's internal memories are not user-inspectable in this release. A future "What Ada knows" screen can expose them if needed.

## Non-goals

- No AI auto-classification of Goal vs Note.
- No "Pin to keep forever" reframing.
- No separate "Ada memories" tab this release.
- No draft persistence across app restarts.
- No search / sort / bulk actions.
- No migration or backfill — hiding is a client-side filter on a list endpoint; existing rows stay in the DB.

## Success criteria

1. User on the Memories tab sees a top chip row with exactly **Goals** and **Notes** — no chip flipping inside the composer.
2. Typing in the Goals tab composer and switching to Notes shows an empty composer (and vice versa). Typing again and switching back restores the original draft.
3. Goals tab shows only `type=goal` rows. Notes tab shows only `type=user_note` rows. Neither tab shows insight, accepted, or dismissed rows.
4. Adding a memory from the Goals tab persists as `type=goal`; from the Notes tab as `type=user_note`.
5. Swipe-to-delete still works per row.
6. Empty state text matches the tab.
7. Existing ruff/pytest/`expo lint` suites stay green.

## Open questions for planning

- **Server-side filter or client-side filter?** Convention in this repo is infinite-scroll pagination; server-side `?type=` filter is the right pattern but will add a backend parameter. The alternative is client-side filtering of `GET /v1/memories`, which overfetches system-authored rows the user cannot see. Planning to pick; recommend server-side.
- **Default tab per session vs per-user persisted preference** — recommend per-session only; adds no schema, keeps behavior predictable.
- **Counts in tab labels** (e.g. "Goals (3)") — nice polish; decide during planning if worth the render complexity.

## Verification

- UI: Goals tab, type + switch + switch back — draft roundtrip works.
- UI: exactly two chips visible; no chip inside the composer.
- UI: Goals tab shows no insight rows when the user has one stored.
- Unit: hook's draft state isolates `goal` from `user_note`.
- Unit/integration: list endpoint (or client filter) excludes `analysis_insight`, `accepted_suggestion`, `dismissed_suggestion`.
- Regression: swipe-to-delete; empty states; composer keyboard offset.
