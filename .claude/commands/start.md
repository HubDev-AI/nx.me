---
description: "Start or resume a feature development workflow. Routes through Research → Specify → Architecture → Plan → Implement with quality gates."
---

# /start — Greenfield Orchestrator

5-phase lifecycle: initialize features, detect existing work, route through gates, manage story loop.
For bug fixes and small changes, suggest `/quick` instead.

> **Path resolution:** All `.claude/skills/` and `.claude/agents/` paths below are relative to the project root or `~/`. If a file is not found at `.claude/skills/...`, check `~/.claude/skills/...` (global install).

## 1. Parse Input

`/start {name}` — derive lowercase hyphenated slug (2-50 chars, no special chars beyond hyphens).
If sentence given, derive slug: "Build a user settings page" → `user-settings`. Confirm derived names.
`/start` alone — scan for `docs/state.json`; if found offer resume, else ask what to build.

## 2. Scan for Existing Work

**Lock check (before state):**
- If `docs/.lock` exists and is NOT stale (<4h):
  ```
  ⚠ Active session detected (started {time})
  [W] Wait — check again in a moment
  [T] Take over — break lock and proceed
  [C] Cancel
  ```
- If stale (>4h): "Stale lock from {time}. Taking over." → auto-break
- If no lock → proceed normally

Check `docs/state.json`. If state.json is missing or fails to parse, follow the reconstruction protocol in §10 (Error Handling).

### Same Feature → RESUME

1. Read state.json → extract `currentPhase`, `currentStep`, `currentCheckpoint`, `currentStory`
2. Cross-reference artifacts: check frontmatter `status: complete` on research.md, spec.md, architecture.md, plan.md. Cross-check story files with sprint-status.yaml.
3. Update metrics: `metrics.execution.totalSessions += 1`
4. If dirty git — **use `AskUserQuestion`** (single-select):
     - `[S] Stash` — stash changes, resume clean
     - `[C] Commit-wip` — commit as work-in-progress
     - `[R] Review diff` — show changes before deciding
     - `[D] Discard` — discard all uncommitted changes
5. Present resume:
   ```
   ═══ LAIM ═══ Resuming: {feature} ═══
   Phase: {N}/5 ({name})  │  Story: {done}/{total}  │  Task: {t}/{T}
   Last activity: {lastUpdated}
   [C] Continue from here  [R] Restart current phase  [P] Pause
   ```
5. **Artifact integrity check (on resume):**
   When resuming, verify key artifacts haven't been modified externally:
   1. Compare artifact file modification times against state.json.lastUpdated
   2. If any planning artifact (research.md, spec.md, architecture.md, plan.md) was modified AFTER the phase completed:
      ```
      ⚠ ARTIFACT MODIFIED EXTERNALLY
      Modified: docs/spec.md (changed {time} — phase completed {time})

      [A] Accept changes — proceed with modified artifact
      [R] Revert — restore from git (git checkout docs/spec.md)
      [D] Diff — show what changed
      ```
6. Route to correct skill at correct step (see §6 Routing Table)

### Different Feature Found

```
Active: "{existing}" — requested: "{new}"
[R] Resume existing  [A] Archive to docs/.archive-{timestamp}/ + start fresh  [C] Cancel
```
On [A]: `mv docs/ docs/.archive-$(date +%Y%m%d-%H%M%S)/`, recreate `docs/` and `docs/stories/`.

### No State Found → Fresh Start

Proceed to §3.

## 3. Scope Check

If description suggests known-scope work ("fix", "bug", "refactor", "config", "tweak", "rename",
"small change", "update") — **use `AskUserQuestion`** (single-select):

```
This might fit /quick — same verification chain (TDD, lint, build, test,
security, code review, Gate 5), skips planning phases.

[Q] Switch to quick — hand off to /quick {name}, skip planning phases
[F] Full flow — proceed with all 5 phases
```

If [Q]: hand off to `/quick {name}`. If clearly complex or [F]: proceed.

