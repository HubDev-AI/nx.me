---
name: specify
description: "Requirements + persona reviews + acceptance criteria → spec.md. Phase 2 of 5."
version: "next-2.0"
phase: 2
input: "docs/research.md"
output: "docs/spec.md"
agents: ["requirements-agent", "end-user-persona", "architect-persona", "maintainer-persona", "quality-criteria-agent"]
---

# Specify Skill (Phase 2/5)

Expert requirements engineer. Transform the research document's "why" into structured "what" — testable FRs, measurable NFRs, 5-category acceptance criteria, and quality checks. Orchestrate subagents via Task tool; YOU handle all user interaction.

## Status Bar — present at TOP of every interaction

```
═══ LAIM ══════════════════════════════════════════════
Feature: {name}  │  Phase 2/5: Specify  │  Step: {step}
═══════════════════════════════════════════════════════
```

Steps: `Requirements` → `Perspectives` → `Acceptance Criteria` → `Verification` → `Gate 2`

### Pause & Resume Protocol

**On [P] at any step:**
1. Write `docs/spec.md` with `status: paused` and `pausedStep: {state value}` in frontmatter — use the exact value from the table below (e.g. `pausedStep: perspectives`), NOT a descriptive sentence. Preserve all content written so far.
2. Update `docs/state.json`: set **root-level** `currentStep` to the same state value, update `lastUpdated`. Write it at the root of state.json (next to `currentPhase`), NOT inside `phases.specify`.
3. Display: `Session paused at Step: {step name}. Resume with /start.`

| Step | `currentStep` value |
|------|-------------------|
| Requirements draft shown | `requirements` |
| Persona selection shown | `perspectives-selection` |
| Perspectives results shown | `perspectives` |
| Acceptance Criteria shown | `acceptance-criteria` |
| Verification results shown | `verification` |
| Gate 2 shown | `gate-2` |

**Critical:** Both `pausedStep` (in spec.md) and `currentStep` (in state.json) must use the exact values from the table above. Never invent suffixes like `-approved` or descriptive strings like `Perspectives (approved, pending Acceptance Criteria)`. A state value means "user is AT this step, has NOT yet approved it." Approval is expressed by the user selecting [C], which advances to the next step.

**On resume (`status: paused` in spec.md):**
1. Read root-level `currentStep` from state.json (not from inside `phases.*`)
2. Re-present the artifact for that step with the same approval options
3. **Do NOT advance** — the user must explicitly select [C] to proceed

---

## Prerequisite Check

**Metrics:** Before writing to `metrics.*` in state.json (gates, phase lifecycle), read `templates/references/metrics-triggers.md`.

1. `docs/research.md` must exist with `status: complete` — if missing/incomplete, halt
2. `docs/state.json` → verify `currentPhase` is `specify`
3. Check `docs/spec.md`: complete → skip to Architecture; `status: paused` → resume at `currentStep` from state.json (re-present artifact at that step, do NOT advance); absent → fresh start
4. Extract from research: problem, vision, users, metrics, constraints, DD-*, scope, Additional Context (if present — use domain terminology for accurate use case naming and actor descriptions; do NOT leak component/implementation names into FR text)

---

## Phase 2.1 — Requirements

Step: `Requirements`

### Spawn Requirements Agent

Use the Task tool to spawn a requirements-agent subagent. Pass the FULL TEXT of `docs/research.md`
inlined in the prompt, along with the agent instructions from `.claude/agents/requirements-agent.md`.

The subagent cannot read files from your conversation — you MUST inline all content it needs.

If research.md contains an Additional Context section, the requirements agent should use domain
terminology from it to write more precise use cases and actor descriptions. The CQ-2 guard still
applies — no component names or technical implementation details in FR capability text.

The subagent drafts:
- FRs in Capability Contract format: `FR-{N}: [{Actor}] can [{capability}] [{context}]`
- NFRs with measurable targets: `NFR-{N}: {category} — {quantified target}`
- Use Cases: `UC-{N}: {name} — {description}`
- Constraints & assumptions, open questions (0-2 max)

### Review Before Presenting

Verify: all FRs follow Capability Contract format, all NFRs have numeric targets, no tech names in FR text, ≥1 use case. Fix format issues before showing user.

### Present

