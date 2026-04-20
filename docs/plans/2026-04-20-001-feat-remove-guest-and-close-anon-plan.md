# Plan — Remove guest mode, close anonymous surface, delete auth-disable flag

**Date:** 2026-04-20
**Branch:** `feat/remove-guest-and-close-anon` (off `origin/dev` @ `0017514`)
**Implements:** A + B + C from `docs/brainstorms/2026-04-19-{A,B,C}-*.md` in a single PR (user directive: one ce:review pass at end, cost-reduced).
**Sequence of commits:** A → B → C → zero-defer sweep → ce:review fixes → final verify → PR + auto-merge.
**Prerequisite verified:** `feat/payments-credits-only-engine` merged to `dev` via PR #170 on 2026-04-19. Payments migrations 0048 + 0050 present on `dev`.

## Unit 1 — A-backend: delete FEATURE_AUTH_REQUIRED flag and `auth_required` capability

**Touch:**
- `app/config/__init__.py` — drop `FEATURE_AUTH_REQUIRED` field.
- `app/.env.example` — drop `FEATURE_AUTH_REQUIRED` block.
- `app/features/__init__.py` — drop `auth_required` field in `AppFeatures` + registry entry.
- `app/features/README.md` — drop `auth_required` row + `DEV_DISABLE_FEATURES=auth` examples.
- `app/api/auth.py:166-173` — make `POST /v1/auth/guest` unconditional (B will delete).
- `app/api/deps.py:185-221` — drop `FEATURE_AUTH_REQUIRED` branch; accept `X-Guest-Token` unconditionally until B.
- `app/api/social.py:282-335` + `/react` alias — replace `elif x_guest_token and not settings.FEATURE_AUTH_REQUIRED:` with `elif x_guest_token:`.
- `app/api/users.py` — strip conditional `FEATURE_AUTH_REQUIRED` language in docstrings.
- Any other `settings.FEATURE_AUTH_REQUIRED` reader — `rg "FEATURE_AUTH_REQUIRED" app/` first; fix every hit.

**Verify:** `make format && make lint && make test`. Commit.

## Unit 2 — A-tests: invariant-test transform

**Touch:** `tests/test_auth_invariants.py`.
- Delete `TestProdAuthSettingsInvariant` (R2 obsolete).
- Delete `TestRoutesRejectGuestTokenWhenAuthRequired` (R1 obsolete).
- Transform `TestRoutesUseApprovedAuthDep`: narrow `_APPROVED_AUTH_DEPS` to `{get_current_user, require_admin}` (drop `get_user_or_guest`); public-route allowlist stays at current 16 entries including `/v1/auth/guest` + reactions (B + C narrow further).

**Verify:** `make test`. Commit.

## Unit 3 — A-mobile: strip FEATURE_AUTH_REQUIRED + DEV_FEATURE_FOCUS

**Touch:**
- `mobile/lib/features-state.ts` — drop `auth_required` field, `setAuthRequired`, `getAuthRequired`.
- `mobile/lib/api.ts:118-147` — drop `getAuthRequired()` reads; `resolveGuestToken` unconditional.
- `mobile/lib/capabilities.ts` — drop all `features.auth_required` reads; delete `caps.requiresAuth`; collapse per A's doc.
- `mobile/constants/features.ts` — drop `auth_required` from `PROD_DEFAULT_FEATURES`; drop `'auth'` from `DEV_SHORT_NAME_TO_FLAG`. Keep mechanism + other short-names.
- `mobile/constants/config.ts:469-472` — drop `DEV_FEATURE_FOCUS`.
- `mobile/app.config.ts:122-125` — drop `devFeatureFocus` entry.
- `mobile/.env.example:24-26` — drop `DEV_FEATURE_FOCUS`. Drop `auth` short-name example in `DEV_DISABLE_FEATURES`.
- `mobile/app/_layout.tsx:34,153-158` — drop `DEV_FEATURE_FOCUS` import + redirect block.
- `mobile/lib/auth-context.tsx` / `AuthGuard` — drop `features.auth_required` checks.
- `mobile/lib/capabilities.test.ts`, `mobile/components/result/ShareDialog.test.tsx:247-248`, `mobile/app/(tabs)/__tests__/profile.test.tsx`, `mobile/components/profile/menu.test.ts` — strip `auth_required` matrix dimension; keep guest-vs-user dimension.