## 4. Detect Tooling

Scan project files and populate state.json `tooling` block:

| File | Detects |
|------|---------|
| `package.json` scripts | npm/node: build, test, lint, format |
| `go.mod` + config | go build/test, golangci-lint |
| `Cargo.toml` | cargo build/test/clippy |
| `Makefile` / `Justfile` | make/just targets |
| `pyproject.toml` / `requirements.txt` | pytest, ruff, black |
| Linter configs (`.eslintrc*`, `biome.json`) | Confirm lint tool |
| Test configs (`vitest.config.*`, `jest.config.*`) | Confirm test runner + `test_changed` |

**CI/CD detection:**
Scan for CI/CD configuration:
- `.github/workflows/` → GitHub Actions
- `.gitlab-ci.yml` → GitLab CI
- `vercel.json` or `.vercel/` → Vercel
- `netlify.toml` → Netlify
- `Jenkinsfile` → Jenkins
- `.circleci/` → CircleCI

If found:
```
⚠ CI/CD DETECTED: {provider}
Commits may trigger automated builds/deployments.

Recommendation: Work on a feature branch to avoid partial deployments.
Current branch: {branch}

[B] Create feature branch (git checkout -b feature/{slug})
[C] Continue on current branch (I understand the risk)
```

**`test_changed` auto-detection** (for per-task verification — full `test` always runs at wave checkpoints and Gate 5):
- `jest` detected → `"jest --changedSince=HEAD~1"`
- `vitest` detected → `"vitest --changed HEAD~1"`
- `pytest` detected → `null` (no built-in changed-file mode)
- `go test` detected → `null`
- If not detected or unsupported → `null` (falls back to `tooling.test`)

Present detected tooling table — **use `AskUserQuestion`** (single-select):
- `[C] Continue` — accept detected tooling as-is
- `[E] Edit commands` — review and override detected commands

If test or build not detected → ask user for commands explicitly.

## 5. Initialize

