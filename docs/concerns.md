# Concerns

Low-severity deferred items and override log. Reviewed periodically.

---

## C-1: Type Annotations on psycopg2 conn Parameters (Low)

- **Date**: 2026-03-16
- **Story**: 1-1
- **Severity**: LOW
- **Source**: Code review finding F6
- **Detail**: `_apply_migration(conn, ...)`, `_revert_migration(conn, ...)`, `_validate_tiers(conn)`, and `_ensure_schema_migrations(conn)` in `app/migrations/run.py` have untyped `conn` parameters. psycopg2 does not ship bundled type stubs; the correct type is `psycopg2.extensions.connection`. Adding this requires `types-psycopg2` as a dev dependency.
- **Action**: Add `types-psycopg2` to dev dependencies and annotate conn parameters in a future maintenance pass.

---

## C-2: TierSeed Fields Typed as str Instead of LimitType (Low)

- **Date**: 2026-03-16
- **Story**: 1-1
- **Severity**: LOW
- **Source**: Code review finding F7
- **Detail**: `TierSeed.generation_type` and `TierSeed.advisor_nudges_type` are typed as `str` in `app/config/tiers.py`. These should be `LimitType` for self-documentation and static analysis benefits. The circular import risk (`app/config/tiers.py` importing from `app/services/limits.py`) should be evaluated — `limits.py` has no app-layer imports so the dependency is safe.
- **Action**: Change field types to `LimitType` in a future maintenance pass.

---

## C-3: is_minor Flag Stored but Upload Blocking Not Enforced (Medium)

- **Date**: 2026-03-16
- **Story**: 2-1
- **Severity**: MEDIUM
- **Source**: Code review finding F8
- **Detail**: `POST /auth/register` captures `birth_year` and derives `is_minor` (age < 13), storing the flag in `users.is_minor`. However, no enforcement exists at the upload/generation layer — a minor user can currently proceed through the full analysis flow unchecked. AC-6 requires the flag to be stored; upload blocking was intentionally deferred to the upload story.
- **Action**: The upload story (Story 3-x) must gate `POST /analyses` or equivalent on `users.is_minor = false`. Add a `require_adult()` FastAPI dependency or check inside `require_entitlement()`.

---
