---
name: research
description: "Interactive discovery session producing a research document. Phase 1 of 5."
version: "next-2.0"
phase: 1
input: "User description, optional existing docs"
output: "docs/research.md"
---

# Research Skill (Phase 1/5)

Facilitated discovery expert. Help the user articulate problem, vision, users, metrics, scope, constraints, and design decisions. Ask questions and synthesize — do NOT generate or invent content.

## Status Bar — present at TOP of every interaction

```
═══ LAIM ══════════════════════════════════════════════
Feature: {name}  │  Phase 1/5: Research  │  Step: {step}
═══════════════════════════════════════════════════════
```

Steps: `Discovery` → `Synthesis` → `Gate 1`

---

## Pause & Resume Protocol

**State table:**

| Step | `currentStep` value |
|------|-------------------|
| Synthesis presented | `synthesis` |
| Gate 1 shown | `gate-1` |

On `[P]` at any HALT: save per Universal Pause Protocol (§5.5 in start.md) using the value from the table above. Write `docs/research.md` with `status: paused` and `pausedStep: {value}`.

On resume (`status: paused` in research.md): read root-level `currentStep` from state.json, re-present the artifact for that step, do NOT advance.

---

## Prerequisite Check

**Metrics:** Before writing to `metrics.*` in state.json (gates, phase lifecycle), read `templates/references/metrics-triggers.md`.

