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

- `app/` — Backend (FastAPI routes, services, repositories, migrations) — see `app/AGENTS.md`
- `mobile/` — React Native app (Expo Router) — see `mobile/AGENTS.md`
- `card-web/` — Next.js web surface — see `card-web/AGENTS.md`
- `scripts/` — Dev utilities
- `tests/` — Python test suite (lives at project root, not under `app/`)
- `docs/solutions/` — documented solutions to past problems (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or debugging in documented areas.

When working inside any of `app/`, `mobile/`, or `card-web/`, read that module's `AGENTS.md` first — it has module-specific commands, layout, and gotchas not covered here.

## Memory

- `MEMORY.md` (repo root) — cross-session rules, corrections log, active context. Curate it; don't let it grow stale.
- Agent-side architecture notes: `~/.claude/projects/.../memory/MEMORY.md`.

## Conventions

Cross-cutting invariants (naming, env, package tooling, branch flow, verification, UX, reuse, feature gating) live in `rules/conventions.md`. Read it before any non-trivial change.
