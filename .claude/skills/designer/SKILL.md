---
name: designer
description: "Design system creation — three modes: Figma + pre-built DS, pre-built DS only, or custom generation from scratch. Supports shadcn/ui v4 + Tailwind + Figma MCP."
version: "next-3.0"
input: "docs/architecture.md"
---

# Designer Skill (Standalone)

Expert UI/UX Designer and Design System Creator. Orchestrate specialized agents for Figma translation, organism composition, style generation, accessibility validation, and wireframe diagramming while maintaining interactive collaboration with the user.

**Output:** `docs/design-system.md` (frontmatter `status: complete`) + `docs/Components.md` + `docs/Wireframes/`
**Agents:** `figma-translator`, `organism-composer`, `accessibility-checker`, `style-generator`, `diagram-generator` (spawned via Task tool)

## Contract Point

This skill produces `docs/design-system.md` which is automatically detected by:
- Plan skill (design constraints that affect UI stories)
- Story creator agent (references design tokens in stories)

Invoke this skill any time after Phase 3 (Architecture) and before Phase 4 (Plan).

---

## Three Modes

```
Mode A: DESIGN_SYSTEM.md exists + Figma MCP available + Figma URL → 5 stages
Mode B: DESIGN_SYSTEM.md exists + no Figma                        → 6 stages
Mode C: No DESIGN_SYSTEM.md                                       → 9 stages (custom)
```

User can override the detected mode at Stage 1.

### Mode Quick Reference

| Mode | When | Stages | Key Agents |
|------|------|--------|------------|
| A: Figma + DS | Pre-built DS + Figma MCP + URL | 5 | figma-translator, organism-composer, diagram-generator, accessibility-checker |
| B: DS Only | Pre-built DS, no Figma | 6 | organism-composer, diagram-generator, accessibility-checker |
| C: Custom | No pre-built DS | 9 | style-generator, diagram-generator, accessibility-checker |

---

## Iteration Protocol

1. Present artifact → **STOP** and wait for user response
2. Feedback → revise → re-present **FULL** updated content (not diffs) → loop
3. Only explicit approval advances: `C`, `continue`, `looks good`, `LGTM`, `yes`, `ok`
4. After addressing feedback, ALWAYS re-present the complete updated artifact

## Principles

1. **Interactive** — Present → user reviews → feedback → revise → re-present loop.
2. **YOU own all interaction** — Agents do heavy lifting and return summaries. Never let agents interact with user directly.
3. **One step at a time** — Complete current step before starting next.
4. **Accessibility is non-negotiable** — Every color combination checked, every component validated.
5. **On-demand DS reading** — Never load full DESIGN_SYSTEM.md. Build section index, read only needed sections per stage.

## Status Bar & Standard Options

Display at TOP of every checkpoint:
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode {A|B|C} │ Stage {N}/{total}: {stage name} ═══
```

Options at every checkpoint:
```
[C] Continue  [R] Revise  [B] Back to Stage {N-1}  [P] Pause
```
Stage 1 has no `[B]`. Final stage: `[C]` text reads "Complete — finalize documentation".

## Agent Invocation

When spawning an agent, use the **Task tool** with the contents of the agent file as instructions.

**Important**: Agents cannot access files via `@` references. You MUST inline any context they need.

**Budget constraints** (on-demand DS reading):
- Skill orchestrator: max ~200 lines of DS in working context at any stage
- Agent invocation: max ~400 lines of DS inlined per agent
- Section 9 (460 lines): never loaded fully — sub-section extraction by `### 9.N` headers

### Available Agents

| Agent | File | Purpose | Returns |
|-------|------|---------|---------|
| Figma Translator | `.claude/agents/figma-translator.md` | Map Figma frames to DS components | Component mapping + JSX skeleton + gap analysis |
| Organism Composer | `.claude/agents/organism-composer.md` | Compose screen layouts from catalog | Screen inventory + organism recipes + data flow |
| Accessibility Checker | `.claude/agents/accessibility-checker.md` | WCAG + DS token compliance | Accessibility report with issues |
| Style Generator | `.claude/agents/style-generator.md` | Generate CSS/design tokens from specs | CSS variables, design tokens JSON |
| Diagram Generator | `.claude/agents/diagram-generator.md` | Create wireframe diagrams | Mermaid/ASCII wireframe layouts |

---

## Figma MCP Integration (Mode A)

Figma MCP tools are called **directly by the skill** (not via agents):

| Tool | Purpose | Used In |
|------|---------|---------|
| `get_metadata(figma_url)` | File structure, pages, frames | Stage 1 (availability test) |
| `get_design_context(figma_url)` | Design tokens, styles | Stage 2 |
| `get_variable_defs(figma_url)` | Variable definitions | Stage 2 |
| `get_screenshot(node_id)` | Frame screenshots | Stage 2 |
| `get_code_connect_map(figma_url)` | Code-connected components | Stage 2 |

Availability is tested in Stage 1 via a lightweight `get_metadata` call.

---

