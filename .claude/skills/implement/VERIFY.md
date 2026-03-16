# Verification Protocol

Read by the implement skill during per-task verification. Contains TDD decision, verification loop, stub detection, behavioral evidence, goal-backward checks, failure handling, and deviation rules.

---

## 0. Interface Verification (pre-implementation)

Before any coding begins, verify that external interfaces this task depends on match expectations:

1. Read the story's `## Verified Interfaces` section
2. For each interface relevant to **this task**: read the actual source file, confirm the signature matches what the story assumes
3. If mismatch detected: **HALT** — deviation Rule 3 (significant interface change). Do not proceed with stale interface assumptions.
4. **Skip if:** no `## Verified Interfaces` section in the story file (backward compatible), OR no external dependencies for this task, OR this is the first story (`storiesDone === 0` — no prior implementations to verify against)

This step catches interface drift that may have occurred between story creation and task execution (e.g., a teammate in a parallel wave changed a signature).

---

## 1. TDD Decision

```
"Can I write expect(fn(input)).toBe(output) before fn exists?"
  YES → Full TDD (write failing tests first)
  NO  → Test-after (implement, then test)
```

**Full TDD:** Pure functions, services, utilities, validators, API handlers, state reducers.
**Test-after:** UI rendering, complex integration, infrastructure, config, migrations. Document rationale.

**Bug fix? → Test-first (default):**
1. Write a failing test that reproduces the reported bug
2. Confirm it fails for the right reason
3. Fix the code
4. Confirm the test passes
5. Run full suite for regressions

**Exception:** If the bug is not reproducible in a test (UI rendering, race condition, environment-specific, config-only):
→ Document why in task checkpoint → fix first → write regression test after → mark "test-after (bug — {reason})"

Tests for NEW functionality must fail before implementation. Integration tests with prior tasks may pass — expected.

**Quality (both paths):** ≥1 test per AC, ≥2 error cases per public function, edge cases (null, empty, boundary). No vacuous assertions.

---

## 2. Implementation

**Full TDD:** Write tests → run (MUST fail) → implement → run (must pass). If all pass before code → tests are weak → **rewrite**.

**Test-after:** Implement → write tests → run (must pass). Same coverage requirements.

Stay within planned file list. Apply deviation rules for surprises (§8).

---

## 3. Verification Loop

Max **5 full cycles** (a full cycle restarts from 3a after any slow-tier failure).
Track: `verifyAttempts: {n}/5` in task state (full cycles).
Track: `fastTierAttempts: {n}/5` in task state (fast tier only).
Each restart logs which step failed and why.

### Fast Tier (format + lint) — max 5 iterations

```
3a. FORMAT → {tooling.format} {changed_files}
3b. LINT   → {tooling.lint_fix} {changed_files}
    On fail → restart from 3a (fast tier only, does NOT count toward the 5 full cycles)
    Max 5 fast-tier iterations — if lint still fails after 5 → escalate to user
```

The fast tier loops independently. A lint failure never triggers a build or test re-run.

### Fast Tier Error State (5 iterations exhausted)

```
⚠ FAST TIER FAILED — 5 format/lint iterations exhausted
Last failure: {step} — {error details}

[R] Retry with guidance  [S] Skip task  [A] Abort story  [H] Show full log
```
**HALT — wait for user response before proceeding.**

### Slow Tier (build + test + test integrity + security) — runs once per full cycle after fast tier passes