1. `mkdir -p docs/ docs/stories/`
2. Create `docs/state.json`:
   ```json
   {
     "feature": "{slug}",
     "flow": "greenfield",
     "version": "next-2.0",
     "created": "{ISO date}",
     "lastUpdated": "{ISO date}",
     "currentPhase": "research",
     "currentStep": null,
     "currentCheckpoint": null,
     "phases": {
       "research":     { "status": "pending", "startedAt": null, "completedAt": null, "gateResult": null },
       "specify":      { "status": "pending", "startedAt": null, "completedAt": null, "gateResult": null },
       "architecture": { "status": "pending", "startedAt": null, "completedAt": null, "gateResult": null },
       "plan":         { "status": "pending", "startedAt": null, "completedAt": null, "gateResult": null }
     },
     "storiesDone": 0,
     "storiesTotal": 0,
     "changeStories": [],
     "currentStory": null,
     "tooling": {
       "format": "{detected or null}",
       "lint": "{detected or null}",
       "lint_fix": "{detected or null}",
       "build": "{detected or null}",
       "test": "{detected or null}",
       "test_changed": "{detected or null}",
       "security": "{detected or null}"
     },
     "metrics": {
       "gates":    { "passes": 0, "fails": 0, "overrides": 0, "backNavigations": 0, "blockingFails": 0 },
       "phases": {
         "research":     { "durationMinutes": null, "revisions": 0, "gateAttempts": 0 },
         "specify":      { "durationMinutes": null, "revisions": 0, "gateAttempts": 0, "personaCount": 0, "personaConcerns": 0 },
         "architecture": { "durationMinutes": null, "revisions": 0, "gateAttempts": 0, "deferredDecisions": 0, "resolvedDecisions": 0 },
         "plan":         { "durationMinutes": null, "revisions": 0, "gateAttempts": 0, "wavesPlanned": 0 }
       },
       "stories":  { "completed": 0, "skipped": 0, "changeStoriesCreated": 0, "gate5Passes": 0, "gate5Fails": 0, "gate5Overrides": 0, "avgTasksPerStory": 0, "sizeDistribution": { "S": 0, "M": 0, "L": 0 } },
       "tasks":    { "totalCompleted": 0, "totalCompletedNoCommit": 0, "totalSkipped": 0, "totalRevisions": 0, "totalVerificationCycles": 0, "firstPassSuccess": 0, "tddCount": 0, "tddTotal": 0, "avgVerificationCycles": 0 },
       "codeReview": { "reviewsRun": 0, "totalFindings": 0, "criticalFindings": 0, "highFindings": 0, "mediumFindings": 0, "lowFindings": 0, "findingsDeferred": 0 },
       "quality":  { "interfaceAudits": 0, "interfaceMismatches": 0, "amendments": 0, "concerns": 0, "concernsBySeverity": { "critical": 0, "high": 0, "medium": 0, "low": 0 } },
       "drift":    { "taskDeviations": 0, "storiesResizedDuringImpl": 0 },
       "estimation": { "sizeAccuracy": { "S": { "planned": 0, "avgActualTasks": 0 }, "M": { "planned": 0, "avgActualTasks": 0 }, "L": { "planned": 0, "avgActualTasks": 0 } } },
       "execution": { "totalSessions": 0, "pauseResumeCount": 0, "agentTeamsUsed": false, "parallelWaves": 0, "parallelStories": 0, "subagentSpawns": 0 },
       "optionalSkills": {
         "designer": { "used": false, "mode": null, "completedAt": null },
         "devopsPass1": { "used": false, "completedAt": null },
         "devopsPass2": { "used": false, "completedAt": null },
         "qa": { "used": false, "completedAt": null },
         "notion": { "used": false, "syncCount": 0, "completedAt": null }
       },
       "git":      { "totalCommits": 0, "totalFilesChanged": 0, "totalInsertions": 0, "totalDeletions": 0, "testsAdded": 0 }
     },
     "waveStrategy": {},
     "devops": {
       "pass1": "pending",
       "pass2": "pending",
       "pass2Partial": false
     }
   }
   ```
   **State write rule:** Always use the **Write** tool (full file) for state.json. A PreToolUse hook (`validate-state.sh`) validates every Write and blocks Edit operations on state.json. Every write MUST update `lastUpdated` to the current ISO timestamp. All timestamp fields (`created`, `lastUpdated`, `startedAt`, `completedAt`) MUST use full ISO 8601 with actual hours/minutes/seconds from the system clock (e.g., `2026-03-04T14:32:07.000Z`). Midnight placeholders (`T00:00:00.000Z`) are PROHIBITED.

   ### Metrics Write Reference

   Before writing to `metrics.*` in state.json, read `templates/references/metrics-triggers.md` for the full list of fields and their exact triggers.

3. Create `docs/.lock` with current timestamp + session identifier
4. Branch check: if on `main` and `docs/state.json` already tracks a different feature → warn

```
═══ LAIM ═══ Starting: {feature} ═══
Research → Specify → Architecture → Plan → Implement
Agent Teams: {Enabled / Not enabled}
[C] Begin Phase 1: Research  [P] Pause
```

## 5.5 Universal Pause Protocol

When a user selects `[P] Pause` at any HALT point in any skill:

1. **Write artifact** with `status: paused` and the skill's pause field (e.g., `pausedStep`, `current_stage`, `current_step`) set to the exact value from the skill's state table. Never invent suffixes like `-approved` or use descriptive sentences.
2. **Update state.json** (root-level fields, NOT inside `phases.*`):
   - Set `currentStep` (or `currentCheckpoint` for implement phase) to the state value from the skill's table.
   - Update `lastUpdated` to the current ISO timestamp.
   - Update metrics: `metrics.execution.pauseResumeCount += 1`
3. **Display:** `Session paused at {step name}. Resume with /start.`

