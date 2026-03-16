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
