# C — Close anonymous sessions — requirements

**Date:** 2026-04-19
**Scope:** backend public-route allowlist narrowing + mobile anonymous-mode removal + card-web unchanged.
**Size:** Standard (small diff once A + B have landed — this is allowlist pruning + `SessionMode='anon'` deletion).
**Sequence:** ships immediately after B. A → B → C is a single connected workstream, not deferred.
**Related:**
- Split from umbrella `docs/brainstorms/2026-04-19-remove-guest-and-auth-flag-requirements.md` (SUPERSEDED).
- Depends on A (`2026-04-19-A-delete-auth-flag-and-dev-bypass-requirements.md`) and B (`2026-04-19-B-delete-guest-merge-plumbing-requirements.md`).

## Problem

After A + B land, the word `guest` is gone from the codebase and the auth-disable flag is deleted, but several product routes remain unauthenticated by historical accident: `/v1/feed`, `/v1/users/{username}/profile`, `/v1/users/check-username`, `/v1/posts/{post_id}/comments`, `/v1/posts/{post_id}/reactions`, `/v1/posts/{post_id}/react`. These routes were allowlisted because guest sessions needed to browse feed + react + comment without a real JWT. With guest removed, none of these routes have a current consumer for the unauthenticated path:

- **card-web** (`card-web/src/lib/api.ts`, `card-web/src/app/sitemap.ts`) uses only `/v1/public/cards/*` — the cards list and individual card endpoints. It does not call feed, profile, comments, or reactions.
- **Mobile** always has a JWT post-A+B (anonymous sessions die with B's SessionMode narrowing, which drops `'guest'` — `'anon'` is the last remaining non-user state and exists only as a "logged out → redirect to login" transient).
- **No other first-party consumer** exists.

Keeping unauthenticated reads on feed/profile/comments/reactions preserves an attack surface (scrapers, abuse, crawl farms) and keeps the mental model "some routes are public for historical reasons" alive in the codebase. Closing them is mechanical and carries no product cost: every legitimate caller already has or will have a JWT.

`__PREFIX__/v1/public/cards` and `__PREFIX__/api/public/cards` stay — they are the card-web consumer and serve public shareable links intentionally.

## Goals

1. Narrow `tests/test_auth_invariants.py::PUBLIC_ROUTE_ALLOWLIST` to the minimal set: auth/login endpoints, health, features bootstrap, card-web public endpoints, Stripe webhook.
2. Add `Depends(get_current_user)` to feed, profile, username-check, comments, reactions endpoints.
3. Delete `SessionMode = 'anon'` from mobile — `SessionMode` collapses to just `'user'`. The logged-out state is expressed by `session.isReady && !session.isUser`, not a separate session mode.
4. Delete `AuthGuard`'s transient `'anon'` branch — AuthGuard now has exactly two states: "JWT present → app" and "no JWT → login screen."
5. Delete any remaining "public view" copy in the mobile UI that implied browsing-without-login (e.g., feed empty-state for unauth users).

## Non-goals

- Removing `__PREFIX__/v1/public/cards` / `__PREFIX__/api/public/cards` — card-web consumes them.
- Removing `/webhooks/stripe` — Stripe-Signature auth, not JWT.
- Removing `/v1/auth/*` — login endpoints authenticate you; they cannot require JWT.
- Blocking sitemap / SEO indexing of card-web — card-web remains publicly crawlable via its own routes and `/v1/public/cards`. Closing feed/profile JWT-gating does not affect SEO.
- Changing card-web.

## Current surface (verified 2026-04-19)

### Backend — edit
- `tests/test_auth_invariants.py::PUBLIC_ROUTE_ALLOWLIST` narrows to:
  - `/health`, `/readiness`
  - `/v1/features`
  - `/v1/auth/register`, `/v1/auth/login`, `/v1/auth/email-login`, `/v1/auth/tiktok-login`, `/v1/auth/providers`, `/v1/auth/refresh`
  - `__PREFIX__/v1/public/cards`, `__PREFIX__/api/public/cards`
  - `/webhooks/stripe`

  Removed entries: `/v1/users/{username}/profile`, `/v1/users/check-username`, `/v1/feed`, `/v1/posts/{post_id}/comments`, `/v1/posts/{post_id}/reactions`, `/v1/posts/{post_id}/react`.

- Route handlers that served unauthenticated reads pre-C — add `Depends(get_current_user)`:
  - `app/api/feed.py::get_feed` (or wherever `GET /v1/feed` lives after B's cleanup).
  - `app/api/users.py` — `GET /v1/users/{username}/profile` and `GET /v1/users/check-username`.
  - `app/api/social.py::get_comments` (`GET /v1/posts/{post_id}/comments`).
  - `app/api/social.py::react_to_post` + `/react` alias — already JWT-required after B; C removes them from allowlist.

### Mobile — edit
- `mobile/lib/session.ts` — `SessionMode = 'user'`. Remove `'anon'`. Remove any `isAnon` / `isGuest` remnants (B already removed `'guest'`).
- `mobile/lib/auth-context.tsx` / `AuthGuard` — two-state logic only. Anything that was `session.mode === 'anon'` becomes "no session → login."
- `mobile/lib/capabilities.ts` — drop any remaining non-user branches. Every capability evaluates to `session.isUser && …` or just `session.isUser`.
- `mobile/lib/me.ts`, `mobile/lib/features-state.ts` — remove anon-case reads.
- UI components with "browse without login" copy / empty states — audit via `rg "sign in to|log in to|without an account|without signing in" mobile/`; rewrite or delete the strings.

### Tests
- `tests/test_auth_invariants.py` — invariant test now asserts every non-allowlisted route in `app/api/` has `get_current_user` or `require_admin` in its dependency tree. Allowlist size should drop to ≤12 entries.
- Any test that previously exercised unauthenticated reads on feed/profile/comments/reactions — update to log in first (Supabase test JWT helper).
- `mobile/lib/capabilities.test.ts` — drop any matrix row that assumed a non-user session could view anything.

### Docs
- `CLAUDE.md` — no changes needed beyond A's edits.
- `.claude/napkin.md` — already edited in B; verify no stale anonymous-mode rule remains.
- `app/features/README.md` — remove any "anonymous can read" language.
- `card-web/.claude/napkin.md` — confirms card-web only needs `/v1/public/cards` (already documented).

## Solution shape

Single PR after B lands. Two edits run in lockstep:
1. Tighten backend allowlist + add `Depends(get_current_user)` to the five route categories.
2. Mobile removes `'anon'` SessionMode, collapses AuthGuard to two states, audits and rewrites "browse without login" copy.

No migration. No DB change. No new behavior for real users (every real user already has a JWT by the time they see the feed). The invariant test passing proves the allowlist is minimal.

## Acceptance criteria

- **AC1.** `PUBLIC_ROUTE_ALLOWLIST` contains only the 13 entries listed above (health + readiness + features + 6 auth routes + 2 card-web prefixes + stripe webhook).
- **AC2.** Feed, profile, comments, reactions endpoints return 401 without a JWT. Manual `curl` proof captured in the PR.
- **AC3.** `SessionMode` type in `mobile/lib/session.ts` is literally `type SessionMode = 'user'`. Any union-literal with `'anon'` or `'guest'` is gone.
- **AC4.** `AuthGuard` code path count: exactly two (logged in + not logged in). No third branch.
- **AC5.** `rg "anon|Anon" mobile/lib/ mobile/components/` returns zero matches (excluding legitimate "anonymous" in copy — grep pattern refined to identifier-boundary).
- **AC6.** Mobile UI sweep: no copy invites "browse without an account," "skip sign-in," or similar. All such strings removed or replaced.
- **AC7.** card-web continues to function: `card-web/src/lib/api.ts::getCardData` returns 200 for valid cards, 404 otherwise. No change to card-web code required.
- **AC8.** `make format && make lint && make test && cd mobile && npx expo lint && cd mobile && npm test -- --runInBand --watchman=false` passes clean. `cd card-web && npm test` still passes.

## Risks

- **R1. SEO / crawler regression on feed endpoint.** Post-C, Google cannot crawl `/v1/feed` content. Mitigation: feed was never a SEO property; content discovery is intended to happen via card-web (`/v1/public/cards/*`) which remains public. Confirm with any stakeholder who expected feed to be crawlable — if none, no action.
- **R2. Hidden consumer of a closed route.** Some script / dashboard / Zapier webhook may hit a closed route without JWT. Mitigation: after deploy, monitor the `/v1/feed`, `/v1/users/*/profile`, `/v1/posts/*/comments`, `/v1/posts/*/reactions` 401 counts for 24 hours. Any 401 from a non-mobile user agent = investigate.
- **R3. Feed bootstrap on cold launch requires JWT.** Mobile must have a JWT by the time it calls `/v1/feed`. Current flow: `AuthGuard` waits for `session.isReady` before rendering feed. After C: `AuthGuard` waits for `session.isUser` explicitly. Confirm no screen pre-fetches feed before login completes.
- **R4. card-web SEO regression.** Not expected — card-web uses `/v1/public/cards` which stays public. Tested by rerunning the card-web sitemap integration test.

## Sources & references

- card-web consumer confirmation: `card-web/src/lib/api.ts:43-49` (only `/api/public/cards/*`), `card-web/src/app/sitemap.ts` (only `/v1/public/cards`).
- Current allowlist (pre-C): `tests/test_auth_invariants.py:50-80`.
- SessionMode definition: `mobile/lib/session.ts` (after B narrows to `'user' | 'anon'`, C removes `'anon'`).
- Reactions route (JWT-required after B): `app/api/social.py::react_to_post`.