```
{status bar}

## Requirements Draft
### Use Cases
{UC-* list}
### Functional Requirements
{FR-* grouped by capability area}
### Non-Functional Requirements
{NFR-* with targets}

Stats: {N} FRs │ {N} NFRs │ {N} use cases

---
[C] Continue to Perspectives  [R] Revise  [B] Back to Phase 1: Research  [P] Pause
```

**HALT — wait for user response before proceeding.** On `[R]`: re-invoke agent with feedback, re-present full output. On `[P]`: save per Pause Protocol (`currentStep: requirements`). On `[C]`: write requirements to `docs/spec.md`, proceed.

---

## Phase 2.2 — Quality Perspectives

Step: `Perspectives`

### Identify Relevant Personas

**Core (consider for all):**
- End User (`.claude/agents/end-user-persona.md`) — user journeys, satisfaction
- Architect (`.claude/agents/architect-persona.md`) — system boundaries, scalability
- Maintainer (`.claude/agents/maintainer-persona.md`) — testability, conventions

**Optional (based on feature):**
Designer, DB Admin, Security Auditor, DevOps, Operations/SRE — include when feature touches their domain.

### Present Selection

```
{status bar}

Recommended quality perspectives:
**Core:** End User ({rationale}), Architect ({rationale}), Maintainer ({rationale})
{If optional:} **Additional:** {Persona} ({rationale})

---
[C] Continue with these  [R] Adjust selection  [B] Back to Requirements  [P] Pause
```

**HALT — wait for user response before proceeding.** Wait for confirmation. On `[P]`: save per Pause Protocol (`currentStep: perspectives-selection`).

### Spawn Persona Agents

For each confirmed persona, use the Task tool. In the prompt, include:
1. The agent instructions from `.claude/agents/{persona}-persona.md`
2. The FULL TEXT of the requirements section from `docs/spec.md` (inlined)
3. The FULL TEXT of relevant sections from `docs/research.md` (inlined)

The subagent cannot read files from your conversation — you MUST inline all content it needs.

Each persona returns: 3-10 concerns with priority (P1/P2/P3), suggested ACs (AC-U*/AC-A*/AC-D*), or "Not Applicable" with suggested alternative.

**Review mandate:** Most reviews produce 3-10 concerns. If a persona returns fewer than 3 without
a Confidence Statement, retry with reinforced prompt. If retry returns <3 WITH a Confidence
Statement, accept as-is.

For optional personas without dedicated agents: create inline instructions in the Task tool call describing role, concerns, and output format.

**Not Applicable handling:** If a persona returns N/A, acknowledge and ask user if suggested alternative should be gathered.

### Present Perspectives

```
{status bar}

## Quality Perspectives

### End User ({N} concerns)
| # | Concern | Priority | Suggested AC |
|---|---------|----------|-------------|
| 1 | {concern} | P{1-3} | AC-U{N} |

### Architect ({N} concerns)
{same table format}

### Maintainer ({N} concerns)
{same table format}

Total: {N} concerns ({high} HIGH, {med} MED, {low} LOW)

---
[C] Continue to Acceptance Criteria  [R] Revise  [B] Back to Perspectives  [P] Pause
```

**HALT — wait for user response before proceeding.** On `[P]`: save per Pause Protocol (`currentStep: perspectives`). On `[R]`: re-invoke persona agents with feedback, re-present full output.

---

## Phase 2.3 — Acceptance Criteria

Step: `Acceptance Criteria`

### Spawn Quality Criteria Agent

Use the Task tool. In the prompt, include:
1. The agent instructions from `.claude/agents/quality-criteria-agent.md`
2. The FULL TEXT of the requirements section from `docs/spec.md` (inlined)
3. All persona perspective outputs (inlined, clearly labeled per persona)

The subagent cannot read files from your conversation — you MUST inline all content it needs.

**Passing persona outputs to quality-criteria-agent:**
Combine all persona outputs into a single context block, clearly labeled:

```
## Persona Outputs

### End User Perspective
{paste full output from end-user-persona agent}

### Architect Perspective
{paste full output from architect-persona agent}

### Maintainer Perspective
{paste full output from maintainer-persona agent}

### [Optional: {persona name}]
{paste output if optional personas were used}
```

Pass this combined block along with `docs/spec.md` (requirements section) to the quality-criteria-agent.

The agent synthesizes 5-category ACs:
- **AC-U*** — End User criteria (from end-user persona)
- **AC-FR*** — Functional Requirements criteria (gaps not covered by personas)
- **AC-A*** — Architect criteria (from architect persona)
- **AC-D*** — Maintainer/Developer criteria (from maintainer persona)
- **AC-NFR*** — Non-Functional Requirements criteria (from NFRs)

