#!/bin/bash
# LaiM Strategic Compaction Hook
# Counts Edit/Write tool calls and suggests /compact at threshold
# Registered as PreToolUse hook on Edit|Write
#
# Design principle: This is an ADVISORY hook (compact suggestions). Advisory hooks
# may skip subagents. SECURITY hooks (e.g., block-sensitive-reads.sh) must apply
# to ALL agents — subagents with less user oversight are an equal or greater risk.

# Read JSON input from stdin (Claude Code PreToolUse payload)
INPUT=$(cat)

# Skip counter for subagents — their context window is separate and they can't
# act on /compact suggestions. Uses python3 JSON parsing (not grep) to extract
# the top-level agent_id field, avoiding false positives from file content inside
# tool_input.old_string/new_string that may contain the string "agent_id".
# (agent_id field available since Claude Code 2.1.69)
IS_SUBAGENT=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('agent_id', ''))
" 2>/dev/null)

# Option A: exit before counter increment — counter reflects main-agent activity only
if [ -n "$IS_SUBAGENT" ]; then
  exit 0
fi

# Counter file is scoped per working directory to isolate concurrent sessions.
# Uses a hash of PWD so different projects get separate counters.
FILE_PREFIX="laim-tool-count"
SESSION_KEY=$(echo "$PWD" | shasum | cut -c1-12)
COUNTER_FILE="/tmp/${FILE_PREFIX}-${SESSION_KEY}"

# Clean up stale counter files from old sessions (older than 24h).
# Uses -mmin for consistent behavior across BSD (macOS) and GNU (Linux/WSL) find.
# Only runs once per session (when counter file doesn't exist yet).
if [ ! -f "$COUNTER_FILE" ]; then
  find /tmp -maxdepth 1 -name "${FILE_PREFIX}-*" -mmin +1440 -delete 2>/dev/null
fi

THRESHOLD=${COMPACT_THRESHOLD:-50}
REPEAT_INTERVAL=${COMPACT_REPEAT:-25}

if [ -f "$COUNTER_FILE" ]; then
  count=$(cat "$COUNTER_FILE")
  count=$((count + 1))
  echo "$count" > "$COUNTER_FILE"
else
  echo "1" > "$COUNTER_FILE"
  count=1
fi

# First threshold hit
if [ "$count" -eq "$THRESHOLD" ]; then
  echo "[LaiM] $THRESHOLD tool calls reached — consider /compact if context is getting large" >&2
fi

# Repeat reminders
if [ "$count" -gt "$THRESHOLD" ] && [ $(((count - THRESHOLD) % REPEAT_INTERVAL)) -eq 0 ]; then
  echo "[LaiM] $count tool calls — good checkpoint for /compact" >&2
fi
