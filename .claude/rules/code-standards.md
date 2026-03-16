---
alwaysApply: true
---
Universal code standards for all languages and frameworks.

# Code Standards

## 1. Commit Protocol

**Critical to LaiM NEXT workflow.** Every commit traceable to a single task.

- **Stage specific files only** — `git add <file>...`; never `git add .` / `-A` / `--all`
- **One commit per task** — never squash multiple tasks or combine unrelated changes
- **Conventional commit format** — `type(scope): description` with optional body explaining WHY

### Tagging Protocol

```bash
git tag pre-{feature}-{story-id}   # Before first commit of a story
git tag post-{feature}-{story-id}  # After Gate 5 passes (story verified)
```

### Pre-Commit Checklist

1. `git status` — review every changed file; stage only current-task files
2. Run full verification loop (Section 2)
3. `git diff --cached` — final review before commit

## 2. Verification Loop

Run the **full chain** before every commit, in order:

```
format → lint → build → test → test integrity → security
```

- **Never skip a step** — even for "just docs"
- **Use tooling from `state.json`** — `{tooling.formatter}`, `{tooling.linter}`, `{tooling.testRunner}`
- **Max 3 retries** per step — then HALT and report
- **All steps must pass** — any failure blocks the commit
- Local verification doesn't replace CI; both must pass
- If `state.json` doesn't specify a tool, check `package.json` scripts or `Makefile`

## 3. Code Organization

- **Dependency direction:** handlers → services → repositories → models (never reverse)
- **Feature-first** over layer-first: `src/users/service.ts` not `src/services/user-service.ts`
- **No barrel exports** (`index.ts` re-exports) unless project already uses them
- **ADRs** in `docs/adr/`
- **Git safety:** never commit secrets/credentials; no force-push to shared branches
- **Code smell thresholds:** function >50 lines, file >800 lines, nesting >4 levels, params >3

## 4. Deviation Rules

### Rule 1 — Minor (naming, formatting, style)
Auto-fix + log the deviation.

### Rule 2 — Moderate (wrong pattern, wrong abstraction)
Auto-fix + log + note in checkpoint.

### Rule 3 — Significant (interface/contract changes)
Fix + create amendment in `docs/amendments.md`.

### Rule 4 — Architectural (new components, boundary changes, dep reversal)
**HALT** — require explicit user approval before proceeding.

**Escalation is mandatory.** When in doubt, treat as the higher rule number.
