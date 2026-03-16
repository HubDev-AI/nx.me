---
name: architecture
description: "System design through interactive collaboration, persona reviews, and quality gate. Phase 3 of 5."
version: "next-2.0"
phase: 3
input: "docs/research.md, docs/spec.md"
output: "docs/architecture.md"
---

# Architecture Skill — Phase 3 of 5

System design. Transforms research + spec into a complete architecture through interactive
collaboration, persona reviews, and an embedded quality gate.

**Input:** `docs/research.md`, `docs/spec.md`
**Output:** `docs/architecture.md` (frontmatter `status: complete`) — **IMMUTABLE after gate**
**Agents:** `.claude/agents/architect-persona.md`, `.claude/agents/maintainer-persona.md` (review mode via Task tool)

## Principles

1. **Generate what's needed** — NOT a fixed template. Sections adapt to the project type.
2. **Interactive** — Present → user reviews → feedback → revise → re-present loop.
3. **Every decision captured** — DD-* log with alternatives-considered and rationale.
4. **Adversarial review** — Persona agents challenge architecture from fresh context.
5. **Immutable after gate** — Once Gate 3 passes, all drift → `docs/amendments.md`.

## Status Bar & Standard Options

Display at TOP of every checkpoint:
```
═══ LAIM ═══ Feature: {name} │ Phase 3/5: Architecture │ Step: {step} ═══
```
Update `{step}`: Initialize, Investigate, Design, Review, Gate, Complete.

Options at every checkpoint: `[C] Continue  [R] Revise  [B] Back  [P] Pause`
Gate adds: `[O] Override  [N] Not Applicable`

**`[B] Back` behavior:** Returns to the previous step within this phase, or to the previous phase's gate checkpoint if at the first step. At Gate 3 PASS, `[B]` returns to Phase 2: Specify.

## Pause & Resume Protocol

**State table:**

| Step | `currentStep` value |
|------|-------------------|
| Step 1: Classify checkpoint | `classify` |
| Step 2: Resolve DEFERRED | `resolve-deferred` |
| Step 3: Draft checkpoint | `draft` |
| Step 4: Iteration checkpoint | `iterate` |
| Step 5: Persona review checkpoint | `persona-review` |
| Gate 3 shown | `gate-3` |

On `[P]` at any HALT: save per Universal Pause Protocol (§5.5 in start.md) using the value from the table above. Write `docs/architecture.md` with `status: paused` and `pausedStep: {value}`.

On resume: read root-level `currentStep` from state.json, re-present the artifact for that step, do NOT advance.

## Prerequisites & Resume

**Metrics:** Before writing to `metrics.*` in state.json (gates, phase lifecycle), read `templates/references/metrics-triggers.md`.

1. Verify `docs/research.md` and `docs/spec.md` both exist with `status: complete`
2. Check `docs/architecture.md`:
   - `status: complete` → Phase already done. Display: "Architecture phase complete. [C] Continue to Plan [R] Redo architecture [P] Pause"
   - `status: paused` → read root-level `currentStep` from state.json, re-present artifact at that step with its approval options, do NOT advance. If `currentStep` is null, fall back to Step 4 (Interactive Iteration).
   - `status: draft` or exists without complete/paused status → Resume: "Architecture draft found. [C] Continue editing [N] Start fresh [P] Pause". On [C]: read `currentStep` from state.json — if set, resume at that step; if null, skip to Step 4 (Interactive Iteration) with existing content.
   - Not exists → Fresh start. Proceed to Step 1.

## Iteration Protocol

1. Present artifact → **HALT — wait for user response before proceeding.**
2. Feedback → revise → re-present **full** updated content (not diffs) → loop
3. Only explicit approval advances: `C`, `continue`, `looks good`, `LGTM`, `yes`, `ok`
4. Feedback signals: `but...`, `what about...`, `change X to Y` → revise and re-present
5. Ambiguous response → ask: "Should I proceed, or is that feedback?"
6. After addressing feedback, ALWAYS re-present the complete updated artifact

---

## Workflow

### Step 1: Initialize & Classify

1. **Check prerequisites:**
   - `docs/research.md` must exist with `status: complete`
   - `docs/spec.md` must exist with `status: complete`
   - If missing: "Prerequisites not met. Complete Phase {N} first."

