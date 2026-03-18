"""Custom migration runner for Supabase PostgreSQL.

Usage:
    python -m app.migrations.run                          # apply all unapplied migrations
    python -m app.migrations.run --target 0001_initial    # apply up to and including target
    python -m app.migrations.run --down --target 0001_initial  # revert down to and including target
    python -m app.migrations.run --validate-tiers         # verify seeded tiers match SEED_TIERS
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

from app.config.tiers import SEED_TIERS


MIGRATIONS_DIR = Path(__file__).parent

DOWN_MARKER = "-- DOWN:"


def _get_dsn() -> str:
    """Return a psycopg2 DSN for the database.

    Checks DATABASE_URL first (preferred for local Supabase CLI),
    then falls back to parsing SUPABASE_URL for hosted Supabase.
    """
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    supabase_url = os.environ.get("SUPABASE_URL")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        print(
            "Error: DATABASE_URL or SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY must be set",
            file=sys.stderr,
        )
        sys.exit(1)

    parsed = urlparse(supabase_url)
    # Supabase URL is https://<project-ref>.supabase.co
    # PostgreSQL host is db.<project-ref>.supabase.co
    host = parsed.hostname
    if not host:
        print(
            f"Error: SUPABASE_URL '{supabase_url}' has no valid hostname",
            file=sys.stderr,
        )
        sys.exit(1)
    if not host.startswith("db."):
        host = f"db.{host}"
    project_ref = parsed.hostname.split(".")[0]

    return (
        f"host={host} port=5432 dbname=postgres "
        f"user=postgres.{project_ref} "
        f"password={service_key} sslmode=require"
    )


def _ensure_schema_migrations(conn) -> None:
    """Create the _schema_migrations tracking table if it does not exist."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _schema_migrations (
                id           SERIAL PRIMARY KEY,
                migration_id TEXT UNIQUE NOT NULL,
                applied_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()


def _get_applied(conn) -> set[str]:
    """Return the set of already-applied migration IDs."""
    with conn.cursor() as cur:
        cur.execute("SELECT migration_id FROM _schema_migrations")
        return {row[0] for row in cur.fetchall()}


def _discover_migrations() -> list[tuple[str, Path]]:
    """Discover migration SQL files and return them sorted by filename.

    Returns a list of (migration_id, file_path) tuples.
    migration_id is the filename without the .sql extension (e.g. '0001_initial').
    """
    pattern = re.compile(r"^\d{4}_.*\.sql$")
    files = sorted(
        f for f in MIGRATIONS_DIR.iterdir()
        if f.is_file() and pattern.match(f.name)
    )
    return [(f.stem, f) for f in files]


def _split_sql(path: Path) -> tuple[str, str]:
    """Split a migration file into up and down SQL using the -- DOWN: marker."""
    content = path.read_text()
    if DOWN_MARKER in content:
        up_sql, down_sql = content.split(DOWN_MARKER, 1)
        return up_sql.strip(), down_sql.strip()
    return content.strip(), ""


def _apply_migration(conn, migration_id: str, path: Path) -> None:
    """Apply a single migration inside a transaction."""
    up_sql, _ = _split_sql(path)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(up_sql)
            cur.execute(
                "INSERT INTO _schema_migrations (migration_id, applied_at) VALUES (%s, NOW())",
                (migration_id,),
            )
        conn.commit()
        print(f"Applied: {migration_id}")
    except Exception:
        conn.rollback()
        print(f"Failed: {migration_id}", file=sys.stderr)
        raise


def _revert_migration(conn, migration_id: str, path: Path) -> None:
    """Revert a single migration inside a transaction."""
    _, down_sql = _split_sql(path)
    if not down_sql:
        print(f"Error: no DOWN section in {path.name}", file=sys.stderr)
        sys.exit(1)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(down_sql)
            cur.execute(
                "DELETE FROM _schema_migrations WHERE migration_id = %s",
                (migration_id,),
            )
        conn.commit()
        print(f"Reverted: {migration_id}")
    except Exception:
        conn.rollback()
        print(f"Failed to revert: {migration_id}", file=sys.stderr)
        raise


def _validate_tiers(conn) -> None:
    """Verify that the tiers table contains exactly the rows defined in SEED_TIERS.

    Uses SEED_TIERS as the authoritative Python source of truth and compares
    slugs, fixed UUIDs, and the is_default flag against the live database.
    Exits non-zero if any mismatch is detected.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, slug, is_default FROM tiers ORDER BY slug")
        rows = {row[1]: {"id": row[0], "is_default": row[2]} for row in cur.fetchall()}

    expected_slugs = {t.slug for t in SEED_TIERS}
    actual_slugs = set(rows)
    if expected_slugs != actual_slugs:
        missing = expected_slugs - actual_slugs
        extra = actual_slugs - expected_slugs
        print("Error: tiers mismatch", file=sys.stderr)
        if missing:
            print(f"  Missing slugs: {sorted(missing)}", file=sys.stderr)
        if extra:
            print(f"  Unexpected slugs: {sorted(extra)}", file=sys.stderr)
        sys.exit(1)

    errors: list[str] = []
    for tier in SEED_TIERS:
        row = rows[tier.slug]
        if str(row["id"]) != tier.id:
            errors.append(f"  {tier.slug}: id mismatch (db={row['id']}, expected={tier.id})")
        if row["is_default"] != tier.is_default:
            errors.append(
                f"  {tier.slug}: is_default mismatch (db={row['is_default']}, expected={tier.is_default})"
            )

    if errors:
        print("Error: tier data mismatch:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    print(f"Tiers OK — {len(SEED_TIERS)} tiers validated against SEED_TIERS")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--target",
        help="Migration ID to target (e.g. 0001_initial)",
    )
    parser.add_argument(
        "--down",
        action="store_true",
        help="Revert migrations down to and including the target",
    )
    parser.add_argument(
        "--validate-tiers",
        action="store_true",
        help="Verify seeded tiers match SEED_TIERS definition (post-migration check)",
    )
    args = parser.parse_args()

    if args.down and not args.target:
        print("Error: --down requires --target", file=sys.stderr)
        sys.exit(1)

    dsn = _get_dsn()
    conn = psycopg2.connect(dsn)

    try:
        if args.validate_tiers:
            _validate_tiers(conn)
            return

        _ensure_schema_migrations(conn)
        migrations = _discover_migrations()
        applied = _get_applied(conn)

        if args.down:
            # Find all applied migrations from current back to target (inclusive),
            # then revert them in reverse order.
            target_idx = None
            for i, (mid, _) in enumerate(migrations):
                if mid == args.target:
                    target_idx = i
                    break
            if target_idx is None:
                print(f"Error: target migration '{args.target}' not found", file=sys.stderr)
                sys.exit(1)

            to_revert = [
                (mid, path)
                for mid, path in reversed(migrations)
                if mid in applied and migrations.index((mid, path)) >= target_idx
            ]

            if not to_revert:
                print("Nothing to revert.")
                return

            for mid, path in to_revert:
                _revert_migration(conn, mid, path)
        else:
            # Apply unapplied migrations in order, up to target (inclusive) if specified.
            target_found = args.target is None
            for mid, path in migrations:
                if mid in applied:
                    print(f"Already applied: {mid}")
                else:
                    _apply_migration(conn, mid, path)
                if args.target and mid == args.target:
                    target_found = True
                    break

            if not target_found:
                print(f"Error: target migration '{args.target}' not found", file=sys.stderr)
                sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
