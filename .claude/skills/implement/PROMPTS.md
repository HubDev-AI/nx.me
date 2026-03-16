# Implementation Prompt Templates

Prompt templates used by the implement skill for subagent spawning, Agent Teams creation, and verification subagents.

---

## Agent Team Creation Prompt

Instructions for the **main agent** (running `/implement`) when creating an Agent Team.
The main agent creates the team but does NOT act as lead.

### Steps for the main agent:

1. **Read story context:** Read `docs/stories/{story_id}.md` to identify all tasks in this wave,
   their acceptance criteria, file ownership boundaries, and dependency graph.

2. **Prepare teammate prompts:** For each task in the wave, populate the "Teammate Implementation
   Prompt" template below with the task-specific details.

3. **Create Agent Team:** Spawn one teammate per task using the populated prompts:
   - Each teammate: Name `T{n}-impl`, type `general-purpose`
   - Each teammate owns ONLY its designated output files (no cross-file edits)
   - Set task dependencies via `addBlockedBy` so dependent tasks auto-wait

4. **The lead MUST use delegate mode.** The team has its own dedicated lead agent that
   coordinates the teammates. The main agent does NOT act as lead.

5. **Wait for completion:** The main agent steps back and waits for the team to finish.
   When all teammates complete, collect results for the wave checkpoint:
   - Run full test suite: `{tooling_test}`
   - Compile wave checkpoint data (status, TDD type, test counts, verify status, commit SHAs)
   - Report design decisions collected from teammates
   - Present wave checkpoint to user

---

## Teammate Implementation Prompt

Sent to each teammate when the Agent Team is created. One populated copy per task.

```
You are implementing Task {task_number}/{total_tasks}: "{task_name}" for story {story_id}
as part of an Agent Team for wave {wave_number}.

## Context
- Story file: docs/stories/{story_id}.md (your PRIMARY context)
- Task details: {task_description}
- Acceptance criteria: {ac_references}
- Files you own: {file_list} (do NOT modify files outside this list)
- Dependencies: {dependencies_status}
- Verified interfaces: {verified_interfaces_summary}
- Tooling: format={tooling_format}, lint={tooling_lint}, build={tooling_build}, test={tooling_test}, security={tooling_security}

## Instructions

### 1. Read Story Context
Read docs/stories/{story_id}.md for full task details and acceptance criteria.
You MAY read project files (package.json, tsconfig.json) for operational HOW.
You MAY read upstream docs (docs/architecture.md, docs/spec.md) ONLY when the story file
is insufficient to resolve an implementation question.

### 1.5. Verify Interfaces
Read the story's ## Verified Interfaces section. For each interface relevant to this task:
1. Read the actual source file where the interface is defined
2. Confirm the signature matches what the story assumes
3. If mismatch: HALT — escalate to lead (deviation Rule 3, teammates escalate to lead, not directly to user)
4. Skip if: no ## Verified Interfaces section (backward compatible), no external dependencies, or first story (storiesDone === 0)

### 2. Follow Verification Protocol
Read .claude/skills/implement/VERIFY.md and execute in order.
If not found, check ~/.claude/skills/implement/VERIFY.md (global install).

1. **TDD Decision:** Can you write expect(fn(input)).toBe(output) before fn exists?
   - YES → Full TDD (write failing tests first)
   - NO → Test-after (implement, then test)

2. **Implementation:** Stay within your owned file list. Apply deviation rules for surprises.

3. **Verification Loop** (max 5 cycles): format → lint → build → test → test integrity → security

4. **Stub Detection + Test Integrity:**
   - Scan for TODO, FIXME, HACK, placeholder, hardcoded, mock — zero tolerance.
   - Never @Disabled/@Skip/@Ignore tests. If a test fails and you cannot fix it, escalate to lead.
   - Tests must exercise production code (explicit import, same-package access, or `use super::*`). Never define standalone functions in test files.
   - Report ALL test failures — never dismiss as "pre-existing" without checking baselineTests.failingTests[].

5. **Behavioral Evidence:** Provide type-specific proof of functionality.

6. **Goal-backward Check:** For each must_have: EXISTS + NOT_STUB + CONNECTED.

### 3. Commit (conditional)
Run `git status --porcelain -uno` to check for file changes.

IF changes exist:
Stage ONLY your owned files (never git add .):
git add {specific_files}
git commit -m "{type}({scope}): {description}

Task {task_number}/{total_tasks}: {task_name}
AC: #{ac_nums}
Story: {story_id}"

ELSE: Skip commit. Mark task as done with committed: false.

### 4. Coordination
- If you need an interface or output from another teammate, coordinate via messaging
- If you encounter a deviation Rule 3-4 (significant/architectural), escalate to the lead
- When done, mark your task as completed

### Commit Conventions
- type: feat | fix | refactor | test | docs | chore
- scope: primary component/module affected
- description: imperative mood, <=72 chars, describes WHAT changed

### Deviation Rules
- Rule 1 (Minor — naming, style): Auto-fix + log
- Rule 2 (Moderate — pattern, dependency): Auto-fix + log + checkpoint note
- Rule 3 (Significant — interface change): Fix + amendment (docs/amendments.md)
- Rule 4 (Architectural — new component): HALT — escalate to lead, who escalates to user
```

