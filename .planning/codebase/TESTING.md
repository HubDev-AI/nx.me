# Testing Patterns

**Analysis Date:** 2026-03-17

## Test Framework

**Runner:**
- Python: `unittest` standard library (no pytest installed; see `tests/test_credit_ledger_invariants.py`)
- TypeScript: Not yet configured (test strategy defers all automated tests until post-completion)

**Test Configuration:**
- Python location: `tests/` directory at repo root
- Test discovery: `unittest.TestCase` subclasses, methods named `test_*`
- Run command: `python -m unittest discover tests/` or `python -m unittest tests.test_credit_ledger_invariants`
- Environment: Pytest may be globally installed but `.pytest_cache/` exists; use `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest ...` if pytest is run to avoid external plugin import failures

**Assertion Library:**
- Python: `self.assertEqual()`, `self.assertTrue()`, `self.assertRaises()` from unittest
- No external assertion library (e.g., pytest, pytest-assert-rewrite)

## Test File Organization

**Location:**
- Co-located with production code (pattern: `tests/test_credit_ledger_invariants.py` mirrors `app/entitlement/ledger.py`)
- Root-level `tests/` directory at repo root (not `app/tests/` subdirectories)
- Naming: `test_*.py` files

**Naming:**
- Test classes: `TestCreditLedgerInvariants`, `TestCreditLedgerRPCFailure`
- Test methods: `test_invariant_1_reserve_plus_release_equals_zero()`, `test_multiple_reserves_mixed_outcomes()`
- Descriptive names that explain the test's assertion in the name itself

**Structure (example from `tests/test_credit_ledger_invariants.py`):**
```
tests/
├── test_credit_ledger_invariants.py
│   ├── TestCreditLedgerInvariants(unittest.TestCase)
│   │   ├── setUp()
│   │   ├── test_invariant_1_reserve_plus_release_equals_zero()
│   │   └── test_double_commit_raises()
│   ├── TestCreditLedgerRPCFailure(unittest.TestCase)
│   │   └── test_balance_raises_on_rpc_failure()
│   └── Mock classes (_InMemorySupabase, _MockExecuteResult, _FailingSupabase)
```

## Test Structure

**Suite Organization:**
```python
class TestCreditLedgerInvariants(unittest.TestCase):
    """Verify credit ledger reserve/release/commit invariants using production CreditLedger."""

    def setUp(self) -> None:
        """Initialize shared state (mock DB, test fixtures)."""
        self.db = _InMemorySupabase()
        self.ledger = CreditLedger(self.db)  # Production class under test
        self.user_id = uuid4()
        self.db.ledger_rows.append({...})  # Seed initial state

    def test_invariant_1_reserve_plus_release_equals_zero(self):
        """reserve + release = 0 (net balance unchanged)."""
        # Arrange: initial balance
        self.assertEqual(self.ledger.balance(self.user_id), 5)

        # Act: reserve, then release
        rid = self.ledger.reserve(self.user_id)

        # Assert: balance temporarily reduced, then restored
        self.assertEqual(self.ledger.balance(self.user_id), 4)
        self.ledger.release(rid)
        self.assertEqual(self.ledger.balance(self.user_id), 5)
```

**Patterns:**
- `setUp()`: Initialize mocks, fixtures, and system-under-test before each test
- `tearDown()`: Optional cleanup (no cleanup needed in credit ledger tests)
- Arrange-Act-Assert comments: Tests read top-to-bottom with clear phases
- Descriptive assertions: `self.assertEqual(X, Y)` with implicit message from test name
- Skip mechanism: `@unittest.skipUnless(_HAS_SUPABASE, "supabase package not installed")` for optional dependencies

## Mocking

**Framework:** Manual mocks using Python classes (no external mocking library)

**Patterns:**
```python
class _InMemorySupabase:
    """Mock Supabase client that simulates credit ledger RPCs in memory."""

    def __init__(self) -> None:
        self.ledger_rows: list[dict] = []  # Append-only ledger
        self.reservation_rows: list[dict] = []

    def rpc(self, name: str, params: dict) -> "_RpcResult":
        """Simulate Supabase RPC calls."""
        if name == "sum_credit_balance":
            user_id = params["p_user_id"]
            total = sum(r["delta"] for r in self.ledger_rows if r["user_id"] == user_id)
            return _RpcResult(data=total)
        # ... more RPC implementations
        raise Exception(f"Unknown RPC: {name}")
```

**What to Mock:**
- External dependencies: Supabase client, Redis, external APIs (fal.ai, Anthropic, Stripe)
- Infrastructure: database connections, HTTP clients
- Use in-memory mocks (manual classes) that simulate just enough behavior for the test

**What NOT to Mock:**
- Production business logic: Always test the real `CreditLedger.balance()`, `EntitlementService.check()`
- Models and dataclasses: Use real `GenerationOptions`, `EntitlementState`
- Validation logic: Test with real validators, not mocked validation

**Mock Failure Injection:**
```python
class _FailingSupabase:
    """Mock Supabase where all RPCs fail."""

    def rpc(self, name: str, params: dict) -> "_FailingRpc":
        return _FailingRpc()

class _FailingRpc:
    def execute(self):
        raise ConnectionError("Supabase RPC unavailable")

# Test: exception propagates, no fallback
def test_balance_raises_on_rpc_failure(self):
    db = _FailingSupabase()
    ledger = CreditLedger(db)
    with self.assertRaises(Exception):
        ledger.balance(uuid4())
```

## Fixtures and Factories

