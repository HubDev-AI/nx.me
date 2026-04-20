#!/usr/bin/env python3
"""Wipe NXME test data from Supabase DB, auth, and Redis.

Only deletes data owned by NXME users (rows in public.users).
Does NOT touch auth users or data belonging to other projects
sharing the same local Supabase instance.

Usage:
    make nuke          # wipe all NXME data except tiers
    make nuke-keep     # also keep demo/seed users
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
import redis
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "app" / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# FK-safe deletion order: children before parents.
# Each entry is (table_name, fk_column_to_users) or None if no user FK.
TABLES_IN_ORDER: list[tuple[str, str | None]] = [
    ("shareable_cards", "user_id"),
    ("reactions", "user_id"),
    ("comments", "user_id"),
    ("reports", "reporter_user_id"),
    ("prompt_experiments", None),  # FK via jobs
    ("posts", "user_id"),
    ("credit_reservations", "user_id"),
    ("jobs", "user_id"),
    ("glowup_analyses", None),  # FK via uploads
    ("uploads", "user_id"),
    ("images", "user_id"),
    ("credit_ledger", "user_id"),
    ("subscriptions", "user_id"),
    ("advisor_messages", None),  # FK via conversation
    ("advisor_nudges", "user_id"),
    ("advisor_conversations", "user_id"),
    ("user_memories", "user_id"),
    ("blocked_users", "blocker_id"),
    ("processed_webhook_events", None),
    ("users", None),  # deleted last, uses id directly
]

DEMO_EMAILS = {
    "demo@nxme.ai",
    "demo@nxme.local",
    "alex.e2e@test.local",
    "maya.e2e@test.local",
}

# Redis key prefixes owned by NXME
NXME_REDIS_PREFIXES = [
    "reg_",
    "login_",
    "gen:",
    "tier:",
    "advisor:",
    "credit:",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nuke NXME test data")
    parser.add_argument(
        "--keep-demo",
        action="store_true",
        help="Preserve demo/seed users and their data",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    # ── 1. Collect NXME user IDs to delete ───────────────────────────────
    if args.keep_demo:
        placeholders = ",".join(f"'{e}'" for e in DEMO_EMAILS)
        cur.execute(f"SELECT id FROM users WHERE email NOT IN ({placeholders})")
    else:
        cur.execute("SELECT id FROM users")
    nxme_user_ids = [str(row[0]) for row in cur.fetchall()]

    if not nxme_user_ids:
        print("  No NXME users found — nothing to delete")
    else:
        print(f"  Found {len(nxme_user_ids)} NXME users to delete")

        id_list = ",".join(f"'{uid}'" for uid in nxme_user_ids)

        # ── 2. Delete child rows by user FK ──────────────────────────────
        for table, fk_col in TABLES_IN_ORDER:
            if table == "users":
                continue  # deleted last
            try:
                if fk_col:
                    cur.execute(f"DELETE FROM {table} WHERE {fk_col} IN ({id_list})")
                elif table == "advisor_messages":
                    # FK via advisor_conversations
                    cur.execute(
                        f"DELETE FROM advisor_messages WHERE conversation_id IN "
                        f"(SELECT id FROM advisor_conversations WHERE user_id IN ({id_list}))"
                    )
                elif table == "prompt_experiments":
                    cur.execute(
                        f"DELETE FROM prompt_experiments WHERE job_id IN "
                        f"(SELECT id FROM jobs WHERE user_id IN ({id_list}))"
                    )
                elif table == "glowup_analyses":
                    cur.execute(
                        f"DELETE FROM glowup_analyses WHERE upload_id IN "
                        f"(SELECT id FROM uploads WHERE user_id IN ({id_list}))"
                    )
                elif table == "processed_webhook_events":
                    # Not user-scoped — skip (shared infra table)
                    continue
                else:
                    continue
                if cur.rowcount:
                    print(f"  Wiped {table} ({cur.rowcount} rows)")
            except Exception as e:
                print(f"  Skip  {table}: {e}")

        # ── 3. Delete NXME user rows ─────────────────────────────────────
        cur.execute(f"DELETE FROM users WHERE id IN ({id_list})")
        print(f"  Wiped users ({cur.rowcount} rows)")

    cur.close()
    conn.close()

    # ── 4. Delete ONLY matching Supabase auth users ──────────────────────
    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    auth_deleted = 0
    nxme_id_set = set(nxme_user_ids)
    for user in sb.auth.admin.list_users():
        if str(user.id) not in nxme_id_set:
            continue  # not an NXME user — leave it alone
        if args.keep_demo and user.email in DEMO_EMAILS:
            continue
        try:
            sb.auth.admin.delete_user(user.id)
            auth_deleted += 1
        except Exception as e:
            print(f"  Auth skip {user.email}: {e}")
    print(f"  Wiped {auth_deleted} auth users")

    # ── 5. Delete only NXME Redis keys (not FLUSHDB) ─────────────────────
    try:
        r = redis.from_url(REDIS_URL)
        deleted_keys = 0
        for prefix in NXME_REDIS_PREFIXES:
            keys = r.keys(f"{prefix}*")
            if keys:
                deleted_keys += r.delete(*keys)
        # Also delete per-user keys
        for uid in nxme_user_ids:
            keys = r.keys(f"*{uid}*")
            if keys:
                deleted_keys += r.delete(*keys)
        print(f"  Cleared {deleted_keys} Redis keys")
    except Exception as e:
        print(f"  Redis failed: {e}")

    print("\nDone. No restart needed.")


if __name__ == "__main__":
    main()
