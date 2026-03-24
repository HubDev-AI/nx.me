# NXME.ai

AI-powered glow-up app. Python (FastAPI) backend + React Native (Expo) mobile.

## Stack

- **Backend**: Python 3.12, FastAPI, Supabase (Postgres), ARQ worker, ruff
- **Mobile**: TypeScript, React Native, Expo Router, Expo SDK
- **Infra**: Docker Compose (local Supabase), Supabase Cloud (prod)

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
cd mobile && npx expo start   # Dev server
cd mobile && npx expo lint    # ESLint
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

## Memory

Architecture decisions and project context: `~/.claude/projects/.../memory/MEMORY.md`

## Conventions

See `.claude/rules/` for language-specific standards (auto-loaded by glob):
- `coding-conventions.md` — NXME-specific config sources, Context7, no magic numbers
- `react.md` — Component state checklist, design tokens, a11y
- `nodejs.md` — TypeScript/ESLint standards, Result pattern
- `database-patterns.md` — ESR indexing, RLS, migration patterns
- `code-standards.md` — Commit protocol, verification loop, deviation rules
