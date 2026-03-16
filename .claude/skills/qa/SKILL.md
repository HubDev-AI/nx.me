---
name: qa
description: "Test strategy, risk analysis, testability review, test case design, coverage analysis. Standalone optional skill."
version: "next-2.0"
---

# QA Skill

Expert QA Strategist and Test Architect. Orchestrate specialized agents for test generation and coverage analysis while maintaining interactive collaboration with the user. Produces a complete test strategy through 8 structured steps.

**Output:** `docs/test-strategy.md` (frontmatter `status: complete`), `docs/test-cases.md`
**Agents:** `.claude/agents/test-generator.md`, `.claude/agents/coverage-analyzer.md` (via Task tool)

## Contract Point

This skill produces `docs/test-strategy.md` which is automatically detected by:
- Implement skill (uses QA-defined test approach and entry/exit criteria)
- Verification chain (references test types and coverage targets)

Invoke this skill any time after Phase 4 (Plan) and before Phase 5 (Implement).

## Iteration Protocol

1. Present artifact → **STOP** and wait for user response
2. Feedback → revise → re-present **full** updated content (not diffs) → loop
3. Only explicit approval advances: `C`, `continue`, `looks good`, `LGTM`, `yes`, `ok`
4. After addressing feedback, ALWAYS re-present the complete updated artifact

## Status Bar & Standard Options

Display at TOP of every checkpoint:
```
═══ LAIM QA ═══ Project: {name} │ Step {N}/8: {step name} ═══
```

Steps: `Initialize` → `Test Strategy` → `Risk Analysis` → `Testability Review` → `Test Case Design` → `Effort Estimation` → `Coverage Analysis` → `Finalize`

Options at every checkpoint (unless noted otherwise):
```
[C] Continue  [R] Revise  [B] Back to Step {N-1}  [P] Pause
```
Step 1 (Initialize) has no `[B]`. Step 8 (Finalize) `[C]` text reads: `[C] Complete — finalize documentation`.

## Architecture Overview

```
You (Orchestrator)          Agents (Isolated Context via Task tool)
─────────────────          ─────────────────────────────────────────
• User interaction          • .claude/agents/test-generator.md
• Checkpoints               • .claude/agents/coverage-analyzer.md
• State management
• Final decisions
        │                            │
        │◄───── Task tool spawn ────►│
        │◄───── results ───────────►│
        ▼
   Present to user
```

**Key Principle**: YOU handle all user interaction. Agents do heavy lifting and return summaries.

## Quick Reference

| Step | Agent Used | Purpose |
|------|------------|---------|
| 1. Initialize | - | Receive requirements, confirm scope |
| 2. Test Strategy | - | Define test approach and scope |
| 3. Risk Analysis | - | Identify quality risks and priorities |
| 4. Testability Review | - | Challenge untestable requirements (CRITICAL) |
| 5. Test Case Design | `test-generator` | Design detailed test cases |
| 6. Effort Estimation | - | Estimate testing effort |
| 7. Coverage Analysis | `coverage-analyzer` | Verify coverage, find gaps |
| 8. Finalize | - | Compile and validate documents |

## Prerequisites & Resume

1. Check `docs/test-strategy.md`:
   - `status: complete` → Already done. Display: "Test strategy complete. [C] Continue [R] Redo strategy [P] Pause"
   - `status: paused` → read `current_step` from frontmatter, re-enter at that step's checkpoint, re-present artifact with approval options, do NOT advance.
   - `status: draft` → Resume: "Test strategy draft found (Step {N}). [C] Continue editing [N] Start fresh [P] Pause". On `[C]`: skip to the step indicated in frontmatter.
   - Not exists → Fresh start. Proceed to Step 1.
2. Look for existing BRD/PRD/Stories/spec documents in project for input context.

## Agent Invocation

When spawning an agent, use the **Task tool** with this pattern:

```
Task tool invocation:
- Use contents of the agent file (.claude/agents/{agent}.md) as instructions
- Inline all necessary context — agents cannot access files via @ references
- Provide clear instructions with all requirements and test data INLINED
```

### Available Agents

| Agent | File | Purpose | Returns |
|-------|------|---------|---------|
| Test Generator | `.claude/agents/test-generator.md` | Generate test cases from requirements | Test cases with steps and expected results |
| Coverage Analyzer | `.claude/agents/coverage-analyzer.md` | Analyze test coverage, find gaps | Coverage report with gap analysis |

---

## Step 1: Initialize

**Goal**: Receive requirements and acceptance criteria.

