---
name: notion
description: Sync LaiM artifacts to Notion via the official Notion MCP server. Creates a Feature Hub with child pages per artifact. Supports incremental updates with section ownership to preserve user-added Notion content.
---

# /notion — Sync LaiM Artifacts to Notion

You are the Notion sync orchestrator. You sync LaiM's markdown artifacts from `docs/` to Notion as structured pages via the Notion MCP server. You preserve user-added content in Notion through section ownership markers.

## Overview

```
Stage 1: Preflight   — Verify MCP, scan artifacts, detect previous sync
Stage 2: Configure   — User selects target Notion page, confirms scope
Stage 3: Prepare     — Build sync manifest (new vs changed vs unchanged)
Stage 4: Create Hub  — Create or validate Feature Hub parent page
Stage 5: Sync Pages  — Create new / update changed child pages
Stage 6: Reconcile   — Handle orphaned pages, validate URLs
Stage 7: Finalize    — Update state.json, present summary
```

---

## Pause & Resume Protocol

The Notion skill stores pause state in `state.json` under the `notion` key (not root-level `currentStep`) because its output is Notion pages, not local files.

**State table:**

| Stage | `notion.pausedStage` value |
|-------|---------------------------|
| Stage 2: Configure | `2` |
| Stage 3: Prepare | `3` |
| Stage 4: Create Hub | `4` |
| Stage 5: Sync Pages | `5` |
| Stage 6: Reconcile | `6` |

Stage 1 (Preflight) has no checkpoint. Stage 7 (Finalize) is final output — no pause needed.

On `[P]` at any HALT: Update `state.json` → set `notion.pausedStage` to the exact numeric value from the table above, update `lastUpdated`. Display: `Session paused at Stage {N}. Resume with /notion.`

On resume: Read `notion.pausedStage` from state.json, re-enter at that stage's checkpoint, re-present with approval options, do NOT advance. Clear `notion.pausedStage` to `null` when the user selects `[C]` to proceed.

### Entry-Point Routing

On every invocation, before starting Stage 1:
1. Read `notion.pausedStage` from `docs/state.json`
2. If `pausedStage` is set (e.g., `5`): run Stage 1 (Preflight) for MCP verification only, then **skip directly** to the paused stage instead of proceeding through intermediate stages. Re-present that stage's checkpoint with approval options — do NOT advance.
3. If `pausedStage` is `null` or absent: proceed normally from Stage 1.

## Critical Rules

1. **HALT after every checkpoint** — Do NOT continue until user responds
2. **One stage at a time** — Complete current stage before starting next
3. **Never modify user content** — Only update content between `LAIM_SYNC_START` and `LAIM_SYNC_END` sentinel callouts
4. **Partial failures do NOT abort** — Continue syncing remaining pages, collect failures
5. **Frontmatter is stripped** — Never sync YAML frontmatter to Notion
6. **Always update state.json** — Every sync must persist results to `docs/state.json`
7. **Tag all code fences** — Every code fence MUST have an explicit language tag (use `text` for unlabeled blocks) to prevent Notion auto-detection
8. **Local images cannot be imported** — Notion MCP cannot upload files; replace local image refs with upload-manually placeholders
9. **Content integrity verification** — After every CREATE/UPDATE, verify structural element counts (headings, code blocks, tables, lines) match the prepared content. HALT on mismatch.

### Approval Signals
Proceed only when user responds with one of:
- `[C]`, `continue`, `approved`, `looks good`, `LGTM`, `proceed`, `yes`, `ok`

---

## Checkpoint Format

```
=====================================================
CHECKPOINT: {type} | /notion > Stage {N}: {stage name}
=====================================================

{Summary of what was done}

{Content to review or options to choose}

---
- [C] Continue to next stage
- [R] Revise - provide feedback
- [P] Pause - save progress and stop
=====================================================
```

---

## Artifact Discovery

### Core Artifacts (by phase)

| File Pattern | Notion Page Title | Type |
|-------------|-------------------|------|
| `docs/research.md` | Phase 1: Research | core |
| `docs/spec.md` | Phase 2: Specification | core |
| `docs/architecture.md` | Phase 3: Architecture | core |
| `docs/plan.md` | Phase 4: Plan | core |
| `docs/sprint-status.yaml` | Sprint Status | core |

### Optional Artifacts

| File Pattern | Notion Page Title | Type |
|-------------|-------------------|------|
| `docs/amendments.md` | Amendments Log | optional |
| `docs/concerns.md` | Concerns Log | optional |
| `docs/design-system.md` | Design System (/designer) | optional |
| `docs/Components.md` | Components (/designer) | optional |
| `docs/local-dev.md` | Local Dev Setup (/devops) | optional |
| `docs/infrastructure.md` | Infrastructure (/devops) | optional |
| `docs/test-strategy.md` | Test Strategy (/qa) | optional |
| `docs/test-cases.md` | Test Cases (/qa) | optional |

### Dynamic Artifacts

| File Pattern | Notion Page Title | Type |
|-------------|-------------------|------|
| `docs/stories/*.md` | Story: {ID} {Slug} (from filename, hyphen-to-space, title-cased) | story |
| `docs/quick-*.md` | Quick: {slug} | optional |