**Verify:** `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false`. Commit.

## Unit 4 — A-docs: remove DEV_FEATURE_FOCUS documentation

**Touch:**
- `CLAUDE.md` — delete "Dev Feature Focus" section (lines 63-78).
- `mobile/AGENTS.md` — remove `DEV_FEATURE_FOCUS` mention (line 4).
- `docs/plans/2026-04-17-003-fix-advisor-context-aware-plan.md:437,556` — edit smoke-test steps.
- Historical `docs/brainstorms/2026-04-16-*`, `docs/plans/2026-04-15-*`, `docs/plans/2026-04-16-002-*`, `docs/superpowers/specs/2026-04-15-*` — NO edit.

**Verify:** none needed. Commit.

## Unit 5 — B-migration 1: rename guest_install_uuid_hash → install_uuid_hash

**Touch:** new `app/migrations/00NN_rename_guest_install_uuid_hash.sql` (next free migration number via `ls app/migrations/ | tail -3`).
- `ALTER TABLE users RENAME COLUMN guest_install_uuid_hash TO install_uuid_hash;`
- Rename any index on the column.
- `INSERT INTO _schema_migrations` in the same transaction.

Update readers: `app/api/auth.py` (merge helper that uses column), `app/repositories/*` references. Single atomic edit set so Unit 5 leaves code + schema in sync.

**Verify:** `make migrate` locally, then `make format && make lint && make test`. Commit.

## Unit 6 — B-migration 2: drop guest artifacts

**Touch:** new `app/migrations/00NN+1_drop_guest_artifacts.sql`:
- `DROP FUNCTION IF EXISTS merge_guest_ledger(UUID, UUID, BYTEA);`
- Rewrite `credit_ledger_type_check`: drop `guest_merge_non_pack`, `guest_merge_truncated`. Enumerate surviving types explicitly.
- `ALTER TABLE users DROP COLUMN is_guest;`
- `ALTER TABLE reactions DROP COLUMN guest_session_token;` + associated CHECK if present.
- Drop `guest_merge_*` tables if they exist (verify first with `\d`).
- `INSERT INTO _schema_migrations` same-txn.

**Verify:** `make migrate`. Commit. Paired with Unit 7.

## Unit 7 — B-backend: delete guest endpoint, RPC callers, dep

**Delete:**
- `app/db/guest.py`
- `app/repositories/guest_merge_repo.py`
- `app/api/auth.py::POST /v1/auth/guest` handler + helpers.
- `app/api/auth.py::_merge_guest_ledger` + call sites in `register`, `social_login`, `tiktok_login`.
- `app/api/deps.py::get_user_or_guest` (and header parsers).
- `app/api/social.py::react_to_post` guest-token branch (keeps JWT path).
- `app/api/middleware/logging.py` — `x_guest_token` log redaction.
- `tests/test_guest_merge_install_uuid_binding.py`, `tests/test_guest_merge_cap.py`, `tests/test_advisor_memory_guest_access.py`, `tests/test_guest_lockdown.py` (if present).
- `scripts/cleanup-guest-users.py`.

**Edit:**
- Every `get_user_or_guest` caller → `Depends(get_current_user)`. Enumerate via `rg "get_user_or_guest" app/api/` and paste full list into the PR body.
- `app/repositories/feed_repo.py` — drop guest branches.
- `app/services/rate_limiter.py` — drop guest key branches.
- `app/workers/weekly_free_grant.py` — drop `.eq('is_guest', False)` filter.
- `tests/test_auth_invariants.py::PUBLIC_ROUTE_ALLOWLIST` — remove `/v1/auth/guest`, `/v1/posts/{post_id}/reactions`, `/v1/posts/{post_id}/react`.

