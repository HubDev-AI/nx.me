"""Custom migration runner for Supabase PostgreSQL.

Usage:
    python -m app.migrations.run                          # apply all unapplied migrations
    python -m app.migrations.run --target 0001_initial    # apply up to and including target
    python -m app.migrations.run --down --target 0001_initial  # revert down to and including target
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2


MIGRATIONS_DIR = Path(__file__).parent

DOWN_MARKER_RE = re.compile(r"^-- DOWN:?\s*$", re.MULTILINE)


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
        f for f in MIGRATIONS_DIR.iterdir() if f.is_file() and pattern.match(f.name)
    )
    return [(f.stem, f) for f in files]


def _split_sql(path: Path) -> tuple[str, str]:
    """Split a migration file into up and down SQL using the -- DOWN[:] marker.

    Accepts both ``-- DOWN`` and ``-- DOWN:`` as the marker line. A missing
    colon previously caused the entire file — including the DOWN section — to
    execute during apply, silently self-destroying the migration's own table
    (see regression in 0052 before 2026-04-20).
    """
    content = path.read_text()
    match = DOWN_MARKER_RE.search(content)
    if match is None:
        return content.strip(), ""
    up_sql = content[: match.start()]
    down_sql = content[match.end() :]
    return up_sql.strip(), down_sql.strip()


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
    args = parser.parse_args()

    if args.down and not args.target:
        print("Error: --down requires --target", file=sys.stderr)
        sys.exit(1)

    # Security: DSN contains credentials — never log it.
    dsn = _get_dsn()
    conn = psycopg2.connect(dsn)

    try:
        _ensure_schema_migrations(conn)
        migrations = _discover_migrations()
        applied = _get_applied(conn)
        conn.rollback()  # end implicit transaction so _apply_migration can set autocommit

        if args.down:
            # Find all applied migrations from current back to target (inclusive),
            # then revert them in reverse order.
            target_idx = None
            for i, (mid, _) in enumerate(migrations):
                if mid == args.target:
                    target_idx = i
                    break
            if target_idx is None:
                print(
                    f"Error: target migration '{args.target}' not found",
                    file=sys.stderr,
                )
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
                print(
                    f"Error: target migration '{args.target}' not found",
                    file=sys.stderr,
                )
                sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