**On resume** (when a skill detects `status: paused` in its artifact):
1. Read root-level `currentStep` (or `currentCheckpoint`) from state.json — not from inside `phases.*`.
2. Re-present the artifact for that step with the same approval options.
3. **Do NOT advance** — the user must explicitly select `[C]` to proceed.

**On `[C]` after resume:** When the user selects `[C]` to proceed from a paused checkpoint, clear `currentStep` (or `currentCheckpoint`) to `null` in state.json and set the artifact's `status` back to `draft`. This prevents stale state if the session crashes before the next checkpoint writes a new value.

**Critical:** A state value means "user is AT this step, has NOT yet approved it." Approval is expressed by the user selecting `[C]`, which advances to the next step.

**Standalone skills exception:** Optional standalone skills (Designer, DevOps, QA) store pause state in their artifact frontmatter only (e.g., `current_step` or `current_stage`), not in root-level `currentStep`. They are not part of the 5-phase flow and manage their own resume via artifact detection. The Notion skill uses `notion.pausedStage` inside state.json's `notion` key.

**AskUserQuestion definition:** `AskUserQuestion` is a Claude Code built-in tool that presents options as an interactive single-select UI with descriptions. Use it for multi-option tradeoff decisions (marked with `**use AskUserQuestion**` in this document). Simple `[C]/[P]` checkpoints remain as plain text. When a user selects "Other" (free-text), map the input to the nearest valid option and confirm before proceeding; if no match, re-present the selection.

**HALT display rule:** At every HALT point, the choices (e.g., `[C] ... [R] ... [P] ...`) MUST be the absolute last output. For plain-text HALTs this is the choices line; for `AskUserQuestion` prompts the options block (bullet list) satisfies this rule. Any supplementary information — task summaries, status recaps, progress notes — goes above the choices, never below. This ensures the actionable prompt is always visible at the bottom of the terminal without scrolling.

**Git push rule:** Never `git push` unless the user explicitly requests it. All commits stay local by default.

## 6. Phase Routing

### Routing Table

| Phase | Condition | Action |
|-------|-----------|--------|
| 1 Research | `currentPhase == "research"` | Invoke the `/research` skill |
| 2 Specify | `currentPhase == "specify"` | Invoke the `/specify` skill |
| 3 Architecture | `currentPhase == "architecture"` | Invoke the `/architecture` skill |
| 4 Plan | `currentPhase == "plan"` | Invoke the `/plan` skill |
| 5 Implement | `currentPhase == "implement"` | Enter Story Loop (§7) |

### Phase Transition Protocol

When a skill completes and its embedded gate passes:
1. Update state.json: phase `status`→`complete`, `gateResult`→`pass`, `completedAt`→now, `lastUpdated`→now
2. Set `currentPhase` to next phase
3. Clear `currentStep` to `null` (the new phase sets its own step values)
4. **Phase tagging:** Create a phase tag:
   ```
   git tag phase-{N}-{feature}  (e.g., phase-1-payment-gateway, phase-2-payment-gateway, etc.)
   ```
   This enables recovery if docs/ is deleted during planning phases.
5. Display: `═══ LAIM ═══ Phase {N} Complete ═══` + artifact path + Gate PASS ✅ + 2-4 bullet summary + `[C] Continue to Phase {N+1}  [B] Back to Phase {N}  [P] Pause`
6. On [C]: invoke the next phase skill (e.g. `/specify`, `/architecture`, `/plan`)
7. On [B]: revert `currentPhase` to the previous phase in state.json, set that phase's status back to `pending`, and re-invoke the previous phase's skill. The artifact from the previous phase is preserved for revision.
8. On [P]: State is already updated (steps 1-3: `currentPhase` set to next phase, `currentStep` null, artifact `status: complete`). Display: `Session paused after Phase {N}. Resume with /start.` On resume, `/start` routes to the next phase's skill which starts fresh.

### Backward Navigation Protocol

When a user selects `[B] Back` at any checkpoint:

| Current Phase | `[B]` Target | Action |
|---------------|-------------|--------|
| Phase 1: Research (at Synthesis) | Discovery step | Re-enter conversational discovery |
| Phase 2: Specify (within steps) | Previous specify sub-step | Return to Requirements/Perspectives/AC/Verification |
| Phase 2: Specify (at Gate 2) | Phase 1: Research | Set `currentPhase` → `research`, re-invoke `/research` |
| Phase 3: Architecture (at Gate 3) | Phase 2: Specify | Set `currentPhase` → `specify`, re-invoke `/specify` |
| Phase 4: Plan (at Gate 4) | Phase 3: Architecture | Set `currentPhase` → `architecture`, re-invoke `/architecture` |
| Phase 5: Implement | N/A | Use `[X] Change Direction` or `[U] Undo` instead |

**On cross-phase back:**
1. Update state.json: set `currentPhase` to target phase, set target phase status → `pending`, clear `currentStep` to `null`, update `lastUpdated`. Update metrics: `metrics.gates.backNavigations += 1`
2. The existing artifact (research.md, spec.md, architecture.md) is preserved — the target skill detects it and enters revision/resume mode
3. Re-invoke the target phase's skill
4. When the target phase completes again, normal forward flow resumes

### Resume Routing

When resuming, route based on `currentPhase` in state.json:

| `currentPhase` | Route |
|----------------|-------|
| `research` | Invoke `/research` skill |
| `specify` | Invoke `/specify` skill |
| `architecture` | Invoke `/architecture` skill |
| `plan` | Invoke `/plan` skill |
| `implement` + `currentStory` is null | Pick next story from sprint-status.yaml |
| `implement` + `currentStory` set | Invoke `/implement` skill (resumes at `currentCheckpoint` if set) |

## Optional Standalone Skills

Standalone skills can be invoked **between phases** to produce artifacts consumed by downstream phases via contract points. They are NOT part of the 5-phase flow — invoke them when the project needs them.

| Skill | Command | Output | Invoke When | Consumed By |
|-------|---------|--------|-------------|-------------|
| Designer | `/designer` | `docs/design-system.md` | After Phase 3, before Phase 4 | Plan (design constraints), Story creator (design tokens) |
| DevOps Pass 1 | `/devops` or `/devops pass-1` | `docs/local-dev.md` + `## Infrastructure Architecture` in architecture.md | After Phase 4, before Phase 5 | Story creator (local dev, Docker), Plan (infra constraints) |
| DevOps Pass 2 | `/devops` or `/devops pass-2` | `docs/infrastructure.md` | After Phase 5 (all stories done) | Deployment, ops |
| QA | `/qa` | `docs/test-strategy.md` | After Phase 4, before Phase 5 | Story creator (test approach, coverage targets) |
| Notion | `/notion` | Notion pages (Feature Hub + child pages) | After any phase | Team knowledge base (Notion) |

**Contract point detection:** Downstream phases automatically detect these artifacts. If a file exists, the consuming phase extracts relevant content. If it doesn't exist, the flow proceeds normally with baseline decisions from the architecture document.

**Two-pass DevOps model:**
- **Pass 1** (pre-implementation): Generates infrastructure architecture decisions and local dev environment (Docker, scripts, env vars). Run after planning, before implementing stories. Story-creator inlines local dev context into stories.
- **Pass 2** (post-implementation): Scans actual codebase for ground-truth values (env vars, ports, build commands, schemas), then generates production Terraform, CI/CD, security, monitoring using real values. Run after all stories are implemented.
- Auto-detection: `/devops` without a pass flag auto-routes based on `state.json` devops block and `currentPhase`.

**When to invoke:**
- `/designer` — UI-heavy features, new visual identity, design system creation
- `/devops` — Infrastructure needs. Pass 1 for local dev + architecture; Pass 2 for production infra
- `/qa` — Complex testing requirements, compliance-driven projects, high-risk features

