# NXME.ai

AI-powered glow-up app. Python (FastAPI) backend + React Native (Expo) mobile.

## Stack

- **Backend**: Python 3.12, FastAPI, Supabase (Postgres), ARQ worker, ruff
- **Mobile**: TypeScript, React Native, Expo Router, Expo SDK
- **Infra**: Docker Compose (local Supabase), Supabase Cloud (prod)

## Quick Start (local dev)

```bash
# Terminal 1 — Backend (Supabase + Redis + API on :8000)
make up

# Terminal 2 — Mobile (native dev build on iOS Simulator)
cd mobile && npx expo run:ios
```

Requires: `app/.env` (backend) and `mobile/.env` (mobile) — copy from `.env.example` and fill in values.
`mobile/.env` must have `API_BASE_URL` set to your machine's LAN IP (e.g. `http://192.168.x.x:8000`).

## Build & Verify

```bash
# Backend
make up              # Start local dev (Supabase + API)
make test            # pytest -x -q
make lint            # ruff check app/ tests/
make format          # ruff format app/ tests/
make migrate         # Run DB migrations
make worker          # ARQ background worker (separate terminal)

# Mobile
cd mobile && npx expo run:ios   # Native dev build (required for Google Sign-In, TikTok SDK)
cd mobile && npx expo start     # JS-only reload (after initial build)
cd mobile && npx expo lint      # ESLint
```

## Verification Loop (run before every commit)

1. `make format` — auto-fix formatting
2. `make lint` — must pass clean
3. `make test` — must pass
4. `cd mobile && npx expo lint` — must pass for mobile changes

## Key Directories

- `app/` — Backend (FastAPI routes, services, repositories, migrations)
- `mobile/` — React Native app (Expo Router)
- `mobile/components/` — Reusable UI components
- `mobile/lib/` — API client, auth context, utilities
- `app/config/` — AppConfig + TierConfig (see coding-conventions rule)
- `scripts/` — Dev utilities

## Dev Feature Focus (test a screen without login)

Skip login entirely and land directly on a specific screen — useful for iterating on the glow-up upload/generation flow.

**Enable:**
1. Open `mobile/.env` — set `DEV_FEATURE_FOCUS=upload`
2. Restart: `cd mobile && npx expo run:ios` (first time) or `npx expo start` (JS reload only)
3. The app bypasses login and opens the upload screen directly. API calls use guest tokens.

**Disable:**
1. Set `DEV_FEATURE_FOCUS=` (empty) in `mobile/.env`
2. Restart the dev server

**How it works:** `AuthGuard` in `app/_layout.tsx` checks `DEV_FEATURE_FOCUS` before any auth logic. If set, it redirects to that route unconditionally. `apiFetch` already falls back to `X-Guest-Token` when no JWT is present, so API calls work without a logged-in user. The constant is always `null` in production (guarded by `__DEV__`).

**Other routes you can focus on:** any valid Expo Router path, e.g. `/(tabs)`, `/onboarding`, `/(auth)/login`.

> Heads up: end-to-end generation requires the backend to accept guest tokens on `POST /v1/analyses`. If you hit 401s, you're authenticated-only on that endpoint.

## Memory

Architecture decisions and project context: `~/.claude/projects/.../memory/MEMORY.md`

## Conventions

See `.claude/rules/` for language-specific standards (auto-loaded by glob):
- `coding-conventions.md` — NXME-specific config sources, Context7, no magic numbers
- `react.md` — Component state checklist, design tokens, a11y
- `nodejs.md` — TypeScript/ESLint standards, Result pattern
- `database-patterns.md` — ESR indexing, RLS, migration patterns
- `code-standards.md` — Commit protocol, verification loop, deviation rules

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
