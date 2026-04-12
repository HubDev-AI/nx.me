# Goal: Code Health

Raise the NXME.ai codebase from ad-hoc early-stage development to a maintainable foundation. Composite score covering backend test coverage, lint cleanliness (backend + mobile), and test pass rate.

## Fitness Function

```bash
# Run this to get the current score:
bash scripts/score.sh
```

### Metric Definition

```
score = backend_coverage + backend_lint + mobile_lint + test_pass_rate
```

| Component | What it measures | Max pts |
|-----------|------------------|---------|
| **backend_coverage** | pytest line coverage of `app/` (raw % / 2) | 50 |
| **backend_lint** | ruff check cleanliness (15 - issues * 3) | 15 |
| **mobile_lint** | ESLint errors & warnings (15 - errors * 3 - warnings * 0.5) | 15 |
| **test_pass_rate** | Fraction of tests passing (passed / total * 20) | 20 |

### Metric Mutability

- [x] **Split** — Agent can improve the instrument (add tests, fix lint) but not the outcome definition (the formula and max values above are fixed)

## Operating Mode

- [x] **Supervised** — Pause at gates for approval

### Stopping Conditions

Stop and report when ANY of:
- Score >= 80
- 15 iterations completed
- Backend coverage >= 60% AND all tests pass AND zero lint errors
- Bootstrap environment becomes unavailable (venv broken, node_modules missing)

## Bootstrap

1. `make up` (or verify `.venv` and `app/.env` exist)
2. `cd mobile && npm install` (ensure node_modules exist)
3. `bash scripts/score.sh` — expect ~36

Starting score: **36**

## Improvement Loop

```
repeat:
  0. Read iterations.jsonl if it exists — note what's been tried and what worked
  1. bash scripts/score.sh > /tmp/before.json
  2. Read scores and component breakdowns
  3. Pick highest-impact action from Action Catalog (coverage > lint > tests)
  4. Make the change
  5. Run targeted verification (pytest for tests, ruff for backend lint, expo lint for mobile)
  6. bash scripts/score.sh > /tmp/after.json
  7. Compare: if improved without regression, commit
  8. If regressed or unchanged, revert
  9. Append to iterations.jsonl: before/after scores, action taken, result, one-sentence note
  10. Continue
```

Commit messages: `[S:NN→NN] component: what you did`

## Iteration Log

File: `iterations.jsonl` (append-only, one JSON object per line)

```jsonl
{"iteration":1,"before":36,"after":42,"action":"Fix 4 failing tests","result":"kept","note":"test_pass_rate 19→20, also fixed coverage collection"}
```

## Action Catalog

### Backend Coverage (target: 40+ pts, currently 8)

This is the biggest lever — 42 pts available. Each new test file covering an API module adds ~2-5 pts.

| Action | Impact | How |
|--------|--------|-----|
| Fix 4 failing tests | +1 pt (test_pass_rate) | Read failures, fix assertions in test_config, test_register_models, test_social |
| Add tests for `app/api/health.py` | +1 pt | Smallest module (57 lines, 2 functions). Test GET /health endpoint |
| Add tests for `app/api/blocks.py` | +2 pts | 134 lines, 3 functions. Test block/unblock/list endpoints |
| Add tests for `app/api/analyses.py` | +2 pts | 210 lines, 2 functions. Test analysis create/retrieve |
| Add tests for `app/api/admin.py` | +2 pts | 226 lines, 7 functions. Test admin CRUD operations |
| Add tests for `app/api/webhooks.py` | +2 pts | 261 lines, 6 functions. Test webhook handlers |
| Add tests for `app/api/entitlement.py` | +3 pts | 279 lines, 6 functions. Test tier/entitlement checks |
| Add tests for `app/api/deps.py` | +3 pts | 339 lines, 25 functions. Test dependency injection functions |
| Add tests for `app/api/generation.py` | +5 pts | 706 lines, 9 functions. Test generation workflow |
| Add tests for `app/api/auth.py` | +8 pts | 1220 lines, 15 functions. The largest module — auth flows, token refresh, rate limiting |
| Add tests for `app/services/` | +5 pts | Service layer coverage (whatever exists) |
| Add tests for `app/repositories/` | +3 pts | Data access layer coverage |