## On-Demand Section Reading

During Stage 1, build a **section index** by scanning DESIGN_SYSTEM.md headers:

```
Section 1: Principles         → lines 29-43
Section 2: Setup               → lines 45-114
Section 3: Color System        → lines 116-399
...
Section 12: Rules              → lines 1242-1258
```

Subsequent stages use `Read` with `offset`/`limit` to load only needed sections. The section index maps each `## N.` heading to its line range.

### DS Sections by Stage (Mode A)

| Stage | DS Sections Read | Approx Lines |
|-------|-----------------|-------------|
| 1: Initialize | Headers only (TOC) | ~20 |
| 2: Figma Analysis | — (Figma MCP data) | 0 |
| 3: Component Mapping | S10 + S8 (inlined to agent) | ~185 |
| 4: Organism Generation | S11 + S9 sub-sections (inlined to agent) | ~100 |
| 5: Finalize | S3 subset + S4 (inlined to agent) | ~310 |

### DS Sections by Stage (Mode B)

| Stage | DS Sections Read | Approx Lines |
|-------|-----------------|-------------|
| 1: Initialize | Headers only (TOC) | ~20 |
| 2: Component Selection | S8 + S9 headers | ~128 |
| 3: Layout Composition | S11 + S5 + S9 sub-sections (inlined to agent) | ~160 |
| 4: Interactions | — (project-specific) | 0 |
| 5: Wireframes | S5 + results (inlined to agent) | ~100 |
| 6: Finalize | S3 subset + S4 (inlined to agent) | ~310 |

---

## Base Document Strategy (Mode A/B)

1. Copy `DESIGN_SYSTEM.md` from installed skill templates to project's `docs/design-system.md`
2. Project-specific content **appended** after Section 12:
   - Component mapping / selection results
   - Project organisms
   - Accessibility report
3. Base sections 1-12 remain immutable — never modify them

---

## Prerequisites & Resume

1. Check `docs/design-system.md`:
   - `status: complete` → Skill already done. Display: "Design system complete. [C] Continue [R] Redo design system [P] Pause"
   - `status: paused` → Read `mode` + `current_stage` from frontmatter, re-enter at that stage's checkpoint, re-present with approval options, do NOT advance.
   - `status: draft` or `status: in-progress` → Resume detection (see below)
   - Not exists → Fresh start. Proceed to Stage 1.

### Resume Detection

Read frontmatter `mode`, `last_completed_stage`, `total_stages`. If detected mode differs from saved mode (e.g. Figma MCP became available since last run):

```
═══ LAIM DESIGNER ═══ Mode Conflict Detected ═══

Saved: Mode {saved} (Stage {N}/{total} completed)
Detected: Mode {detected}

Reason: {e.g., "Figma MCP is now available" or "DESIGN_SYSTEM.md was added"}

Options:
- [K] Keep saved mode — continue from Stage {N+1}
- [S] Switch to Mode {detected} — restart from Stage 1
- [P] Pause — decide later

Select:
```

**HALT** — Wait for user response. On `[P]`: save per Pause Protocol using the saved mode's `current_stage` value. The mode mismatch will be re-detected on next resume.

---

## Document Frontmatter (all modes)

```yaml
---
title: "Design System: {Project Name}"
mode: A | B | C
figma_url: "{url}" | null
design_system_source: "pre-built" | "generated"
total_stages: 5 | 6 | 9
status: complete | draft | in-progress | paused
current_stage: {N}
last_completed_stage: {N}
steps_completed: [1, 2, ...]
dark_mode: true | false
created: {ISO date}
last_updated: {ISO date}
---
```

---

# Mode A: Figma + Design System (5 Stages)

## A1: Initialize

**Goal**: Detect mode, build DS section index, test Figma MCP, gather project context.

### Actions
1. Check for existing `docs/design-system.md` (see Prerequisites & Resume)
2. Locate `DESIGN_SYSTEM.md` in installed skill templates
3. Scan DS headers to build section index (heading → line range mapping)
4. Read `docs/architecture.md` — extract component decomposition and constraints
5. Test Figma MCP: call `get_metadata` with user-provided Figma URL
   - If MCP unavailable: fall back to Mode B, inform user
   - If URL invalid: ask user for correct URL
6. Copy `DESIGN_SYSTEM.md` to `docs/design-system.md` with frontmatter
7. Record phase start time

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode A │ Stage 1/5: Initialize ═══

**Detected Mode**: A (Figma + Pre-built Design System)

**Design System**: LimeChain DS (shadcn/ui v4 + Tailwind)
- {N} sections indexed, {N} components in catalog
- Source: pre-built template

**Figma**: Connected
- File: {figma file name from metadata}
- Pages: {page count}
- Frames: {frame list}

**Architecture**: docs/architecture.md loaded
- Components: {component count from architecture}
- Key constraints: {list}

**Next**: Analyze Figma frames and extract design data