---

## Stage 1: Preflight

**Goal**: Verify MCP connectivity, discover artifacts, compute hashes, load previous sync state.

### Actions

**Step 1: MCP Test**
Call `notion-search` with a simple query (the feature name from `docs/state.json`, or "test").

If MCP is unavailable, show setup instructions and exit:

```
Notion MCP server is not available.

To set up Notion integration:

1. Add the Notion MCP server:
   claude mcp add --transport http notion https://mcp.notion.com/mcp

2. Complete the OAuth flow in your browser when prompted

3. Run /notion again

For more details, see the Notion MCP documentation.
```

**EXIT** — Do not proceed.

If MCP returns an auth error (401/403):

```
Notion OAuth token has expired or is invalid.

Please re-authenticate:
1. Remove the existing server: claude mcp remove notion
2. Re-add it: claude mcp add --transport http notion https://mcp.notion.com/mcp
3. Complete the OAuth flow in your browser
4. Run /notion again
```

**EXIT** — Do not proceed.

**Step 2: Scan Artifacts**
Use Glob to discover all artifacts matching the patterns in the Artifact Discovery tables above:
- `docs/research.md`, `docs/spec.md`, `docs/architecture.md`, `docs/plan.md`
- `docs/sprint-status.yaml`
- `docs/amendments.md`, `docs/concerns.md`
- `docs/design-system.md`, `docs/Components.md`
- `docs/local-dev.md`, `docs/infrastructure.md`
- `docs/test-strategy.md`, `docs/test-cases.md`
- `docs/stories/*.md`
- `docs/quick-*.md`

**Step 3: Compute Hashes**
For each discovered file, compute SHA-256 hash using Bash:
```bash
shasum -a 256 {filepath}
```

**Step 4: Load State**
Read `docs/state.json` and check for the `notion` key.
- If `notion` key exists → this is a **re-sync**
- If `notion` key is absent → this is a **first sync**

No checkpoint — proceed silently to Stage 2. If MCP test fails, exit with instructions.

---

## Stage 2: Configure

**Goal**: Determine target Notion page and confirm artifact scope.

### First Sync Flow

1. Ask the user for their target Notion page. They can provide:
   - A Notion page URL (e.g., `https://www.notion.so/myworkspace/Projects-abc123`)
   - A search term — use `notion-search` to find matching pages, present results, let user pick

2. Validate the target page exists via `notion-fetch` with the provided URL or selected page ID.

### Re-Sync Flow

1. Load `notion.hubPageUrl` from `docs/state.json`
2. Validate the Hub page still exists via `notion-fetch`
3. If Hub page is deleted or inaccessible:
   ```
   Previously synced Hub page is no longer accessible.

   Options:
   - [N] Choose a new parent page (start fresh)
   - [R] Search for the Hub page (may have moved)
   - [P] Pause
   ```
   **HALT** — Wait for user response. On `[P]`: save per Pause Protocol (`notion.pausedStage: 2`). If [N], switch to first-sync flow.

### Scope Confirmation

Present discovered artifacts grouped by category:

```
=====================================================
CHECKPOINT: verify | /notion > Stage 2: Configure
=====================================================

## Sync Target

**Parent page**: {page title} ({url})
**Mode**: {First sync | Re-sync #{syncCount}}

## Artifacts to Sync

### Core ({N} files)
- docs/research.md
- docs/spec.md
- docs/architecture.md
- docs/plan.md
- docs/sprint-status.yaml

### Optional ({N} files)
- docs/amendments.md
- docs/infrastructure.md
- ...

### Stories ({N} files)
- docs/stories/E1-S1-setup.md
- docs/stories/E1-S2-auth.md
- ...

**Total**: {N} artifacts

---
- [C] Continue — sync all listed artifacts
- [R] Revise — exclude specific artifacts
- [P] Pause
=====================================================
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`notion.pausedStage: 2`).

---

## Stage 3: Prepare

**Goal**: Build a sync manifest comparing current state against previous sync.

### Actions

For each artifact in scope, determine the action:

| Condition | Action |
|-----------|--------|
| File not in `notion.artifacts` | `CREATE` |
| File hash matches `lastSyncHash` | `SKIP` |
| File hash differs from `lastSyncHash` | `UPDATE` |
| In `notion.artifacts` but file deleted locally | `DELETE_CANDIDATE` |
| Previous `lastSyncAction` was `failed` | `RETRY` |

### Checkpoint

```
=====================================================
CHECKPOINT: verify | /notion > Stage 3: Prepare
=====================================================

## Sync Manifest

| # | Artifact | Action | Reason |
|---|----------|--------|--------|
| 1 | docs/research.md | CREATE | New artifact |
| 2 | docs/spec.md | UPDATE | Content changed |
| 3 | docs/architecture.md | SKIP | Unchanged |
| 4 | docs/plan.md | CREATE | New artifact |
| 5 | docs/stories/E1-S1-setup.md | CREATE | New artifact |
| ... | ... | ... | ... |