**When to skip:** Internal tools, simple features, CLIs, libraries without UI — the 5-phase flow handles these without optional skills.

### Post-Plan DevOps Suggestion

After Phase 4 gate passes, before entering the Story Loop:

1. Read `docs/architecture.md` — check for references to databases, caches, queues, message brokers, external services, or container-based deployment.
2. If infrastructure dependencies are found AND `docs/local-dev.md` does NOT exist AND `state.json` `devops.pass1` is not `"complete"`:
   ```
   Infrastructure dependencies detected in architecture (database, cache, queue, etc.).
   Local dev environment not yet configured.

   [D] Run /devops pass-1 now (recommended — sets up Docker, dev scripts, env vars)
   [S] Skip — implement without local dev setup
   [C] Continue to Story Loop
   ```
3. If no infrastructure dependencies found, or `docs/local-dev.md` already exists → proceed directly to Story Loop.

## 7. Story Loop

After Gate 4 passes, manage the story execution loop.

### 7a. Initialize Loop

1. Read `docs/sprint-status.yaml` → count stories, set `storiesTotal` in state.json
2. Stories execute in wave order. Within a wave, process sequentially.
3. **Wave execution strategy:**
   Check `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` env var.
   - If available AND wave has 2+ stories:
     ```
     Wave {N} has {count} independent stories.

     [S] Sequential — Full checkpoints per story (current behavior, recommended)
     [P] Parallel — Agent Teams executes stories simultaneously (autonomous, wave-level checkpoint)
     ```
   - If wave has 1 story → sequential (regardless of Agent Teams, no prompt)
   - If not available AND wave has 2+ stories:
     ```
     ℹ Wave {N} has {count} independent stories — running sequentially.
     Tip: See README for enabling parallel execution via Agent Teams.
     ```

   **Sequential (default):** Current behavior. Full HALT points per story.
   **Parallel:** Each story becomes a teammate. Autonomous execution with wave-level checkpoint only.

   Parallel mode implications (shown to user):
   - Per-story HALT points (task checkpoint, code review) run autonomously
   - User reviews at wave completion, not per-story
   - Higher token cost (~Nx for N stories)
   - Faster wall-clock time

   Store the choice in state.json `waveStrategy` (maps wave number → "sequential" | "parallel").

### 7b. Per Story

For each story (respecting wave and dependency order):

1. **Tag baseline:** `git tag pre-{feature}-{story-id}`
2. **Update state:** set `currentStory` in state.json with storyId, clear `currentCheckpoint` to `null`, status → `in-progress`, `lastUpdated`→now. Update metrics: `metrics.stories.sizeDistribution.{S|M|L} += 1` (from sprint-status.yaml size)
3. **Update sprint-status.yaml:** story status → `in-progress`
4. **Display story header:**
   ```
   ═══ LAIM ══════════════════════════════════════════════
   Feature: {name}  │  Story {done+1}/{total}: {title}
   ████████████░░░░░░░░  {done}/{total} stories
   ═══════════════════════════════════════════════════════

   [C] Continue  [S] Skip  [J] Jump to specific  [E] Edit story  [P] Pause
   ```
   On [P]: `currentStory` is already set (step 2). Display: `Session paused at story {storyId}. Resume with /start.` On resume, `/start` sees `currentPhase: implement` + `currentStory` set → routes to `/implement` skill.
5. **Route to implement skill:** Invoke the `/implement` skill
6. **On Gate 5 pass:**
   - Update sprint-status.yaml: story → `done`
   - Clear `currentStory` and `currentCheckpoint` to `null` in state.json
   - Increment `storiesDone` and update `lastUpdated` in state.json
   - Update metrics: `metrics.stories.completed += 1`, `metrics.stories.gate5Passes += 1`
   - `git tag post-{feature}-{story-id}`
   - Check for remaining stories

**Change Story insertion:**
If the implement skill created a CS-* story (cross-story change detected during [X] Change Direction):
1. CS-* story was inserted into sprint-status.yaml by the implement skill
2. Process it next (before continuing to the originally next story)
3. After CS-*: regenerate remaining story files if architecture was amended

