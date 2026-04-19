# A — Delete `FEATURE_AUTH_REQUIRED` flag and `DEV_FEATURE_FOCUS` — requirements

**Date:** 2026-04-19
**Scope:** backend (`app/`) + mobile (`mobile/`) + tests + docs
**Size:** Standard (contained — touches flag readers, capability layer, one inline auth branch, dev escape hatches)
**Sequence:** ship independently; no dependency on payments branch or on the B/C follow-ups
**Related:**
- Split from umbrella `docs/brainstorms/2026-04-19-remove-guest-and-auth-flag-requirements.md` (SUPERSEDED).
- Supersedes the runtime-toggle lockdown from `docs/brainstorms/2026-04-16-prod-guest-mode-lockdown-requirements.md` (R1/R2 obsolete; R3 transforms).
- B follow-up `2026-04-19-B-delete-guest-merge-plumbing-requirements.md` depends on A landing first.

## Problem

`FEATURE_AUTH_REQUIRED` is a runtime toggle with exactly one production setting (`true`) and one dev setting (`false`). It exists only because guest mode existed as a dev-convenience fallback. Having auth be a runtime-gated feature creates:

- An invariant at `APP_ENV=production ⇒ FEATURE_AUTH_REQUIRED=true` that must be tested at boot (R2 from 2026-04-16 lockdown).
- A per-route audit (R3 from 2026-04-16 lockdown) that walks `route.dependant.dependencies` to assert no route reads `X-Guest-Token` outside `get_user_or_guest`.
- Capability branches in mobile: `features.auth_required` combined with `session.isGuest` yields different views.
- A dev-only mobile bypass `DEV_FEATURE_FOCUS` that depends on `X-Guest-Token` falling through `apiFetch` to bypass login on route redirect.

Auth is not a feature — it is an invariant. Deleting the flag collapses three audit surfaces into one positive assertion ("every authenticated route requires JWT or is on the public allowlist") and removes the runtime-toggle footgun. Deleting `DEV_FEATURE_FOCUS` removes the only non-production reader of the guest-token fallback code, which unblocks B (guest-merge removal) and C (anonymous-session removal) downstream.

## Goals

1. Delete `FEATURE_AUTH_REQUIRED` from backend config, middleware, handlers, tests, env examples.
2. Delete `auth_required` capability from `app/features/__init__.py` + `app/features/README.md`.
3. Delete `DEV_FEATURE_FOCUS` env var + mobile constant + `AuthGuard` redirect branch.
4. Collapse the R3 invariant test into a single positive assertion: every `app/api/*` route either requires JWT (`get_current_user` or `require_admin`) or appears on an explicit public-route allowlist enumerated in this doc.
5. Convert `app/api/social.py::react_to_post` inline `FEATURE_AUTH_REQUIRED` branch into a cleaner path that still accepts `X-Guest-Token` (B will remove guest later — A only strips the flag read).

## Non-goals

- Removing guest token issuance (`POST /v1/auth/guest`) — handled in B.
- Removing guest→user merge plumbing (`merge_guest_ledger`, `guest_install_uuid_hash`) — handled in B.
- Removing anonymous session support from feed / public preview routes — handled in C.
- Touching install-UUID / device-fingerprint code used by payments — out of scope.
- Deleting the `DEV_DISABLE_FEATURES` mechanism — only its `auth` short-name is removed; `social`, `share`, `onboarding`, `advisor` short-names remain active.
- Deleting `AUTH_ENDPOINTS.REFRESH` from `mobile/constants/config.ts` — it is actively used by `mobile/lib/api.ts:70` for token refresh; the 2026-04-14 audit finding was stale.

## Current surface (verified 2026-04-19)

### Backend — delete
- `app/config/__init__.py` — `FEATURE_AUTH_REQUIRED: bool = True` field.
- `app/.env.example` — `FEATURE_AUTH_REQUIRED` block.
- `app/features/__init__.py` — `auth_required` field in `AppFeatures` + registry entry.
- `app/features/README.md` — `auth_required` row and `DEV_DISABLE_FEATURES=auth` examples.

### Backend — edit (strip flag reads, keep guest path for B)
- `app/api/auth.py:166-173` — the `POST /v1/auth/guest` 403 branch becomes unconditional `200` issue (still issues guest tokens — B deletes the endpoint).
- `app/api/deps.py:185-221` — `get_user_or_guest` drops the `FEATURE_AUTH_REQUIRED` branch; guest token acceptance remains until B.
- `app/api/social.py:282-335` (`react_to_post`) + the `/react` alias — strip `elif x_guest_token and not settings.FEATURE_AUTH_REQUIRED:` condition to `elif x_guest_token:`. Endpoint continues to accept guest tokens until B.
- `app/api/users.py:11, 280, 612, 762` — docstrings referencing `FEATURE_AUTH_REQUIRED`; strip the conditional language.
- Any other `settings.FEATURE_AUTH_REQUIRED` reader discovered via `rg "FEATURE_AUTH_REQUIRED" app/`.

