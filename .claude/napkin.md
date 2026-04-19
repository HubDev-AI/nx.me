# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Execution & Validation (Highest Priority)
1. **[2026-03-17] Never publish review findings without re-reading the live tree**
   Do instead: before writing a review doc, reopen current files and re-validate every high-severity finding against HEAD.
2. **[2026-03-17] Don't trust subagent package-version claims**
   Do instead: verify every package version via Context7 + PyPI before writing or committing code.
3. **[2026-03-17] Spec validation ≠ ID coverage**
   Do instead: for every source finding, check required branches/status codes/scope against the sprint summary, not just whether the ID appears.
4. **[2026-04-18] Negative-delta REPLACE paths need explicit coverage**
   Do instead: credits-ledger tests must cover negative deltas and backfill-script smoke, not only positive grants.
5. **[2026-04-19] Delete-account must sweep every new surface**
   Do instead: for every new user-owned table / device key / Redis key / blob prefix, wire it into `delete_account` in the same PR; never ship silent remnants.
6. **[2026-04-19] Verification before claiming done**
   Do instead: run `make format && make lint && make test` (+ `cd mobile && npx expo lint` for mobile); report pass/fail. For UI, screenshot the sim.

## Shell & Command Reliability
1. **[2026-03-17] Global pytest plugins break raw `pytest`**
   Do instead: run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest ...` unless repo explicitly depends on external plugins.
2. **[2026-04-19] This repo's pytest suite depends on `pytest-cov` from `pytest.ini`**
   Do instead: for nxme.ai, do NOT set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` on the full suite; run tests with the repo's normal plugin loading, and force `APP_ENV=test` if local `.env` is development-flavored.
3. **[2026-04-19] Mobile Jest hits Watchman permission errors in sandbox**
   Do instead: run `cd mobile && npm test -- --runInBand --watchman=false` in Codex sandbox sessions.
2. **[2026-03-17] code-review-graph MCP sometimes unavailable but DB is**
   Do instead: when MCP tools fail, query `.code-review-graph/graph.db` directly via `sqlite3` for nodes/risk/community.
3. **[2026-03-20] `cryptography` absent in project venv breaks PyJWT ES256 silently**
   Do instead: verify `cryptography` is in the project venv (not system Python) for any non-HS256 JWT algo. Never use `PyJWKClient` inside async handlers — use httpx + PyJWK.
4. **[2026-04-19] Never push directly to dev/main**
   Do instead: feature branch → PR → merge; after merge, pull origin/dev and clean up worktree before declaring done.
5. **[2026-04-19] Always `uv` for Python packages**
   Do instead: `uv add <pkg>`; never `pip`/`pip3`.

## Domain Behavior Guardrails
1. **[2026-04-19] Payments is credits-only with milli-credit ledger**
   Do instead: no tiers, no trial counter, no `usage_events`, no legacy credit RPCs — use the milli-credit ledger. Device-fingerprint exception is the only hard-reset override. See `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md`.
2. **[2026-04-19] Mobile ⇄ backend API shapes must stay aligned**
   Do instead: when changing a backend response, update the matching mobile port + test in the same PR. Recent P0×2 on this branch came from shape drift.
3. **[2026-04-18] Pre-launch — destructive DB changes allowed**
   Do instead: delete tables in place, no migrations/backfills/deprecation shims; flip to post-launch safety rules only when launch gate trips.
4. **[2026-04-16] Feature gating only via the capabilities module**
   Do instead: mobile uses `useCapabilities()`, backend uses `Depends(require_app_feature("..."))`; never scatter `if features.X` checks.
5. **[2026-03-17] Do not trust raw `X-Forwarded-For` for auth rate-limit**
   Do instead: behind proxies/LBs, use a trusted-proxy strategy or socket IP; the first XFF hop is client-controlled.
6. **[2026-03-24] Floating pill tab bar needs navigator-level zero insets**
   Do instead: set `safeAreaInsets={{top:0,right:0,bottom:0,left:0}}` on `Tabs`/Navigator AND zero insets in the tabBar wrapper. Navigator prop is the primary fix; wrapper override is the safety net.
7. **[2026-03-16] Multi-step DB writes require explicit transactions**
   Do instead: migrations = SQL + `_schema_migrations` INSERT in one txn; services = wrap multi-row ops (`conn.autocommit=False` → `commit()`/`rollback()`). Single-row ops can stay auto-commit.
8. **[2026-03-17] Migration runner lives at `app/migrations/run.py`**
   Do instead: cite that path (not `app/scripts/`) whenever documenting the migration workflow.
9. **[2026-03-17] Auth providers gated by `AUTH_PROVIDER_*_ENABLED`**
   Do instead: mobile fetches `GET /auth/providers`; disabled provider → 403 + hidden button. TikTok uses native SDK + server code exchange; requires a dev build.
10. **[2026-03-17] card-web is Next.js 14 — TS config unsupported**
    Do instead: use `next.config.mjs` in card-web; `.ts` config is only Next.js 15+.

## User Directives
1. **[2026-04-19] No magic strings/numbers — ever**
   Do instead: every literal goes into a named constant, config module, or env var; reject inline values in review.
2. **[2026-04-19] No env fallbacks**
   Do instead: fail fast if a required env var is missing; do not silently substitute defaults.
3. **[2026-04-19] Reuse before writing**
   Do instead: before creating a component/hook/utility, grep for an existing one and extend it; shared UI lives in one shared location.
4. **[2026-04-19] Cursor-based infinite scroll only**
   Do instead: `next_cursor` API + infinite scroll UI; no load-more buttons, no offset/page.
5. **[2026-04-19] Every UI story pauses for manual test**
   Do instead: after implementing a UI story, give exact runnable manual-test steps and wait for user signal before advancing. Issues found → fix first.
6. **[2026-04-19] Context7 before using any library**
   Do instead: `mcp__context7__resolve-library-id` + `mcp__context7__query-docs` for current API; never guess or rely on training cutoff.
7. **[2026-04-19] Female-first copy and targeting**
   Do instead: write all user-facing copy, nudges, and Ada prompts for a majority-female user base; no male/beard-coded examples.
8. **[2026-04-19] Guest mode is first-class except for account mutations**
   Do instead: test guest paths (via `X-Guest-Token`) before declaring any non-account surface done.
9. **[2026-04-19] Disabled UI buttons are a bug**
   Do instead: cancel/retry/close/back must stay CLICKABLE whenever the action is available; never disable, never hide.
10. **[2026-04-19] UI work must route through a UI/UX skill or design agent**
    Do instead: do not hand-tune UI from instinct; invoke a design skill first, then implement.