**Verify:** `make format && make lint && make test`. Commit.

## Unit 8 — B-mobile: delete guest-session, X-Guest-Token, GUEST_TOKEN key

**Delete:**
- `mobile/lib/guest-session.ts`.

**Edit:**
- `mobile/lib/api.ts:108-147,254-260` — drop `resolveGuestToken`, `X-Guest-Token` header, 401-rotate-guest retry.
- `mobile/lib/session.ts` — narrow `SessionMode` to `'user' | 'anon'`; drop `isGuest`.
- `mobile/lib/capabilities.ts` — drop all `session.isGuest` branches per B doc.
- `mobile/lib/auth-context.tsx` / `AuthGuard` — "JWT present → app, else → login"; add one-shot SecureStore purge of `GUEST_TOKEN` on first post-upgrade launch.
- `mobile/lib/me.ts`, `mobile/lib/features-state.ts` — drop guest readers.
- `mobile/constants/config.ts` — drop `AUTH_ENDPOINTS.GUEST`. Keep `AUTH_ENDPOINTS.REFRESH`.
- Components listed in B doc § Mobile — edit.

**Verify:** `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false`. Commit.

## Unit 9 — B-doc amendment: rescope payments R16

**Touch:**
- `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md` R16 — append rescoped note (cite this PR).
- `docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md` Unit 10 — same note.
- `CLAUDE.md` — remaining guest references.
- `app/features/README.md` — guest references, install-UUID note.
- `.claude/napkin.md` — replace rule 8 in User Directives ("Guest mode is first-class…") with "Guest mode removed 2026-04-20. Auth is invariant; every route JWT-required except 13 allowlisted public routes. See `tests/test_auth_invariants.py::PUBLIC_ROUTE_ALLOWLIST`." Re-curate to enforce 10-item cap per category.

**Verify:** none. Commit.

## Unit 10 — C-backend: narrow allowlist, add JWT deps

**Touch:**
- `tests/test_auth_invariants.py::PUBLIC_ROUTE_ALLOWLIST` — narrow to 13 entries per C doc.
- `app/api/feed.py::get_feed` (or current feed handler) — add `Depends(get_current_user)`.
- `app/api/users.py` — `GET /v1/users/{username}/profile` and `GET /v1/users/check-username` — add `Depends(get_current_user)`.
- `app/api/social.py::get_comments` — add `Depends(get_current_user)`.
- `app/api/social.py::react_to_post` + `/react` — already JWT-only after Unit 7; allowlist update only.

**Verify:** `make format && make lint && make test`. Commit.

## Unit 11 — C-mobile: collapse SessionMode to 'user'

**Touch:**
- `mobile/lib/session.ts` — `SessionMode = 'user'`. Drop `'anon'`.
- `mobile/lib/auth-context.tsx` / `AuthGuard` — two-state: logged-in OR login-screen.
- `mobile/lib/capabilities.ts` — every capability is `session.isUser` (or compound of it with features).
- `mobile/lib/me.ts`, `mobile/lib/features-state.ts` — drop anon-case reads.
- Sweep mobile UI copy: `rg "sign in to|log in to|without an account|without signing in" mobile/` — rewrite / delete.

**Verify:** `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false`. Commit.

## Unit 12 — zero-defer audit

**Command:**
```
rg '\b(TODO|FIXME|XXX|HACK|deprecated|legacy|temporarily|for now|later|follow-?up)\b' \
  app/ mobile/ tests/ -g '!docs/**' -g '!*.lock'
```
Every hit fixed in this PR. No exceptions. Commit each fix cluster separately.

## Unit 13 — ce:review + fixes

Invoke `compound-engineering:ce-review` on the full diff of the feature branch. Read each finding; implement fix; commit per-finding cluster. Re-verify after each cluster.