2. **Read both documents.** Extract:
   - DD-* decisions (especially any DEFERRED needing investigation)
   - FR-* and NFR-* requirements (these become architecture drivers)
   - Constraints (technical, business, regulatory)
   - User personas
   - Additional Context section from research.md (if present) — user-provided component names,
     architecture descriptions, technical specifications, data models, and domain terminology.
     Treat these as input constraints: use the user's component names and structure as the
     starting point for Component Decomposition rather than inventing from scratch. User-provided
     architecture details are LOCKED unless there is a clear technical reason to deviate.

3. **Check for optional skill artifacts (contract points):**
   - `docs/infrastructure.md` — If exists: extract cloud provider, service choices, deployment targets, and networking topology. These inform Infrastructure & Deployment sections and constrain technology choices. Note: In the two-pass model, `docs/infrastructure.md` may not exist at architecture time — that is expected. Architecture defines WHAT infrastructure is needed. `/devops` Pass 1 and Pass 2 generate HOW (local dev setup, then production Terraform/CI/CD).
   - `docs/test-strategy.md` — If exists: extract testing approach, coverage targets, and tool choices. These inform the Testing Strategy section of the architecture document.
   - If none exist: display "No standalone skill artifacts found. Architecture will define testing and infrastructure decisions from scratch. To pre-constrain these areas, run `/qa` → `docs/test-strategy.md` before this phase. Infrastructure is handled post-architecture by `/devops` (Pass 1 for local dev, Pass 2 for production)." Then proceed normally.

4. **Classify project type** to determine conditional sections:
   - Service/backend/API → API Contracts
   - Frontend-heavy (web, mobile) → UI Component Architecture
   - CLI tool → CLI Command Structure
   - Library/SDK → Library Public API Surface
   - Deployed service → Infrastructure & Deployment
   - Blockchain/smart contracts → Smart Contract Interfaces
   - Data pipeline/ETL → Data Flow & Pipeline Architecture
   - Real-time (WebSocket/SSE) → Event-Driven Architecture
   - Multiple types → include all applicable conditional sections
   - Unclear → always-present sections + Security only
5. **Determine security depth** based on the HIGHEST applicable tier:
   - **High** (OWASP Top 10 analysis, threat model, auth deep-dive): handles PII, financial
     transactions, health data, authentication/authorization as a primary feature, or
     regulatory compliance (GDPR, HIPAA, PCI-DSS, SOC2)
   - **Medium** (auth patterns, data protection, input validation): SaaS without PII,
     e-commerce (non-financial backend), public APIs with rate limiting, multi-tenant systems
   - **Low** (dependency scanning, basic input sanitization, secret management): internal
     tools, CLIs, libraries, dev tooling, single-tenant internal apps

   When uncertain between tiers, choose the higher tier. Present classification for user confirmation.

6. **Present** classification summary: project type, security depth, conditional sections
   selected, DEFERRED DD-* count, key architecture drivers from NFRs, additional context from research (if present), standalone skill artifacts (list which were found with what they constrain, or the "none found" message above)

**Checkpoint:** `[C] [R] [P]` — On `[P]`: save per Pause Protocol (`currentStep: classify`).

### Step 2: Resolve DEFERRED DD-*

For each DEFERRED DD-* from the research:
1. Investigate options and trade-offs
2. Present findings with recommendation
3. User confirms → status becomes LOCKED or DISCRETION

Apply the appropriate investigation level:
- **Skip:** Decision has no downstream impact
- **Quick Verify:** One web search confirms/denies
- **Standard:** Multiple sources needed (3-5 searches)
- **Deep Dive:** Complex trade-off analysis with full comparison

Skip if none exist. **Checkpoint per decision.** On `[P]`: save per Pause Protocol (`currentStep: resolve-deferred`). All must be resolved before Step 3.

### Step 3: Generate Architecture Document

Generate what the project needs — NOT a rigid template.

**Adaptation rules:**
- Always-present sections below are REQUIRED but their depth varies. A CLI tool's Data Models
  section may be 5 lines; a SaaS app's may be 50.