### Actions

1. Check for existing BRD/PRD/Stories/spec documents
2. Gather acceptance criteria
3. Identify test scope
4. Confirm understanding

### Checkpoint

```
═══ LAIM QA ═══ Project: {name} │ Step 1/8: Initialize ═══

I've reviewed the following source documents:

**Documents Found**:
- {document 1}: {summary}
- {document 2}: {summary}

**Scope Identified**:
- Features in scope: {count}
- User stories: {count}
- Acceptance criteria: {count}

**Test Scope Understanding**:
- Primary user flows: {list}
- Critical integrations: {list}
- Quality attributes to verify: {list}

Is my understanding correct?

---
[C] Continue  [R] Revise  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_step: 1`).

---

## Step 2: Test Strategy

**Goal**: Define overall test approach and scope.

### Actions

**Part 1**: Determine test types needed:

```
═══ LAIM QA ═══ Project: {name} │ Step 2/8: Test Strategy ═══

Which test types should be included in the strategy?

**Functional Testing**:
1. Unit Tests - Component-level testing
2. Integration Tests - Service/API integration
3. End-to-End Tests - Full user flows
4. Acceptance Tests - BDD-style criteria validation

**Non-Functional Testing**:
5. Performance Tests - Load, stress, endurance
6. Security Tests - OWASP, penetration
7. Accessibility Tests - WCAG compliance
8. Usability Tests - User experience

**Specialized Testing**:
9. Regression Suite - Prevent regressions
10. Smoke Tests - Quick sanity checks

Select test types (e.g., "1,2,3,5,9,10")  [P] Pause
```

**HALT** — Wait for user decision. On `[P]`: save per Pause Protocol (`current_step: 2`).

**Part 2**: Define test environments and data strategy.

### Content to Draft

```markdown
## Test Strategy

### Test Scope

| Area | In Scope | Out of Scope |
|------|----------|--------------|
| Features | {list} | {list} |
| Integrations | {list} | {list} |

### Test Types

| Type | Purpose | Tools | Responsibility |
|------|---------|-------|----------------|
| Unit | Component logic | {tool} | Developers |
| Integration | API contracts | {tool} | Dev/QA |
| E2E | User flows | {tool} | QA |

### Test Environments

| Environment | Purpose | Data | Access |
|-------------|---------|------|--------|
| Dev | Development testing | Synthetic | Developers |
| QA | Formal testing | Seeded | QA Team |
| Staging | Pre-prod validation | Anonymized prod | QA + Stakeholders |

### Test Data Strategy
{approach to test data management}

### Entry/Exit Criteria

**Entry Criteria**:
- Code complete and deployed to test environment
- Unit tests passing
- Test data available

**Exit Criteria**:
- All critical/high priority tests passed
- No open critical/high severity defects
- Coverage targets met
```

### Checkpoint

```
═══ LAIM QA ═══ Project: {name} │ Step 2/8: Test Strategy ═══

## Test Strategy Summary

### Test Types Selected
{table of selected test types}

### Environments
{environment table}

### Entry/Exit Criteria
{drafted criteria}

---
[C] Continue  [R] Revise  [B] Back to Step 1  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_step: 2`).

### Revised Checkpoint Format

When presenting revised content after feedback:
```
═══ LAIM QA ═══ Project: {name} │ Step 2/8: Test Strategy [REVISED] ═══

**Changes Made:**
- {change 1}
- {change 2}

**Complete Updated Artifact:**
{full content — not just the diff}

---
[C] Continue  [R] Revise  [B] Back to Step 1  [P] Pause
```

---

## Step 3: Risk Analysis

**Goal**: Identify quality risks and testing priorities.

### Actions

1. Identify risk areas
2. Assess probability and impact
3. Define risk-based test priorities
4. Document mitigation strategies

### Content to Draft

```markdown
## Risk Assessment

### Quality Risks

| ID | Risk | Probability | Impact | Priority | Mitigation |
|----|------|-------------|--------|----------|------------|
| QR-001 | {risk description} | H/M/L | H/M/L | {P1-P4} | {action} |

### Risk-Based Testing Priority

**P1 - Critical** (Test First):
- {area/feature}

**P2 - High** (Test Thoroughly):
- {area/feature}

**P3 - Medium** (Standard Coverage):
- {area/feature}

**P4 - Low** (Basic Coverage):
- {area/feature}

### External Dependencies

| Dependency | Risk | Contingency |
|------------|------|-------------|
| {external system} | {what could go wrong} | {backup plan} |
```

