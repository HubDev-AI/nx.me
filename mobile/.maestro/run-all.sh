#!/usr/bin/env bash
# Run all Maestro test flows in a loop
set -uo pipefail
export PATH="$PATH:$HOME/.maestro/bin"

FLOWS_DIR="$(dirname "$0")/flows"
RESULTS_DIR="$(dirname "$0")/results"
mkdir -p "$RESULTS_DIR"

ITERATION=${1:-1}
MAX_ITERATIONS=${2:-10}
PASS=0
FAIL=0
TOTAL=0

echo "=========================================="
echo "NXME Mobile Test Suite — Iteration $ITERATION/$MAX_ITERATIONS"
echo "=========================================="

for flow in "$FLOWS_DIR"/[0-9]*.yaml; do
  name=$(basename "$flow" .yaml)

  # Skip all reusable flows (00-*)
  [[ "$name" == 00-* ]] && continue

  TOTAL=$((TOTAL + 1))
  echo ""
  echo "--- Running: $name ---"

  if maestro test "$flow" --no-ansi 2>&1 | tee "$RESULTS_DIR/${name}-iter${ITERATION}.log" | tail -5; then
    PASS=$((PASS + 1))
    echo "✓ PASS: $name"
  else
    FAIL=$((FAIL + 1))
    echo "✗ FAIL: $name"
  fi
done

echo ""
echo "=========================================="
echo "Iteration $ITERATION Results: $PASS/$TOTAL passed, $FAIL failed"
echo "=========================================="

# Return non-zero if any test failed
[[ $FAIL -eq 0 ]]