- Conditional sections are INCLUDED only when the classification triggers them.
- Within any section, omit subsections that genuinely don't apply (e.g., "indexes" in Data Models
  for a stateless service). Add a one-line note: "N/A — {reason}".
- If the project needs a section not listed below, add it. The tables are a starting point,
  not an exhaustive list.

**Always-present sections:**

| Section | Content |
|---------|---------|
| Goals & Constraints | Architecture drivers from NFRs, non-negotiable boundaries |
| Component Decomposition | Named components: responsibilities, interfaces, boundaries, dependencies |
| Data Models | Entity schemas: fields, types, relationships, indexes with justification |
| Key Workflows | 2-5 critical paths: happy path + error paths as sequence descriptions |
| Error Handling Strategy | Error taxonomy, codes, recovery patterns, propagation rules |
| Design Rationale | Complete DD-* log with LOCKED/DISCRETION, alternatives-considered, rationale |
| Testing Strategy | Framework, patterns (AAA/BDD), coverage approach, mocking, test data |

**Conditional sections (from Step 1 classification):**

| Section | When | Content |
|---------|------|---------|
| API Contracts | Services, backends, APIs | Full request/response JSON per endpoint |
| Security | **ALWAYS present** | OWASP for fintech; basic hygiene for tools — depth adapts |
| Infrastructure & Deployment | Deployed services | Environments, CI/CD, monitoring — captures architectural decisions; actual Terraform/CI/CD/monitoring generated by `/devops` |
| Smart Contract Interfaces | Blockchain | ABI definitions, gas considerations |
| UI Component Architecture | Frontend-heavy | Component tree, state management, design tokens |
| CLI Command Structure | CLI tools | Command tree, flags, output formats |
| Library Public API Surface | Libraries, SDKs | Public types, exports, versioning |

**Design Decision format:**
```
DD-{N}: {decision title}
- Status: LOCKED / DISCRETION / DEFERRED
- Alternatives considered: {list with trade-offs}
- Rationale: {why this choice}
```
LOCKED = do not revisit. DISCRETION = adjust within bounds. DEFERRED = must resolve before gate.

**Checkpoint:** `[C] [R] [P]` — On `[P]`: save per Pause Protocol (`currentStep: draft`).

### Step 4: Interactive Iteration

Expect 1-5 feedback rounds. For each:
1. User provides feedback on specific sections
2. Revise affected sections
3. Re-present **full** updated architecture
4. **HALT — wait for user response before proceeding.**

Do NOT interpret feedback as implicit approval. Only explicit signals transition to
Step 5: "ready for review", "looks good, get feedback", "proceed to persona review".
On `[P]`: save per Pause Protocol (`currentStep: iterate`).

### Step 5: Persona Review

Spawn two reviews via **Task tool**. You MUST inline all content in the Task tool prompt —
subagents cannot read files from your conversation.

**Architect persona:**
Use the Task tool with:
1. Instructions from `.claude/agents/architect-persona.md`
2. FULL TEXT of the architecture draft (inlined)
3. FR-* and NFR-* requirements from spec.md (inlined)
4. DD-* decisions (inlined)

Review focus: structural soundness, boundary violations, scalability concerns,
security gaps, integration risks. Return 3-10 concerns with priority (P1-P3).

**Maintainer persona:**
Use the Task tool with:
1. Instructions from `.claude/agents/maintainer-persona.md`
2. FULL TEXT of the architecture draft (inlined)
3. Requirements from spec.md (inlined)
4. Testing strategy section (inlined)

Review focus: maintainability, testability, documentation clarity, convention
consistency, onboarding difficulty. Return 3-10 concerns with priority (P1-P3).

**Review mandate:** Most reviews produce 3-10 concerns. If a persona returns fewer than 3
without a Confidence Statement, retry with reinforced prompt. If retry returns <3 WITH a
Confidence Statement, accept as-is.

**Present combined findings:**
```
### Architect ({N} concerns)
| # | Concern | Priority | Resolution | Status |
|---|---------|----------|------------|--------|

### Maintainer ({N} concerns)
| # | Concern | Priority | Resolution | Status |
|---|---------|----------|------------|--------|
```
Each concern: **Addressed** (incorporated — explain how) or **Acknowledged** (explain why not).
User may request revisions → loop back to Step 4.

