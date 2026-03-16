#!/bin/bash
# LaiM State Validation Hook
# Validates state.json writes and blocks Edit operations on state files.
# Registered as PreToolUse hook on Edit|Write.
#
# Enforcement: state.json is always written via the Write tool, never Edit.
# Edit operations on state.json are denied with guidance to use Write instead.
# Write operations are validated for required fields, structure, and timestamps.
#
# Design: Python core logic with thin bash entry point, matching the
# block-sensitive-reads.sh pattern. Uses python3 (ships with macOS/Linux,
# already required by block-sensitive-reads.sh).

# Read JSON input from stdin (Claude Code PreToolUse payload)
INPUT=$(cat)

# Extract file_path and tool_name from hook payload
EXTRACTED=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('tool_input', {}).get('file_path', ''))
print(d.get('tool_name', ''))
" 2>/dev/null)

# If extraction failed, allow (safe fallback)
if [ -z "$EXTRACTED" ]; then
  exit 0
fi

FILE_PATH=$(echo "$EXTRACTED" | head -1)
TOOL_NAME=$(echo "$EXTRACTED" | tail -1)

# Short-circuit: only act on state.json and .quick-state.json
FILENAME=$(basename "$FILE_PATH" 2>/dev/null)
if [ "$FILENAME" != "state.json" ] && [ "$FILENAME" != ".quick-state.json" ]; then
  exit 0
fi

# Consecutive failure counter — HALT after 3 consecutive failures to prevent retry loops
FAIL_PREFIX="laim-state-fail"
FAIL_SESSION_KEY=$(echo "$PWD" | shasum | cut -c1-12)
FAIL_COUNTER="/tmp/${FAIL_PREFIX}-${FAIL_SESSION_KEY}"

# Helper: increment failure counter and check for HALT threshold
increment_failures() {
  local count=0
  if [ -f "$FAIL_COUNTER" ]; then
    count=$(cat "$FAIL_COUNTER")
  fi
  count=$((count + 1))
  echo "$count" > "$FAIL_COUNTER"
  if [ "$count" -ge 3 ]; then
    printf '\n[LaiM] ⛔ HALT: 3 consecutive state.json validation failures.\nStop retrying and fix the root cause. Read the errors above carefully.\nIf stuck, ask the user for help.\n' >&2
  fi
}

# Helper: reset failure counter on successful validation
reset_failures() {
  rm -f "$FAIL_COUNTER" 2>/dev/null
}

# Block Edit operations on state files — must use Write for validation to work
if [ "$TOOL_NAME" = "Edit" ]; then
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[LaiM] Use Write (full file) for %s, not Edit. Edit bypasses state validation. Write the complete state.json content using the Write tool."}}\n' "$FILENAME"
  printf '[LaiM] ❌ Edit blocked on %s — use Write (full file) instead.\nThe validate-state.sh hook can only validate complete Write operations.\n' "$FILENAME" >&2
  increment_failures
  exit 2
fi

# Run Python validation on the Write content and handle output in one pass
echo "$INPUT" | python3 -c "
import sys, json, re

# Parse hook payload
payload = json.load(sys.stdin)
content = payload.get('tool_input', {}).get('content', '')

errors = []

# 1. Valid JSON
try:
    state = json.loads(content)
except (json.JSONDecodeError, TypeError) as e:
    errors.append(f'Invalid JSON: {e}')
    # Can't validate further — emit deny and exit
    reason = '[LaiM] Blocked invalid state.json write: ' + errors[0]
    deny = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    print(json.dumps(deny))
    print('[LaiM] ❌ Invalid state.json write blocked:', file=sys.stderr)
    print(f'  - {errors[0]}', file=sys.stderr)
    print('Fix the error above and retry the Write.', file=sys.stderr)
    sys.exit(2)

if not isinstance(state, dict):
    reason = '[LaiM] Blocked: state.json must be a JSON object, got ' + type(state).__name__
    deny = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    print(json.dumps(deny))
    print(reason, file=sys.stderr)
    sys.exit(2)

# 2. Required top-level fields
required_fields = ['feature', 'flow', 'version', 'created', 'lastUpdated', 'currentPhase']
for field in required_fields:
    if field not in state:
        errors.append(f'Missing required field: {field}')

# 3. Expected sub-objects
expected_objects = {
    'tooling': ['format', 'lint', 'build', 'test'],
    'metrics': ['gates', 'phases', 'stories', 'tasks', 'codeReview', 'quality', 'drift', 'estimation', 'execution', 'git'],
}
for obj_name, expected_keys in expected_objects.items():
    if obj_name not in state:
        errors.append(f'Missing required object: {obj_name}')
    elif not isinstance(state[obj_name], dict):
        errors.append(f'{obj_name} must be an object')
    else:
        for key in expected_keys:
            if key not in state[obj_name]:
                errors.append(f'Missing field: {obj_name}.{key}')

