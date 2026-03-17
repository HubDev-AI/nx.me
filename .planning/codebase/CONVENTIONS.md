# Coding Conventions

**Analysis Date:** 2026-03-17

## Naming Patterns

**Files:**
- Python: `snake_case` for modules and files (`entitlement_service.py`, `credit_ledger.py`)
- TypeScript/React: `camelCase` for component files and utilities, `PascalCase` for React components (`_layout.tsx`, `advisor/index.tsx`)
- Enums and Constants: `SCREAMING_SNAKE_CASE` for constants (`LANE_PREMIUM`, `FAILURE_IDENTITY`, `MIN_AGE_YEARS`)
- Directories: `snake_case` for feature domains (`app/advisor/`, `app/generation/`, `app/image_pipeline/`)

**Functions:**
- Python: `snake_case` functions and methods (`get_entitlement()`, `can_generate()`, `build_context()`)
- TypeScript: `camelCase` for functions and hooks (`getOrCreateGuestToken()`, `getStoredJwt()`)
- Prefix private/internal methods with underscore: `_extract_image_url()`, `_build_user_data()`

**Variables:**
- Python: `snake_case` for all variables and attributes (`user_id`, `credit_balance`, `reservation_id`)
- TypeScript: `camelCase` for variables (`isReady`, `navigationRef`, `jwt`)
- UUID variables explicitly include `_id` suffix when identifiers (`user_id: UUID`, `conversation_id`)

**Types:**
- Python dataclasses: `PascalCase` (`GenerationOptions`, `EntitlementState`, `CreditLedger`)
- Python enums: `PascalCase` class, values are `SCREAMING_SNAKE_CASE` or `camelCase` strings (`class JobStatus(StrEnum): PENDING = "pending"`)
- TypeScript interfaces: `PascalCase` (`UserClaims`, `LLMResponse`)
- Protocol/Port types: Suffix with `Port` for interface contracts (`GlowUpGeneratorPort`, `LLMPort`)

## Code Style

**Formatting:**
- Python: Standard `black`-compatible formatting with 88-character line width (implicit, not configured)
- TypeScript: ESLint + Next.js core rules (see `card-web/.eslintrc.json`)
- Indentation: 4 spaces (Python), 2 spaces (TypeScript/TSX)

**Linting:**
- Python: No explicit linter configured; code follows PEP 8 conventions
- TypeScript: ESLint extended from `next/core-web-vitals` and `next/typescript` presets
- No blanket `eslint-disable` comments allowed; all disables must be justified inline
- Unused imports removed regularly (TypeScript: `noUnusedLocals: true`, `noUnusedParameters: true` in `tsconfig.json`)

**Type Safety:**
- Python: Use `from __future__ import annotations` in all modules (consistent across 62+ files)
- Python: Explicit return type annotations required: `-> int`, `-> None`, `-> dict[str, Any]`
- Python: Use `UUID` type from `uuid` module for all user/entity IDs, not strings
- TypeScript: `strict: true` in `tsconfig.json` (both mobile and card-web)
- TypeScript: `noUncheckedIndexedAccess: true`, `noImplicitReturns: true` for defensive coding

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first in Python)
2. Python standard library (`import logging`, `from datetime import datetime`, `from typing import ...`)
3. Third-party packages (`from fastapi import ...`, `from supabase import Client`, `import redis.asyncio`)
4. Internal app imports (`from app.config import settings`, `from app.entitlement.service import EntitlementService`)
5. (TypeScript) Relative imports after external (`import { useRouter } from "expo-router"`, then `import { getStoredJwt } from "../lib/auth"`)

**Path Aliases:**
- TypeScript: `@/*` → root of project (mobile, card-web) — `import { getStoredJwt } from "@/lib/auth"`
- Python: No aliases; use fully qualified imports relative to `app/` package root

**Avoid Barrel Files:**
- No `__init__.py` re-exports in app code (exception: FastAPI module init files may import routers to register them)
- Direct imports preferred: `from app.advisor.service import AdvisorService` not `from app.advisor import AdvisorService`

## Error Handling

**Pattern — Explicit Exceptions:**
- Raise named, descriptive exceptions: `ValueError()`, `RuntimeError()`, `FileNotFoundError()`
- Include context in exception message: `ValueError(f"Unknown model: {options.model}")`
- Never use bare `raise` to re-raise without context
- Use `raise ... from exc` to chain exceptions and preserve tracebacks: `raise ValueError(str(exc)) from exc`

**Pattern — FastAPI HTTPException:**
- Route handlers raise `HTTPException` with explicit `status_code` and `detail` dict structure
- Error responses have consistent structure: `{ "error": { "code": str, "message": str, "detail": {...} } }`
- Example: `HTTPException(status_code=402, detail={"error": {"code": "TIER_LIMIT_CREDITS", "message": "...", "detail": {...}}})`
- Never return raw exception messages to clients; map to business error codes

**Pattern — Entitlement Checks:**
- Use `EntitlementResult` dataclass with `ok: bool`, `error_code: str` fields (defined in `app/entitlement/models.py`)
- Check entitlement at FastAPI dependency level via `require_entitlement()` or `require_feature()` decorators
- Service layer returns `EntitlementResult`; handler layer translates to HTTP status code

**Pattern — Database Failure Propagation:**
- DB errors (RPC failures, connection errors) propagate as exceptions — no silent fallback
- CS-1 L-1: "RPC failure must propagate as exception" — never swallow or return default value
- Example from `credit_ledger.py`: `self._sb.rpc("sum_credit_balance", {...}).execute()` raises on RPC error

