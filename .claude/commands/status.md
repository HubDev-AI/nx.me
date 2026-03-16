---
description: "Display current LaiM project progress. Read-only — no state changes."
---

# /status — Progress Display

Read-only. No state mutations.

## 1. Read State

Check `docs/state.json` and `docs/.quick-state.json`. If neither found:
```
No active LaiM project. Use /start or /quick to begin.
```

## 2. Greenfield Display

From `docs/state.json` with `"flow": "greenfield"`:

Phase status: `complete` + `gateResult: pass` → ✅ with date │ `in-progress` → 🔄 │ `pending` → ⬜
Progress bar: `storiesDone / storiesTotal` as filled/empty blocks.

**In story loop:**
```
═══ LAIM ══════════════════════════════════════════════
Feature: {name}  │  Story Loop
████████████░░░░░░░░  {done}/{total} stories
═══════════════════════════════════════════════════════

Phases:
  ✅ Research      — {date}
  ✅ Specify       — {date}
  ✅ Architecture  — {date}
  ✅ Plan          — {date}
  🔄 Implement     — {done}/{total} done

Current: Story {id} — {title}
  Task {t}/{T}: {name}  │  TDD: {mode}  │  Verifications: {n}

Tech Debt: {n} items ({high} high)  │  Amendments: {n} entries
```

**In planning phases:**
```
═══ LAIM ═══ Feature: {name} │ Phase {N}/5: {phase} ═══
  ✅ Research  │  🔄 Specify  │  ⬜ Architecture  │  ⬜ Plan  │  ⬜ Implement
```

## 3. Quick Display

From state with `"flow": "quick"`:
```
═══ LAIM QUICK ════════════════════════════════════════
Task: {name}  │  Step {n}/3: {step}
Task {t}/{T}  │  TDD: {mode}
═══════════════════════════════════════════════════════
```

## 4. Both Active

If greenfield + quick state both exist, show both displays stacked.

## 5. Sprint Summary

If `docs/sprint-status.yaml` exists:
```
Sprint: Wave 1 ✅ {n}/{n}  │  Wave 2 🔄 {n}/{n}  │  Wave 3 ⬜ {n}/{n}
```

## 6. Metrics

From state.json `metrics`:
```
TDD: {metrics.tasks.tddCount}/{metrics.tasks.tddTotal}  │  First-pass: {metrics.tasks.firstPassSuccess}/{metrics.tasks.totalCompleted}  │  Gates: {metrics.gates.passes}✅ {metrics.gates.fails}❌ {metrics.gates.overrides}⚡  │  Subagents: {metrics.execution.subagentSpawns}
```