---
[C] Continue  [R] Revise  [P] Pause
Override: [B] Switch to Mode B (no Figma)  [X] Switch to Mode C (custom)
```

**HALT** — Wait for user response. On `[P]`: save per Pause Protocol (`current_stage: 1`).

After approval, write initial frontmatter to `docs/design-system.md`.

---

## A2: Figma Analysis

**Goal**: Extract design data from Figma using MCP tools.

### Actions
1. Call `get_design_context(figma_url)` — extract design tokens, styles
2. Call `get_variable_defs(figma_url)` — extract variable definitions
3. Call `get_code_connect_map(figma_url)` — extract code-connected components
4. For each key frame: call `get_screenshot(node_id)` — capture visual reference
5. Compile Figma data summary:
   - Color tokens found
   - Typography styles found
   - Component instances found
   - Layout patterns detected

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode A │ Stage 2/5: Figma Analysis ═══

## Figma Design Data

### Color Tokens
| Token | Value | DS Match |
|-------|-------|----------|
| {figma token} | {value} | {DS token or "—"} |

### Typography Styles
| Style | Font/Size/Weight | DS Match |
|-------|-----------------|----------|
| {figma style} | {value} | {DS token or "—"} |

### Component Instances ({count})
| Figma Component | Occurrences | Likely DS Match |
|----------------|-------------|----------------|
| {component} | {N} | {DS component or "?"} |

### Frame Screenshots
{screenshot references for key frames}

---
[C] Continue  [R] Revise  [B] Back to Stage 1  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 2`).

---

## A3: Component Mapping

**Goal**: Map Figma elements to DS components using the figma-translator agent.

### Actions
1. Read DS Section 10 (Figma→Code Mapping) and Section 8 (Component Catalog) via section index
2. Spawn `figma-translator` agent via Task tool, inlining:
   - Figma frame data from Stage 2
   - Figma screenshots from Stage 2
   - DS Section 10 content (~70 lines)
   - DS Section 8 content (~115 lines)
3. Review agent output for completeness
4. Present mapping with gap analysis

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode A │ Stage 3/5: Component Mapping ═══

## Component Mapping

| # | Figma Element | DS Component | Variant/Props | Confidence |
|---|--------------|-------------|---------------|------------|
{mapping table from agent}

## JSX Skeleton
```tsx
{skeleton from agent}
```

## Gap Analysis
| # | Unmapped Element | Suggested Approach |
|---|-----------------|-------------------|
{gaps from agent}

## Implementation Order
| # | Component | Action | Dependencies |
|---|-----------|--------|-------------|
{order from agent}

---
[C] Continue  [R] Revise  [B] Back to Stage 2  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 3`).

---

## A4: Organism Generation

**Goal**: Compose page-level organisms from mapped components.

### Actions
1. Read DS Section 11 (Organism Recipes) and relevant Section 9 sub-sections via section index
2. Spawn `organism-composer` agent via Task tool, inlining:
   - Component mapping from Stage 3
   - Requirements from `docs/architecture.md`
   - DS Section 11 content (~30 lines)
   - DS Section 9 sub-sections (only those referenced in mapping, ~70 lines)
3. Optionally spawn `diagram-generator` agent for wireframes of key screens
4. Review and present organism compositions

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode A │ Stage 4/5: Organism Generation ═══

## Screen Inventory

| # | Screen | Route | Components | Recipe |
|---|--------|-------|-----------|--------|
{screen table from agent}

## Organism Details
{per-screen details: JSX skeleton, data flow, responsive behavior}

## Wireframes (if generated)
{wireframe diagrams}

## Custom Components Needed
| # | Component | Reason | Approach |
|---|-----------|--------|---------|
{custom components from agent}

---
[C] Continue  [R] Revise  [B] Back to Stage 3  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 4`).

---

## A5: Finalize

**Goal**: Validate accessibility, compile final documentation.

### Actions
1. Read DS Section 3 (Color System — theme token tables only) and Section 4 (Typography) via section index
2. Spawn `accessibility-checker` agent via Task tool, inlining:
   - Color system from DS Section 3 subset (~200 lines)
   - Typography from DS Section 4 (~40 lines)
   - Component mapping from Stage 3
   - Organism compositions from Stage 4
   - Figma alignment data from Stage 2
3. Address any critical (P1) issues
4. Append project-specific sections to `docs/design-system.md` (after Section 12):
   - `## 13. Component Mapping` (from Stage 3)
   - `## 14. Project Organisms` (from Stage 4)
   - `## 15. Accessibility Report` (from this stage)
5. Update frontmatter: `status: complete`, `last_completed_stage: 5`

### Final Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode A │ Stage 5/5: Finalize ═══

## Accessibility Validation
{from accessibility-checker agent}

### Summary
- WCAG Level: {level}
- DS Compliance: {status}
- Issues: {P1 count} critical, {P2 count} important, {P3 count} minor

## Design System Complete

**Sections (base)**:
- [x] Principles, Setup, Colors, Typography, Spacing, Shadows, Icons
- [x] Component Catalog, Custom Components, Figma Mapping
- [x] Organism Recipes, Rules