**Test Data:**
- Manual setup in `setUp()` method: `self.user_id = uuid4()`, seed ledger rows
- No external fixture files (no conftest.py, no YAML/JSON test data)
- Inline data creation: `self.db.ledger_rows.append({"user_id": str(self.user_id), "delta": 5, "type": "purchase"})`

**Factories:**
- Not used (test scope is small; manual setup is clearer)
- If tests proliferate, consider factory helper methods in TestCase subclass:
  ```python
  def _create_ledger_entry(self, user_id: UUID, delta: int) -> dict:
      return {"user_id": str(user_id), "delta": delta, ...}
  ```

**Location:**
- Fixtures defined in test file itself (no shared `fixtures.py`)
- Mock classes placed above test classes in same file: `_InMemorySupabase`, `_FailingSupabase`

## Coverage

**Requirements:** Not enforced (docs/test-strategy.md: "Zero automated tests during development")

**Current Status:**
- One test module: `tests/test_credit_ledger_invariants.py` (AC-3 verification)
- After project completion: E2E tests via Playwright; unit/integration deferred
- Manual acceptance testing on staging environment (331 test cases in `docs/test-cases.md`)

**View Coverage (once implemented):**
```bash
# Not currently used, but would be:
coverage run -m unittest discover tests/
coverage report
coverage html  # Generate htmlcov/index.html
```

## Test Types

**Unit Tests:**
- Scope: Single class in isolation (e.g., `CreditLedger`)
- Mock all external dependencies (Supabase client)
- Test business logic invariants
- Example: `test_invariant_1_reserve_plus_release_equals_zero()` tests `CreditLedger.balance()`, `reserve()`, `release()`

**Integration Tests:**
- Scope: Multiple layers working together (service + repository + DB)
- Not written during development (deferred per test-strategy.md)
- Would test: `EntitlementService.check()` with real tier data + mock Supabase
- Would verify: Cross-cutting concerns (rate limiting, audit trails, tier transitions)

**E2E Tests (Post-Completion):**
- Framework: Playwright (not yet configured)
- Scope: Full request-response cycle via HTTP
- Example: POST /auth/register → verify user created, trial granted, email verification required
- ~30 critical flows covering all story acceptance criteria
- Will use real staging API (test mode for Stripe, mock adapters for fal.ai/Anthropic)

## Common Patterns

**Async Testing (if needed):**
- Python unittest doesn't have built-in async support
- Use `unittest.IsolatedAsyncioTestCase` (Python 3.8+):
  ```python
  class TestAdvisorService(unittest.IsolatedAsyncioTestCase):
      async def test_send_message(self):
          service = AdvisorService(mock_supabase, mock_redis, mock_llm)
          result = await service.send_message(user_id, "Hello")
          self.assertIn("response", result)
  ```
- Not yet in use (no async tests in codebase)

**Error Testing:**
```python
def test_double_release_raises(self):
    """Releasing the same reservation twice raises ValueError."""
    rid = self.ledger.reserve(self.user_id)
    self.ledger.release(rid)

    with self.assertRaises(ValueError):
        self.ledger.release(rid)
```

**Invariant Testing (AC-3 Pattern):**
```python
def test_multiple_reserves_mixed_outcomes(self):
    """3 reserves: 2 committed, 1 released -> balance reduced by 2."""
    # Arrange: start with 5 credits
    self.assertEqual(self.ledger.balance(self.user_id), 5)

    # Act: reserve 3 times
    r1 = self.ledger.reserve(self.user_id)
    r2 = self.ledger.reserve(self.user_id)
    r3 = self.ledger.reserve(self.user_id)
    self.assertEqual(self.ledger.balance(self.user_id), 2)

    # Act: commit 2, release 1
    self.ledger.commit(r1)
    self.ledger.commit(r2)
    self.ledger.release(r3)

    # Assert: final balance reflects 2 commits (2 credits spent)
    self.assertEqual(self.ledger.balance(self.user_id), 3)
```

## Test Integrity Rules

**No Test Disabling:**
- Per test-integrity.md: Never use `@unittest.skip()` or `@Disabled` without a tracking reference
- If a test fails, fix the code or the test — do not disable it
- Exception: `@unittest.skipUnless(_HAS_SUPABASE, "supabase not installed")` is allowed (infrastructure availability, not test failure)

**Tests Exercise Real Code:**
- All tests import production code: `from app.entitlement.ledger import CreditLedger`
- Tests instantiate and call real `CreditLedger()` methods
- Mocks replace only external dependencies (Supabase), not production business logic
- Verify: Tests fail if production code has bugs (no false negatives)

**Error Propagation:**
- CS-1 L-1: "RPC failure must propagate as exception" — tests verify this
- `TestCreditLedgerRPCFailure.test_balance_raises_on_rpc_failure()` confirms exceptions are not swallowed
- No fallback/retry patterns that hide errors

## Test Organization Summary

**Current Test Coverage:**
- `tests/test_credit_ledger_invariants.py`: 9 unit tests covering reserve/release/commit lifecycle
- Validates AC-3 (credit ledger invariants)
- Mock-based: `_InMemorySupabase` simulates Supabase RPC behavior

**Future Testing:**
- After all 30 stories: Manual acceptance (331 test cases)
- After manual validation: E2E automation (Playwright, ~30 flows)
- Never: Unit test framework during development (zero during coding)

**Running Tests:**
```bash
# Run all tests
python -m unittest discover tests/

# Run specific test class
python -m unittest tests.test_credit_ledger_invariants.TestCreditLedgerInvariants

# Run specific test
python -m unittest tests.test_credit_ledger_invariants.TestCreditLedgerInvariants.test_invariant_1_reserve_plus_release_equals_zero
```

---

*Testing analysis: 2026-03-17*
