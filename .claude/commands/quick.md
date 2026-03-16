---
description: "Quick flow — for known-scope work (bug fixes, enhancements, refactors). Same verification quality as full flow."
---

# /quick — Quick Flow Orchestrator

3-step workflow for known-scope changes in existing codebases. Same verification chain as `/start`
(TDD, verify, review, Gate 5) — skips the 4 planning phases.

> **Path resolution:** All `.claude/skills/` and `.claude/agents/` paths below are relative to the project root or `~/`. If a file is not found at `.claude/skills/...`, check `~/.claude/skills/...` (global install).

## 1. Parse Input

`/quick {name}` or `/quick {description}` — derive lowercase hyphenated slug.

Auto-classify task type from description:

| Signal | Type |
|--------|------|
| "fix", "bug", "broken", "error", "crash" | `bug-fix` |
| "add", "feature", "support", "enable" | `enhancement` |
| "refactor", "rename", "extract", "clean" | `refactor` |
| "config", "setting", "env", "update dep" | `config` |

If description is ambiguous, default to `enhancement`. Confirm slug and type with user.

## 2. Prerequisites

### 2a. Existing Codebase Required

Check for source files (`*.ts`, `*.js`, `*.go`, `*.py`, `*.rs`). If none found:
`No existing codebase detected. Use /start for greenfield.` — redirect.

### 2b. Greenfield Conflict Check

If `docs/state.json` exists with `"flow": "greenfield"`:
```
Active greenfield: {feature} (Phase {N}/5 — {phase name})

[Q] Quick anyway — creates separate .quick-state.json
[R] Resume greenfield — /start {feature}
[C] Cancel
```
On [Q]: all state operations use `docs/.quick-state.json` instead of `docs/state.json`.
On [R]: hand off to `/start {feature}`.

### 2c. Existing Quick Flow Check

**Existing quick flow check:**
- If `docs/state.json` exists with `"flow": "quick"` and a different feature slug:
  ```
  Active quick task: {feature-name}
  [F] Finish first — resume existing quick task
  [R] Replace — abandon existing, start new (state lost)
  [C] Cancel
  ```
- If same slug: resume existing quick task

**Lock check:**
- When using `.quick-state.json` (greenfield active), all lock operations use `docs/.quick-lock` instead of `docs/.lock`.
- Check for non-stale lock file, offer [W] Wait / [T] Take over / [C] Cancel

### 2d. Initialize

Create state file (`docs/state.json`, or `docs/.quick-state.json` if greenfield active):
`{ "feature": "{slug}", "flow": "quick", "version": "next-2.0", "created": "{ISO date}", "lastUpdated": "{ISO date}", "currentPhase": "analyze", "quickSpec": null, "currentStory": null, "tooling": {...}, "metrics": {...} }`

**State write rule:** Always use the **Write** tool (full file) for state.json. A PreToolUse hook (`validate-state.sh`) validates every Write and blocks Edit operations on state.json. Every write MUST update `lastUpdated` to the current ISO timestamp.
Create lock file with timestamp + session-id: use `docs/.quick-lock` when greenfield active (i.e., using `.quick-state.json`), otherwise `docs/.lock`.

## 3. Step 1/3 — Analyze

```
═══ LAIM QUICK ═══ Task: {name} │ Step 1/3: Analyze ═══
```

### Intake
Understand what the user wants to change. If the description is vague, ask 1-2 focused
clarifying questions. Do NOT over-question — prefer inferring from context and codebase.

### Scope Guard
Fires when **≥2** triggers hit simultaneously: new DB table, new bounded context/service, new API namespace/version, new auth flow.

If ≥2: `⚠️ Scope Guard: {triggers}. [C] Continue (override logged)  [F] Switch to /start  [R] Revise scope`
On [C]: log to concerns.md. On [F]: hand off to `/start`.

### Codebase Discovery (Iterative Retrieval)

**Cycle 1 — Broad:** `grep -rl`, `find -name`, `git grep` across src. Score files by relevance.
**Cycle 2 — Refined:** Read top 5-10 files, follow import chains 1 level deep, note boundaries.
**Extract conventions:** Import style, error handling pattern, test organization, naming conventions.

### Tooling Detection
Same as `/start` §4. Populate `tooling` block. If test/build not detected → ask user.

**Phase transition:** Update state: `currentPhase` → `spec`, `lastUpdated` → now.

## 4. Step 2/3 — Quick-Spec

```
═══ LAIM QUICK ═══ Task: {name} │ Step 2/3: Spec ═══
```

Auto-generate `docs/quick-{slug}.md` with this structure:

```markdown
---
status: ready
type: {bug-fix|enhancement|refactor|config}
created: {date}
---
# Quick: {name}

## Change Description
{What and why — 2-5 sentences}

## Affected Files
- `{path}`: {what changes}

## Acceptance Criteria
### AC-1: {title}
Given {context} / When {action} / Then {outcome}

## must_haves
truths: ["{behavioral assertions}"]
artifacts: ["{file paths that must exist}"]
key_links: ["{grep-able patterns proving wiring}"]

## Detected Conventions
{Import style, error handling, test location, naming — from discovery}
```

Present to user: `[C] Continue to implement  [R] Revise  [P] Pause`
On [R]: incorporate feedback, regenerate. On [C]: update state `currentPhase` → `implement`, `quickSpec` → path, proceed.

## 5. Step 3/3 — Implement

```
═══ LAIM QUICK ═══ Task: {name} │ Step 3/3: Implement ═══
```

1. Update state: `currentPhase` → `implement`
2. Record baseline: run `{tooling.test}`, store test count in state `baselineTests`
3. **Route:** Invoke the `/implement` skill. Pass `docs/quick-{slug}.md` as story input — implement skill treats it identically: TDD → verify → stub detection → evidence → goal-backward → review → Gate 5.
4. On Gate 5 pass: proceed to completion. On fail: follow implement skill's escalation.

## 6. Completion

```
═══ LAIM QUICK ═══ Complete: {name} ═══
Type: {type}  │  Tasks: {N}  │  TDD: {rate}%
Tests: {baseline} → {current} ({delta})
All acceptance criteria verified. ✅
```
- Remove lock file (`docs/.quick-lock` if greenfield active, otherwise `docs/.lock`)
- Update state: `currentPhase` → `complete`, final metrics

## 7. Resume

On re-invocation with same name, read state file and present:
```
═══ LAIM QUICK ═══ Resuming: {name} │ Step {n}/3 ═══
Last activity: {lastUpdated}
[C] Continue from here  [R] Restart  [P] Pause
```

Route by `currentPhase`:
| `currentPhase` | Route to |
|----------------|----------|
| `analyze` | §3 (Analyze) |
| `spec` | §4 (Quick-Spec) |
| `implement` | §5 (Implement) — resume at `currentTask` |
| `complete` | Show completion summary |

## 8. Context Window & Restart

If context degrades during a long implement step, the user can start a fresh conversation and re-invoke `/quick {name}`. The framework detects the existing state and quick-spec, and resumes from the current task checkpoint. See `/start` §9 for full context window documentation.

## 9. Error Handling

**Corrupted state:** Reconstruct from available sources:
1. `docs/quick-{slug}.md` exists → resume from implement step
2. git log for recent commits → infer task progress
3. Present reconstructed state → user confirms before proceeding

**Stale lock (>4h):** Auto-break with notice, same as `/start`.

**State/artifact mismatch:** If state says `implement` but quick-spec missing → re-run from analyze.