**Sections (project-specific)**:
- [x] Component Mapping (from Figma)
- [x] Project Organisms
- [x] Accessibility Report

**Output Files**:
- `docs/design-system.md`
- `docs/Components.md` (if applicable)
- `docs/Wireframes/` (if created)

---
[Complete — finalize documentation]  [R] Address accessibility issues first  [B] Back to Stage 4  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 5`).

---

# Mode B: Design System Only (6 Stages)

## B1: Initialize

**Goal**: Detect mode, build DS section index, gather project context.

### Actions
1. Check for existing `docs/design-system.md` (see Prerequisites & Resume)
2. Locate `DESIGN_SYSTEM.md` in installed skill templates
3. Scan DS headers to build section index
4. Read `docs/architecture.md` — extract component decomposition and constraints
5. Test Figma MCP availability: check if Figma MCP tools are registered in the current environment
   - If available: inform user Mode A is possible, offer switch (ask for Figma URL)
   - If unavailable: confirm Mode B
6. Copy `DESIGN_SYSTEM.md` to `docs/design-system.md` with frontmatter
7. Record phase start time

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode B │ Stage 1/6: Initialize ═══

**Detected Mode**: B (Pre-built Design System, no Figma)

**Design System**: LimeChain DS (shadcn/ui v4 + Tailwind)
- {N} sections indexed, {N} components in catalog
- Source: pre-built template

**Architecture**: docs/architecture.md loaded
- Components: {component count}
- Key constraints: {list}

**Next**: Select components for your project

---
[C] Continue  [R] Revise  [P] Pause
Override: [A] Switch to Mode A (provide Figma URL)  [X] Switch to Mode C (custom)
```

**HALT** — Wait for user response. On `[P]`: save per Pause Protocol (`current_stage: 1`).

---

## B2: Component Selection

**Goal**: Interactive selection of components from the DS catalog.

### Actions
1. Read DS Section 8 (Component Catalog) headers and Section 9 (Custom Components) headers via section index
2. Present component catalog organized by category
3. User selects which components their project needs
4. For selected custom components (Section 9), read their specific sub-sections

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode B │ Stage 2/6: Component Selection ═══

## shadcn Components (Section 8)

### Layout & Navigation
- [ ] Accordion  [ ] Collapsible  [ ] Tabs  [ ] Sheet  [ ] Drawer
- [ ] ScrollArea  [ ] Separator  [ ] NavigationMenu

### Data Display
- [ ] Table  [ ] Card  [ ] Badge  [ ] Avatar  [ ] Progress
- [ ] Skeleton  [ ] Tooltip

### Forms & Input
- [ ] Button  [ ] Input  [ ] Select  [ ] Checkbox  [ ] RadioGroup
- [ ] Switch  [ ] Slider  [ ] Label

### Feedback & Overlay
- [ ] Dialog  [ ] Popover  [ ] DropdownMenu  [ ] Alert
- [ ] Pagination

## Custom Components (Section 9)
- [ ] IconButton  [ ] Tag  [ ] TokenInput  [ ] List/ListItem
- [ ] SegmentedControl  [ ] DetailRow/DetailList  [ ] Disclosure
- [ ] CollapsibleCard  [ ] DataTableColumnHeader  [ ] NavLink  [ ] InfoPanel
- [ ] Input (extended)  [ ] Separator (extended)

Select components (comma-separated numbers or "all"):

---
[C] Continue  [R] Revise  [B] Back to Stage 1  [P] Pause
```

**HALT** — Wait for user selection. On `[P]`: save per Pause Protocol (`current_stage: 2`).

---

## B3: Layout Composition

**Goal**: Compose page-level organisms from selected components.

### Actions
1. Read DS Section 11 (Organism Recipes), Section 5 (Spacing), and selected Section 9 sub-sections
2. Spawn `organism-composer` agent via Task tool, inlining:
   - Selected components from Stage 2
   - Requirements from `docs/architecture.md`
   - DS Section 11 content
   - DS Section 5 content (Spacing & Layout)
   - Relevant Section 9 sub-sections
3. Review and present organism compositions

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode B │ Stage 3/6: Layout Composition ═══

## Screen Inventory
{screen table from agent}

## Organism Details
{per-screen: JSX skeleton, data flow, responsive behavior, state coverage}

## Custom Components Needed
{components not in catalog}

---
[C] Continue  [R] Revise  [B] Back to Stage 2  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 3`).

---

## B4: Interactions

**Goal**: Define interaction patterns and animations for project-specific needs.

### Actions
1. Define hover states for selected components
2. Establish transition timing
3. Document animation principles
4. Specify feedback patterns (toasts, loading, error states)

This stage is project-specific — no DS sections needed.

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode B │ Stage 4/6: Interactions ═══

## Transition Timing
| Purpose | Duration | Easing |
|---------|----------|--------|
| Micro (hover, focus) | 150ms | ease-out |
| Small (expand, slide) | 200ms | ease-in-out |
| Medium (modal, drawer) | 300ms | ease-in-out |
| Large (page transition) | 400ms | ease-in-out |

