#!/usr/bin/env python3
"""Admin script — list / delete stale `users.is_guest=true` rows.

Defaults to dry-run. Pass `--apply` to actually delete (with a confirmation
prompt). FK CASCADEs handle child rows in advisor_messages, user_memories,
uploads, etc. (per migration 0007).

Usage:
    .venv/bin/python scripts/cleanup-guest-users.py
    .venv/bin/python scripts/cleanup-guest-users.py --older-than-days=7
    .venv/bin/python scripts/cleanup-guest-users.py --apply

Refuses to run unless `APP_ENV` is `development` or `staging` to keep the
script away from production DBs by accident. Override with `--allow-prod`
if you really mean it.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "app" / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="List or delete stale guest user rows.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--older-than-days",
        type=int,
        default=30,
        help="Only consider guest rows whose created_at is older than this "
        "many days (default: 30). Must be >= 1.",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=100,
        help="Refuse to delete if matches exceed this cap unless --force is "
        "passed (default: 100).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matching rows. Without this flag the script "
        "only lists.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Bypass --max-rows cap. Use with care.",
    )
    p.add_argument(
        "--allow-prod",
        action="store_true",
        help="Run even when APP_ENV=production. Default refuses.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-row output (useful for cron-style invocations).",
    )
    args = p.parse_args()

    if args.older_than_days < 1:
        p.error("--older-than-days must be >= 1")
    if args.max_rows < 1:
        p.error("--max-rows must be >= 1")
    return args


def main() -> int:
    args = parse_args()

    if APP_ENV == "production" and not args.allow_prod:
        sys.stderr.write(
            "Refusing to run with APP_ENV=production. Pass --allow-prod "
            "to override.\n"
        )
        return 2

    if not DATABASE_URL:
        sys.stderr.write(
            "DATABASE_URL not set. Source app/.env or export it manually.\n"
        )
        return 2

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # is_guest column was added in migration 0033.
            cur.execute(
                "SELECT id, created_at "
                "FROM users WHERE is_guest = true AND created_at < %s "
                "ORDER BY created_at ASC",
                (cutoff,),
            )
            rows = cur.fetchall()

        match_count = len(rows)
        if not args.quiet:
            print(
                f"Matched {match_count} guest rows older than "
                f"{args.older_than_days} day(s) (cutoff: {cutoff.isoformat()})"
            )
            for row_id, created_at in rows[:50]:
                print(f"  {row_id}  {created_at.isoformat()}")
            if match_count > 50:
                print(f"  ... and {match_count - 50} more")

        if match_count == 0:
            print("Nothing to do.")
            return 0

        if not args.apply:
            print("\nDry run — pass --apply to delete these rows.")
            return 0

        if match_count > args.max_rows and not args.force:
            sys.stderr.write(
                f"\nMatched {match_count} rows exceeds --max-rows="
                f"{args.max_rows}. Pass --force to override or narrow "
                "--older-than-days.\n"
            )
            return 3

        confirm = input(
            f"\nDelete {match_count} guest user rows (cascades to "
            "advisor_messages, user_memories, uploads, etc.)? [y/N]: "
        ).strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return 0

        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM users WHERE is_guest = true AND created_at < %s",
                (cutoff,),
            )
            deleted = cur.rowcount
        conn.commit()
        print(f"Deleted {deleted} guest user rows.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