### Backend — invariant test transform
- `tests/test_auth_invariants.py`:
  - Delete `TestProdAuthSettingsInvariant` (R2 — obsolete once flag is gone).
  - Delete `TestRoutesRejectGuestTokenWhenAuthRequired` (R1 — the probe tests flag-off behavior that no longer exists).
  - Transform `TestRoutesUseApprovedAuthDep` (R3) by narrowing `_APPROVED_AUTH_DEPS` to `{get_current_user, require_admin}` (remove `get_user_or_guest` temporarily kept for B).
  - Public-route allowlist explicitly enumerated (see below). No "enumerate during implementation" deferral.

### Public-route allowlist (authoritative — lives in `tests/test_auth_invariants.py::PUBLIC_ROUTE_ALLOWLIST`)

Exact paths (no wildcard unless noted):
- `/health`, `/readiness`
- `/v1/features`
- `/v1/auth/register`, `/v1/auth/login`, `/v1/auth/email-login`, `/v1/auth/tiktok-login`, `/v1/auth/providers`, `/v1/auth/refresh`, `/v1/auth/guest` (last entry kept until B deletes the route)
- `/v1/users/{username}/profile`, `/v1/users/check-username`
- `/v1/feed`, `/v1/posts/{post_id}/comments`, `/v1/posts/{post_id}/reactions`, `/v1/posts/{post_id}/react`
- `__PREFIX__/v1/public/cards`, `__PREFIX__/api/public/cards`
- `/webhooks/stripe`

Any new route added in a future PR either uses `Depends(get_current_user)` / `Depends(require_admin)` OR appears as a new allowlist entry with reviewer sign-off in the PR description.

### Mobile — edit
- `mobile/lib/features-state.ts` — delete `auth_required` field, delete `setAuthRequired`, delete `getAuthRequired`.
- `mobile/lib/api.ts:118-147` — delete `getAuthRequired()` reads; `resolveGuestToken` retains its current behavior (unconditional) until B.
- `mobile/lib/capabilities.ts` — delete every `features.auth_required` read. Collapse:
  - `canSignOut := session.isUser`.
  - `canSignIn := !session.isUser`.
  - `canViewOwnProfile := session.isUser || session.isGuest` (guest branch still valid until C).
  - `canEditProfile := session.isUser || session.isGuest` (guest branch still valid until C).
  - `canPublishGlowup := session.isUser` (drop the `!features.auth_required` gate).
  - `canViewBlockedUsers := features.social_enabled` (drop the `auth_required` factor).
  - Delete `caps.requiresAuth` field and every consumer — post-A, auth is always required.
- `mobile/lib/session.ts` — `SessionMode` stays `'user' | 'guest' | 'anon'` (B/C narrow it further).
- `mobile/constants/features.ts` — delete `auth_required` from `PROD_DEFAULT_FEATURES`, delete `'auth'` entry from `DEV_SHORT_NAME_TO_FLAG`. **Keep** the `DEV_DISABLE_FEATURES` mechanism — `social`, `share`, `onboarding`, `advisor` short-names remain.
- `mobile/constants/config.ts:469-472` — delete `DEV_FEATURE_FOCUS` export.
- `mobile/app.config.ts:122-125` — delete `devFeatureFocus` expo-extra entry. Keep `devDisableFeatures`.
- `mobile/.env.example:24-26` — delete `DEV_FEATURE_FOCUS`. Keep `DEV_DISABLE_FEATURES` example (drop only the `auth` short-name example value).
- `mobile/app/_layout.tsx:34,153-158` — delete `DEV_FEATURE_FOCUS` import + redirect block.
- `mobile/lib/auth-context.tsx` / `AuthGuard` — delete `features.auth_required` checks. AuthGuard becomes: "if session mode is `'anon'` then redirect to login, else allow." Guest mode still reaches the app until B.

### Mobile — tests
- `mobile/lib/capabilities.test.ts` — delete every assertion matrix varying `auth_required`. Keep guest-vs-user matrices (B removes guest rows).
- `mobile/components/result/ShareDialog.test.tsx:247-248` — same; strip the `auth_required=false` dimension, keep the guest-vs-user dimension.
- `mobile/app/(tabs)/__tests__/profile.test.tsx`, `mobile/components/profile/menu.test.ts` — same.

### Docs
- `CLAUDE.md` — delete "Dev Feature Focus" section (lines 63-78).
- `mobile/AGENTS.md` — delete `DEV_FEATURE_FOCUS` mention (line 4).
- `.claude/napkin.md` — no edit in A; napkin's guest rule remains accurate until C lands.
- `docs/plans/2026-04-17-003-fix-advisor-context-aware-plan.md:437,556` — edit smoke-test commands that use `DEV_FEATURE_FOCUS=upload` to "login normally, navigate to /(tabs)/upload."
- Historical `docs/brainstorms/2026-04-16-*`, `docs/plans/2026-04-15-*`, `docs/plans/2026-04-16-002-*`, `docs/superpowers/specs/2026-04-15-*` — no edit. AC grep pattern excludes these directories.