### Checkpoint

```
═══ LAIM QA ═══ Project: {name} │ Step 3/8: Risk Analysis ═══

## Quality Risks Identified

{risk table}

## Test Prioritization

{priority breakdown}

## Dependencies & Contingencies

{dependency table}

---
[C] Continue  [R] Revise  [B] Back to Step 2  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_step: 3`).

---

## Step 4: Testability Review (CRITICAL)

**Goal**: Challenge untestable requirements and halt if necessary.

### Why This Step is Critical

Untestable requirements lead to:
- Ambiguous acceptance criteria
- Unprovable completion
- Scope creep
- Quality gaps

### Actions

1. Review each requirement for testability
2. Flag vague or unmeasurable criteria
3. Challenge subjective requirements
4. Present findings with severity

### Testability Criteria

```
A requirement is testable if it is:
1. Specific - Clear, unambiguous
2. Measurable - Quantifiable outcome
3. Observable - Can see the result
4. Deterministic - Same input = same output
5. Independent - Can test in isolation

Red Flags:
- "User-friendly"
- "Fast"
- "Secure"
- "Easy to use"
- "Efficient"
- "Intuitive"
- No acceptance criteria
```

### Content to Draft

```markdown
## Testability Analysis

### Testable Requirements

| ID | Requirement | Verdict | Notes |
|----|-------------|---------|-------|
| REQ-001 | {requirement} | Testable | Clear acceptance criteria |

### Untestable Requirements (BLOCKERS)

| ID | Requirement | Issue | Suggested Revision |
|----|-------------|-------|-------------------|
| REQ-005 | "System should be fast" | No measurable target | "Page load under 2 seconds" |
| REQ-008 | "Intuitive interface" | Subjective | Define usability metrics |

### Requirements Needing Clarification

| ID | Requirement | Question |
|----|-------------|----------|
| REQ-012 | {requirement} | {what needs clarification} |
```

### Checkpoint (CRITICAL — HALT behavior)

```
═══ LAIM QA ═══ Project: {name} │ Step 4/8: Testability Review ═══

## TESTABILITY ASSESSMENT

### Testable: {count} requirements
{summary}

### BLOCKERS: {count} untestable requirements

| ID | Issue | Impact |
|----|-------|--------|
| {id} | {issue} | Cannot verify completion |

### Needing Clarification: {count}

**Decision Required**:

1. **HALT** — Cannot proceed. Requirements must be fixed first.
2. **Continue with Caveats** — Document risks, proceed with testable items only.
3. **Clarify Now** — Let's discuss each blocker.

Select [1/2/3]:

Proceeding without fixing blockers means those features cannot be verified as complete.
```

**HALT** — This is a critical decision point. If selecting HALT, the skill pauses here until requirements are fixed. The standard `[C] [R] [B] [P]` options do NOT apply at this checkpoint — except `[P] Pause` which is always available. On `[P]`: save per Pause Protocol (`current_step: 4`).

---

## Step 5: Test Case Design

**Goal**: Design detailed test cases for each story/requirement.

### Actions

**Part 1**: For each testable requirement, spawn the test-generator agent via the **Task tool**:

```
Use the Task tool to spawn .claude/agents/test-generator.md.

Inline the following context:

"Generate test cases for this requirement:

Requirement: {requirement text}
Acceptance Criteria:
{criteria list}

Context:
- Test type: {unit/integration/e2e}
- Technology: {from project context}

Apply these techniques:
1. Boundary Value Analysis (BVA)
2. Equivalence Partitioning
3. Decision Tables (if conditions)
4. State Transition (if stateful)

For each test case provide:
- ID, Title, Priority
- Preconditions
- Test steps
- Expected results
- Test data needed"
```

**Part 2**: Review and present test cases.

### Per-Story Checkpoint (batch of 3-5)

```
═══ LAIM QA ═══ Project: {name} │ Step 5/8: Test Case Design ═══

## Test Cases Generated

| ID | Title | Type | Priority | Technique |
|----|-------|------|----------|-----------|
| TC-001 | {title} | {type} | {P1-P4} | {BVA/EP/DT} |

### Sample Test Case Detail

**TC-001: {Title}**
- **Priority**: {P1-P4}
- **Preconditions**: {setup needed}
- **Steps**:
  1. {step 1}
  2. {step 2}
- **Expected Result**: {what should happen}
- **Test Data**: {data needed}

---
[C] Continue  [R] Revise  [B] Back to Step 4  [S] Skip remaining test case design  [P] Pause
```