## State Behaviors
{hover, focus, active, disabled, loading, error behaviors}

## Animation Principles
{project-specific animation guidelines}

---
[C] Continue  [R] Revise  [B] Back to Stage 3  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 4`).

---

## B5: Wireframes

**Goal**: Create key screen wireframes.

### Actions
1. Read DS Section 5 (Spacing & Layout) via section index
2. Spawn `diagram-generator` agent for each selected screen, inlining:
   - Organism compositions from Stage 3
   - DS Section 5 content
   - Component specs from Stage 2
3. Spawn `accessibility-checker` agent for initial validation, inlining:
   - Wireframe layouts
   - DS Section 3 subset (color tokens)
4. Present wireframes with accessibility notes

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode B │ Stage 5/6: Wireframes ═══

## Wireframes
{per-screen: desktop + mobile wireframe diagrams}

## Early Accessibility Notes
{initial findings from accessibility-checker}

---
[C] Continue  [R] Revise  [B] Back to Stage 4  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 5`).

---

## B6: Finalize

**Goal**: Full accessibility validation and compile final documentation.

### Actions
1. Read DS Section 3 subset (theme token tables) and Section 4 (Typography) via section index
2. Spawn `accessibility-checker` agent via Task tool, inlining:
   - Color system from DS Section 3 subset (~200 lines)
   - Typography from DS Section 4 (~40 lines)
   - Selected components from Stage 2
   - Organism compositions from Stage 3
   - Wireframes from Stage 5
3. Address any critical (P1) issues
4. Append project-specific sections to `docs/design-system.md` (after Section 12):
   - `## 13. Selected Components` (from Stage 2)
   - `## 14. Project Organisms` (from Stage 3)
   - `## 15. Interactions` (from Stage 4)
   - `## 16. Wireframes` (from Stage 5)
   - `## 17. Accessibility Report` (from this stage)
5. Update frontmatter: `status: complete`, `last_completed_stage: 6`

### Final Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode B │ Stage 6/6: Finalize ═══

## Accessibility Validation
{from accessibility-checker agent}

## Design System Complete

**Sections (base)**: [x] 1-12 (pre-built)
**Sections (project-specific)**:
- [x] Selected Components
- [x] Project Organisms
- [x] Interactions
- [x] Wireframes
- [x] Accessibility Report

**Output Files**:
- `docs/design-system.md`
- `docs/Components.md` (if applicable)
- `docs/Wireframes/` (if created)

---
[Complete — finalize documentation]  [R] Address accessibility issues first  [B] Back to Stage 5  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 6`).

---

# Mode C: Custom Design System (9 Stages)

Mode C is the full custom generation flow — used when no pre-built DESIGN_SYSTEM.md is available.

## C1: Initialize

**Goal**: Understand project context and establish design system structure.

### Actions
1. Check for existing `docs/design-system.md` (see Prerequisites & Resume)
2. Check for `DESIGN_SYSTEM.md` in installed skill templates
   - If found: inform user Mode A/B are available, offer switch
   - If not found: confirm Mode C
3. Read `docs/architecture.md` — extract component decomposition, data models, API contracts, and technical constraints
4. Gather project context and brand direction
5. Determine deliverables needed
6. Write `mode: C` to frontmatter

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 1/9: Initialize ═══

I'll help you create a comprehensive design system and style guide.

**Project Context**
- What is the product/brand name?
- What industry/domain?
- Who is the target audience?
- Any existing brand guidelines?

**Design System Structure**
1. Full Design System (all sections)
2. Component Library Only
3. Wireframes Only
4. Custom selection

**Output Location**
- `docs/design-system.md`, `docs/Components.md`

Select structure [1-4] and provide project context:

---
[C] Continue  [R] Revise  [P] Pause
```

**HALT** — Wait for user response. On `[P]`: save per Pause Protocol (`current_stage: 1`).

---

## C2: Brand Identity

**Goal**: Establish brand personality and visual direction.

### Actions
1. Define brand personality traits
2. Establish visual mood (modern, classic, playful, etc.)
3. Document logo usage guidelines (if logo exists)
4. Define brand voice and tone

### Content to Draft
```markdown
# Brand Identity

## Brand Personality
- **Core Traits**: {3-5 adjectives}
- **Visual Mood**: {description}
- **Voice & Tone**: {description}

## Logo Usage
{guidelines or placeholder}

## Brand Keywords
{words that capture the brand feeling}
```

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 2/9: Brand Identity ═══

## Brand Personality
{drafted content}

## Visual Mood
{drafted content}

## Logo Guidelines
{drafted content}

---
[C] Continue  [R] Revise  [B] Back to Stage 1  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 2`).

---

## C3: Color System

**Goal**: Define comprehensive color palette with accessibility in mind.

### Actions

**Part 1**: Discuss color direction with user:
- Primary brand color preference
- Secondary color direction
- Light/dark mode requirements

**Part 2**: Spawn `style-generator` agent via Task tool:

```
Inline context:
"Generate a color system based on:
Primary Color: {user preference}
Secondary Direction: {user input}
Brand Personality: {from C2}
Dark Mode: {yes/no}

