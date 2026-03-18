---
id: "CS-1-security-corrections"
status: complete
created: 2026-03-16
---

# Story: Security Corrections for Completed Stories

## User Story

As the platform, I need critical security and correctness issues from the architecture risk review and red team analysis fixed before more features ship, so that the existing foundation is production-safe.

## Acceptance Criteria

- AC-1: Given the credit ledger, When the reserve/release/commit RPC is unavailable, Then the operation fails with an error — no fallback two-write path exists. The RPC is the only write path.
- AC-2: Given concurrent release/commit calls for the same reservation, When both execute, Then only one succeeds — the RPC uses `UPDATE ... WHERE status = 'reserved' RETURNING *` and the application checks the return.
- AC-3: Given a registration with a disposable email (e.g., guerrillamail.xyz, tempail.com), When processed, Then HTTP 422 is returned — using a community-maintained blocklist package, not a hardcoded 60-domain list.
- AC-4: Given a POST /login request, When rate-limited IP sends >= 4 login attempts per hour, Then HTTP 429 is returned (same window as registration).
- AC-5: Given APP_ENV != "development", When any ADAPTER__*_ADAPTER config value is "mock" or "local", Then the application logs CRITICAL and refuses to start.
- AC-6: Given a DELETE /account request for an already-deleted account, When processed, Then HTTP 409 is returned — the update result row count is checked.
- AC-7: Given a DELETE /account request for a user with active credit reservations, When processed, Then all `reserved` reservations are released before soft-delete.

## Tasks

- [x] Task 1: Remove fallback paths from CreditLedger — reserve/release/commit must use RPC only, fail on RPC unavailable
  - Maps to: AC-1, AC-2
  - Files: `app/entitlement/ledger.py`

- [x] Task 2: Replace hardcoded disposable email blocklist with `disposable-email-domains` package
  - Maps to: AC-3
  - Files: `app/services/disposable_email.py`, `requirements.txt`

- [x] Task 3: Add per-IP rate limit to POST /login endpoint
  - Maps to: AC-4
  - Files: `app/api/auth.py`

- [x] Task 4: Add startup adapter guard for non-development environments
  - Maps to: AC-5
  - Files: `app/main.py`

- [x] Task 5: Fix account deletion — check row count, release reservations
  - Maps to: AC-6, AC-7
  - Files: `app/api/auth.py`

## Dev Notes

### Source

All findings from the production risk analysis and red team review performed 2026-03-16. Full details in `docs/corrections.md`.

### Priority

These are blocking fixes. L-1 (non-atomic fallback) is CRITICAL severity. All others are HIGH or MEDIUM. Ship before story 4-2 starts.

### Conventions

Same as prior stories — see story 4-1 for entitlement patterns, story 2-2 for auth patterns.