### Auto-memory (author runtime action — NOT enforceable by PR)
Post-merge, author runs in a fresh session:
```
memory_correct(query="feedback_tab_visibility_flag_gated", new_content="Tabs gate on capability only — auth is always required.", reason="FEATURE_AUTH_REQUIRED removed 2026-04-19 in PR #A")
```
No other memory edits in A.

## Solution shape

Single PR. No phases. Backend + mobile changes land together because the mobile `features-state` fallback and the backend response shape must move in lock-step for `/v1/features` to not return `auth_required` and for mobile to not expect it.

Test-first sequence:
1. Transform invariant test with narrowed `_APPROVED_AUTH_DEPS` + enumerated allowlist (test fails).
2. Edit backend to satisfy: remove flag reads, update `auth.py`, `deps.py`, `social.py`, `users.py`. Invariant test passes.
3. Delete `auth_required` from `features/__init__.py`; `/v1/features` response shape narrows.
4. Edit mobile `features-state`, `capabilities`, `AuthGuard`, configs. Update mobile tests.
5. Strip mobile `DEV_FEATURE_FOCUS`.
6. Run full verification loop.

## Acceptance criteria

- **AC1.** Backend: `rg "FEATURE_AUTH_REQUIRED|settings\.FEATURE_AUTH_REQUIRED" app/ tests/ -g '!docs/**'` returns zero matches.
- **AC2.** Backend: `rg "auth_required" app/features/ app/api/ tests/` returns zero matches. (Allowed: `docs/`, `.claude/napkin.md`, historical plans.)
- **AC3.** Mobile: `rg "DEV_FEATURE_FOCUS|devFeatureFocus" mobile/ -g '!docs/**'` returns zero matches.
- **AC4.** Mobile: `rg "features\.auth_required|getAuthRequired|setAuthRequired|caps\.requiresAuth" mobile/` returns zero matches.
- **AC5.** Transformed invariant test `TestRoutesUseApprovedAuthDep` passes with `_APPROVED_AUTH_DEPS = frozenset({get_current_user, require_admin})` and the enumerated `PUBLIC_ROUTE_ALLOWLIST`. Adding a new route without auth dep or allowlist entry fails the test.
- **AC6.** `mobile/constants/features.ts` `DEV_SHORT_NAME_TO_FLAG` still contains `social`, `share`, `onboarding`, `advisor` keys. The `auth` key is removed.
- **AC7.** `mobile/lib/api.ts` still imports and calls `AUTH_ENDPOINTS.REFRESH`; `refreshAccessToken` is unchanged.
- **AC8.** Manual iOS sim smoke: fresh install, login with Google, land on feed. Then sign out, confirm login screen reappears. `DEV_FEATURE_FOCUS` env var in `.env` has no effect (route override path gone).
- **AC9.** `make format && make lint && make test` passes clean. `cd mobile && npx expo lint && npm test -- --runInBand --watchman=false` passes clean.

## Risks

- **R1. `react_to_post` still accepts guest tokens after A.** Intentional — B removes it. A only strips the flag read to prevent runtime `AttributeError` when `FEATURE_AUTH_REQUIRED` is deleted from Settings.
- **R2. Stored `GUEST_TOKEN` in SecureStore sits unused.** A does not purge it (B does). Current users: `getStoredGuestToken()` continues to return it, `apiFetch` continues to send `X-Guest-Token`, backend continues to accept it. No behavior change for real users.
- **R3. `DEV_FEATURE_FOCUS` removed without replacement.** Developers who relied on it for "jump to upload screen without logging in" must log in first. Acceptable: working auth providers exist in local dev; `AUTH_PROVIDER_GOOGLE_ENABLED=true` already in `scripts/local-env.sh`.
- **R4. Capability test matrix shrinks.** Tests that combined `auth_required` × `isGuest` become purely `isGuest`. Coverage of guest mode is preserved; only the toggle dimension drops.

## Sources & references

- Backend flag: `app/config/__init__.py`, `app/.env.example`.
- Reactions inline branch (must be edited this PR): `app/api/social.py:282-335` + `/react` alias.
- Existing invariant test scaffolding: `tests/test_auth_invariants.py:50-80`.
- Mobile bypass: `mobile/constants/config.ts:469-472`, `mobile/app.config.ts:122-125`, `mobile/app/_layout.tsx:34,153-158`.
- Historical: `docs/brainstorms/2026-04-16-prod-guest-mode-lockdown-requirements.md`, `docs/superpowers/specs/2026-04-15-feature-flags-redesign-design.md`.