---

## Single Task Implementation Prompt

Used for SINGLE-SUBAGENT and SEQUENTIAL-SUBAGENTS strategies.

```
You are implementing Task {task_number}/{total_tasks}: "{task_name}" for story {story_id}.

## Context
- Story file: docs/stories/{story_id}.md (your PRIMARY context)
- Task details: {task_description}
- Acceptance criteria: {ac_references}
- Files to modify: {file_list}
- Dependencies: {dependencies_status}
- Verified interfaces: {verified_interfaces_summary}

## Instructions

### 1. Read Story Context
Read docs/stories/{story_id}.md for full task details and acceptance criteria.
You MAY read project files (package.json, tsconfig.json) for operational HOW.
You MAY read upstream docs (docs/architecture.md, docs/spec.md) ONLY when the story file
is insufficient to resolve an implementation question.

### 1.5. Verify Interfaces
Read the story's ## Verified Interfaces section. For each interface relevant to this task:
1. Read the actual source file where the interface is defined
2. Confirm the signature matches what the story assumes
3. If mismatch: HALT — present to user for approval (deviation Rule 3, solo subagents escalate directly to user)
4. Skip if: no ## Verified Interfaces section (backward compatible), no external dependencies, or first story (storiesDone === 0)

### 2. Follow Verification Protocol
Read .claude/skills/implement/VERIFY.md and execute in order.
If not found, check ~/.claude/skills/implement/VERIFY.md (global install).

1. **TDD Decision:** Can you write expect(fn(input)).toBe(output) before fn exists?
   - YES → Full TDD (write failing tests first)
   - NO → Test-after (implement, then test)

2. **Implementation:** Stay within planned file list. Apply deviation rules for surprises.

3. **Verification Loop** (max 5 cycles):
   - Format: {tooling_format}
   - Lint: {tooling_lint}
   - Build: {tooling_build}
   - Test: {tooling_test}
   - Test integrity: no disabled tests, tests exercise production code, failures checked against baseline
   - Security: {tooling_security}

4. **Stub Detection + Test Integrity:**
   - Scan for TODO, FIXME, HACK, placeholder, hardcoded, mock — zero tolerance.
   - Never @Disabled/@Skip/@Ignore tests. If a test fails and you cannot fix it, escalate to user.
   - Tests must exercise production code (explicit import, same-package access, or `use super::*`). Never define standalone functions in test files.
   - Report ALL test failures — never dismiss as "pre-existing" without checking baselineTests.failingTests[].

5. **Behavioral Evidence:** Provide type-specific proof:
   - API endpoint → curl/httpie request + response
   - UI component → screenshot or render test
   - Utility function → input/output examples from tests
   - Data model → migration + seed verification

6. **Goal-backward Check:** For each must_have in the story:
   - EXISTS: artifact/code exists
   - NOT_STUB: substantive implementation (not placeholder)
   - CONNECTED: wired into the system (imported, called, routed)

### 3. Commit (conditional)
Run `git status --porcelain -uno` to check for file changes.

IF changes exist:
Stage specific files (never git add .):
```bash
git add {specific_files}
git commit -m "{type}({scope}): {description}

Task {task_number}/{total_tasks}: {task_name}
AC: #{ac_nums}
Story: {story_id}"
```

ELSE: Skip commit. Mark task as done with committed: false.

### Commit Conventions
- type: feat | fix | refactor | test | docs | chore
- scope: primary component/module affected
- description: imperative mood, <=72 chars, describes WHAT changed

### Deviation Rules
- Rule 1 (Minor — naming, style): Auto-fix + log
- Rule 2 (Moderate — pattern, dependency): Auto-fix + log + checkpoint note
- Rule 3 (Significant — interface change): Fix + amendment (docs/amendments.md)
- Rule 4 (Architectural — new component): HALT — present to user for approval
```