**Pattern — Async Exception Handling:**
- Use standard `try/except` blocks in async functions (no special async syntax needed)
- Catch specific exceptions: `except ValueError`, not bare `except`
- Log exceptions at appropriate level: `logger.error()` for unexpected, `logger.info()` for expected/recoverable

## Logging

**Framework:** Python `logging` module; TypeScript `console.*` methods

**Patterns:**
- Always use `logger = logging.getLogger(__name__)` at module top
- Log at appropriate level: `logger.info()` for state changes, `logger.error()` for failures, `logger.debug()` for detail
- Include structured context in log messages: `logger.info("Credit reserved for user %s: reservation %s", user_id_str, reservation_id)`
- Never log sensitive data (passwords, API keys, PII like biometric data)
- TypeScript: Use `console.warn()` for non-fatal issues, `console.info()` for startup events

## Comments

**When to Comment:**
- Explain the WHY, not the WHAT — the code already shows what it does
- Business logic constraints: "AC-3: Device fingerprint rate limit — ≥3 attempts in 24h → HTTP 429"
- Non-obvious algorithm choices: "Use RPC for atomic SUM to prevent race conditions"
- TODOs with context: `# TODO: AC-5 requires email verification before trial grant (Story 2-1)`
- Security notes: "X-Forwarded-For is attacker-controlled; only trust it if a verified proxy normalizes it"

**JSDoc/TSDoc:**
- Python: Use docstrings for all public functions and classes (triple-quoted)
  - Format: Brief summary, blank line, Args section, Returns section, Raises section
  - Example:
    ```python
    """Get entitlement state for user.

    AC-1: Recompute from credit_ledger + subscriptions, never cached.

    Args:
        user_id: UUID of the user.

    Returns:
        EntitlementState with tier, credits, trial remaining.

    Raises:
        Exception: On Supabase RPC failure.
    """
    ```
- TypeScript: Inline comments for complex logic; no blanket JSDoc expected

**File-Level Comments:**
- Every Python module starts with a docstring explaining its role and key contracts
- Example from `advisor/service.py`: `"""AdvisorService — orchestrates conversations, memories, nudges, and LLM calls."""`
- Reference story IDs and amendment numbers: "Story 4-1", "AC-5", "A-4"

## Function Design

**Size Guidelines:**
- Keep functions under 50 lines of code
- If a function exceeds 50 lines, extract helper functions or break into multiple steps
- Example: `AdvisorService.send_message()` is ~120 lines but broken into sequential 3-4 line steps with clear comments

**Parameters:**
- Limit to 3 positional parameters (fastapi Depends injection doesn't count)
- Use dataclasses for multiple related parameters: `GenerationOptions` instead of 8 separate params
- Keyword-only arguments after positional: `def func(user_id: UUID, *, options: Dict) -> Result`

**Return Values:**
- Always specify return type annotation: `-> None`, `-> int`, `-> EntitlementState`
- Return dataclasses for multiple values, not tuples: return `EntitlementResult(allowed=True, error_code=None)` not `(True, None)`
- For optional returns, be explicit: `-> TierRecord | None` (Python 3.10+ union syntax) or `-> Optional[TierRecord]`

**Async Functions:**
- Mark with `async def` if they call async dependencies
- Use `await` explicitly for all async calls — no fire-and-forget unless intentional background task
- Example: `async def send_message(...) -> dict[str, Any]` calls `await self._memory_manager.get_relevant_memories(...)`

## Module Design

**Exports:**
- Import what you need, export what others should use
- Private/internal code prefixed with `_` (file-level functions, methods)
- Public API clear from type annotations and docstrings

**Layering:**
- Dependency flow: handlers → services → repositories/adapters → models/config
- Services define business logic (entitlement checks, generation orchestration)
- Repositories abstract data access (tier_repo, usage_repo for read-only queries)
- Adapters implement external integrations (stripe_adapter, falai.py, anthropic_adapter.py)
- Example: `app/api/auth.py` → `TrialGrantor` → `CreditLedger` (RPC) → models

**No Circular Dependencies:**
- Adapter pattern enforces loose coupling: services depend on ports (interfaces), adapters implement ports
- Example: `GlowUpGeneratorPort` is a Protocol; `FalAiAdapter` and `MockGeneratorAdapter` implement it

**Configuration:**
- All environment-sensitive values in `app/config.py` (Settings class)
- All per-tier/per-environment values in DB (tiers table) — never hardcoded
- Feature flags via tier.feature_* columns (e.g., `tier.feature_advisor_chat: bool`)
- Runtime constants in module top-level: `_MAX_TOKENS_CHAT = 256`, `_MODEL_SONNET = "claude-3-5-sonnet-20241022"`

## API Contract Patterns

**Port/Protocol Pattern (for Adapters):**
- Define interface as Python Protocol in `ports.py`: `class GlowUpGeneratorPort(Protocol):`
- Implementations in `adapters/` subdir: `FalAiAdapter`, `MockGeneratorAdapter`
- Services receive adapter via constructor: `def __init__(self, generator: GlowUpGeneratorPort)`
- FastAPI dependency layer selects adapter: `get_payment_adapter()` returns Stripe or Mock based on config

**Dependency Injection (FastAPI):**
- All dependencies provided via `Depends()` in route signature
- Example: `async def create_generation(..., supabase: Client = Depends(get_supabase), claims: UserClaims = Depends(get_current_user))`
- No global state; all state attached to `app.state` in lifespan context manager

**Entitlement Checks:**
- Use `require_entitlement("generation")` and `require_feature("advisor_chat")` decorators on routes
- These are FastAPI dependencies that short-circuit with `HTTPException(402)` or `HTTPException(429)`
- Implementation in `app/api/deps.py`

---

*Convention analysis: 2026-03-17*