### 7b-parallel. Per Wave (Parallel Mode)

For each wave with parallel execution:

1. **Tag baselines:** `git tag pre-{feature}-wave-{N}`
2. **Create story files:** Spawn story-creator-agent for each story in the wave (parallel Task tool calls)
3. **Present stories:** Show all wave stories for review
   ```
   === Wave {N}: {count} stories ===
   | # | Story | Tasks | Size |
   [C] Continue all  [E] Edit  [P] Pause
   ```
   **HALT — wait for user approval.** On [P]: Display: `Session paused before wave {N} execution. Resume with /start.` On resume, `/start` routes to implement phase; the wave stories are re-presented from sprint-status.yaml.

4. **Launch Agent Team:**
   - One teammate per story in the wave
   - Each teammate invokes the full `/implement` skill autonomously
   - Lead coordinates in delegate mode
   - Teammates cannot modify files outside their story scope

5. **Wave Checkpoint:**
   ```
   === Wave {N} Complete ===

   | Story | Tasks | Tests | Gate 5 | Commit Range |
   |-------|-------|-------|--------|-------------|
   | {id}  | {t/T} | +{n} | PASS   | {sha..sha}  |

   Integration: {tooling.test} → {total} tests passing

   [C] Continue to Wave {N+1}  [R] Review specific story  [U] Undo wave  [P] Pause
   ```
   **HALT — wait for user response.** On [P]: Wave stories are already committed. Display: `Session paused after wave {N}. Resume with /start.` On resume, `/start` routes to implement phase; remaining waves continue from sprint-status.yaml state.

6. **On wave pass:**
   - Update sprint-status.yaml: all wave stories → `done`
   - `git tag post-{feature}-wave-{N}`
   - Increment storiesDone for all stories
   - Update metrics: `metrics.execution.parallelWaves += 1`, `metrics.execution.parallelStories += {count}`

### 7c. Between Stories

```
═══ LAIM ═══ Story {id} complete ═══
Progress: {done}/{total} stories

[N] Next: {next-title}  [J] Jump  [S] Skip  [P] Pause
```

On [P]: Previous story is already complete (Gate 5 passed, `currentStory` cleared). Display: `Session paused between stories. Resume with /start.` On resume, `/start` sees `currentPhase: implement` + `currentStory` null → picks next story from sprint-status.yaml.

In parallel mode: between-stories checkpoint is replaced by wave checkpoint above (§7b-parallel step 5).

### 7c.1. Wave Transition Verification

When the last story in wave N completes, before starting wave N+1:

1. **Build check:** Run `{tooling.build}` — typed languages catch cross-story parameter/signature mismatches at compile time
2. **Integration test:** Run `{tooling.test}` — full test suite catches behavioral regressions across stories
3. **Present wave transition checkpoint:**
   ```
   ═══ Wave {N} → Wave {N+1} Transition ═══

   Build: ✅ PASS / ❌ FAIL ({error summary})
   Tests: {passing}/{total} passing ({new_failures} new failures)

   [C] Continue to Wave {N+1}  [F] Fix failures  [H] Halt
   ```
4. **HALT** before starting wave N+1 — user must approve transition
5. Update metrics: `metrics.quality.interfaceAudits += 1`, `metrics.quality.interfaceMismatches += {count}`

If build or tests fail with type/signature errors, this likely indicates a cross-story interface mismatch. Route to `[F] Fix` which investigates the mismatch and may create a CS-* change story.

If `{tooling.build}` is not configured: skip build check, note "no build tooling configured — skipping compile-time interface check".

### 7d. Tech Debt Check

After each story, if `docs/concerns.md` has ≥5 medium-severity or any high-severity items:
```
⚠️ Tech Debt Alert: {count} concerns ({high} high)
Review docs/concerns.md before continuing.
[A] Acknowledge and continue  [F] Fix first
```