## Unit 14 — auto-memory + napkin sync (runtime actions via memoria MCP)

```
memory_purge(topic="feedback_guest_first_class", reason="guest removal complete 2026-04-20 in PR #remove-guest-and-close-anon")
memory_correct(query="project_payments_credits_only", new_content="Credits-only engine ships WITHOUT guest-merge; every new signup gets a flat signup grant (no credit carry from anonymous session).", reason="R16 rescoped 2026-04-20")
memory_store(content="Guest mode + FEATURE_AUTH_REQUIRED + DEV_FEATURE_FOCUS removed 2026-04-20. Every route JWT-required except /health, /readiness, /v1/features, /v1/auth/*, __PREFIX__/v1/public/cards, __PREFIX__/api/public/cards, /webhooks/stripe. SessionMode collapsed to 'user'. install_uuid_hash column renamed from guest_install_uuid_hash; payments device-fingerprint primitive preserved.", memory_type="semantic")
```

Napkin rule 8 (User Directives) already rewritten in Unit 9.

## Unit 15 — final verification + PR + merge

1. `make format && make lint && make test`
2. `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false`
3. Manual iOS sim smoke (per C AC8) — fresh install + login + feed + profile + glow-up; then seeded GUEST_TOKEN → purge verified.
4. `gh pr create --base dev --head feat/remove-guest-and-close-anon …` (title + body per scheduled prompt).
5. `gh pr merge --squash --auto` or `--admin` on branch-protection block.
6. Post-merge: `git checkout dev && git pull origin dev && git branch -D feat/remove-guest-and-close-anon`.

## Acceptance gates (summary — exact list per brainstorm ACs)

Backend greps (zero matches expected):
- `rg "FEATURE_AUTH_REQUIRED|settings\.FEATURE_AUTH_REQUIRED" app/ tests/ -g '!docs/**'`
- `rg '\b(is_guest|x_guest_token|X-Guest-Token|get_user_or_guest|GUEST_TOKEN_KEY|guest_session_token|guest_session|guest-session)\b' app/ mobile/ tests/ -g '!docs/**'`
- `rg '\bmerge_guest_ledger\b' app/ tests/ -g '!app/migrations/**'`
- `rg '\bguest_merge_(non_pack|truncated)\b' app/ tests/ -g '!app/migrations/**'`

Mobile greps (zero matches expected):
- `rg "DEV_FEATURE_FOCUS|devFeatureFocus" mobile/ -g '!docs/**'`
- `rg "features\.auth_required|getAuthRequired|setAuthRequired|caps\.requiresAuth" mobile/`

Type invariants:
- `SessionMode` in `mobile/lib/session.ts` is literally `type SessionMode = 'user'`.
- `_APPROVED_AUTH_DEPS = frozenset({get_current_user, require_admin})` in `tests/test_auth_invariants.py`.
- `PUBLIC_ROUTE_ALLOWLIST` has exactly 13 entries.

Runtime invariants:
- Every `app/api/*` route returns 401 without JWT except the 13 allowlisted.
- Manual iOS sim: seeded `GUEST_TOKEN` → AuthGuard purges it on first launch, no 401 loop.
- `tests/test_signup_grant_fingerprint.py` still passes after column rename.

## Risks + abort points

- **Migration rollback unavailable.** Destructive drop of `is_guest` + CHECK enum narrowing + RPC drop. Pre-launch — acceptable.
- **Payments code interaction.** Column rename breaks `merge_guest_ledger` signature; RPC is deleted immediately after so no window.
- **Capability test matrix simplification.** B and C shrink the matrix; coverage preservation audited by rerunning the full jest suite.
- **Mobile UI visual verification.** Napkin rule 6 ("screenshot the sim") applies to AuthGuard + capability layer changes. This plan requires human-in-loop for final sign-off.

If any unit's verification fails for reasons outside the current diff's scope, abort per scheduled-prompt protocol: write `/tmp/sleep-run-abort.md` + leave branch untouched + stop.