1. Read `docs/state.json` — verify `currentPhase` is `research` (or doesn't exist)
2. Check `docs/research.md`:
   - `status: complete` → "Research already complete. Proceeding to Specify."
   - `status: paused` → read root-level `currentStep` from state.json, re-present artifact at that step with its approval options, do NOT advance. Offer `[C] Continue  [N] Start fresh`.
   - Not exists → fresh start

---

## Step 1: Discovery

### 1.1 Scan for Existing Documents

Check for `**/README.md`, `**/BRD.md`, `**/PRD.md`, `**/RFC*.md`, `**/DESIGN.md`, `**/*.pdf`. Also check `docs/state.json` → `discoveredDocuments` from `/start`.

If found: "Found existing documents: {list}. I'll use these as context." Pre-fill from them, verify with user.

Read each discovered document in full. Identify ALL valuable content — not just business context.
This includes: component/contract names, architecture descriptions, technical specifications,
protocol mechanics, API definitions, data models, domain terminology, UX descriptions, and any
other substantive content the user authored. Nothing the user wrote should be discarded — it will
be captured in the Additional Context section during synthesis.

### 1.2 Conversational Exchanges (3-7 rounds)

Ask about **4 required gate criteria first**, then recommended topics if not naturally covered.

**Required (ask first):**

| Topic | Gate Check | Key Questions |
|-------|-----------|--------------|
| Problem | ≥2 sentences | What pain exists? Who feels it? Current workarounds? |
| Vision | ≥2 sentences | If this succeeds perfectly, what changes? |
| Users | ≥1 persona | Who are the primary users? Goals? Frustrations? |
| Metrics | ≥1 numeric | How will you know this succeeded? What number moves? |

**Recommended (if not naturally covered):**

| Topic | Gate Check | Key Questions |
|-------|-----------|--------------|
| Scope | In/out sections | What's in scope? What's explicitly out? |
| Constraints | Section present | Technical, business, or timeline constraints? |
| Design Decisions | DD-* tagged | Tech choices made? What should AI decide? What's uncertain? |

**Smart Exit:** After each user response, check recommended topics against these thresholds:
- **Scope**: "Addressed" = user stated ≥1 in-scope AND ≥1 out-of-scope item
- **Constraints**: "Addressed" = user stated ≥1 technical, business, or timeline constraint
- **Design Decisions**: "Addressed" = ≥1 decision classified as LOCKED, DISCRETION, or DEFERRED

If all 4 required topics meet their gate thresholds (§Step 3) AND ≥2 recommended topics are
addressed → proceed to Synthesis. If required done but 0 recommended → ask 1-2 more targeted
questions. Min 3, max 7 exchanges total.

**Style:** 2-3 questions per cluster. Reflect back before next cluster. Push for numbers on metrics.

**Ambiguous response** (e.g., "interesting", "hmm", "ok I see") → ask: "Should I proceed to the next topic, or is that feedback for revision?"

### 1.3 Design Decisions

Classify decisions as they surface:
- **LOCKED** — user explicitly decided ("use PostgreSQL")
- **DISCRETION** — AI/implementer chooses ("pick a test framework")
- **DEFERRED** — needs investigation later ("unsure about auth provider")

---

## Step 2: Synthesis

Update step to `Synthesis`.

1. **Ensure output directory:** `mkdir -p docs/`

Write `docs/research.md`:

```markdown
---
status: complete
created: {ISO date}
feature: {slug}
---
# Brief: {Feature Name}

## Problem
{2+ sentences from user's words}

## Vision
{2+ sentences — north star}

## Users
- {Persona 1}: {description, goals, pain points}

## Success Metrics
- {Metric 1}: {target with specific number}

## Scope
### In Scope
- {items}
### Out of Scope
- {items with reasons}

## Constraints
- {Constraint}: {type}

## Design Decisions
- DD-1: {decision} [LOCKED/DISCRETION/DEFERRED]

## Additional Context
{Any valuable content from user-provided documents that does not fit the sections above.
This may include: component/contract architecture, technical specifications, protocol
mechanics, API definitions, data models, domain terminology, UX flows, or any other
substantive detail the user authored in their source documents.

Extract from user documents verbatim where possible. Synthesize only for clarity.
Never invent or generate content for this section — only include what the user provided.

Omit this section entirely if discovered documents contained no additional content beyond
what is already captured in the sections above.}
```

Present full research document to user:

```
{status bar with Step: Synthesis}

Here's the research document from our discussion:
{full research document content}

---
[C] Continue to Gate 1  [R] Revise  [B] Back to Discovery  [P] Pause
```

**HALT — wait for user response before proceeding.** On `[R]`: process feedback, re-present FULL updated content. On `[B]`: return to Discovery — ask follow-up questions to gather more information, then re-synthesize. On `[P]`: save per Pause Protocol (`currentStep: synthesis`).

---

## Step 3: Gate 1 (Embedded)

Update step to `Gate 1`.

### Criteria

| # | Criterion | Required | Check |
|---|-----------|----------|-------|
| 1 | Problem defined | ✅ Required | Section exists, ≥2 sentences |
| 2 | Vision articulated | ✅ Required | Section exists, ≥2 sentences |
| 3 | Users identified (≥1) | ✅ Required | At least 1 persona listed |
| 4 | Metrics with targets | ✅ Required | At least 1 metric with numeric target |
| 5 | Scope boundaries | ⚠️ Recommended | In-scope and out-of-scope sections present |
| 6 | Constraints listed | ⚠️ Recommended | Constraints section present |
| 7 | DD-* classified | ⚠️ Recommended | Design decisions tagged LOCKED/DISCRETION/DEFERRED |

Required: ✅/❌. Recommended: ✅/⚠️.

### Display

```
{status bar with Step: Gate 1}

┌─────────────────────────────────────┐
│ GATE 1: RESEARCH — {PASS | FAIL}   │
├─────────────────────────────────────┤
│ Required:                           │
│  1. Problem defined       {✅|❌}   │
│  2. Vision articulated    {✅|❌}   │
│  3. Users identified      {✅|❌}   │
│  4. Metrics with targets  {✅|❌}   │
├─────────────────────────────────────┤
│ Recommended:                        │
│  5. Scope boundaries      {✅|⚠️}   │
│  6. Constraints listed    {✅|⚠️}   │
│  7. DD-* classified       {✅|⚠️}   │
└─────────────────────────────────────┘
```

**If PASS:** `[C] Continue to Phase 2: Specify  [R] Revise  [P] Pause`
**If FAIL:** `[R] Revise  [O] Override (→ concerns.md)  [N] Not Applicable  [P] Pause`

**HALT — wait for user response before proceeding.** On `[P]`: save per Pause Protocol (`currentStep: gate-1`). On `[O]`: append override record to `docs/concerns.md`:

**Override format (append to `docs/concerns.md`):**
```markdown
## OV-{N}: Gate {gate_number} Override — {criteria_name}
- **Date**: {ISO date}
- **Phase**: {phase name}
- **Criteria**: #{number} — {criteria description}
- **Severity**: HIGH
- **Risk**: {what could go wrong because this was skipped}
- **Acknowledged by**: user
```

---

## Step 4: Completion

Update `docs/state.json` (preserve existing fields):
```json
{
  "currentPhase": "specify",
  "phases": {
    "research": {
      "status": "complete",
      "startedAt": "{ISO}",
      "completedAt": "{ISO}",
      "gateResult": "pass"
    }
  }
}
```

Display completion, then invoke the `/specify` skill.

```
{status bar with ✅ Complete}
Research finalized at docs/research.md → Proceeding to Phase 2: Specify
{If Additional Context section was included: "Includes additional technical context extracted from user documents."}
```

---

## Anti-Patterns

- ❌ Proceed without user response at any checkpoint
- ❌ Generate problem/vision without user input
- ❌ Accept vague metrics ("faster" → demand a number)
- ❌ Ask more than 7 questions
- ❌ Generate implementation details the user did not provide
- ✅ Facilitate, don't generate — synthesize user's words
- ✅ Push for specificity (numbers > adjectives)
- ✅ Classify every decision LOCKED / DISCRETION / DEFERRED
- ✅ Write file before gate (crash safety)
- ✅ Re-present full content after revisions (not diffs)
- ✅ Preserve all valuable content from user-provided documents in the Additional Context section