### Post-Implementation DevOps Suggestion

When all stories in sprint-status.yaml are `done`, before displaying Feature Completion:

1. If `state.json` `devops.pass2` is NOT `"complete"`:
   ```
   All stories implemented. Production infrastructure not yet generated.

   [D] Run /devops pass-2 now (recommended — scans codebase, generates Terraform/CI/CD with actual values)
   [S] Skip — complete feature without production infra
   [C] Complete without infrastructure
   ```
2. If `devops.pass2` is already `"complete"` → proceed directly to Feature Completion.

## 8. Feature Completion

When all stories in sprint-status.yaml are `done`:
```
═══ LAIM ═══ Feature Complete: {name} ═══
Stories: {N}/{N}  │  Tech Debt: {n}  │  Amendments: {n}  │  Time: {duration}
All stories implemented and verified. 🎉
Commits are local only — push when ready.
Rollback: git revert --no-commit pre-{feature}-{id}..post-{feature}-{id}
```
Remove `docs/.lock`. Update state.json: `currentPhase` → `complete`. Compute final metrics: `metrics.stories.avgTasksPerStory` = `(metrics.tasks.totalCompleted + metrics.tasks.totalCompletedNoCommit) / metrics.stories.completed`, `metrics.tasks.avgVerificationCycles` = `metrics.tasks.totalVerificationCycles / (metrics.tasks.totalCompleted + metrics.tasks.totalCompletedNoCommit)`.

## 9. Context Window & Restart-from-Checkpoint

**Context accumulation:** Each phase adds skill instructions to the conversation. By Phase 5, the conversation may include instructions from all prior phases plus implementation artifacts. Claude Code compacts (summarizes) the conversation automatically when the context limit is approached — this is expected and normal.

**Signs of context degradation:**
- Claude forgets earlier instructions or conventions
- Responses become less structured or miss checkpoint formatting
- Gate criteria are evaluated incompletely

**Restart-from-checkpoint:** If context degradation is noticeable, the user can start a fresh conversation and re-invoke `/start`. The framework detects the existing state.json and resumes from the current checkpoint:
1. All completed phases are preserved (artifacts on disk with `status: complete`)
2. The current phase resumes with full skill instructions freshly loaded
3. No work is lost — only in-progress conversation context between the last checkpoint and the restart

**Proactive compaction in implement phase:**
During the story loop, every 3 completed tasks trigger a summary write to state.json (see implement SKILL.md "Context Compaction"). Only the 2 most recent tasks are kept in full detail. This extends the effective context window for long stories.

**Tool-call compaction hook:** LaiM installs a PreToolUse hook (`hooks/suggest-compact.sh`)
that counts Edit/Write calls and suggests `/compact` at configurable thresholds. This provides
session-wide compaction reminders independent of the implement skill's per-3-task compaction.
The hook is found at `.claude/hooks/suggest-compact.sh` (local) or `~/.claude/hooks/suggest-compact.sh` (global).

**Recommendation for complex features (>5 stories):**
Consider restarting the conversation between stories. Each story starts fresh from sprint-status.yaml and the story file, so no cross-story context is needed in the conversation.

## 10. Error Handling

**Corrupted state.json:**
Reconstruct from available sources in priority order:
1. `docs/sprint-status.yaml` → story statuses (highest authority)
2. `git log --tags` → completed stories via `post-{feature}-*` tags
3. Artifact frontmatter `status: complete` → phase completion
Present reconstructed state → user confirms before proceeding.

**Stale lock (>4 hours):**
```
Stale lock detected ({hours}h ago). Previous session likely crashed.
[T] Take over — break lock  [C] Cancel
```

**State/artifact mismatch:**
If state.json says a phase is complete but artifact is missing or incomplete:
```
⚠️ State mismatch: {phase} marked complete but {artifact} missing.
[R] Re-run phase  [F] Fix state to match reality  [C] Cancel
```