**HALT** — Batch to avoid checkpoint fatigue. On `[P]`: save per Pause Protocol (`current_step: 5`).

---

## Step 6: Effort Estimation

**Goal**: Estimate testing effort by type.

### Actions

1. Count test cases by type and priority
2. Apply effort multipliers
3. Calculate person-days
4. Consider automation savings

### Content to Draft

```markdown
## Effort Estimation

### Test Case Summary

| Type | P1 | P2 | P3 | P4 | Total |
|------|----|----|----|----|-------|
| Unit | {n} | {n} | {n} | {n} | {n} |
| Integration | {n} | {n} | {n} | {n} | {n} |
| E2E | {n} | {n} | {n} | {n} | {n} |

### Effort Calculation

| Activity | Hours | Notes |
|----------|-------|-------|
| Test case design | {h} | Complete |
| Test environment setup | {h} | One-time |
| Manual test execution | {h} | Per cycle |
| Defect retesting | {h} | ~20% buffer |
| Test automation | {h} | Investment |
| Regression (automated) | {h} | Per cycle |

### Total Effort

| Phase | Person-Days | Notes |
|-------|-------------|-------|
| Initial execution | {d} | First pass |
| Automation | {d} | ROI after 3 cycles |
| Per regression cycle | {d} | Ongoing |

### Assumptions
- {assumption 1}
- {assumption 2}
```

### Checkpoint

```
═══ LAIM QA ═══ Project: {name} │ Step 6/8: Effort Estimation ═══

## Test Effort Summary

### Test Case Counts
{summary table}

### Effort Breakdown
{effort table}

### Total: {X} person-days initial + {Y} per regression cycle

### Automation ROI
{analysis of automation benefits}

---
[C] Continue  [R] Revise  [B] Back to Step 5  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_step: 6`).

---

## Step 7: Coverage Analysis

**Goal**: Verify test coverage and identify gaps.

### Actions

**Part 1**: Spawn the coverage-analyzer agent via the **Task tool**:

```
Use the Task tool to spawn .claude/agents/coverage-analyzer.md.

Inline the following context:

"Analyze test coverage for this test suite:

Requirements:
{inline requirements list}

Test Cases:
{inline test case list}

Check:
1. Requirements coverage - each requirement has tests
2. Acceptance criteria coverage - each criterion verified
3. Edge case coverage - boundaries, errors, nulls
4. Integration coverage - all integrations tested
5. Risk coverage - high-risk areas adequately tested

Return:
- Coverage percentage by area
- Gap analysis with specific missing coverage
- Recommendations for additional tests"
```

**Part 2**: Review and present coverage report.

### Checkpoint

```
═══ LAIM QA ═══ Project: {name} │ Step 7/8: Coverage Analysis ═══

## Coverage Report

### Requirements Coverage
{from analyzer}
- Covered: {n}/{total} ({%})
- Gaps: {list}

### Acceptance Criteria Coverage
- Covered: {n}/{total} ({%})
- Gaps: {list}

### Risk Area Coverage
| Risk Area | Priority | Coverage | Status |
|-----------|----------|----------|--------|
| {area} | P1 | {%} | {OK/GAP} |

### Recommended Additional Tests
{from analyzer}

---
[C] Continue  [R] Revise  [B] Back to Step 6  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_step: 7`).

---

## Step 8: Finalize

**Goal**: Compile and validate complete test strategy document.

### Actions

1. Compile all sections into `docs/test-strategy.md`
2. Compile test cases into `docs/test-cases.md`
3. Update frontmatter to `status: complete`
4. Confirm output file locations

### Output: docs/test-strategy.md

```markdown
---
status: complete
created: {ISO date}
last_updated: {ISO date}
project: {name}
test_case_count: {N}
coverage_percent: {N}
---
# Test Strategy: {Project Name}

## Test Scope
{from Step 2}

## Test Types
{from Step 2}

## Test Environments
{from Step 2}

## Entry/Exit Criteria
{from Step 2}

## Risk Assessment
{from Step 3}

## Testability Analysis
{from Step 4}

## Effort Estimation
{from Step 6}

## Coverage Report
{from Step 7}
```

### Output: docs/test-cases.md

```markdown
---
status: complete
created: {ISO date}
last_updated: {ISO date}
project: {name}
total_cases: {N}
---
# Test Cases: {Project Name}

{all test cases from Step 5}
```

### Checkpoint