**Checkpoint:** `[C] [R] [P]` — On `[P]`: save per Pause Protocol (`currentStep: persona-review`).

### Step 6: Finalize & Write

1. **Ensure output directory:** `mkdir -p docs/`
2. Apply all approved changes
3. Write `docs/architecture.md` with frontmatter: `status: complete`, `feature: {slug}`, `phase: 3`

**⚠ IMMUTABILITY:** After Gate 3, this document is FROZEN. Future drift → `docs/amendments.md`:
```
## A-{N}: {description}
- Story: {story-id} | Date: {ISO date}
- Original: {what architecture.md says}
- Actual: {what was implemented}
- Rationale: {why the change was needed}
```
Story-creator-agent reads BOTH files, using amended values where they conflict.

### Step 7: Gate 3

**Required (ALL must pass):**

| # | Criterion | Check |
|---|-----------|-------|
| 1 | Components defined | Component Decomposition section with named components |
| 2 | Data models with schemas | Entity fields, types, relationships |
| 3 | Key workflows documented | Sequence descriptions for critical paths |
| 4 | Error handling strategy | Error taxonomy, codes, recovery patterns |
| 5 | Testing strategy | Framework, patterns, coverage approach |
| 6 | Security section present | Even for low-relevance features |
| 7 | All DD-* resolved or justified | No DEFERRED without explicit rationale |

**Recommended (advisory, non-blocking):**

| # | Criterion | Check |
|---|-----------|-------|
| 8 | Persona review complete | Architect + maintainer reviews with findings |
| 9 | API contracts with examples | Request/response JSON |
| 10 | Architecture diagrams | Component/data flow diagrams |

**Gate display format:**
```
┌──────────────────────────────────────────────────────┐
│ GATE 3: ARCHITECTURE — {PASS | FAIL}                 │
├──────────────────────────────────────────────────────┤
│ Required:                                            │
│  1. Components defined          ✅ | ❌              │
│  2. Data models with schemas    ✅ | ❌              │
│  3. Key workflows documented    ✅ | ❌              │
│  4. Error handling strategy     ✅ | ❌              │
│  5. Testing strategy            ✅ | ❌              │
│  6. Security section present    ✅ | ❌              │
│  7. All DD-* resolved           ✅ | ❌              │
├──────────────────────────────────────────────────────┤
│ Recommended:                                         │
│  8.  Persona review complete    ✅ | ⚠️              │
│  9.  API contracts + examples   ✅ | ⚠️              │
│  10. Architecture diagrams      ✅ | ⚠️              │
└──────────────────────────────────────────────────────┘
```

**On FAIL:** Identify which criteria failed → route back to relevant step.
**On [P]:** save per Pause Protocol (`currentStep: gate-3`).
**Override [O]:** Append override to `docs/concerns.md` using the standard override format (see Research skill Gate 1 for format definition). Risk propagates.

### Step 8: Completion & Handoff

On Gate 3 PASS:

1. **Update state.json:**
   ```json
   {
     "currentPhase": "plan",
     "phases": {
       "architecture": {
         "status": "complete",
         "completedAt": "{ISO date}",
         "gateResult": "pass"
       }
     }
   }
   ```
2. **Display handoff:**
```
═══ LAIM ═══ Feature: {name} │ Phase 3/5: Architecture │ Step: Complete ═══

✅ Architecture complete — docs/architecture.md
⚠ IMMUTABLE. Future changes → docs/amendments.md

Components: {n} | Data models: {n} | DD-*: {n} ({locked}/{discretion})
Persona concerns addressed: {n}

Next: Phase 4 — Plan → invoke `/plan` skill
```
3. Route to plan skill.

---

## Anti-Patterns

**NEVER:** Proceed without user response · Skip Security section · Leave DEFERRED DD-* at gate ·
Modify architecture.md after Gate 3 · Present only diffs after feedback · Skip persona review ·
Generate fixed template regardless of project type

**ALWAYS:** Adapt sections to project type · Capture every decision in DD-* · Include error handling ·
Write to file after approval · Inline content for Task tool subagents · Present [C] [R] [P] at checkpoints
