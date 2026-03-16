#!/bin/bash
# LaiM Sensitive File Protection Hook
# Blocks Read tool calls to .env, key, credential, and secret files
# Registered as PreToolUse hook on Read

# Read JSON input from stdin
INPUT=$(cat)

# Extract file_path using python3 (available on macOS/Linux)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', ''))
" 2>/dev/null)

# If extraction failed, allow (safe fallback)
if [ -z "$FILE_PATH" ]; then
  exit 0
fi

FILENAME=$(basename "$FILE_PATH")
BLOCKED=false
REASON=""

# .env files (.env, .env.local, .env.production, etc.)
if [[ "$FILENAME" == .env ]] || [[ "$FILENAME" == .env.* ]] || [[ "$FILENAME" == *.env ]]; then
  BLOCKED=true
  REASON=".env file"
fi

# Private key / certificate files
if [[ "$FILENAME" =~ \.(pem|key|p12|pfx|jks|keystore)$ ]]; then
  BLOCKED=true
  REASON="Private key/certificate file"
fi

# SSH keys
if [[ "$FILENAME" == id_rsa* ]] || [[ "$FILENAME" == id_ed25519* ]] || [[ "$FILENAME" == id_ecdsa* ]]; then
  BLOCKED=true
  REASON="SSH key file"
fi

# Credentials / secrets files
if [[ "$FILENAME" =~ ^(credentials|secrets|secret|token|tokens)\.(json|yaml|yml|xml|txt|ini|cfg|conf)$ ]]; then
  BLOCKED=true
  REASON="Credentials/secrets file"
fi

# Package registry auth files
if [[ "$FILENAME" == .npmrc ]] || [[ "$FILENAME" == .pypirc ]]; then
  BLOCKED=true
  REASON="Package registry auth file"
fi

if [ "$BLOCKED" = true ]; then
  # Primary: structured JSON deny (documented PreToolUse pattern)
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[LaiM] Blocked: %s — %s. If you need this file, ask the user to provide the relevant content directly."}}\n' "$REASON" "$FILE_PATH"
  # Fallback: exit 2 ensures the read is blocked even if JSON parsing fails
  printf '[LaiM] Blocked: %s — %s. If you need this file, ask the user to provide the relevant content directly.\n' "$REASON" "$FILE_PATH" >&2
  exit 2
fi

exit 0