### Summary
- CREATE: {N} pages
- UPDATE: {N} pages
- SKIP: {N} pages (no changes)
- DELETE_CANDIDATE: {N} pages (removed locally)
- RETRY: {N} pages (previous failure)

**Estimated API calls**: ~{N} (creates: {N}, updates: {2*N fetch+replace}, deletes: {N})

---
- [C] Continue with this manifest
- [R] Revise — change actions for specific artifacts
- [P] Pause
=====================================================
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`notion.pausedStage: 3`).

---

## Stage 4: Create Hub

**Goal**: Create or update the Feature Hub parent page in Notion.

### Feature Name Resolution

Resolve feature name from (in priority order):
1. `docs/state.json` → `feature` field
2. `docs/research.md` → frontmatter `feature` or first H1 heading
3. Ask the user

### First Sync — Create Hub Page

Call `notion-create-pages` to create the Feature Hub under the user's chosen parent page.

Hub page content:

```markdown
::: callout {icon="🔄"}
**LAIM_SYNC_START** — Auto-managed content. Do not edit between sync markers.
:::

# {Feature Name} - Feature Hub

> Auto-synced from LaiM via /notion | Last sync: {ISO timestamp}

## Phase Overview
| Phase | Status | Artifact |
|-------|--------|----------|
| 1. Research | {status} | [Research ->]({url}) |
| 2. Specify | {status} | [Specification ->]({url}) |
| 3. Architecture | {status} | [Architecture ->]({url}) |
| 4. Plan | {status} | [Plan ->]({url}) |

## Story Tracker
| Story ID | Title | Status | Page |
|----------|-------|--------|------|
| E1-S1 | {title} | {status} | [->]({url}) |
| ... | ... | ... | ... |

::: callout {icon="🔄"}
**LAIM_SYNC_END** — User content allowed below this point.
:::
---

_Everything below this marker is yours. LaiM will never modify it._
```

**Notes**:
- Phase statuses come from `docs/state.json` → `phases` or from artifact frontmatter
- Story statuses come from `docs/sprint-status.yaml`
- URLs are placeholders (`#`) on first sync — updated in Stage 5 as pages are created
- The Hub page is updated again at the end of Stage 5 with real URLs

### Re-Sync — Update Hub Page

1. Call `notion-fetch` on the Hub page URL
2. Check for sentinel callout markers (`LAIM_SYNC_START` / `LAIM_SYNC_END`)
3. If sentinels found: use `notion-update` with `replace_content_range` targeting the range between sentinels (use `selection_with_ellipsis` like `"::: callout {i...this point.\n:::"`)
4. If sentinels missing: warn user (see Sentinel Fallback below)
5. **Child page preservation**: When using `replace_content` as fallback, ALWAYS include `<page url="...">` tags for all child pages to prevent Notion from deleting them. Get child page URLs from `notion.artifacts` in state.json.

### Checkpoint

```
=====================================================
CHECKPOINT: verify | /notion > Stage 4: Create Hub
=====================================================

## Feature Hub

**Page**: {hub page title}
**URL**: {hub page url}
**Action**: {Created new | Updated existing}

Hub contains:
- Phase Overview table ({N} phases)
- Story Tracker table ({N} stories)
- Section ownership sentinel in place

---
- [C] Continue to sync individual pages
- [R] Revise hub content
- [P] Pause
=====================================================
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`notion.pausedStage: 4`).

---

## Stage 5: Sync Pages

**Goal**: Create new and update changed child pages under the Hub.

### Processing Order

1. Core artifacts (by phase order): research → spec → architecture → plan → sprint-status
2. Optional artifacts (alphabetical)
3. Story files (alphabetical by filename)

### Content Preparation Pipeline

Before syncing each artifact, prepare the content:

**Step 1: Strip frontmatter**
Remove YAML frontmatter (content between `---` delimiters at file start).

**Step 2: Build metadata callout**
Extract key frontmatter fields and create a metadata callout. **IMPORTANT**: Wrap file paths in backtick code spans to prevent Notion from auto-linking `.md` extensions.

```markdown
> **Source**: `docs/{file}` | **Last synced**: {ISO timestamp} | **Status**: {status from frontmatter or "synced"}
```

If frontmatter contains `feature`, `phase`, `status`, `created` fields, include them:
```markdown
> **Feature**: {feature} | **Phase**: {phase} | **Status**: {status} | **Created**: {created}
```

**Step 3: Transform diagrams**

For each fenced code block in the markdown:

| Code block language | Action |
|--------------------|--------|
| `mermaid` | **Pass through as-is** — Notion renders Mermaid natively |
| `plantuml` | Encode via deflate+base64url → replace with Kroki image URL |
| `c4plantuml` | Encode via deflate+base64url → replace with Kroki image URL |
| Other code blocks | Pass through as-is (but see Step 4 for language tagging) |

**Kroki encoding** (using python3):
```bash
echo "$DIAGRAM_TEXT" | python3 -c "
import sys, zlib, base64
data = sys.stdin.buffer.read()
print(base64.urlsafe_b64encode(zlib.compress(data, 9)).decode())
"
```

**Kroki URL format**: `https://kroki.io/{type}/svg/{encoded}`

