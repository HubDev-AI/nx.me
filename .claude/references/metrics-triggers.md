# Metrics Write Reference

Skills MUST update the following metrics at the specified moments. Unless noted otherwise, all paths are relative to `metrics.*` in state.json.

## Phase lifecycle (all skills with gates)
- **Root-level** `phases.{phase}.startedAt` → set ISO timestamp when phase skill begins (first invocation only, skip if already set). Path: `phases.{phase}.startedAt` (NOT under `metrics`)
- **Root-level** `phases.{phase}.completedAt` → set ISO timestamp on gate pass. Path: `phases.{phase}.completedAt` (NOT under `metrics`)
- `phases.{phase}.durationMinutes` → compute `(completedAt - startedAt) / 60000`, rounded
- `phases.{phase}.gateAttempts += 1` → every time a gate is presented (pass or fail)
- `phases.{phase}.revisions += 1` → every `[R] Revise` selection at any checkpoint within the phase

## Gates (all skills with gates)
- `gates.passes += 1` → gate PASS (Gates 1-5)
- `gates.fails += 1` → gate FAIL
- `gates.overrides += 1` → `[O] Override` selected
- `gates.backNavigations += 1` → cross-phase `[B] Back` selected
- `gates.blockingFails += 1` → gate FAIL with no override option (e.g., CQ-3/CQ-4)

## Specify phase (specify skill)
- `phases.specify.personaCount` → number of personas spawned
- `phases.specify.personaConcerns` → total concerns raised across all personas

## Architecture phase (architecture skill)
- `phases.architecture.deferredDecisions` → count of DD-* items marked DEFERRED at gate time
- `phases.architecture.resolvedDecisions` → count of DD-* items resolved at gate time

## Plan phase (plan skill)
- `phases.plan.wavesPlanned` → wave count in sprint-status.yaml at gate time

## Stories (start.md story loop + implement skill)
- `stories.completed += 1` → Gate 5 pass
- `stories.skipped += 1` → story `[S] Skip`
- `stories.changeStoriesCreated += 1` → CS-* story inserted via `[X] Change Direction`
- `stories.gate5Passes += 1` → Gate 5 PASS
- `stories.gate5Fails += 1` → Gate 5 FAIL
- `stories.gate5Overrides += 1` → Gate 5 `[O] Override`
- `stories.sizeDistribution.{S|M|L} += 1` → per story at story start, from sprint-status.yaml size

## Tasks (implement skill)
- `tasks.totalCompleted += 1` → task committed successfully
- `tasks.totalCompletedNoCommit += 1` → task completed without commit (verification-only, no file changes)
- `tasks.totalSkipped += 1` → task `[S] Skip`
- `tasks.totalRevisions += 1` → `[R] Revise` at task checkpoint
- `tasks.totalVerificationCycles += 1` → each verify→fix loop iteration
- `tasks.firstPassSuccess += 1` → task where verification cycle 1 passes with zero `[R] Revise`
- `tasks.tddCount += 1` → task implemented test-first
- `tasks.tddTotal += 1` → every completed task with file changes (denominator for TDD rate; excludes verification-only tasks with committed: false)

## Code review (implement skill, per story)
- `codeReview.reviewsRun += 1` → code-review-agent spawned
- `codeReview.totalFindings += {count}` → findings from review
- `codeReview.criticalFindings += {count}` → Critical severity
- `codeReview.highFindings += {count}` → High severity
- `codeReview.mediumFindings += {count}` → Medium severity
- `codeReview.lowFindings += {count}` → Low severity
- `codeReview.findingsDeferred += {count}` → findings sent to concerns.md instead of fixed

## Quality (implement skill + architecture skill)
- `quality.interfaceAudits += 1` → interface audit run (pre-story)
- `quality.interfaceMismatches += {count}` → mismatches detected
- `quality.amendments += 1` → A-* entry added to amendments.md
- `quality.concerns += 1` → entry added to concerns.md
- `quality.concernsBySeverity.{level} += 1` → per concern severity
- `quality.disabledTestsDetected += {count}` → VERIFY.md §4 grep found test-disable annotations in changed files
- `quality.testIntegrityViolations += 1` → VERIFY.md §3d.1 test integrity gate caught a violation

## Drift (implement skill)
- `drift.taskDeviations += 1` → D-* deviation logged during task execution
- `drift.storiesResizedDuringImpl += 1` → actual task count exceeds size threshold (S: >3, M: >6, L: >10)

## Estimation (start.md story loop, computed at feature completion)
- `estimation.sizeAccuracy.{S|M|L}.planned += 1` → story of that size started
- `estimation.sizeAccuracy.{S|M|L}.avgActualTasks` → recompute as running average at each story completion

## Execution (start.md + all skills)
- `execution.totalSessions += 1` → each `/start` resume (not first initialization)
- `execution.pauseResumeCount += 1` → each `[P] Pause` selection
- `execution.agentTeamsUsed = true` → parallel wave execution chosen
- `execution.parallelWaves += 1` → parallel wave completed
- `execution.parallelStories += {count}` → stories in completed parallel wave
- `execution.subagentSpawns += 1` → each Task tool call within implement skill

## Optional skills (each standalone skill, on completion)
- `optionalSkills.designer.used = true`, `.mode = "A"|"B"|"C"`, `.completedAt = {ISO}` → /designer completion
- `optionalSkills.devopsPass1.used = true`, `.completedAt = {ISO}` → /devops pass-1 completion
- `optionalSkills.devopsPass2.used = true`, `.completedAt = {ISO}` → /devops pass-2 completion
- `optionalSkills.qa.used = true`, `.completedAt = {ISO}` → /qa completion
- `optionalSkills.notion.used = true`, `.syncCount += 1`, `.completedAt = {ISO}` → /notion completion

## Git (implement skill, per task commit)
- `git.totalCommits += 1` → each task commit
- `git.totalFilesChanged += {count}` → from `git diff --stat` of task commit
- `git.totalInsertions += {count}` → from `git diff --stat`
- `git.totalDeletions += {count}` → from `git diff --stat`
- `git.testsAdded += {count}` → new test files created in task commit

## Computed at feature completion (start.md, after all stories done)
- `stories.avgTasksPerStory` → `(tasks.totalCompleted + tasks.totalCompletedNoCommit) / stories.completed`
- `tasks.avgVerificationCycles` → `tasks.totalVerificationCycles / (tasks.totalCompleted + tasks.totalCompletedNoCommit)`
