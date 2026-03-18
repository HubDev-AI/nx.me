# Sprint 3: API Consistency & Error Handling — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize all error responses to `{"error": {"code": "...", "message": "..."}}`, fix status codes to match REST conventions, type response models, migrate idempotency key to header, and add Retry-After headers.

**Architecture:** Custom exception handler registered on the FastAPI app normalizes all HTTPException and RequestValidationError into a consistent format. A `raise_api_error()` helper replaces inline HTTPException raises. Quick fixes are decorator-level changes.

**Tech Stack:** FastAPI exception handlers, Pydantic models, pytest

**Source spec:** `docs/superpowers/specs/2026-03-17-review-sweep-design.md` (Sprint 3)

---

## Task 1: Unified error handler + custom exceptions (ME-1, QF-7)

**Files:**
- Create: `app/api/errors.py` — error handler, helper, custom exceptions
- Modify: `app/main.py` — register exception handlers
- Modify: `app/advisor/content_filter.py` — replace ValueError with RateLimitExceeded

Create `app/api/errors.py` with:
- `class ApiError(HTTPException)` with `code` and `message` fields
- `class RateLimitExceeded(Exception)` — replaces ValueError("RATE_LIMIT_EXCEEDED")
- `raise_api_error(status_code, code, message)` helper function
- `api_error_handler(request, exc)` — catches ApiError, returns `{"error": {"code": ..., "message": ...}}`
- `http_exception_handler(request, exc)` — catches HTTPException, normalizes detail
- `validation_error_handler(request, exc)` — catches RequestValidationError

Register handlers in `app/main.py`.

Replace `raise ValueError("RATE_LIMIT_EXCEEDED")` in content_filter.py with `raise RateLimitExceeded()`.

## Task 2: Status code fixes (QF-1, QF-2, QF-3, QF-4, QF-6)

**Files:**
- Modify: `app/api/posts.py` — DELETE returns 204, already-deleted returns 409
- Modify: `app/api/entitlement.py` — POST /credits/purchase → 201, POST /subscriptions → 201, remove SubscriptionRequest, split SubscriptionResponse
- Modify: `app/api/generation.py` — POST /cancel → explicit status_code=200
- Modify: `app/api/auth.py` — logout 502 error shape normalization

## Task 3: Response model improvements (ME-2, ME-3)

**Files:**
- Modify: `app/api/entitlement.py` — split SubscriptionResponse into CreateSubscriptionResponse + CancelSubscriptionResponse
- Modify: `app/api/public.py` — type recommendations as list[RecommendationItem]
- Modify: `app/api/users.py` — type HistoryEntry.recommendations

Create a `RecommendationItem` model with actual typed fields (read the analyses output to determine fields).

## Task 4: Idempotency key migration (ME-5)

**Files:**
- Modify: `app/api/generation.py` — accept Idempotency-Key header, keep body field for backward compat

## Task 5: Rate limit improvements (LE-1, LE-5)

**Files:**
- Modify: `app/services/rate_limiter.py` — add LOGIN_IP_LIMIT and LOGIN_IP_WINDOW_SECONDS
- Modify: `app/config/__init__.py` — add new settings
- Modify: all 429 response points — add Retry-After header

## Task 6: Tests + verification