### Backend Lint (target: 15 pts, currently 9)

2 ruff errors to fix — each is worth 3 pts.

| Action | Impact | How |
|--------|--------|-----|
| Remove unused import `fastapi.status` in `app/api/middleware/auth.py` | +3 pts | Delete unused import at line 27 |
| Remove unused variable `username_changed` in `app/api/users.py` | +3 pts | Remove assignment at line 418 or use the variable |

### Mobile Lint (target: 10+ pts, currently 0)

2 errors and 51 warnings. Errors are worth 3 pts each, every 2 warnings is worth 1 pt.

| Action | Impact | How |
|--------|--------|-----|
| Fix 2 ESLint errors (likely unused imports or syntax) | +6 pts | Find and fix the 2 error-level issues |
| Fix unused variable warnings (`@typescript-eslint/no-unused-vars`) | +2 pts | Remove ~4 unused vars in GlowButton, HeroBackground, PageBackground |
| Fix import ordering warnings (`import/first`) | +2 pts | Move imports to top of file in RadialMenu and one other file |
| Fix `react-hooks/exhaustive-deps` warnings | +5 pts | Add missing deps or wrap in useCallback/useMemo — ~8 warnings across FloatingParticles, GlowButton, ShimmerLogo |
| Run `npx expo lint --fix` for auto-fixable warnings | +3 pts | Auto-fix the 16 fixable warnings reported by ESLint |

### Test Pass Rate (target: 20 pts, currently 19)

4 failing tests.

| Action | Impact | How |
|--------|--------|-----|
| Fix `test_registration_ip_limit` in test_config.py | +0.25 pts | Read the test, fix the assertion |
| Fix `test_register_response_model` in test_register_models.py | +0.25 pts | Schema likely changed — update expected fields |
| Fix 2 failures in test_social.py | +0.5 pts | Feed model and guest token tests — likely model schema drift |

## Constraints

1. **No new production dependencies** — tests can add dev dependencies only (in requirements-dev.txt or package.json devDependencies)
2. **Do not modify scoring script** — scripts/score.sh defines truth; game the score by improving code, not the metric
3. **Tests must use real code, not mocks** — per project convention, no mocking the database; test against real modules
4. **Never disable or skip tests** — per test-integrity.md rules; fix failures, don't suppress them
5. **Do not modify API behavior** — test the existing code; don't change production logic to make tests pass
6. **Feature branch + PR workflow** — never push directly to dev; always feature branch → PR → merge
7. **Run full verification before commit** — `make format && make lint && make test && cd mobile && npx expo lint`
8. **Keep iterations atomic** — one logical change per iteration; revert the whole thing if score drops

## File Map

| File | Role | Editable? |
|------|------|-----------|
| `GOAL.md` | This file — goal definition | No |
| `scripts/score.sh` | Fitness function | No |
| `iterations.jsonl` | Iteration log | Append-only |
| `tests/` | Backend test files | Yes |
| `tests/conftest.py` | Test fixtures | Yes |
| `app/api/*.py` | Backend API modules | Yes (lint fixes only) |
| `app/services/*.py` | Backend services | Yes (lint fixes only) |
| `mobile/components/**/*.tsx` | Mobile components | Yes (lint fixes only) |
| `mobile/hooks/*.ts` | Mobile hooks | Yes (lint fixes only) |
| `mobile/app/**/*.tsx` | Mobile screens | Yes (lint fixes only) |
| `requirements-dev.txt` | Dev dependencies | Yes |

## When to Stop

```
Starting score: 36
Ending score:   NN
Iterations:     N
Changes made:   (list)
Remaining gaps: (list)
Next actions:   (what a human or future agent should do next)
```
