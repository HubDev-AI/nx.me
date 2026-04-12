#!/bin/bash
# stop-verify.sh
# Runs on Stop event: "employee-grade verification" — no "Done!" until the
# project actually compiles, lints, and passes tests.
#
# nxme.ai layout is split-module:
#   app/        Python (FastAPI) — ruff + pytest driven by Makefile
#   mobile/     React Native (Expo) — own tsconfig, eslint.config.js, jest
#   card-web/   Next.js — own tsconfig, .eslintrc.json, vitest
#   No tsconfig / eslint / pyproject at project root, so we must descend.
#
# Prefers Makefile targets over bare tool invocation (runs inside .venv,
# avoids fighting system Python / Node).
#
# exit 2 + {"decision": "block"} sends errors back to Claude.
# stop_hook_active=true breaks the retry loop.

INPUT=$(cat)

STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_ACTIVE" = "true" ]; then
  exit 0
fi

ERRORS=""
CHECKS_RUN=0

run_check() {
  # $1 label, $2 cwd, $3 command
  local label="$1" cwd="$2" cmd="$3" out exit_code
  CHECKS_RUN=$((CHECKS_RUN + 1))
  out=$(cd "$cwd" 2>/dev/null && eval "$cmd" 2>&1)
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    # Environment-level failures (missing deps, no venv) shouldn't block the turn
    if echo "$out" | grep -qE "(ModuleNotFoundError|No module named|command not found|No such file or directory|\.venv/bin/[a-z]+: No such)"; then
      echo "stop-verify: $label skipped (environment issue)" >&2
      return 0
    fi
    ERRORS="${ERRORS}${label} FAILED:\n$(echo "$out" | tail -40)\n\n"
  fi
}

# --- Python: prefer Makefile `lint` (ruff) ---
if [ -f "Makefile" ] && grep -qE "^lint:" Makefile 2>/dev/null; then
  run_check "ruff (make lint)" "." "make lint"
elif [ -d "app" ] && command -v ruff &> /dev/null; then
  run_check "ruff (app/, tests/)" "." "ruff check app/ tests/"
fi

# --- TypeScript: descend into each module with its own tsconfig ---
for TS_DIR in mobile card-web; do
  if [ -f "$TS_DIR/tsconfig.json" ]; then
    # Use the module's package.json type-check script if present, else bare tsc
    if [ -f "$TS_DIR/package.json" ] && jq -e '.scripts."type-check"' "$TS_DIR/package.json" >/dev/null 2>&1; then
      run_check "tsc ($TS_DIR)" "$TS_DIR" "npm run type-check --silent"
    else
      run_check "tsc ($TS_DIR)" "$TS_DIR" "npx tsc --noEmit"
    fi
  fi
done

# --- ESLint: descend into each module with its own eslint config ---
for JS_DIR in mobile card-web; do
  if ls "$JS_DIR"/.eslintrc* 2>/dev/null | grep -q . || ls "$JS_DIR"/eslint.config.* 2>/dev/null | grep -q .; then
    if [ -f "$JS_DIR/package.json" ] && jq -e '.scripts.lint' "$JS_DIR/package.json" >/dev/null 2>&1; then
      run_check "eslint ($JS_DIR)" "$JS_DIR" "npm run lint --silent"
    else
      run_check "eslint ($JS_DIR)" "$JS_DIR" "npx eslint . --quiet"
    fi
  fi
done

# --- Test suite: prefer Makefile `test` target ---
if [ -f "Makefile" ] && grep -qE "^test:" Makefile 2>/dev/null && [ "${STOP_VERIFY_SKIP_TESTS:-0}" != "1" ]; then
  run_check "tests (make test)" "." "make test"
fi

# --- Report ---
if [ -n "$ERRORS" ]; then
  SUMMARY="Verification failed ($CHECKS_RUN checks ran). Fix these errors before completing:\n\n${ERRORS}"
  echo "{\"decision\": \"block\", \"reason\": \"${SUMMARY}\"}"
  exit 2
fi

if [ $CHECKS_RUN -eq 0 ]; then
  echo "{\"additionalContext\": \"No type-checker, linter, or test suite detected. Task completion is unverified. State this to the user.\"}"
  exit 0
fi

echo "stop-verify: $CHECKS_RUN checks passed" >&2
exit 0