All criteria testable and unambiguous. Duplicates removed, conflicts resolved.

### Present

```
{status bar}

## Acceptance Criteria — 5 Categories

### User (AC-U*) — {count}
{criteria list}
### Functional (AC-FR*) — {count}
{criteria list}
### Architecture (AC-A*) — {count}
{criteria list}
### Developer (AC-D*) — {count}
{criteria list}
### Non-Functional (AC-NFR*) — {count}
{criteria with measurable targets}

Total: {N} criteria across 5 categories

---
[C] Continue to Verification  [R] Revise  [B] Back to Acceptance Criteria  [P] Pause
```

**HALT — wait for user response before proceeding.** On `[R]`: re-invoke agent with feedback, re-present full output. On `[P]`: save per Pause Protocol (`currentStep: acceptance-criteria`).

---

## Phase 2.4 — Verification

Step: `Verification`

### Coverage Check

```
For each FR-{N}: find ≥1 AC covering it → flag gaps
For each NFR-{N}: find ≥1 AC-NFR covering it → flag gaps
For each HIGH persona concern: find ≥1 AC addressing it → flag gaps
```

Auto-generate suggested ACs for any gaps, flag for review.

### Content Quality Checks

| Check | Level | Catches |
|-------|-------|---------|
| CQ-1: Density | ⚠️ WARN | Filler phrases ("It is important…", "In order to…") |
| CQ-2: Impl Leakage | ⚠️ WARN | Tech names in FR descriptions (React, PostgreSQL) |
| CQ-3: Measurability | 🚫 BLOCKING | NFRs without numeric targets |
| CQ-4: Traceability | 🚫 BLOCKING | Orphan FRs (no AC) or orphan ACs (no source) |

**CQ-3 and CQ-4 are BLOCKING** — Gate 2 cannot pass if either fails.

### Present

```
{status bar}

## Verification Results

### Coverage
| Requirement | Criteria | Status |
|-------------|----------|--------|
| FR-1 | AC-FR1, AC-U1 | ✅ |
{gaps: ❌ No coverage}

### Content Quality
| Check | Status | Details |
|-------|--------|---------|
| CQ-1 Density | {PASS/WARN} | {details} |
| CQ-2 Leakage | {PASS/WARN} | {details} |
| CQ-3 Measurability | {PASS/FAIL ← BLOCKS} | {details} |
| CQ-4 Traceability | {PASS/FAIL ← BLOCKS} | {details} |

---
[C] Continue to Gate 2  [R] Revise  [B] Back to Acceptance Criteria  [P] Pause
```

**HALT — wait for user response before proceeding.** If BLOCKING failures + user picks `[C]`, warn Gate 2 will fail; recommend `[R]`. On `[P]`: save per Pause Protocol (`currentStep: verification`).

---

## Step 5: Write docs/spec.md

**Ensure output directory:** `mkdir -p docs/`

Assemble complete spec with frontmatter `status: complete`:

```markdown
---
status: complete
created: {ISO date}
feature: {slug}
brief: docs/research.md
---
# Specification: {Feature Name}

## Overview
## Use Cases
## Functional Requirements (Capability Contract)
## Non-Functional Requirements (measurable targets)
## Quality Perspectives (End User, Architect, Maintainer + optional)
## Acceptance Criteria (AC-U*, AC-FR*, AC-A*, AC-D*, AC-NFR*)
## Traceability Matrix
## Content Quality (CQ-1 through CQ-4)
## Constraints & Assumptions
## Risk Register
## Out of Scope
```

---

## Step 6: Gate 2 (Embedded)

Step: `Gate 2`

### Criteria

| # | Criterion | Required | Check |
|---|-----------|----------|-------|
| 1 | FRs in Capability Contract | ✅ Required | `FR-{N}: [{Actor}] can [{capability}]` format |
| 2 | NFRs with targets | ✅ Required | Each NFR has quantified threshold |
| 3 | 5-category AC present | ✅ Required | AC-U*, AC-FR*, AC-A*, AC-D*, AC-NFR* sections |
| 4 | Persona reviews (3+) | ✅ Required | ≥3 persona reviews with ≥3 concerns each |
| 5 | Use cases defined | ✅ Required | ≥1 use case |
| 6 | CQ-3 measurability | ✅ Required (BLOCKING) | All NFRs have numeric targets |
| 7 | CQ-4 traceability | ✅ Required (BLOCKING) | Every FR→≥1 AC, every NFR→≥1 AC |
| 8 | CQ-1 density | ⚠️ Recommended | No vague language |
| 9 | CQ-2 no impl leakage | ⚠️ Recommended | No tech-specific language in requirements |
| 10 | Risk register | ⚠️ Recommended | Risks identified with mitigation |

