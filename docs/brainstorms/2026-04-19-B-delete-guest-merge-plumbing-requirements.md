# B — Delete guest→user merge plumbing — requirements

**Date:** 2026-04-19
**Scope:** backend (`app/`) + mobile (`mobile/`) + migrations + tests
**Size:** Deep (touches payments migrations 0048, 0050, ledger CHECK constraints, guest-token issuance, merge RPC, SecureStore purge)
**Sequence:** blocked on A (flag removed) and on `feat/payments-credits-only-engine` landing. Ship when both prerequisites are merged to `dev`.
**Related:**
- Split from umbrella `docs/brainstorms/2026-04-19-remove-guest-and-auth-flag-requirements.md` (SUPERSEDED).
- Depends on `2026-04-19-A-delete-auth-flag-and-dev-bypass-requirements.md`.
- Payments contract affected: `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md` R16 (guest-merge section) is rescoped by this plan.

## Problem

The P0 incidents cited in the umbrella brainstorm — guest-merge install-UUID binding bug, feed-cache guest branches, credit-ledger cross-user writes — all trace to the guest→user MERGE pathway, not to the existence of anonymous sessions. Merge is the failure surface: two identities share a device, one evolves into a real account, and state has to move between them without leaking ledgers across installs.

The credits-only payments branch (`feat/payments-credits-only-engine`) just shipped the merge machinery as a first-class primitive:
- `users.guest_install_uuid_hash BYTEA NULL` column (migration 0048).
- `merge_guest_ledger(p_guest_user_id UUID, p_new_user_id UUID, p_install_uuid_hash BYTEA)` RPC (migration 0050).
- Two ledger enum values inside `credit_ledger_type_check`: `guest_merge_non_pack`, `guest_merge_truncated`.
- Call sites in `app/api/auth.py::_merge_guest_ledger` (register, social_login, tiktok_login).
- Mobile guest-session provisioning + merge notice flow.
- Tests: `tests/test_guest_merge_install_uuid_binding.py`, `tests/test_guest_merge_cap.py`, `tests/test_advisor_memory_guest_access.py`.

Deleting this mechanism without a replacement has a product consequence: new signups no longer inherit credits earned as guests. That credit-carry is the entire commercial argument of R16. B takes the position: **the simpler path is to let every new signup start with a clean signup grant**, and delete both sides (merge plumbing + the credits that accumulate before signup) rather than keep the merge as an ongoing footgun. Read-only anonymous sessions (feed/preview/demo glow-up) can still exist for C's eventual decision; they never accumulate credits.

## Goals

1. Delete `merge_guest_ledger` RPC and remove both `guest_merge_non_pack` / `guest_merge_truncated` types from `credit_ledger_type_check`.
2. Rename `users.guest_install_uuid_hash` → `users.install_uuid_hash` (device-fingerprint primitive survives — it is used by signup-grant abuse prevention independent of guest concept).
3. Delete `app/db/guest.py`, `app/repositories/guest_merge_repo.py`, and `POST /v1/auth/guest` endpoint.
4. Delete `get_user_or_guest` dependency from `app/api/deps.py`. Every caller swaps to `get_current_user`.
5. Delete `mobile/lib/guest-session.ts`, `X-Guest-Token` fallback in `mobile/lib/api.ts`, `SECURE_STORE_KEYS.GUEST_TOKEN` key and its one-shot purge.
6. Delete `is_guest` column from `users` (no caller remains once guest-issuance is gone).
7. Rescope payments R16: new signups earn the flat signup grant; no merge transfer.
8. Update the R3 invariant-test allowlist to remove guest-related public routes: `/v1/auth/guest`, `/v1/posts/{post_id}/reactions`, `/v1/posts/{post_id}/react` (reactions must now require JWT).

## Non-goals

- Removing read-only anonymous sessions for feed / public preview / card-web — handled (or not) in C with funnel data.
- Touching install-UUID plumbing except for the column rename — the primitive stays.
- Reverting the `feat/payments-credits-only-engine` branch — B lands on top of it.
- Building a new "credits earned before signup" alternative. R16's funnel value is accepted as lost in B.
- Editing `~/.claude/` auto-memory from a PR — author runs `memory_purge` / `memory_correct` manually post-merge.