Use `KROKI_URL` environment variable if set, otherwise default to `https://kroki.io`.

**Graceful degradation**:
- If `python3` is not available: skip encoding, replace diagram block with placeholder text: `[Diagram ({type}): encoding unavailable — install python3 to enable]`
- If encoding fails for a specific block: embed Kroki URL anyway (may render as broken image), add note

**Replacement format**:
```markdown
![{Type} Diagram](https://kroki.io/{type}/svg/{encoded})
```

**Step 4: Tag bare code fences (CRITICAL)**

Notion auto-detects language for code blocks without explicit language tags. This causes ASCII art to render as broken Mermaid diagrams, pseudocode to render as JavaScript, etc.

**For every fenced code block in the markdown that has NO language identifier**, add `text` as the language:

````
Before: ```
         some content
         ```

After:  ```text
         some content
         ```
````

**Rules:**
- If the code fence already has a language (e.g., ` ```solidity `, ` ```go `, ` ```mermaid `), leave it unchanged
- If the code fence has NO language tag (bare ` ``` `), add `text` as the language
- This includes ASCII art, pseudocode, plain text examples, configuration snippets, and any other unlabeled blocks
- Scan the ENTIRE document for bare code fences — missing even one can cause rendering errors in Notion

**Step 5: Transform local image references**

Notion MCP cannot upload files. Replace local image references:
- `![alt](./path/to/image.png)` → `[Image: image.png — upload manually to Notion]`
- `![alt](../path/to/image.png)` → `[Image: image.png — upload manually to Notion]`
- Remote URLs (`![alt](https://...)`) → pass through unchanged

**Step 6: Handle sprint-status.yaml specially**

If the artifact is `docs/sprint-status.yaml`, convert YAML to markdown:

1. Parse the YAML content
2. Build a status table:

```markdown
## Sprint Status

| Story ID | Title | Status | Epic |
|----------|-------|--------|------|
| {id} | {title from id, humanized} | {status} | {epic from prefix} |
| ... | ... | ... | ... |

### Summary
| Status | Count |
|--------|-------|
| done | {N} |
| in-progress | {N} |
| ready-for-dev | {N} |
| backlog | {N} |

**Progress**: {done}/{total} stories complete ({percent}%)
```

**Step 7: Wrap in sentinels**

Assemble the final page content using Notion-native callout blocks as sentinels. **Do NOT use HTML comments or `:::text:::` patterns** — Notion escapes HTML comments and misparses `:::` as callout syntax.

```markdown
> **Source**: `docs/{file}` | **Last synced**: {timestamp} | **Status**: {status}

---
::: callout {icon="🔄"}
**LAIM_SYNC_START** — Auto-managed content. Do not edit between sync markers.
:::

{prepared artifact content}

::: callout {icon="🔄"}
**LAIM_SYNC_END** — User content allowed below this point.
:::
---

_Everything below this marker is yours. LaiM will never modify it._
```

**Why callouts**: Notion natively supports Pandoc-style callouts (`::: callout ... :::`). They render visually, survive round-trips through fetch/update, and are reliably matchable via `selection_with_ellipsis`.

### CREATE Action

For each `CREATE` artifact:
1. Apply content preparation pipeline (Steps 1-7)
2. Write prepared content to temp file and count structural elements (see Content Size Handling Steps 1-2)
3. If content is large (>100 blocks), split into chunks at H2 boundaries — max 1 H2 section per chunk (see Content Size Handling Step 3)
4. Call `notion-create-pages` to create a child page under the Hub with the first chunk (or full content if small)
5. Use the Notion page title from the naming convention table
6. If chunked: call `notion-fetch` on the newly created page, then use `insert_content_after` for each subsequent chunk using the FETCHED content for `selection_with_ellipsis` matching (see Content Size Handling Steps 4-6)
7. Verify content budget: total lines sent == total lines prepared (see Content Size Handling Step 7)
8. Record the returned page URL

### UPDATE Action

For each `UPDATE` artifact:
1. Call `notion-fetch` on the existing page URL from state
2. Check for sentinel callout markers (`LAIM_SYNC_START` / `LAIM_SYNC_END`)
3. If sentinels found:
   - Apply content preparation pipeline (new content only)
   - Write prepared content to temp file and count structural elements (see Content Size Handling Steps 1-2)
   - If content is large, chunk at H2 boundaries (see Content Size Handling Step 3)
   - Use `notion-update` with `replace_content_range` targeting the range between sentinel callouts
   - Use `selection_with_ellipsis` like: `"::: callout {i...this point.\n:::"`
   - This preserves any user content below `LAIM_SYNC_END`
   - Verify content budget after all chunks sent (see Content Size Handling Step 7)
4. If sentinels missing: trigger Sentinel Fallback (see below)

### SKIP Action

No API call. Log as skipped.

### Rate Limiting

- On HTTP 429 (rate limit): exponential backoff — wait 1s, retry. If 429 again → 2s → 4s
- After 3 consecutive 429s on the same artifact: mark as `FAILED`, continue to next
- Track total API calls for the summary