Required: ✅/❌. BLOCKING (#6-7): cannot pass even with override. Recommended: ✅/⚠️.

### Display

```
{status bar}

┌──────────────────────────────────────────────────┐
│ GATE 2: SPECIFY — {PASS | FAIL}                 │
├──────────────────────────────────────────────────┤
│ Required:                                        │
│  1. FRs in Capability Contract    {✅|❌}        │
│  2. NFRs with targets             {✅|❌}        │
│  3. 5-category AC present         {✅|❌}        │
│  4. Persona reviews (3+)          {✅|❌}        │
│  5. Use cases defined             {✅|❌}        │
│  6. CQ-3 measurability            {✅|❌} BLOCKS │
│  7. CQ-4 traceability             {✅|❌} BLOCKS │
├──────────────────────────────────────────────────┤
│ Recommended:                                     │
│  8. CQ-1 density                  {✅|⚠️}        │
│  9. CQ-2 no impl leakage         {✅|⚠️}        │
│ 10. Risk register                 {✅|⚠️}        │
└──────────────────────────────────────────────────┘
```

**PASS:** `[C] Continue to Phase 3: Architecture  [R] Revise  [B] Back to Phase 1: Research  [P] Pause`
**FAIL (non-blocking):** `[R] Revise  [O] Override (→ concerns.md)  [N] Not Applicable  [B] Back to Phase 1: Research  [P] Pause`
**FAIL (BLOCKING):** `[R] Revise (REQUIRED)  [B] Back to Phase 1: Research  [P] Pause` — no override available.

**HALT — wait for user response before proceeding.** On `[O]`: append override to `docs/concerns.md` using the standard override format (see Research skill Gate 1 for format definition). On `[P]`: save per Pause Protocol (`currentStep: gate-2`).

---

## Step 7: Completion

Update `docs/state.json` (preserve existing fields):
```json
{
  "currentPhase": "architecture",
  "phases": {
    "specify": {
      "status": "complete",
      "startedAt": "{ISO}",
      "completedAt": "{ISO}",
      "gateResult": "pass"
    }
  }
}
```

Display completion with stats (FRs, NFRs, ACs, personas, CQ results), then invoke the `/architecture` skill.

```
{status bar with ✅ Complete}
Specification finalized at docs/spec.md → Proceeding to Phase 3: Architecture
```

---

## Iteration Protocol

1. Present artifact → **HALT — wait for user response before proceeding.**
2. Feedback → revise → re-present **full** updated content (not diffs) → loop
3. Only explicit approval advances: `C`, `continue`, `looks good`, `LGTM`, `yes`, `ok`
4. Feedback signals: `but...`, `what about...`, `change X to Y` → revise and re-present
5. After addressing feedback, ALWAYS re-present the complete updated artifact
6. Ambiguous response (e.g., "interesting", "hmm", "ok I see") → ask: "Should I proceed to the next step, or is that feedback for revision?"

## Anti-Patterns

- ❌ Proceed without user response at any checkpoint
- ❌ Let subagents interact with user directly
- ❌ Show raw subagent output without review
- ❌ Vague NFRs without numbers
- ❌ Tech names in FR descriptions
- ❌ Let CQ-3/CQ-4 failures slide — BLOCKING
- ❌ Accept <3 concerns from any persona without a Confidence Statement
- ✅ Capability Contract for every FR: `FR-{N}: [{Actor}] can [{capability}]`
- ✅ Every NFR has numeric/measurable target
- ✅ 3+ persona reviews with review mandate (3-10 concerns typical, <3 requires Confidence Statement)
- ✅ Complete traceability (FR/NFR → AC)
- ✅ All 4 CQ checks before Gate 2
- ✅ Write file after each approved phase (crash safety)
- ✅ Preserve LOCKED DD-* from research
- ✅ Full content after revisions (not diffs)
- ✅ Task tool for all agent spawning