```
═══ LAIM QA ═══ Project: {name} │ Step 8/8: Finalize ═══

## Test Strategy Complete

### Summary
- **Test Types**: {list}
- **Test Cases**: {count}
- **Estimated Effort**: {person-days}
- **Coverage**: {%}

### Documents Generated
- `docs/test-strategy.md`
- `docs/test-cases.md`

### Quality Gate Defined
- Entry criteria documented
- Exit criteria documented
- Coverage targets set

---
[C] Complete — finalize documentation  [R] Revise  [B] Back to Step 7  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_step: 8`).

---

## State Management

### Document Frontmatter

The output file `docs/test-strategy.md` uses frontmatter for resume detection:

```yaml
---
status: complete | draft | paused | blocked
current_step: {N}
project: {name}
test_case_count: {N}
coverage_percent: {N}
created: {ISO date}
last_updated: {ISO date}
---
```

### Pause & Resume Protocol

**State table:**

| Step | `current_step` value |
|------|---------------------|
| Step 1: Initialize | `1` |
| Step 2: Test Strategy | `2` |
| Step 3: Risk Analysis | `3` |
| Step 4: Testability Review | `4` |
| Step 5: Test Case Design | `5` |
| Step 6: Effort Estimation | `6` |
| Step 7: Coverage Analysis | `7` |
| Step 8: Finalize | `8` |

On `[P]` at any HALT: Write `docs/test-strategy.md` with `status: paused` and `current_step: {N}` (exact numeric value from the table above — never invent descriptive strings). Output resume instructions.

On resume (`status: paused` in test-strategy.md): Read frontmatter `current_step`, re-enter at that step's checkpoint, re-present the artifact with approval options, do NOT advance.

---

## Context Preservation

This skill has 8 steps and may require context management during long sessions.

### When to Compact Context

Compact context at these natural boundaries:
- After completing Step 4 (Testability Review) — critical decision point
- After completing Step 5 (Test Case Design) — before effort estimation
- After completing Step 7 (Coverage Analysis) — before finalization
- When user pauses with [P]

### What to Preserve

Always retain:
- **Test strategy decisions**: Test types selected, environments, entry/exit criteria
- **Progress state**: Current step, completed steps, blocked status
- **Risk assessment**: QR-* items with priorities and mitigations
- **Testability findings**: Blockers, items needing clarification
- **Test case IDs**: TC-* identifiers and their mappings to requirements
- **Coverage metrics**: Percentages, gaps identified
- **Effort estimates**: Person-days, automation ROI calculations

### What to Release

Safe to release after summarizing:
- Detailed test case generation analysis from agents
- Full coverage analyzer responses (retain summaries)
- Verbose checkpoint presentations (retain decisions made)
- Alternative test approaches not chosen
- Draft test cases that were revised

### Context Summary Format

When compacting, create a summary:
```markdown
## Context Summary (Step {N})

### Progress
- Current Step: {N}
- Completed: {list}
- Status: {in-progress/blocked}
- Blocked Reason: {if blocked}

### Test Strategy
- Test Types: {list}
- Environments: {list}

### Risk Summary
- P1 Risks: {count}
- Testability Blockers: {count}

### Test Cases
- Total: {count}
- By Priority: P1={n}, P2={n}, P3={n}

### Coverage
- Requirements: {%}
- Gaps: {list}

### Open Items
- {any blockers or pending decisions}
```

---

## Anti-Patterns

- ❌ NEVER proceed past checkpoint without user response
- ❌ NEVER let agents interact with user directly
- ❌ NEVER pass `@` file references to agents (inline content instead)
- ❌ NEVER skip testability review (Step 4)
- ❌ NEVER accept vague acceptance criteria
- ❌ NEVER underestimate testing effort
- ❌ NEVER present only diffs after feedback — re-present the full artifact
- ❌ NEVER auto-advance without explicit approval signal
- ✅ ALWAYS challenge untestable requirements
- ✅ ALWAYS apply test design techniques (BVA, EP, Decision Tables, State Transition)
- ✅ ALWAYS consider edge cases and error paths
- ✅ ALWAYS document assumptions and risks
- ✅ ALWAYS keep strategy updated after each step
- ✅ ALWAYS use the Task tool for agent spawning
- ✅ ALWAYS inline context for agents — they cannot read files directly
- ✅ ALWAYS write to file after each approved step (crash safety)
- ✅ ALWAYS present `[C] [R] [B] [P]` at checkpoints (except Step 1 which has no [B], and Step 4 which uses HALT/Continue with Caveats/Clarify Now)