Generate: primary scale (50-900), secondary scale, neutral scale,
semantic colors, surface colors, CSS custom properties, accessibility notes"
```

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 3/9: Color System ═══

## Primary Palette
{color swatches with hex codes}

## Secondary Palette
{color swatches}

## Semantic Colors
| Purpose | Light Mode | Dark Mode | Usage |
|---------|------------|-----------|-------|
| Success | {hex} | {hex} | Positive actions, confirmations |
| Warning | {hex} | {hex} | Caution states, pending actions |
| Error   | {hex} | {hex} | Destructive actions, validation errors |
| Info    | {hex} | {hex} | Informational messages, hints |

## Surface Colors
| Surface | Light Mode | Dark Mode | Usage |
|---------|------------|-----------|-------|
| Background | {hex} | {hex} | Page background |
| Card       | {hex} | {hex} | Elevated surfaces |
| Muted      | {hex} | {hex} | Subdued backgrounds |

## Accessibility Notes
{contrast ratio information — computed using WCAG relative luminance formula}

---
[C] Continue  [R] Revise  [B] Back to Stage 2  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 3`).

---

## C4: Typography

**Goal**: Define type system with scale and hierarchy.

### Actions

**Part 1**: Discuss typography preferences (serif, sans-serif, specific fonts)

**Part 2**: Spawn `style-generator` agent via Task tool:

```
Inline context:
"Generate a typography system based on:
Font Preference: {user preference}
Brand Personality: {from C2}

Generate: font families, type scale, font weights, line heights,
letter spacing, CSS custom properties, responsive considerations"
```

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 4/9: Typography ═══

## Font Families
| Purpose | Family | Weights | Fallback |
|---------|--------|---------|----------|

## Type Scale
| Token | Size (rem) | Line Height | Weight | Usage |
|-------|-----------|-------------|--------|-------|
| display-xl | 3.75 | 1.1 | 700 | Hero headings |
| display | 3 | 1.1 | 700 | Page titles |
| h1 | 2.25 | 1.2 | 700 | Section headings |
| h2 | 1.875 | 1.2 | 600 | Subsection headings |
| h3 | 1.5 | 1.3 | 600 | Card titles |
| h4 | 1.25 | 1.4 | 600 | Minor headings |
| body | 1 | 1.5 | 400 | Body text |
| small | 0.875 | 1.5 | 400 | Secondary text, captions |
| caption | 0.75 | 1.4 | 400 | Labels, fine print |

## CSS Variables
```css
{generated CSS}
```

---
[C] Continue  [R] Revise  [B] Back to Stage 3  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 4`).

---

## C5: Spacing & Layout

**Goal**: Define spacing scale and grid system.

### Actions
1. Define spacing scale (base unit)
2. Establish grid system (columns, gutters, margins)
3. Define breakpoints
4. Document layout patterns

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 5/9: Spacing & Layout ═══

## Spacing Scale
| Token | Value | Pixels | Usage |
|-------|-------|--------|-------|
| 0.5 | 0.125rem | 2px | Hairline gaps |
| 1 | 0.25rem | 4px | Tight inline spacing |
| 2 | 0.5rem | 8px | Related element gaps |
| 3 | 0.75rem | 12px | Component internal padding |
| 4 | 1rem | 16px | Standard spacing |
| 6 | 1.5rem | 24px | Section padding |
| 8 | 2rem | 32px | Card padding, group gaps |
| 12 | 3rem | 48px | Section margins |
| 16 | 4rem | 64px | Page section separation |

## Grid System
| Property | Value |
|----------|-------|
| Columns | 12 |
| Gutter | 1.5rem (24px) |
| Margin (mobile) | 1rem (16px) |
| Margin (desktop) | 2rem (32px) |
| Max content width | 80rem (1280px) |

## Breakpoints
| Name | Min Width | Typical Device |
|------|-----------|---------------|
| sm | 640px | Large phone / small tablet |
| md | 768px | Tablet |
| lg | 1024px | Laptop |
| xl | 1280px | Desktop |
| 2xl | 1536px | Large desktop |

---
[C] Continue  [R] Revise  [B] Back to Stage 4  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 5`).

---

## C6: Components

**Goal**: Define core UI component specifications.

### Actions

**Part 1**: Identify components needed (buttons, form elements, cards, navigation, feedback)

**Part 2**: Spawn `style-generator` agent via Task tool:

```
Inline context:
"Generate component specifications based on:
Color System: {from C3}
Typography: {from C4}
Spacing: {from C5}

Generate specs for: buttons, inputs, cards, alerts
For each: dimensions, colors per state, typography, CSS example"
```

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 6/9: Components ═══

