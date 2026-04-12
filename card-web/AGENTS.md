# AGENTS.md — `card-web/` (Next.js)

Next.js **14.2.x** (pinned), React 18, TypeScript, Tailwind, vitest + Playwright.
Root CLAUDE.md covers project-wide rules — this file is for web-specific context only.

## Layout

- `src/` — app code
- `public/` — static assets
- `scripts/` — utility scripts
- `next.config.mjs` — Next.js config
- `tailwind.config.ts`, `postcss.config.mjs` — styling
- `playwright.config.ts` — e2e runner config

## Commands (from `card-web/`)

- `npm run dev` — Next dev server on **port 3006**
- `npm run build` / `npm start` — production build + serve
- `npm run type-check` — `tsc --noEmit`
- `npm run lint` — `next lint`
- `npm test` — vitest unit tests
- `npm run test:e2e` — Playwright e2e
- `npm run audit` — `npm audit --audit-level=high`

## Next.js 14.2.x gotchas

- **Config must be `next.config.mjs`** — `.ts` config files are only supported from Next 15+.
- Don't bump to Next 15 without migration planning (breaking changes in routing, caching, async APIs).

## Package version hygiene

Before adding or bumping any dependency, verify the actual latest via Context7 (`mcp__context7__resolve-library-id` → `query-docs`) or PyPI/npm. Do **not** trust subagent version claims — user was burned by a stripe `14.4.0` claim when `14.4.1` was current.

## Testing

- Unit: `vitest run` (default `npm test`)
- E2E: Playwright — the project has a working `playwright.config.ts`. `test-results/` is the runtime artifact dir; do not commit.
