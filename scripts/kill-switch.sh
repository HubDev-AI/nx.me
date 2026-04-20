#!/usr/bin/env bash
# Manage rows in app_kill_switches without a redeploy.
#
# Usage:
#   scripts/kill-switch.sh status [key]
#   scripts/kill-switch.sh pause  <key> [note]
#   scripts/kill-switch.sh resume <key> [note]
#
# Reads DATABASE_URL from the calling environment (sourced from app/.env by
# the make targets). Fails fast if DATABASE_URL is unset (no fallback).

set -euo pipefail

ACTION="${1:-}"
KEY="${2:-}"
NOTE="${3:-}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set. Source app/.env first." >&2
  exit 2
fi

toggle() {
  local new_enabled="$1"   # 'TRUE' or 'FALSE'
  local default_note="$2"  # default note prefix
  if [[ -z "${KEY}" ]]; then
    echo "ERROR: action '${ACTION}' requires a key." >&2
    echo "Usage: scripts/kill-switch.sh ${ACTION} <key> [note]" >&2
    exit 2
  fi
  local note_val="${NOTE:-${default_note} $(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  psql "${DATABASE_URL}" \
    -v ON_ERROR_STOP=1 \
    -v "ks_key=${KEY}" \
    -v "ks_note=${note_val}" <<SQL
UPDATE app_kill_switches
   SET enabled = ${new_enabled},
       note = :'ks_note',
       updated_at = now()
 WHERE key = :'ks_key';
SELECT key, enabled, note, updated_at
  FROM app_kill_switches
 WHERE key = :'ks_key';
SQL
}

case "${ACTION}" in
  status)
    if [[ -n "${KEY}" ]]; then
      psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 -v "ks_key=${KEY}" <<'SQL'
SELECT key, enabled, note, updated_at
  FROM app_kill_switches
 WHERE key = :'ks_key';
SQL
    else
      psql "${DATABASE_URL}" -v ON_ERROR_STOP=1 \
        -c "SELECT key, enabled, note, updated_at FROM app_kill_switches ORDER BY key;"
    fi
    ;;
  pause)
    toggle "FALSE" "paused"
    ;;
  resume)
    toggle "TRUE" "resumed"
    ;;
  *)
    cat >&2 <<USAGE
Usage:
  scripts/kill-switch.sh status [key]
  scripts/kill-switch.sh pause  <key> [note]
  scripts/kill-switch.sh resume <key> [note]

Known keys (seeded):
  weekly_free_grant  — Monday 02:30 UTC weekly free-credit grant cron
USAGE
    exit 2
    ;;
esac