## Buttons
| Variant | Default | Hover | Active | Disabled |
|---------|---------|-------|--------|----------|
| Primary | {bg, text, border} | {changes} | {changes} | {opacity, cursor} |
| Secondary | {bg, text, border} | {changes} | {changes} | {opacity, cursor} |
| Ghost | {bg, text, border} | {changes} | {changes} | {opacity, cursor} |
| Destructive | {bg, text, border} | {changes} | {changes} | {opacity, cursor} |

Sizes: sm (h-8), default (h-9), lg (h-10), icon (h-9 w-9)

## Form Elements
| Element | Default | Focus | Error | Disabled |
|---------|---------|-------|-------|----------|
| Input | {border, bg, text} | {ring, border} | {border color, message} | {opacity} |
| Select | {border, bg, text} | {ring, border} | {border color} | {opacity} |
| Checkbox | {border, bg} | {ring} | {border color} | {opacity} |

## Cards
| Part | Style |
|------|-------|
| Container | {bg, border, radius, shadow} |
| Header | {padding, typography} |
| Content | {padding} |
| Footer | {padding, border-top} |

## Alerts
| Variant | Icon | Border | Background | Text |
|---------|------|--------|------------|------|
| Default | info | {color} | {color} | {color} |
| Success | check | {color} | {color} | {color} |
| Warning | alert | {color} | {color} | {color} |
| Destructive | x-circle | {color} | {color} | {color} |

---
[C] Continue  [R] Revise  [B] Back to Stage 5  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 6`).

---

## C7: Interactions

**Goal**: Define interaction patterns and animations.

### Actions
1. Define hover states
2. Establish transition timing
3. Document animation principles
4. Specify feedback patterns

### Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 7/9: Interactions ═══

## Transition Timing
| Purpose | Duration | Easing | Example |
|---------|----------|--------|---------|
| Micro (hover, focus) | 150ms | ease-out | Button hover color change |
| Small (expand, slide) | 200ms | ease-in-out | Accordion open, tooltip appear |
| Medium (modal, drawer) | 300ms | ease-in-out | Dialog open, sheet slide |
| Large (page transition) | 400ms | ease-in-out | Route change, view switch |

## State Behaviors
| State | Visual Treatment |
|-------|-----------------|
| Hover | Subtle background shift or opacity change |
| Focus | 2px ring using --ring token, 3:1 contrast minimum |
| Active/Pressed | Slight scale-down or darker background |
| Disabled | 50% opacity, cursor-not-allowed, no pointer events |
| Loading | Skeleton shimmer or spinner replacing content |
| Error | --destructive border, error text below element |

## Animation Principles
- Respect `prefers-reduced-motion` — disable or simplify all non-essential animation
- Use transform/opacity for GPU-accelerated transitions (avoid animating layout properties)
- Entrance: fade-in + slide-up; Exit: fade-out + slide-down
- Stagger list items by 50ms for sequential reveal
- Loading skeletons use a horizontal shimmer at 1.5s cycle

---
[C] Continue  [R] Revise  [B] Back to Stage 6  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 7`).

---

## C8: Wireframes

**Goal**: Create key screen wireframes.

### Actions

**Part 1**: Decide which screens to wireframe (present options based on project type, include `[P] Pause` option)

**HALT** — Wait for user selection. On `[P]`: save per Pause Protocol (`current_stage: 8`).

**Part 2**: For each selected screen, spawn `diagram-generator` agent via Task tool:

```
Inline context:
"Create a wireframe for: {screen name}
Components available: {from C6}
Grid system: {from C5}

Create: desktop wireframe, mobile wireframe, interaction notes"
```

### Per-Wireframe Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 8/9: Wireframe — {Screen} ═══

## Desktop Layout
{wireframe}

## Mobile Layout
{wireframe}

## Interaction Notes
{notes}

---
[C] Continue  [R] Revise  [B] Back to Stage 7  [P] Pause
```

**HALT** — Repeat for each screen. On `[P]`: save per Pause Protocol (`current_stage: 8`).

---

## C9: Finalize

**Goal**: Validate accessibility and compile final documentation.

### Actions

**Part 1**: Spawn `accessibility-checker` agent via Task tool:

```
Inline context:
"Validate this design system for WCAG 2.1 AA compliance:
Colors: {from C3}
Typography: {from C4}
Components: {from C6}

Check: contrast ratios, touch targets, focus indicators, motion, text sizing"
```

**Part 2**: Address any issues identified
**Part 3**: Compile final documents
**Part 4**: Write `docs/design-system.md` with frontmatter `status: complete`
**Part 5**: Update frontmatter: `status: complete`, `last_completed_stage: 9`

### Final Checkpoint
```
═══ LAIM DESIGNER ═══ Project: {name} │ Mode C │ Stage 9/9: Finalize ═══

## Accessibility Validation
{from accessibility-checker agent}

## Design System Complete

**Sections**:
- [x] Brand Identity
- [x] Color System
- [x] Typography
- [x] Spacing & Layout
- [x] Components
- [x] Interactions
- [x] Wireframes