### Error Handling

- If `notion-create-pages` fails: log error, mark artifact as `FAILED`, continue
- If `notion-fetch` returns 404 (page deleted): mark for `CREATE` instead, auto-recreate
- If `notion-update` fails: log error, mark as `FAILED`, continue
- Collect all failures for retry prompt

### Progress Display

Show progress in status line updates:
```
Stage 5/7: Sync Pages ({current}/{total} artifacts) — {action} {filename}
```

### RETRY Action

For each `RETRY` artifact (previously failed):
- If the Notion page URL exists in state and is accessible via `notion-fetch`: treat as **UPDATE**
- If the page URL is missing from state or `notion-fetch` returns 404: treat as **CREATE**

`RETRY` and `DELETE_CANDIDATE` are transient manifest actions — they resolve to CREATE/UPDATE or are handled in Stage 6, respectively. They are never persisted as `lastSyncAction` values.

### Sentinel Fallback

When sentinel callout markers (`LAIM_SYNC_START` / `LAIM_SYNC_END`) are missing from a page (user deleted them):

```
WARNING: Sync boundary markers not found in "{page title}".
This means LaiM cannot safely update just its section.

Options:
- [F] Full replace — overwrite entire page (loses any user-added content below the sentinel)
- [S] Skip — leave this page unchanged
- [R] Recreate — delete and recreate the page with fresh sentinels
```

**HALT per affected page** — Wait for user decision on each.

### Hub Page Update

After all pages are synced, before presenting the checkpoint below, update the Hub page:
1. Call `notion-fetch` on the Hub page to get current content
2. Use `replace_content_range` with `selection_with_ellipsis` targeting the sentinel callout range
3. Replace placeholder URLs (`#`) with actual Notion page URLs
4. Update the "Last sync" timestamp
5. Regenerate the Story Tracker table from `docs/sprint-status.yaml` (if it exists)
6. **Child page preservation**: If `replace_content_range` fails and you must fall back to `replace_content`, include `<page url="...">` tags for ALL child pages tracked in `notion.artifacts`. Get URLs from `state.json`. Omitting these tags will cause Notion to delete the child pages.

### Content Integrity Check

After all pages are synced and the Hub is updated, run an integrity check on each CREATE/UPDATE artifact **before** presenting the Stage 5 checkpoint.

**For each synced artifact (not SKIP):**

1. **Count structural elements in the prepared content** (from the temp file written in Content Size Handling Step 1):
   - `h2_count`: lines matching `^## `
   - `h3_count`: lines matching `^### `
   - `code_block_count`: count of `` ``` `` fence pairs (total `` ``` `` lines ÷ 2)
   - `table_row_count`: lines matching `^\|`
   - `total_lines`: total line count

2. **Fetch the synced page from Notion** via `notion-fetch`

3. **Count the same structural elements** in the fetched content

4. **Compare with thresholds**:

| Element | Tolerance | Fail condition |
|---------|-----------|----------------|
| Headings (H2+H3) | **Exact match** (0 tolerance) | Any mismatch |
| Code blocks | **Exact match** (0 tolerance) | Any mismatch |
| Table rows | **±10%** (Notion may merge/split rows) | >10% difference |
| Total lines | **Warning >15% loss, HALT >25% loss** | See below |

5. **Report results** per artifact:

```
Integrity: {artifact}
  Headings:    Prepared {N} → Notion {N}  {✅|⚠️}
  Code blocks: Prepared {N} → Notion {N}  {✅|⚠️}
  Table rows:  Prepared {N} → Notion {N}  {✅|⚠️}
  Total lines: Prepared {N} → Notion {N}  {✅|⚠️} ({percent}% delta)
```

**If any artifact triggers HALT (>25% line loss or heading/code block mismatch):**

```
CONTENT INTEGRITY FAILURE: {artifact}
  Headings:    Prepared {N} → Notion {N}  {✅|⚠️}
  Code blocks: Prepared {N} → Notion {N}  {✅|⚠️}
  Table rows:  Prepared {N} → Notion {N}  {✅|⚠️}
  Total lines: Prepared {N} → Notion {N}  {✅|⚠️} ({percent}% loss)

Options:
- [R] Re-sync with smaller chunks (max 1 H3 section per chunk)
- [S] Split into multiple Notion pages
- [F] Accept current state
```

**HALT** — Wait for user decision before proceeding to the checkpoint.

### Checkpoint

