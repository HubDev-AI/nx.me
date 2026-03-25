#!/usr/bin/env bash
# GOAL.md fitness function — composite code health score
# Output: JSON with score, max, and per-component breakdown
# Exit 0 always (non-zero means the script itself broke)
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

# ── Backend test coverage (0-50 pts) ─────────────────────────────────────────
COV_JSON=$(mktemp)
.venv/bin/pytest tests/ -q \
  --override-ini="addopts=--cov=app --cov-report=json:${COV_JSON} -p pytest_asyncio" \
  -p no:twisted --tb=no >/dev/null 2>&1 || true

if [ -f "$COV_JSON" ] && [ -s "$COV_JSON" ]; then
  COVERAGE=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['totals']['percent_covered'])" "$COV_JSON" 2>/dev/null || echo "0")
else
  COVERAGE="0"
fi
rm -f "$COV_JSON"

COV_SCORE=$(python3 -c "print(min(50, int(float($COVERAGE) / 2 + 0.5)))")

# ── Backend lint (0-15 pts) ──────────────────────────────────────────────────
RUFF_OUT=$(.venv/bin/ruff check app/ tests/ 2>&1 || true)
# Parse "Found N errors." from ruff summary
RUFF_ERRORS=$(echo "$RUFF_OUT" | python3 -c "
import sys, re
text = sys.stdin.read()
m = re.search(r'Found (\d+) error', text)
print(m.group(1) if m else '0')
")

BACKEND_LINT=$(python3 -c "print(max(0, 15 - $RUFF_ERRORS * 3))")

# ── Mobile lint (0-15 pts) ───────────────────────────────────────────────────
MOBILE_OUT=$(cd mobile && npx expo lint 2>&1 || true)
# Parse "N problems (M errors, K warnings)" from eslint summary
read -r MOBILE_ERRORS MOBILE_WARNINGS <<< "$(echo "$MOBILE_OUT" | python3 -c "
import sys, re
text = sys.stdin.read()
errors = 0; warnings = 0
# Match the ESLint summary line: 'N problems (M errors, K warnings)'
m = re.search(r'\((\d+)\s+error', text)
if m: errors = int(m.group(1))
m = re.search(r'(\d+)\s+warning(?:s)?\)', text)
if m: warnings = int(m.group(1))
print(f'{errors} {warnings}')
")"

MOBILE_LINT=$(python3 -c "print(max(0, int(15 - $MOBILE_ERRORS * 3 - $MOBILE_WARNINGS * 0.5 + 0.5)))")

# ── Test pass rate (0-20 pts) ────────────────────────────────────────────────
TEST_OUT=$(.venv/bin/pytest tests/ -q \
  --override-ini="addopts=-p pytest_asyncio" \
  -p no:twisted --tb=no 2>&1 || true)

read -r PASSED FAILED <<< "$(echo "$TEST_OUT" | python3 -c "
import sys, re
text = sys.stdin.read()
passed = 0; failed = 0
m = re.search(r'(\d+)\s+passed', text)
if m: passed = int(m.group(1))
m = re.search(r'(\d+)\s+failed', text)
if m: failed = int(m.group(1))
print(f'{passed} {failed}')
")"

TOTAL=$((PASSED + FAILED))
if [ "$TOTAL" -gt 0 ]; then
  TEST_SCORE=$(python3 -c "print(int(($PASSED / $TOTAL) * 20 + 0.5))")
else
  TEST_SCORE=0
fi

# ── Composite ────────────────────────────────────────────────────────────────
SCORE=$((COV_SCORE + BACKEND_LINT + MOBILE_LINT + TEST_SCORE))

cat <<EOF
{
  "score": $SCORE,
  "max": 100,
  "components": {
    "backend_coverage": {"score": $COV_SCORE, "max": 50, "raw_pct": $(python3 -c "print(round(float($COVERAGE), 1))")},
    "backend_lint": {"score": $BACKEND_LINT, "max": 15, "issues": $RUFF_ERRORS},
    "mobile_lint": {"score": $MOBILE_LINT, "max": 15, "errors": $MOBILE_ERRORS, "warnings": $MOBILE_WARNINGS},
    "test_pass_rate": {"score": $TEST_SCORE, "max": 20, "passed": $PASSED, "failed": $FAILED}
  }
}
EOF