**Output Files**:
- `docs/design-system.md`
- `docs/Components.md`
- `docs/Wireframes/` (if created)

---
[Complete — finalize documentation]  [R] Address accessibility issues first  [B] Back to Stage 8  [P] Pause
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`current_stage: 9`).

---

## State Management

### Incremental File Writing Protocol

After each stage's checkpoint is approved with [C]:
1. **Write** current accumulated content to `docs/design-system.md`
2. Update frontmatter: `current_stage`, `steps_completed`, `last_updated`, `last_completed_stage`
3. Status progresses: `draft` → `in-progress` → `complete`

### Two-Way Sync Protocol

Before starting the next stage:
1. **Read** the file from disk
2. **Compare** with last-written version
3. If **unchanged**: proceed normally
4. If **changed externally**: present detected modifications
   ```
   File was modified since last write.

   Changes detected in:
   - Section: {section name} — {brief diff description}

   Options:
   - [F] Use file version (accept external edits)
   - [C] Use console version (discard external edits)
   - [M] Merge — show both, let me choose per section
   ```
5. Apply chosen version and continue

### File Isolation
- **WRITES to**: `docs/design-system.md`, `docs/Components.md`, `docs/Wireframes/` (ONLY these)
- **READS from** (read-only): `docs/architecture.md`, DESIGN_SYSTEM.md (templates), codebase

### Pause & Resume Protocol

**State table (per mode):**

| Mode A Stage | `current_stage` value |
|-------------|----------------------|
| A1: Initialize | `1` |
| A2: Figma Analysis | `2` |
| A3: Component Mapping | `3` |
| A4: Organism Generation | `4` |
| A5: Finalize | `5` |

| Mode B Stage | `current_stage` value |
|-------------|----------------------|
| B1: Initialize | `1` |
| B2: Component Selection | `2` |
| B3: Layout Composition | `3` |
| B4: Interactions | `4` |
| B5: Wireframes | `5` |
| B6: Finalize | `6` |

| Mode C Stage | `current_stage` value |
|-------------|----------------------|
| C1: Initialize | `1` |
| C2: Brand Identity | `2` |
| C3: Color System | `3` |
| C4: Typography | `4` |
| C5: Spacing & Layout | `5` |
| C6: Components | `6` |
| C7: Interactions | `7` |
| C8: Wireframes | `8` |
| C9: Finalize | `9` |

On **[P] Pause** at any HALT: Write `docs/design-system.md` with `status: paused` and `current_stage: {N}` (exact numeric value from the table above — never invent descriptive strings). Output resume instructions.

On resume (`status: paused` in design-system.md): Read frontmatter `mode` + `current_stage`, re-enter at that stage's checkpoint, re-present the artifact with approval options, do NOT advance.

---

## Context Preservation

This skill may require context management during long sessions.

### When to Compact Context

Compact at natural boundaries:
- **Mode A**: After Stage 3 (Component Mapping) — before organism generation
- **Mode B**: After Stage 3 (Layout Composition) — before interactions
- **Mode C**: After Stage 4 (Typography), after Stage 6 (Components), after Stage 8 (Wireframes)
- Any mode: When user pauses with [P]

### What to Preserve

Always retain:
- **Mode and progress**: Current mode, stage, completed stages
- **Design tokens**: All color, typography, spacing values defined
- **Component selections**: Which components are in use
- **Organism structures**: Screen layouts and JSX skeletons
- **DS section index**: Header → line range mapping (Mode A/B)
- **Figma data summary**: Token mapping, component instances (Mode A)
- **Accessibility findings**: Issues found, remediation status

### What to Release

Safe to release after summarizing:
- Full agent output (retain decisions, release analysis details)
- Raw Figma MCP responses (retain extracted summary)
- Full DS section content (retain via section index for re-reading)
- Draft content that was revised
- Alternative designs not chosen

---

## Anti-Patterns

**NEVER**:
- Proceed past a checkpoint without user response
- Let agents interact with user directly
- Pass `@` file references to agents (inline content instead)
- Skip accessibility validation
- Load full DESIGN_SYSTEM.md into context (use section index + Read with offset/limit)
- Modify DS Sections 1-12 in `docs/design-system.md` (base is immutable in Mode A/B)
- Present only diffs after feedback — always re-present full artifact
- Auto-advance on ambiguous responses — ask for clarification
- Hardcode colors, spacing, or typography values (use DS tokens)

**ALWAYS**:
- Detect mode in Stage 1 and write to frontmatter
- Build DS section index before reading any section (Mode A/B)
- Read DS sections on-demand with offset/limit (max ~200 lines per stage)
- Inline DS content to agents (max ~400 lines per agent)
- Review agent output before presenting to user
- Ensure minimum contrast ratios (4.5:1 for text, 3:1 for UI components)
- Provide both light and dark mode when requested
- Document all design decisions
- Write to file after each approved stage (crash safety)
- Use Task tool for all agent spawning
- Re-present complete updated artifact after addressing feedback
- Offer mode override at Stage 1