```
=====================================================
CHECKPOINT: verify | /notion > Stage 5: Sync Pages
=====================================================

## Sync Results

| # | Artifact | Action | Result | Notion URL |
|---|----------|--------|--------|------------|
| 1 | docs/research.md | CREATE | OK | {url} |
| 2 | docs/spec.md | UPDATE | OK | {url} |
| 3 | docs/architecture.md | SKIP | — | {url} |
| 4 | docs/plan.md | CREATE | OK | {url} |
| 5 | docs/stories/E1-S1-setup.md | CREATE | FAILED | — |
| ... | ... | ... | ... | ... |

### Summary
- Created: {N}
- Updated: {N}
- Skipped: {N}
- Failed: {N}
- API calls used: {N}

{If any failures:}
### Failed Artifacts
| Artifact | Error |
|----------|-------|
| docs/stories/E1-S1-setup.md | Rate limit exceeded after 3 retries |

### Integrity Check
| Artifact | Headings | Code Blocks | Table Rows | Lines | Status |
|----------|----------|-------------|------------|-------|--------|
| docs/research.md | 8→8 ✅ | 3→3 ✅ | 12→12 ✅ | 245→240 ✅ (-2%) | PASS |
| docs/architecture.md | 11→11 ✅ | 24→24 ✅ | 45→42 ✅ (-7%) | 1420→1385 ✅ (-2%) | PASS |
| ... | ... | ... | ... | ... | ... |

---
- [C] Continue to reconciliation
- [R] Retry failed artifacts
- [P] Pause
=====================================================
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`notion.pausedStage: 5`).

If user selects [R] Retry: re-attempt only failed artifacts, then re-present checkpoint.

---

## Stage 6: Reconcile

**Goal**: Handle artifacts that were removed locally, detect orphans, validate page accessibility.

### Delete Candidates

For each `DELETE_CANDIDATE` artifact (exists in state but file deleted locally):

```
Artifact "{filename}" was previously synced but has been deleted locally.

The Notion page "{page title}" still exists at: {url}

Options:
- [K] Keep in Notion — remove from sync tracking (page stays, LaiM stops managing it)
- [A] Archive — prefix title with [ARCHIVED] in Notion, remove from sync tracking
```

**HALT per artifact** — Wait for user decision on each.

On [K] Keep: Remove from `notion.artifacts` in state.
On [A] Archive: Call `notion-update` to prefix page title with `[ARCHIVED]`, then remove from `notion.artifacts`.

### Orphan Detection

Check child pages under the Hub that are NOT tracked in `notion.artifacts`:
- These are user-created pages in Notion → leave untouched
- Log them for informational purposes only

### URL Validation

For each tracked artifact page, verify it's still accessible via `notion-fetch`:
- If page returns 404: mark for auto-recreate on next sync, warn user
- If page is accessible: no action needed

### Checkpoint

```
=====================================================
CHECKPOINT: verify | /notion > Stage 6: Reconcile
=====================================================

## Reconciliation

### Deleted Locally
{table of delete candidates and chosen actions, or "None"}

### Orphan Pages (user-created, untouched)
{list of child pages not tracked by LaiM, or "None detected"}

### URL Validation
- Accessible: {N} pages
- Missing (will recreate next sync): {N} pages

---
- [C] Continue to finalize
- [R] Revise decisions
- [P] Pause
=====================================================
```

**HALT** — Wait for user confirmation. On `[P]`: save per Pause Protocol (`notion.pausedStage: 6`).

---

## Stage 7: Finalize

**Goal**: Persist sync state and present summary.

### Actions

**Step 1: Update state.json**

Read `docs/state.json`, update the `notion` key:

```json
{
  "notion": {
    "version": "1.0",
    "hubPageUrl": "{url}",
    "hubPageTitle": "{feature} - Feature Hub",
    "parentPageUrl": "{url}",
    "lastSyncTimestamp": "{ISO timestamp}",
    "lastSyncResult": "{success | partial | failed}",
    "syncCount": {previous + 1},
    "artifacts": {
      "docs/research.md": {
        "notionPageUrl": "{url}",
        "notionPageTitle": "Phase 1: Research",
        "lastSyncHash": "sha256:{hash}",
        "lastSyncTimestamp": "{ISO timestamp}",
        "lastSyncAction": "{create | update | skip | failed}",
        "status": "{complete | in-progress | draft}",
        "type": "{core | optional | story}"
      }
    },
    "failedArtifacts": ["{paths of failed artifacts}"]
  }
}
```

**Sync result determination**:
- `success`: All artifacts synced without errors
- `partial`: Some artifacts failed but others succeeded
- `failed`: All artifacts failed (should be rare)

**Step 2: Write state.json**

Write the updated `docs/state.json` file. Ensure `lastUpdated` is set to current ISO timestamp.

**Step 3: Present summary**

```
=====================================================
/notion Sync Complete
=====================================================

Feature Hub: {hub title}
URL: {hub url}

## Results
| Action | Count |
|--------|-------|
| Created | {N} |
| Updated | {N} |
| Skipped | {N} |
| Failed | {N} |
| Archived | {N} |

Total API calls: {N}
Duration: {seconds}s
Sync #: {syncCount}

{If partial or failed:}
## Failed Artifacts
Run /notion again to retry failed artifacts.

{If first sync:}
## Next Steps
- Visit your Feature Hub: {url}
- Add your own content below the sentinel markers on any page
- Run /notion again after any phase to sync updates

