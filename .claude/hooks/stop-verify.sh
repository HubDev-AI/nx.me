#!/bin/bash
# stop-verify.sh
# Runs when Claude tries to finish a task (Stop event).
# This is the "employee-grade verification" - the agent cannot declare
# "Done!" until the project actually compiles, lints, and passes tests.
#
# If verification fails, exit 2 blocks the stop and sends errors back
# to Claude so it can fix them before completing.
#
# The stop_hook_active field prevents infinite loops: when Claude retries
# after fixing errors, the system sets this to true so we let it through.

INPUT=$(cat)

# Prevent infinite loop: if this hook already blocked once and Claude
# retried, allow the stop
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_ACTIVE" = "true" ]; then
  exit 0
fi

ERRORS=""
CHECKS_RUN=0

# --- TypeScript type-check (runs here, not per-edit, to avoid 10-30s delays) ---
if [ -f "tsconfig.json" ]; then
  CHECKS_RUN=$((CHECKS_RUN + 1))
  TSC_OUTPUT=$(npx tsc --noEmit 2>&1)
  if [ $? -ne 0 ]; then
    ERRORS="${ERRORS}TYPE CHECK FAILED:\n$(echo "$TSC_OUTPUT" | head -30)\n\n"
  fi
fi

# --- ESLint (full project) ---
if [ -f ".eslintrc" ] || [ -f ".eslintrc.js" ] || [ -f ".eslintrc.json" ] || [ -f ".eslintrc.yml" ] || [ -f "eslint.config.js" ] || [ -f "eslint.config.mjs" ] || [ -f "eslint.config.ts" ]; then
  CHECKS_RUN=$((CHECKS_RUN + 1))
  ESLINT_OUTPUT=$(npx eslint . --quiet 2>&1)
  if [ $? -ne 0 ]; then
    ERRORS="${ERRORS}LINT FAILED:\n$(echo "$ESLINT_OUTPUT" | head -30)\n\n"
  fi
fi

# --- Python type-check ---
if [ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "setup.cfg" ]; then
  if command -v mypy &> /dev/null && { [ -f "mypy.ini" ] || grep -q '\[tool.mypy\]' pyproject.toml 2>/dev/null; }; then
    CHECKS_RUN=$((CHECKS_RUN + 1))
    MYPY_OUTPUT=$(mypy . 2>&1)
    if [ $? -ne 0 ]; then
      ERRORS="${ERRORS}MYPY FAILED:\n$(echo "$MYPY_OUTPUT" | head -30)\n\n"
    fi
  fi

  if command -v ruff &> /dev/null; then
    CHECKS_RUN=$((CHECKS_RUN + 1))
    RUFF_OUTPUT=$(ruff check . 2>&1)
    if [ $? -ne 0 ]; then
      ERRORS="${ERRORS}RUFF FAILED:\n$(echo "$RUFF_OUTPUT" | head -30)\n\n"
    fi
  fi
fi

# --- Rust ---
if [ -f "Cargo.toml" ]; then
  CHECKS_RUN=$((CHECKS_RUN + 1))
  CARGO_OUTPUT=$(cargo check 2>&1)
  if [ $? -ne 0 ]; then
    ERRORS="${ERRORS}CARGO CHECK FAILED:\n$(echo "$CARGO_OUTPUT" | head -30)\n\n"
  fi
fi

# --- Test suite ---
# Prefer Makefile targets (run inside project .venv) over bare tool invocation
# so we don't fight system Python / Node / etc.
TEST_RUNNER=""
if [ -f "Makefile" ] && grep -q "^test:" Makefile 2>/dev/null; then
  TEST_RUNNER="make test"
elif [ -f "package.json" ]; then
  HAS_TEST=$(jq -r '.scripts.test // empty' package.json 2>/dev/null)
  if [ -n "$HAS_TEST" ] && [ "$HAS_TEST" != "echo \"Error: no test specified\" && exit 1" ]; then
    TEST_RUNNER="npm test"
  fi
elif [ -f "pytest.ini" ] || [ -f "pyproject.toml" ]; then
  if command -v pytest &> /dev/null; then
    TEST_RUNNER="pytest --tb=short -q"
  fi
elif [ -f "Cargo.toml" ]; then
  TEST_RUNNER="cargo test"
fi

if [ -n "$TEST_RUNNER" ] && [ "${STOP_VERIFY_SKIP_TESTS:-0}" != "1" ]; then
  CHECKS_RUN=$((CHECKS_RUN + 1))
  TEST_OUTPUT=$(eval "$TEST_RUNNER" 2>&1)
  TEST_EXIT=$?
  if [ $TEST_EXIT -ne 0 ]; then
    # Environment/setup issues (missing plugins, no venv, unknown args) aren't
    # real test failures — skip with a breadcrumb instead of blocking the turn.
    # Real failures still block.
    if echo "$TEST_OUTPUT" | grep -qE "(ModuleNotFoundError|ImportError|No module named|command not found|No such file or directory|unrecognized arguments|error: Unknown argument|\.venv/bin/[a-z]+: No such)"; then
      echo "stop-verify: test suite skipped ($TEST_RUNNER — environment issue, set STOP_VERIFY_SKIP_TESTS=1 to silence)" >&2
    else
      ERRORS="${ERRORS}TESTS FAILED ($TEST_RUNNER):\n$(echo "$TEST_OUTPUT" | tail -30)\n\n"
    fi
  fi
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
