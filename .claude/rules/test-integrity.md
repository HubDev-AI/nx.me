---
alwaysApply: false
globs: ["*test*", "*spec*", "*Test*", "*Spec*", "*.java", "*.kt", "*.py", "*.ts", "*.js", "*.go", "*.rs", "*.cs", "*.tsx", "*.jsx"]
---

# Test Integrity

These rules are **awareness-layer** guidance. Enforcement is procedural — see VERIFY.md §3d.1 (test integrity gate) and §4 (stub/disable detection grep).

---

## 1. Transparent Reporting

- Report ALL test failures accurately. Never dismiss a failure as "pre-existing" without a mechanical check against `baselineTests.failingTests[]`.
- If you cannot determine whether a failure is pre-existing, HALT and present it to the user — do not silently skip it.
- Every test run must produce a clear pass/fail summary with counts.

## 2. Never Disable Tests

- Never add `@Disabled`, `@Ignore`, `@Skip`, `@Pending`, `pytest.mark.skip`, `unittest.skip`, `xit(`, `xdescribe(`, `.skip(`, `.todo(`, `t.Skip`, `t.SkipNow`, `#[ignore]`, `[Ignore]`, `[Fact(Skip`, `enabled = false`, or any equivalent annotation to silence a failing test.
- If a test fails and you cannot fix it, escalate to the user/lead — do not disable it.
- **Escape hatch:** A disabled test WITH a tracking reference (e.g., `@Disabled("JIRA-1234: flaky due to external service timeout")`) is logged as INFO and allowed to proceed. A disabled test WITHOUT a tracking reference is a HALT violation.

## 3. Tests Must Exercise Real Code

- Every test file must exercise production code. Tests that define standalone helper functions and test only those functions (never accessing production code) are not valid tests.
- Tests must assert on the behavior of production code paths, not on locally-defined mocks or stubs that shadow the real implementation.
- If a test cannot access production code yet (e.g., the module doesn't exist yet in TDD), that is expected — but the access must exist before the task is marked complete.
- **Ecosystem-specific access patterns** — all of the following count as exercising production code (no explicit import required):
  - **Java/Kotlin:** same-package tests accessing production classes without imports
  - **Go:** `package foo` internal tests accessing unexported symbols via same-package membership
  - **Rust:** `mod tests { use super::*; }` or `use crate::` accessing parent module code
  - **Any language:** test file in the same directory/package as production code with implicit access

---

**Enforcement:** VERIFY.md §3d.1 runs a test integrity gate after tests complete (pass or fail) and before the security scan. On test failure, §3d.1(c) performs baseline comparison before any slow-tier restart. VERIFY.md §4 includes a test-disable grep as part of stub detection. Violations increment `metrics.quality.testIntegrityViolations`.