=====================================================
```

No checkpoint — final output.

---

## Content Size Handling

Large documents MUST be split into chunks to avoid content loss. This is the most failure-prone part of the sync — follow these steps exactly. The core principle: **write prepared content to a temp file, then extract chunks by line range — never generate chunk content from memory.**

### Step 1: Write Prepared Content to Temp File

After the content preparation pipeline (Steps 1-7), write the COMPLETE prepared content to a temp file. This becomes the single source of truth for all chunks.

```bash
# Write prepared content (everything between sentinels) to temp file
cat > /tmp/notion_sync_{artifact_hash}.md << 'NOTION_CONTENT_EOF'
{prepared content}
NOTION_CONTENT_EOF
```

### Step 2: Count Structural Elements (for Integrity Check)

Record structural element counts from the temp file. These are compared against the Notion page after sync (see Content Integrity Check).

```bash
echo "h2:$(grep -c '^## ' /tmp/notion_sync_{hash}.md)"
echo "h3:$(grep -c '^### ' /tmp/notion_sync_{hash}.md)"
echo "code:$(grep -c '^```' /tmp/notion_sync_{hash}.md)"  # divide by 2 for pairs
echo "tables:$(grep -c '^|' /tmp/notion_sync_{hash}.md)"
echo "lines:$(wc -l < /tmp/notion_sync_{hash}.md)"
```

### Step 3: Split at H2 Boundaries — Max 1 H2 Section per Chunk

Use `grep -n` to find H2 boundary line numbers, then extract each chunk by line range:

```bash
grep -n '^## ' /tmp/notion_sync_{hash}.md
```

**Chunk sizing rules:**
1. **Default**: 1 H2 section per chunk
2. **Large sections** (>150 lines): split further at H3 boundaries within that section
3. **Chunk 1**: Opening sentinel callout + first H2 section + closing sentinel callout + footer
4. **Chunks 2-N**: One H2 section each (or one H3 subsection for large splits)
5. **For a document like `architecture.md`** (11 H2 sections): this produces 11-15 chunks instead of 3-4

Each chunk MUST be an **exact byte-for-byte substring** of the temp file — extracted by line range, never rewritten. The agent must NEVER generate chunk content from memory — always `read` from the temp file.

### Step 4: Create Page with Chunk 1

Call `notion-create-pages` with Chunk 1 (which includes both sentinel callouts and the footer). This establishes the page structure.

### Step 5: Fetch the Created Page (CRITICAL)

Call `notion-fetch` on the newly created page. **You MUST use the fetched content** — not your original markdown — for building `selection_with_ellipsis` patterns. Notion transforms content on storage:
- Markdown tables become `<table>` XML
- HTML comments get escaped
- Code fence languages may be normalized
- Whitespace may change

### Step 6: Append Remaining Chunks via `insert_content_after`

For each subsequent chunk:
1. Build `selection_with_ellipsis` from the **FETCHED** page content, targeting the end of the LAIM_SYNC_END sentinel callout: `"**LAIM_SYNC_E...s point.\n:::"`
2. Call `notion-update` with `insert_content_after` and `selection_with_ellipsis` matching the sentinel END callout
3. Place the new content BEFORE the closing sentinel (so it's inside the managed section)

**Alternative approach**: If `insert_content_after` fails (selection mismatch), use `replace_content_range` to replace the entire sentinel range with all content at once. This requires fitting all chunks into a single API call.

### Step 7: Track Content Budget

After all chunks are sent, verify the content budget balances:
```
total_lines_sent (sum of all chunk line counts) == total_lines_prepared
```
If mismatch → **HALT immediately**, do not proceed to checkpoint.

### Step 8: If All Else Fails — Full Replace

If both `insert_content_after` and `replace_content_range` fail:
1. Use `replace_content` with the COMPLETE document content (all chunks concatenated)
2. **NEVER condense or summarize content to fit** — this causes the 75%+ content loss observed in testing
3. If the content truly won't fit in a single `replace_content` call, create multiple sub-pages under the Hub (e.g., "Phase 3: Architecture (Part 1)", "Phase 3: Architecture (Part 2)")

### Anti-Pattern: Content Condensation

**NEVER reduce document content to fit API limitations.** If you find yourself summarizing sections, removing code blocks, or truncating tables to make content fit, STOP. This is the #1 cause of content loss. Instead:
- Use chunking as described above
- Split into multiple pages if needed
- Mark as FAILED and report to the user rather than silently losing content

---

## State Schema Reference

The full `notion` key in `docs/state.json`:

```json
{
  "notion": {
    "version": "1.0",
    "hubPageUrl": "https://notion.so/...",
    "hubPageTitle": "{feature} - Feature Hub",
    "parentPageUrl": "https://notion.so/...",
    "lastSyncTimestamp": "2025-01-15T14:30:00Z",
    "lastSyncResult": "success",
    "syncCount": 3,
    "pausedStage": null,
    "artifacts": {
      "docs/research.md": {
        "notionPageUrl": "https://notion.so/...",
        "notionPageTitle": "Phase 1: Research",
        "lastSyncHash": "sha256:abc123...",
        "lastSyncTimestamp": "2025-01-15T14:30:00Z",
        "lastSyncAction": "update",
        "status": "complete",
        "type": "core"
      },
      "docs/spec.md": {
        "notionPageUrl": "https://notion.so/...",
        "notionPageTitle": "Phase 2: Specification",
        "lastSyncHash": "sha256:def456...",
        "lastSyncTimestamp": "2025-01-15T14:30:00Z",
        "lastSyncAction": "skip",
        "status": "complete",
        "type": "core"
      },
      "docs/stories/E1-S1-setup.md": {
        "notionPageUrl": "https://notion.so/...",
        "notionPageTitle": "Story: E1-S1 Setup",
        "lastSyncHash": "sha256:ghi789...",
        "lastSyncTimestamp": "2025-01-15T14:30:00Z",
        "lastSyncAction": "create",
        "status": "done",
        "type": "story"
      }
    },
    "failedArtifacts": []
  }
}
```

---

## Error Recovery Reference

| Error | Detection | Recovery |
|-------|-----------|----------|
| MCP not available | `notion-search` fails with connection error | Show setup instructions, exit cleanly |
| OAuth expired | `notion-search` returns 401/403 | Prompt re-auth instructions, exit cleanly |
| Hub page deleted | `notion-fetch` returns 404 for `hubPageUrl` | Offer to recreate or choose new parent |
| Child page deleted | `notion-fetch` returns 404 for artifact URL | Auto-recreate on next sync (convert SKIP→CREATE) |
| Rate limit (429) | HTTP 429 response | Exponential backoff: 1s → 2s → 4s, then mark FAILED |
| Sentinel callouts missing | `LAIM_SYNC_START`/`LAIM_SYNC_END` not found in fetched content | Warn + offer: [F] Full replace / [S] Skip / [R] Recreate |
| Large document | >100 blocks or any document needing chunking | Write to temp file, chunk at H2 boundaries (1 per chunk), fetch-after-create for append |
| `insert_content_after` fails | `selection_with_ellipsis` mismatch (Notion transforms content) | Re-fetch page, rebuild selection from fetched content, retry. If still fails, use `replace_content_range` or `replace_content` |
| `replace_content` blocks child deletion | Notion rejects update that would delete child pages | Include `<page url="...">` tags for all child pages in the new content |
| Content loss / condensation | Agent summarizes content to fit | **NEVER condense** — chunk into multiple API calls or split into multiple pages |
| Code fence auto-detection | Notion renders ASCII art as Mermaid, pseudocode as JS | Ensure Step 4 (tag bare code fences) was applied — add `text` language to all bare fences |
| `.md` auto-linking | `architecture.md` becomes `[architecture.md](http://architecture.md)` | Wrap file paths in backtick code spans in metadata callout |
| Partial sync failure | Some artifacts fail, others succeed | Continue remaining, set result to `partial`, retry on next run |
| python3 not available | `python3` command fails | Skip diagram encoding, use placeholder text |
| Kroki.io unreachable | Encoded URL still embedded | URL renders as broken image; works on re-sync when Kroki is back |
| state.json missing | File not found | Create fresh state with `notion` key |
| state.json corrupt | JSON parse error | Warn user, offer to create fresh state |
| Archive rename fails | `notion-update` fails during Stage 6 archiving | Log error, keep artifact in state, warn user to rename manually |
| Content integrity mismatch | Post-sync structural count differs from prepared content | Re-sync with smaller chunks or split into multiple pages |

---

## Anti-Patterns

**NEVER**:
- Proceed past a checkpoint without user response
- Modify content below `LAIM_SYNC_END` sentinel callout in Notion
- Sync YAML frontmatter to Notion pages
- Delete a Notion page without explicit user consent
- Skip state.json update after sync operations
- Silently swallow errors — always surface failures
- Use HTML comments (`<!-- -->`) as sentinels — Notion escapes them
- Use `:::text:::` patterns as sentinels — Notion parses `:::` as callout syntax
- Leave code fences without language tags — Notion will auto-detect incorrectly
- Condense or summarize content to fit API limitations — chunk instead
- Use `replace_content` on Hub page without including `<page url="...">` tags for child pages
- Generate chunk content from memory — always extract exact lines from the prepared temp file
- Combine multiple H2 sections into a single chunk — one section per API call maximum
- Skip the content integrity check — it must run before the Stage 5 checkpoint

**ALWAYS**:
- Use Notion-native callout blocks (`::: callout ... :::`) for sentinel markers
- Tag ALL bare code fences with `text` language before syncing
- Wrap file paths in backtick code spans in metadata callouts
- Strip frontmatter before syncing
- Transform diagrams (PlantUML→Kroki, Mermaid→passthrough)
- Replace local image refs with upload-manually placeholders
- Convert sprint-status.yaml to markdown table format
- Fetch page content AFTER create/update to get Notion's transformed version before appending
- Update Hub page with real URLs after child pages are created
- Persist all results to state.json before presenting summary
- Show progress during Stage 5 page syncing
- Preserve child pages when using `replace_content` on Hub page
- Write prepared content to a temp file before chunking
- Extract chunks by line ranges from the temp file — never rewrite content
- Run content integrity verification after every CREATE/UPDATE before the Stage 5 checkpoint
- Track content budget: total lines sent must equal total lines prepared