## Current surface (verified 2026-04-19)

### Backend — delete
- `app/db/guest.py`
- `app/repositories/guest_merge_repo.py`
- `app/api/auth.py::POST /v1/auth/guest` handler + helpers
- `app/api/auth.py::_merge_guest_ledger` + its call sites in `register`, `social_login`, `tiktok_login`
- `app/api/deps.py::get_user_or_guest` (and header-parsing helpers)
- `app/api/social.py::react_to_post` guest-token branch (path becomes pure JWT)
- `app/api/middleware/logging.py` — strip `x_guest_token` log redaction (keep install-UUID redaction)
- `tests/test_guest_merge_install_uuid_binding.py`, `tests/test_guest_merge_cap.py`, `tests/test_advisor_memory_guest_access.py`, `tests/test_guest_lockdown.py` (if present from PR #101)
- `scripts/cleanup-guest-users.py`

### Backend — edit
- All `get_user_or_guest` call sites across `app/api/users.py`, `app/api/social.py`, `app/api/entitlement.py`, `app/api/glowup.py`, `app/api/jobs.py`, `app/api/uploads.py`, `app/api/advisor.py`, `app/api/user_consent.py` → swap to `Depends(get_current_user)`. Enumerate each route + line via `rg "get_user_or_guest" app/api/` before the PR is opened; every site goes in the PR description as a checklist.
- `app/repositories/feed_repo.py` — strip guest branches (feed stays public; guest-token tracking drops).
- `app/services/rate_limiter.py` — strip `guest:*` key branches; per-IP rate limit remains for unauthenticated endpoints (login, reactions after JWT requirement lands).
- `app/workers/weekly_free_grant.py` — drop `.eq('is_guest', False)` filter from the page query (line 84). Update docstring. Semantically equivalent post-column-drop: all non-pro users get the grant.
- `tests/test_auth_invariants.py` — narrow `PUBLIC_ROUTE_ALLOWLIST`: remove `/v1/auth/guest`, `/v1/posts/{post_id}/reactions`, `/v1/posts/{post_id}/react`. (Reactions now require JWT.)

### Backend — new migrations (two separate files; explicit order)
1. `app/migrations/00NN_rename_guest_install_uuid_hash.sql` — `ALTER TABLE users RENAME COLUMN guest_install_uuid_hash TO install_uuid_hash;` Also rename indexes.
2. `app/migrations/00NN+1_drop_guest_artifacts.sql`:
   - `DROP FUNCTION IF EXISTS merge_guest_ledger(UUID, UUID, BYTEA);`
   - Rewrite `credit_ledger_type_check` to exclude `guest_merge_non_pack`, `guest_merge_truncated` (`ALTER TABLE credit_ledger DROP CONSTRAINT credit_ledger_type_check, ADD CONSTRAINT credit_ledger_type_check CHECK (type IN (...)) ;`).
   - `ALTER TABLE users DROP COLUMN is_guest;`
   - `ALTER TABLE reactions DROP COLUMN guest_session_token;` (and the associated CHECK constraint).
   - Drop any `guest_merge_*` tables if present (verify via `\d` prior to the migration; doc assumed tables but current payments branch uses an RPC; adjust accordingly).

### Mobile — delete
- `mobile/lib/guest-session.ts`
- Any guest-specific tests beyond the capability matrix already pruned in A.

### Mobile — edit
- `mobile/lib/api.ts:108-147, 254-260` — delete `resolveGuestToken`, `X-Guest-Token` header injection, the 401-then-rotate-guest-token retry path. `apiFetch` becomes: "attach JWT if present, else return 401 to caller."
- `mobile/lib/session.ts` — narrow `SessionMode` to `'user' | 'anon'`; delete `isGuest`; `buildSessionState` loses the guest branch.
- `mobile/lib/capabilities.ts` — drop every `session.isGuest` branch (A already dropped `features.auth_required` branches).
  - `canViewOwnProfile := session.isUser`
  - `canEditProfile := session.isUser`
  - `canPublishGlowup := session.isUser`
  - `canSignIn := !session.isUser`
  - `canSignOut := session.isUser`
- `mobile/lib/auth-context.tsx` / `AuthGuard` — unconditional "JWT present → app, else → login." SecureStore purge of `GUEST_TOKEN` on first post-upgrade launch (one-shot idempotent).
- `mobile/lib/me.ts`, `mobile/lib/features-state.ts` — strip remaining guest readers.
- `mobile/constants/config.ts` — delete `AUTH_ENDPOINTS.GUEST`. **Keep** `AUTH_ENDPOINTS.REFRESH`.
- `mobile/components/feed/FeedCreditBadge.tsx`, `mobile/components/feed/EmailVerifyBanner.tsx`, `mobile/components/feed/FeedCard.tsx`, `mobile/components/result/ShareDialog.tsx`, `mobile/components/result/ResultActions.tsx`, `mobile/components/comments/CommentInput.tsx`, `mobile/components/profile/menu.test.ts`, `mobile/app/(tabs)/profile.tsx`, `mobile/app/(tabs)/__tests__/profile.test.tsx`, `mobile/app/settings.tsx`, `mobile/app/result/__tests__/[jobId].test.tsx` — strip guest branches / copy.

### Payments plan — rescope R16
- `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md` R16 — append note: "B (`docs/brainstorms/2026-04-19-B-delete-guest-merge-plumbing-requirements.md`) replaces guest-merge with flat signup grant. Credits earned anonymously do NOT carry across signup."
- `docs/plans/2026-04-19-002-feat-payments-credits-only-engine-plan.md` Unit 10 — same note.

### Docs
- `CLAUDE.md` — remove remaining guest references (most already cleaned in A).
- `app/features/README.md` — remove `auth_required` row remnants; note install-UUID is independent of guest.
- Historical `docs/plans/` and `docs/brainstorms/` — no edits. Grep ACs exclude `docs/`.

### Auto-memory (author runtime action — NOT enforceable by PR)
Post-merge, author runs in a fresh session:
```
memory_purge(topic="feedback_guest_first_class", reason="guest→user merge removed 2026-04-19 in PR #B")
memory_correct(query="project_payments_credits_only", new_content="Credits-only engine ships without guest-merge. Every new signup gets flat signup grant. No credit carry from anonymous session.", reason="R16 rescoped 2026-04-19 in PR #B")
memory_store(content="Guest→user merge plumbing deleted 2026-04-19 in PR #B. `install_uuid_hash` column (renamed from `guest_install_uuid_hash`) survives as payments device-fingerprint primitive. Read-only anonymous sessions status decided by C.", memory_type="semantic")
```

## Solution shape

Two PRs within a single feature branch, merged in order:

**PR B.1 — Rename column + add new enum + transition reads.** Rename `guest_install_uuid_hash` → `install_uuid_hash`. Backend reads the new name. Ledger CHECK constraint expanded to accept both old and new type strings (so in-flight rows don't break). Ship B.1 to `dev`, verify no test regressions, wait for 24h before B.2.

**PR B.2 — Delete guest side + drop column + narrow CHECK.** Delete guest endpoint, merge RPC, `get_user_or_guest`, guest-session.ts, X-Guest-Token handling, is_guest column, reactions guest branch. Narrow `credit_ledger_type_check` to exclude `guest_merge_*`. Update tests.

**Atomicity within PR B.2:** backend + mobile ship in one PR. Dev environments with stored `GUEST_TOKEN` in SecureStore: AuthGuard post-upgrade one-shot purge clears it on next cold launch.

**Deploy order for B.2:** backend first (return 401 for X-Guest-Token), then mobile binary release. Pre-launch means no TestFlight users, so "mobile binary release" reduces to "merge + sim rebuild."

## Acceptance criteria

- **AC1.** `rg '\b(is_guest|x_guest_token|X-Guest-Token|get_user_or_guest|GUEST_TOKEN_KEY|guest_session_token|guest_session|guest-session)\b' app/ mobile/ tests/ -g '!docs/**'` returns zero matches. (Deliberately boundary-anchored to avoid false positives on `guest_install_uuid_hash` which is renamed.)
- **AC2.** `rg '\bmerge_guest_ledger\b' app/ tests/ -g '!app/migrations/**'` returns zero matches. Migration files keep the reference (history).
- **AC3.** `rg '\bguest_merge_(non_pack|truncated)\b' app/ tests/ -g '!app/migrations/**'` returns zero matches.
- **AC4.** `users.is_guest` column dropped; `users.guest_install_uuid_hash` renamed to `users.install_uuid_hash`. Schema diff attached to PR.
- **AC5.** `credit_ledger_type_check` CHECK constraint enumerates only the surviving enum strings (explicit list in migration + PR description).
- **AC6.** `tests/test_signup_grant_fingerprint.py` passes unchanged (install-UUID primitive survives via column rename).
- **AC7.** Invariant test `TestRoutesUseApprovedAuthDep` passes with `_APPROVED_AUTH_DEPS = frozenset({get_current_user, require_admin})` and the `PUBLIC_ROUTE_ALLOWLIST` narrowed to exclude `/v1/auth/guest`, reactions routes. Reactions endpoints respond 401 without JWT.
- **AC8.** Mobile `apiFetch` no longer attaches `X-Guest-Token`. `AuthGuard` one-shot purges `GUEST_TOKEN` from SecureStore on first post-upgrade launch; verified via Jest test using a SecureStore mock.
- **AC9.** `make format && make lint && make test && cd mobile && npx expo lint && cd mobile && npm test -- --runInBand --watchman=false` passes clean.
- **AC10.** iOS sim smoke including the upgrade path: seed SecureStore with a fake `GUEST_TOKEN` in a pre-upgrade build, then rebuild + relaunch → AuthGuard purges the token, user sees login screen, no 401 storm.

## Risks

- **R1. Cross-branch contract with payments.** R16 and Unit 10 change meaning. Mitigation: the two brainstorm/plan docs get an amendment note in the same PR that opens B (not a separate "doc-only" PR — keeps the amendment atomic with the semantic change).
- **R2. `install_uuid_hash` column rename breaks RPC signatures.** `merge_guest_ledger(...) p_install_uuid_hash BYTEA` reads the column via name. Mitigation: B.1 renames the column and updates the RPC parameter + body; B.2 deletes the RPC so any lingering signature mismatch is caught early.
- **R3. Allowlist change breaks existing reactions clients.** Reactions previously accepted guest tokens. Post-B, JWT required. Clients in dev / sim must be logged in. Pre-launch: acceptable.
- **R4. Guest-merge rollback not available.** Dropping the column + types is destructive. Mitigation: pre-launch destructive-OK per napkin. A rollback plan is not required.
- **R5. Auto-memory + napkin drift after B.** `.claude/napkin.md` still says "Guest mode is first-class." Napkin rule edit is part of this PR (single-line replacement: "Guest→user merge removed. Read-only anonymous sessions decided by C."). Memory-file edits are the author's post-merge responsibility — explicitly noted, not relied on for correctness.

## Sources & references

- Payments migrations: `app/migrations/0048_payments_schema_phase_a.sql:70-81,141-142`, `app/migrations/0050_credit_grants_and_allotment_rpcs.sql:337-463`.
- Merge call sites: `app/api/auth.py::_merge_guest_ledger` (register, social_login, tiktok_login).
- Mobile rotation path: `mobile/lib/api.ts:254-260`.
- Reactions inline branch (from A, now removed): `app/api/social.py:282-335`.
- R16 to rescope: `docs/brainstorms/2026-04-19-payments-credits-only-requirements.md`.
- Worker filter to strip: `app/workers/weekly_free_grant.py:83-86`.
