# Napkin

## Corrections
| Date | Source | What Went Wrong | What To Do Instead |
|------|--------|----------------|-------------------|
| 2026-03-13 | self | Assumed the repo napkin existed; `.claude/napkin.md` was missing | Create the napkin immediately at session start when it does not exist |
| 2026-03-17 | user | Trusted story-creator agent's stripe version (14.4.0) without verifying via Context7/PyPI — actual latest was 14.4.1 | ALWAYS verify package versions yourself via Context7 + PyPI. Never trust subagent version claims. |
 | 2026-03-17 | self | Used `next.config.ts` — Next.js 14.2.x does not support TypeScript config files | Use `next.config.mjs` for Next.js 14.x; `.ts` config only supported from Next.js 15+ |
 | 2026-03-17 | self | Ran `pytest` directly and hit globally installed plugin import failures unrelated to this repo | Use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest ...` first in this workspace unless the repo explicitly depends on external pytest plugins |
| 2026-03-17 | self | Treated the first `X-Forwarded-For` value as trustworthy for auth rate limiting | Behind proxies/load balancers, do not trust raw client-supplied `X-Forwarded-For`; use a trusted proxy strategy or socket IP |
| 2026-03-17 | self | Nearly repeated stale review findings from an earlier pass without re-checking the current tree | Before writing review docs, reopen the live files and re-validate every high-severity finding against current code, scripts, and docs |
| 2026-03-17 | self | Assumed the migration runner lived under `app/scripts/` while reviewing migration docs | In this repo the runner is `app/migrations/run.py`; verify actual file paths before citing migration workflow details |
| 2026-03-17 | self | Treated spec validity as ID coverage only and missed acceptance-detail gaps | When validating backlog/spec docs, also compare each source finding's required branches/status codes/scope against the sprint summary, not just whether the ID appears |
| 2026-03-20 | self | JWT ES256 validation crashed because `cryptography` package was missing from venv (PyJWT needs it for EC keys). Standalone test worked because system Python had it. | When PyJWT uses non-HS256 algorithms, always verify `cryptography` is installed in the project venv, not just system Python. Also: never use `PyJWKClient` (urllib-based) inside async handlers -- use httpx + PyJWK instead. |
| 2026-03-24 | self | BottomTabBar icon clipping: overriding `insets` prop in custom tabBar wrapper was insufficient because BottomTabView.renderTabBar reads insets from SafeAreaInsetsContext BEFORE passing them to the tabBar callback | For floating pill tab bars, ALWAYS set `safeAreaInsets={{ top:0, right:0, bottom:0, left:0 }}` on the Tabs/Navigator component AND zero insets in the tabBar wrapper. The navigator-level prop is the primary fix; the wrapper-level override is a safety net. |

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
- When code-review-graph MCP tools are unavailable but `.code-review-graph/graph.db` exists, query it directly with `sqlite3` for node/risk/community context before falling back to broad file reads.

## Patterns That Don't Work
- Proceeding before checking for required session skills creates avoidable cleanup.

## DB Transaction Pattern
- **Always use transactions for multi-step DB writes** — if any step fails, nothing is committed
- Migration runner: each migration SQL + `_schema_migrations` INSERT in one transaction (`conn.autocommit = False` → `conn.commit()` or `conn.rollback()`)
- Service layer: wrap multi-step operations (create user + grant credits, reserve + commit credit, etc.) in explicit transactions
- Single-read queries or single-row INSERTs don't need explicit transaction wrappers (auto-commit is fine)

## Domain Notes
- This repo defines skills in `AGENTS.md`; `napkin` is mandatory every session.
- **CRITICAL: Feature specs are PRIMARY source for implementation:**
  - `docs/generation-spec.md` — for ANY story touching generation (4-2, 4-3, etc.). Contains model selection, parameters, prompts, scoring, retry, cost, module architecture. 17 sections. READ THIS FIRST for generation stories.
  - `docs/advisor-spec.md` — for ANY story touching advisor (7-1, 7-2, 7-3, 7-4). Contains SOUL.md integration, memory system, context assembly, nudges, cost, pluggable design. 17 sections. READ THIS FIRST for advisor stories.
  - These specs override architecture.md for implementation details. Architecture.md is the system overview; these specs are the engineering blueprints.
- **Advisor persona**: Ada (she/her) — personal style and self-improvement advisor
- **Generation spec**: `docs/generation-spec.md` — single source of truth for all AI generation behavior
- **Primary model**: Flux PuLID `fal-ai/flux-pulid` (id_weight=0.85). NO post-processing. ~$0.035/image.
- **Fallbacks**: Flux Dev img2img + IP-Adapter → InstantID (SDXL). Only on model failure.
- **NXME is NOT a beauty filter**: Never smooth skin, remove freckles, or retouch. Styling only.
- **Identity**: 3 layers — model conditioning (id_weight) → ArcFace post-check → prompt guidance
- **Keyword allowlist blocks skin terms**: "clear skin", "reduced blemishes" etc NOT in allowlist
- **High modularity required** — adapters for all external services (Rekognition, MediaPipe, fal.ai, Anthropic, Stripe, Supabase Storage), pipeline steps composable in `config/pipelines.py`, all LLM prompts in `prompts/*.txt` files loaded at runtime. Never inline prompts or call providers directly from services.
- Amendment A-3 defines the full adapter pattern — read `docs/amendments.md#a-3` before implementing any service story.
- Amendment A-4 defines the DB-driven tier system — no tier names in code, `user.tier_id: UUID` only, tiers seeded via migration, admin CRUD API at `/admin/tiers`.
- Amendment A-5 defines usage tracking (`usage_events` table), `EntitlementResult`, error codes (TIER_LIMIT_DAILY etc.), and `require_entitlement()` / `require_feature()` FastAPI dependencies. **Read A-5 before implementing any story that touches generation, nudges, or advisor chat.**

## Auth Provider Patterns

- **TikTok uses native SDK + server code exchange**: `react-native-tiktok` (Expo plugin) handles auth natively on iOS/Android → returns `authCode` (+`codeVerifier` on Android). Backend exchanges code via TikTok API → creates Supabase user with synthetic email + HMAC-derived password. No web browser flow, no HTTPS redirect URI hassle.
- **Auth provider flags**: `AUTH_PROVIDER_{GOOGLE,APPLE,EMAIL,TIKTOK}_ENABLED` in config. When disabled: API returns 403, mobile hides the button. Mobile fetches enabled providers from `GET /auth/providers`.
- **Login/signup is one screen**: `(auth)/login.tsx` is the unified auth screen. `(auth)/signup.tsx` is a redirect. Social auth handles both login and signup in a single flow (backend creates account on first login).
- **TikTok native SDK requires dev build**: Won't work in Expo Go or web. Use `npx expo run:ios` or `npx expo run:android` to test.

## Story Creator Patterns

- **A-4 vs AC-3 tension**: AC-3 requires FREE_TRIAL_ANALYSES, IDENTITY_SIMILARITY_THRESHOLD, MAX_CONCURRENT_GENERATIONS_PER_USER in config module. A-4 says these are DB-driven. Resolution: keep them in config as global defaults/ceilings; per-tier values in DB take precedence in EntitlementService, but config values serve as circuit-breaker / non-tier paths (e.g., stuck-job watchdog).
- **Circular FK pattern**: credit_reservations <-> glow_up_jobs. Create credit_reservations without FK first, create glow_up_jobs with FK to credit_reservations, then ALTER TABLE credit_reservations ADD CONSTRAINT FK.
- **app/config.py vs app/config/ directory**: Two separate things. `app/config.py` = runtime Settings singleton. `app/config/` directory = seed-only data (e.g., tiers.py with SEED_TIERS). Never import from `app/config/tiers.py` at runtime.
- **.env.example is blocked by LaiM hooks** — get env var names from local-dev.md instead (it has the full env var table).
- **pydantic-settings latest stable**: 2.13.1 as of 2026-03-16.
- **users.tier_id requires tiers table first**: In migrations, 0001_initial.sql creates users WITHOUT tier_id. 0002_tiers.sql creates tiers table, then ALTER TABLE users ADD COLUMN tier_id. 0004_seed_tiers.sql seeds tiers, then sets tier_id NOT NULL.