# 4. Midnight timestamp detection — scoped to known timestamp fields only
# Avoids false positives from free-text fields (e.g., taskSummary, deviations)
midnight_re = re.compile(r'T00:00:00(?:\.0+)?Z?$')

def check_field(value, path):
    if isinstance(value, str) and midnight_re.search(value) and re.match(r'\d{4}-\d{2}-\d{2}T', value):
        errors.append(f'Midnight timestamp at {path}: {value} — use actual system time')

# Root-level timestamps
for field in ['created', 'lastUpdated']:
    if field in state:
        check_field(state[field], field)

# phases.*.startedAt, phases.*.completedAt
if isinstance(state.get('phases'), dict):
    for phase_name, phase_data in state['phases'].items():
        if isinstance(phase_data, dict):
            for ts_field in ['startedAt', 'completedAt']:
                if ts_field in phase_data:
                    check_field(phase_data[ts_field], f'phases.{phase_name}.{ts_field}')

# metrics.optionalSkills.*.completedAt
metrics = state.get('metrics', {})
if isinstance(metrics.get('optionalSkills'), dict):
    for skill_name, skill_data in metrics['optionalSkills'].items():
        if isinstance(skill_data, dict) and 'completedAt' in skill_data:
            check_field(skill_data['completedAt'], f'metrics.optionalSkills.{skill_name}.completedAt')

# 5. Type checks for known fields
type_checks = {
    'feature': str,
    'flow': str,
    'version': str,
    'created': str,
    'lastUpdated': str,
    'currentPhase': str,
    'storiesDone': (int, float),
    'storiesTotal': (int, float),
}
for field, expected_type in type_checks.items():
    if field in state and state[field] is not None:
        if not isinstance(state[field], expected_type):
            type_name = expected_type.__name__ if isinstance(expected_type, type) else 'number'
            errors.append(f'Wrong type for {field}: expected {type_name}, got {type(state[field]).__name__}')

# 6. Flow value validation
if 'flow' in state and state['flow'] not in ('greenfield', 'quick'):
    errors.append(f'Invalid flow value: {state[\"flow\"]} (expected greenfield or quick)')

# 7. Completeness checking — if a phase is marked complete, its expected metrics must exist
# This turns omission detection into involuntary enforcement (catches model forgetting metrics on gate pass)
phases = state.get('phases', {})
metrics_obj = state.get('metrics', {})

for phase_name, phase_data in phases.items():
    if not isinstance(phase_data, dict) or 'completedAt' not in phase_data:
        continue
    # Universal phase-completion metrics
    for required_metric in ['durationMinutes', 'gateAttempts']:
        metrics_phase = metrics_obj.get('phases', {}).get(phase_name, {})
        if required_metric not in phase_data and required_metric not in metrics_phase:
            errors.append(f'Phase {phase_name} is complete but missing {required_metric}')

# Phase-specific completeness (only checked when that phase has completedAt)
phase_specific = {
    'specify': ['personaCount', 'personaConcerns'],
    'architecture': ['deferredDecisions', 'resolvedDecisions'],
    'plan': ['wavesPlanned'],
}
for phase_name, required_fields_list in phase_specific.items():
    phase_data = phases.get(phase_name, {})
    if not isinstance(phase_data, dict) or 'completedAt' not in phase_data:
        continue
    metrics_phase = metrics_obj.get('phases', {}).get(phase_name, {})
    for field in required_fields_list:
        if field not in phase_data and field not in metrics_phase:
            errors.append(f'Phase {phase_name} is complete but missing {field}')

# Gate pass completeness — if any phase is completed, gates.passes should be > 0
completed_phases = [p for p, d in phases.items() if isinstance(d, dict) and 'completedAt' in d]
if completed_phases:
    gates = metrics_obj.get('gates', {})
    if not gates.get('passes'):
        errors.append(f'Phase(s) {\", \".join(completed_phases)} completed but metrics.gates.passes is missing or zero')

# Output results
if errors:
    # Structured JSON deny — uses json.dumps for safe escaping
    summary = '; '.join(errors[:3])
    if len(errors) > 3:
        summary += f' (and {len(errors) - 3} more)'
    reason = '[LaiM] Blocked invalid state.json write: ' + summary
    deny = {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', 'permissionDecisionReason': reason}}
    print(json.dumps(deny))
    # Human-readable stderr
    print('[LaiM] ❌ Invalid state.json write blocked:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    print('Fix the errors above and retry the Write.', file=sys.stderr)
    sys.exit(2)
" 2>/dev/null

# Wire consecutive failure counter to Python exit code
PYTHON_EXIT=$?
if [ "$PYTHON_EXIT" -eq 2 ]; then
  increment_failures
  exit 2
elif [ "$PYTHON_EXIT" -eq 0 ]; then
  reset_failures
  exit 0
fi
# Any other exit code = python3 failed entirely, safe fallback (allow the write)
exit 0