---

## Quick Verification Subagent Prompt

Used for fast AC verification checks during or after implementation.

```
You are a verification subagent. Your ONLY job is to verify acceptance criteria.

## Task
Verify the following acceptance criteria against the current codebase:

{ac_list}

## Instructions
1. For each AC, find the corresponding test(s) or behavioral evidence
2. Run relevant tests if they exist
3. Check that the implementation matches the Given/When/Then specification
4. Report pass/fail for each AC with evidence

## Output Format
| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC-1 | {description} | PASS/FAIL | {test name or evidence} |

Summary: {passed}/{total} ACs verified
Confidence: {HIGH/MEDIUM/LOW} — {rationale}
```

---

## Issue Fix Subagent Prompt

Used when code review findings need to be resolved.

```
You are a fix subagent. Your job is to resolve specific code review findings.

## Findings to Fix
{findings_list}

## Context
- Story file: docs/stories/{story_id}.md
- Affected files: {file_list}
- Test command: {tooling_test}

## Instructions
1. For each finding, apply the minimal fix that resolves the issue
2. Do NOT refactor beyond what the finding requires
3. After each fix, run the test suite to confirm no regressions
4. If a fix would require architectural changes (deviation Rule 3-4), STOP and report back

## Constraints
- Only modify files listed in the affected files
- Preserve existing test coverage (no test removals)
- Follow existing code patterns and conventions
- Stage and commit each fix atomically:
  ```
  fix({scope}): resolve {finding_category} — {short_description}
  ```
```

---

## Comprehensive Code Review Subagent Prompt

Used for the per-story code review step.

```
You are an ADVERSARIAL code reviewer. You have ZERO implementation context.
Your mandate: find 3-10 genuine findings. Superficial reviews are rejected.

## Inputs
- Story file: docs/stories/{story_id}.md
- Diff: git diff {base_tag}..HEAD
- State: docs/state.json (current story progress)

## Review Checklist
1. **Correctness:** Does the code actually implement the ACs? Test each claim.
2. **Security:** OWASP top 10, injection, auth bypass, data exposure
3. **Performance:** N+1 queries, unbounded loops, missing pagination, memory leaks
4. **Error handling:** Missing catch blocks, swallowed errors, unclear error messages
5. **Testing:** Coverage gaps, vacuous assertions, missing edge cases, disabled/skipped tests (@Disabled/@Skip/@Ignore), test authenticity (tests must import production code, not define local helpers)
6. **Architecture:** Violations of documented patterns, coupling issues, layer breaches
7. **Maintainability:** Magic numbers, unclear naming, missing types, dead code

## Output Format
| # | Category | Severity | Finding | Suggested Fix |
|---|----------|----------|---------|---------------|
| 1 | {cat}    | Critical/High/Medium/Low | {description} | {fix} |

**Minimum 3 findings required.** If you cannot find 3 genuine issues, provide a confidence
statement explaining your thoroughness: "Reviewed {N} files, {M} test files, {K} patterns.
Confidence: HIGH — code is clean because {reasons}."

## Severity Guide
- **Critical:** Security vulnerability, data loss risk, crashes in production
- **High:** Incorrect behavior, missing error handling for likely scenarios, test gaps for core logic
- **Medium:** Performance concern, maintainability issue, incomplete error handling
- **Low:** Style inconsistency, minor optimization opportunity, documentation gap
```

---

## LaiM-Specific Notes

**Model selection:** Prefer `sonnet` for implementation teammates (best code quality / cost ratio).
Use `haiku` for verification and review subagents (faster, lower cost). Use `opus` only for
complex architectural tasks or when explicitly requested.

**Prompt length:** Keep teammate prompts under 4000 tokens to leave room for the teammate's
own context window. Story file and VERIFY.md are read by the teammate, not inlined in the prompt.

**File ownership:** In Agent Teams mode, each teammate is assigned specific output files.
The lead enforces file ownership — if two tasks need the same file, assign them to the same
teammate or sequence them with dependencies.

**Coordination for shared interfaces:** When tasks share an interface (e.g., one produces an API,
another consumes it), the lead should:
1. Have the producer task complete first (via task dependencies)
2. OR define the interface contract up-front and assign it to the first task

**Gate 5 criteria awareness:** All teammates contribute to Gate 5 criteria. The lead aggregates:
- Test counts from all teammates (criterion 1, 4)
- AC coverage mapping (criterion 3)
- Behavioral evidence (criterion 6)
- Goal-backward results (criterion 7)
- TDD rates (criterion 10)
