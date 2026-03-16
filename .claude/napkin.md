# Napkin

## Corrections
| Date | Source | What Went Wrong | What To Do Instead |
|------|--------|----------------|-------------------|
| 2026-03-13 | self | Assumed the repo napkin existed; `.claude/napkin.md` was missing | Create the napkin immediately at session start when it does not exist |

## User Preferences
- Follow repo `AGENTS.md` skill instructions before doing substantive work.
- **After every UI story**: provide manual testing steps before moving to the next story. User tests manually, then signals to continue. If issues found → fix first, then continue. Never auto-advance past a UI story.
- **Always use Context7** (`mcp__context7__resolve-library-id` + `mcp__context7__query-docs`) to get the latest API/usage for any package before writing code — never guess at APIs.
- **No magic numbers or strings** in code — all constants go in named config variables, enums, or env-backed config files.
- **All env-sensitive values in env/config** — connection strings, API keys, feature flags, limits (e.g. `FREE_TRIAL_ANALYSES`), timeouts, URLs — never hardcoded.
- **No code duplication** — before writing a component, hook, utility, or service, check if one already exists. Reuse and extend, don't duplicate.
- **No duplicate components or hooks** — shared UI components and hooks live in a single shared location; feature code imports from there.

## Patterns That Work
- Read only the specific skill files that apply, then proceed with the smallest useful action.
- ChatGPT share pages can embed the full conversation in the first `window.__reactRouterContext.streamController.enqueue(...)` payload; `linear_conversation` is enough to reconstruct visible turns.

## Patterns That Don't Work
- Proceeding before checking for required session skills creates avoidable cleanup.

## Domain Notes
- This repo defines skills in `AGENTS.md`; `napkin` is mandatory every session.
- **High modularity required** — adapters for all external services (Rekognition, MediaPipe, fal.ai, Anthropic, Stripe, Supabase Storage), pipeline steps composable in `config/pipelines.py`, all LLM prompts in `prompts/*.txt` files loaded at runtime. Never inline prompts or call providers directly from services.
- Amendment A-3 defines the full adapter pattern — read `docs/amendments.md#a-3` before implementing any service story.
- Amendment A-4 defines the DB-driven tier system — no tier names in code, `user.tier_id: UUID` only, tiers seeded via migration, admin CRUD API at `/admin/tiers`.
- Amendment A-5 defines usage tracking (`usage_events` table), `EntitlementResult`, error codes (TIER_LIMIT_DAILY etc.), and `require_entitlement()` / `require_feature()` FastAPI dependencies. **Read A-5 before implementing any story that touches generation, nudges, or advisor chat.**