```
3c. BUILD    → {tooling.build}
    On fail  → Build Error Resolution:
               1. Parse error → identify file:line
               2. Smallest fix (<5% of file, one error at a time)
               3. NO architecture changes, NO refactoring, NO features
               4. Re-run from 3a (full cycle, counts toward 5 max)
               5. Max 3 build-fix attempts → escalate to user
3d. TEST     → {tooling.test_changed} (if configured)
              OR {tooling.test} (fallback — always used at wave checkpoints and Gate 5)
              If {tooling.test_changed} exits with a runner error (not a test assertion failure),
              fall back to {tooling.test} and log the fallback reason.
    On test failure → route to §3d.1(c) BEFORE slow-tier restart.
    On test pass   → proceed to §3d.1(a).
3d.1 TEST INTEGRITY → Run after tests complete (pass or fail), before security:
    (a) Disabled-test scan (on pass or fail): run §4 test-disable grep on {changed_files}
        Match WITH tracking ref (e.g. @Disabled("JIRA-1234: reason")): INFO — log, proceed.
        Match WITHOUT tracking ref: HALT — present to user.
    (b) Test authenticity (on pass or fail): for each changed test file, verify it exercises
        production code. Acceptable evidence (any one):
        - Explicit import from production source (e.g. `import com.foo.MyService`)
        - Same-package access (Java/Kotlin test in same package as production class)
        - Internal package test (Go `package foo` test accessing unexported symbols)
        - `use super::*` or `use crate::` (Rust module tests)
        Zero evidence of production code access → HALT: "Test {path} has no production code access."
    (c) Baseline comparison (on test failure only): compare failed test names against
        baselineTests.failingTests[].
        - Failure IN baseline → pre-existing, proceed (do not restart).
        - Failure NOT in baseline → HALT as new failure.
        - If baselineTests.failingTests is empty AND baselineTests.failing > 0 (count-only mode):
          compare failure count. If current failures ≤ baseline.failing → proceed with WARNING.
          If current failures > baseline.failing → HALT as new failure(s).
        Never classify a failure as "pre-existing" without this mechanical baseline check.
        After baseline comparison: if only pre-existing failures remain → proceed to (a)/(b).
        If new failures detected → HALT (do NOT restart slow tier — user must decide).
    On any HALT → metrics.quality.testIntegrityViolations += 1
3e. SECURITY → {tooling.security} + secret scan:
    grep -rnE "(password|secret|api_key|private_key)\s*[:=]\s*['\"][^'\"]{8,}['\"]" {changed_files} \
      | grep -v "\.test\.\|\.spec\.\|__tests__\|__mocks__\|\.example\|\.sample" \
      | grep -vi "token_address\|token_symbol\|contract_address\|token_id"

    On any slow-tier fail → restart from 3a (full cycle, counts toward 5 max)
```

If a command is not configured: SKIP with note. If test command missing: WARN.
`tooling.test_changed` is optional — if not configured, falls back to `tooling.test`.

On **all pass** → proceed to stub detection without halting.

### Error State (5 cycles exhausted)

```
⚠ VERIFICATION FAILED — 5 attempts exhausted
Last failure: {step} — {error details}

[R] Retry with guidance  [S] Skip task  [A] Abort story  [H] Show full log
```
**HALT — wait for user response before proceeding.**

---

## 4. Stub Detection

Scan all changed files after verification passes:

```bash
# Stub markers (WARNING on match)
grep -rn "TODO\|FIXME\|HACK\|XXX\|placeholder\|not implemented\|coming soon" {changed_files}

# Empty/hollow implementations
grep -rn "return null;?\s*$\|return undefined;?\s*$\|return {};?\s*$\|return \[\];?\s*$" {changed_files}

# Console-only handlers
grep -rn "{\s*console\.log.*}\s*$" {changed_files}

# Throw-not-implemented
grep -rn "throw new Error.*not impl" {changed_files}

# Python: pass-only methods
grep -rn "^\s*pass\s*$" {changed_files}

# Empty catch blocks
grep -nA1 "catch" {changed_files} | grep -E "^\s*}\s*$"

# Test-disable annotations (flags Gate 5 Criterion 13 — required)
grep -rnE "@Disabled|@Ignore|@Skip|@Pending|\
pytest\.mark\.skip|pytest\.skip|unittest\.skip|\
xit\(|xdescribe\(|xcontext\(|\.skip\(|\.todo\(|\
t\.Skip|t\.SkipNow|b\.Skip|\
#\[ignore\]|\[Ignore\]|\[Fact\(Skip|\[Theory\(Skip|\
enabled\s*=\s*false" {changed_files}
```

Also check: unused imports, functions returning hardcoded values, mock data in production code.

Report: `Stubs: {count} found` — flags at Gate 5 Criterion 12 (recommended).
        `Disabled tests: {count} found` — flags at Gate 5 Criterion 13 (required).

---

## 5. Behavioral Evidence

Type-specific proof the code actually WORKS:

| Task Type | Evidence |
|-----------|----------|
| Service / Business logic | Unit tests with concrete assertions (input → output) |
| API endpoint | Integration test (request → status code + response shape) |
| UI component | Render test (mounts, interaction handlers fire) |
| CLI command | Output capture (args → expected stdout) |
| Database migration | Up + down cycle without error |
| Configuration | Validation test (valid loads, invalid rejects) |
| State management | Transition test (action → state change) |
| Middleware | Chain test (passes through / blocks as expected) |

**Confidence:** High (end-to-end automated) / Medium (unit only) / Low (manual check needed).
If Low → document manual steps in checkpoint.

---

## 6. Goal-Backward Verification

For each `must_haves` entry relevant to this task:

### L1 — EXISTS
```bash
ls -la {must_haves.artifacts[].path}  # File exists?
```

### L2 — NOT A STUB
Run stub detection (§4) specifically on must_have artifacts. If any stub markers found → FAIL.
Additionally check: file has ≥10 non-blank, non-import, non-comment lines.

### L3 — CONNECTED
For each `key_links` entry:
```bash
grep -rn "{pattern}" {in_files}
```
If pattern not found: flag as WARNING (not automatic FAIL). Some connection patterns (dependency
injection, dynamic imports, plugin registration) aren't grep-able. If grep fails, check:
1. Is the component registered via config/IoC? → PASS with note
2. Is there a test that imports and uses it? → PASS with note
3. Neither? → FAIL

Report with nuance:
```
| must_have | exists | not_stub | connected | status |
|-----------|--------|----------|-----------|--------|
| {item}    | ✅     | ✅       | ✅        | PASS   |
| {item}    | ✅     | ✅       | ⚠️ (IoC)   | PASS*  |
```

**Note:** Not all must_haves apply per task. Full verification runs at Gate 5.

---

## 7. Consecutive Failure Protocol

If **3 tasks in a row** fail verification:

```
⚠ 3 CONSECUTIVE FAILURES — Root cause analysis needed

Failed: {task_n-2}, {task_n-1}, {task_n}
Common patterns: {shared error/file/dependency}

[F] Fix root cause — investigate shared issue
[M] Amend architecture — fundamentally wrong (→ docs/amendments.md)
[R] Rollback to last passing task
[S] Stop — save state and exit
```
**HALT — wait for user response before proceeding.** Do NOT attempt a 4th task.

**Indicators:** Same file in all failures → structural. Same test fails → dependency broken. Build cascade → base component.

---

## 8. Deviation Rules

Applied when implementation diverges from story plan.

| Rule | Trigger | Action |
|------|---------|--------|
| **1** | Minor (naming, style, path) | Auto-fix to match codebase + log discrepancy |
| **2** | Moderate (pattern, extra dependency) | Auto-fix + log + note in task checkpoint |
| **3** | Significant (interface, data structure) | Fix + create amendment (`docs/amendments.md`) |
| **4** | Architectural (new component, boundary) | **HALT — wait for user response before proceeding.** Present to user, amendment if approved |

**Amendment format** (Rule 3-4):
```markdown
## Amendment A-{N}: {title}
- **Story**: {story-id}
- **Date**: {ISO date}
- **Original**: {what story specified}
- **Actual**: {what was implemented}
- **Rationale**: {why the change}
- **Affected**: {architecture sections}
```

**Discrepancy tracking:** `D-{N} (Task {t}): Rule {1-4} — Expected: {story} → Actual: {implemented} → Resolution: {action}`
Categories: signature | structure | flow | addition | removal | pattern | architecture

---

## Execution Order Summary

```
 0. Interface verification (check Verified Interfaces against actual source)
 1. Drift detection (git diff)
 2. TDD decision
 3. Implementation (code + tests)
 4. Verification loop:
    - Fast tier (format → lint) — loops until clean, max 5 iterations
    - Slow tier (build → test → test integrity → security) — runs once after fast tier passes
    - Slow-tier failure restarts full cycle from 3a (max 5 full cycles)
 5. Stub detection
 6. Behavioral evidence
 7. Goal-backward (EXISTS → NOT_STUB → CONNECTED)
 8. Task checkpoint (HALT — wait for user)
 9. Atomic commit (specific files only)
10. Context compaction (every 3 tasks)
```

Never skip a step. Never proceed past a HALT point without user approval.
