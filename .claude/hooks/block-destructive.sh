#!/bin/bash
# block-destructive.sh
# PreToolUse hook for Bash commands.
# Blocks obviously destructive operations before they execute.

INPUT=$(cat)

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

# Block recursive deletion of root, home, or current directory
if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|(-[a-zA-Z]*\s+)*)(\/|~|\$HOME|\.\.)'; then
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked destructive rm command targeting root, home, or parent directory. If intentional, run manually."}}'
  exit 0
fi

# Block database destruction
if echo "$COMMAND" | grep -qiE 'DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\S+\s*;?\s*$'; then
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked destructive database command. If intentional, run manually."}}'
  exit 0
fi

# Block force pushes
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force|git\s+push\s+-f\b|git\s+reset\s+--hard\s+(HEAD~|origin)'; then
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked force push or hard reset. If intentional, run manually."}}'
  exit 0
fi

# Block .env file reads (prevent accidental credential exposure)
if echo "$COMMAND" | grep -qE '(cat|less|head|tail|more|source|grep|sed|awk|bat)\s+\.env\b|echo.*\$\(.*\.env'; then
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked .env file access. Credentials should not be read by the agent."}}'
  exit 0
fi

# Block pip / pip3 install — project standard is uv
if echo "$COMMAND" | grep -qE '(^|[^a-zA-Z_])(pip3?|python3?\s+-m\s+pip)\s+install\b'; then
  echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked pip install. Use uv add <packages> (see CLAUDE.md). If this is an intentional override, run manually."}}'
  exit 0
fi

# Block direct push to dev / main (must go through PR)
# Matches: git push <remote> dev|main, git push <remote> HEAD:dev, git push -u origin dev
# Allows: git push origin <feature-branch>, git push --delete, fetch/pull
if echo "$COMMAND" | grep -qE 'git\s+push(\s+(-[a-zA-Z]+|--[a-z-]+))*\s+\S+(\s+(HEAD:)?(dev|main)\b|\s*$)'; then
  # Further check: only block if dev/main is the target ref (or implicit via tracking)
  if echo "$COMMAND" | grep -qE 'git\s+push.*\s(HEAD:)?(dev|main)(\s|$)'; then
    echo '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "Blocked direct push to dev/main. Workflow is feature-branch -> PR -> merge (see MEMORY.md). If this is an intentional override, run manually."}}'
    exit 0
  fi
fi

exit 0
