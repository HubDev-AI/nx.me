# API Design Review

- Date: 2026-03-17
- Scope: app/api/*.py
- Reviewer: API Designer (Claude)
- Branch: feature/story-2-2-auth-social-login

---

## Endpoint Inventory

| Method   | Path                                    | File            | Auth               | Success Codes | Router Prefix       |
|----------|-----------------------------------------|-----------------|--------------------|---------------|---------------------|
| POST     | /v1/auth/register                       | auth.py         | None               | 201           | /v1/auth            |
| POST     | /v1/auth/verify-email                   | auth.py         | JWT                | 200           | /v1/auth            |
| POST     | /v1/auth/login                          | auth.py         | None               | 200           | /v1/auth            |
| POST     | /v1/auth/logout                         | auth.py         | JWT                | 204           | /v1/auth            |
| DELETE   | /v1/auth/account                        | auth.py         | JWT                | 204           | /v1/auth            |
| POST     | /v1/analyses                            | analyses.py     | JWT                | 201           | /v1                 |
| GET      | /v1/analyses/{analysis_id}              | analyses.py     | JWT                | 200           | /v1                 |
| POST     | /v1/analyses/{analysis_id}/generate     | generation.py   | JWT                | 202           | /v1                 |
| GET      | /v1/jobs/{job_id}                       | generation.py   | JWT                | 200           | /v1                 |
| POST     | /v1/jobs/{job_id}/cancel                | generation.py   | JWT                | 200           | /v1                 |
| GET      | /v1/entitlement                         | entitlement.py  | JWT                | 200           | /v1                 |
| POST     | /v1/credits/purchase                    | entitlement.py  | JWT                | 200           | /v1                 |
| POST     | /v1/subscriptions                       | entitlement.py  | JWT                | 200           | /v1                 |
| DELETE   | /v1/subscriptions                       | entitlement.py  | JWT                | 200           | /v1                 |
| GET      | /v1/feed                                | social.py       | None               | 200           | /v1                 |
| POST     | /v1/posts/{post_id}/react               | social.py       | JWT or Guest Token | 200           | /v1                 |
| POST     | /v1/posts                               | posts.py        | JWT                | 201           | /v1                 |
| DELETE   | /v1/posts/{post_id}                     | posts.py        | JWT                | 200           | /v1                 |
| POST     | /v1/posts/{post_id}/comments            | posts.py        | JWT                | 201           | /v1                 |
| GET      | /v1/posts/{post_id}/comments            | posts.py        | None               | 200           | /v1                 |
| POST     | /v1/posts/{post_id}/report              | posts.py        | JWT                | 201           | /v1                 |
| GET      | /api/public/cards/{username}            | public.py       | None               | 200           | /api                |
| GET      | /v1/users/{username}/profile            | users.py        | None               | 200           | /v1                 |
| GET      | /v1/users/{username}/history            | users.py        | JWT                | 200           | /v1                 |
| PATCH    | /v1/users/{username}                    | users.py        | JWT                | 200           | /v1                 |
| POST     | /webhooks/stripe                        | webhooks.py     | Stripe Signature   | 200           | / (unversioned)     |
| POST     | /v1/advisor/messages                    | advisor.py      | JWT + feature flag | 201           | /v1                 |
| GET      | /v1/advisor/messages                    | advisor.py      | JWT                | 200           | /v1                 |
| GET      | /v1/advisor/nudges                      | advisor.py      | JWT                | 200           | /v1                 |
| POST     | /v1/advisor/nudges/{nudge_id}/read      | advisor.py      | JWT                | 204           | /v1                 |
| POST     | /v1/memories                            | advisor.py      | JWT                | 201           | /v1                 |
| GET      | /v1/memories                            | advisor.py      | JWT                | 200           | /v1                 |
| DELETE   | /v1/memories/{memory_id}                | advisor.py      | JWT                | 204           | /v1                 |

---

## Findings

### 1. Naming Conventions

**Good practices observed:**

- Collections use plural nouns: `/analyses`, `/posts`, `/jobs`, `/memories`, `/subscriptions`, `/credits`.
- Sub-resources are correctly nested: `/posts/{id}/comments`, `/posts/{id}/report`, `/analyses/{id}/generate`, `/jobs/{id}/cancel`.
- Username-scoped resources follow a consistent pattern: `/users/{username}/profile`, `/users/{username}/history`.

**Issues found:**

**F-N1 (Moderate) — Verb in path: `/posts/{id}/react`**

`react` is a verb. REST convention requires a noun representing the resource being created. The correct form is `/posts/{id}/reactions`, using `POST` to create a reaction. This also better supports a future `DELETE /posts/{id}/reactions` for unreacting.

```
Current:  POST /v1/posts/{post_id}/react
Correct:  POST /v1/posts/{post_id}/reactions
```

**F-N2 (Moderate) — Verb in path: `/advisor/nudges/{id}/read`**

`read` is a verb embedded in the path. The state transition (marking a nudge read) should be modeled as a `PATCH` on the nudge resource, or as a `POST` to a noun sub-resource. Two idiomatic alternatives:

```
Option A (preferred — PATCH semantics):
  PATCH /v1/advisor/nudges/{nudge_id}   body: {"read_at": "<iso-timestamp>"}

Option B (action-as-sub-resource):
  POST  /v1/advisor/nudges/{nudge_id}/acknowledgements
```

**F-N3 (Minor) — `/jobs/{job_id}/cancel` uses a verb**

Cancel is an action on the job resource. While action sub-resources are an accepted REST idiom for state transitions that have no better noun mapping (e.g., GitHub's `/repos/{owner}/{repo}/actions/cancel`), this is worth flagging. If a `status` field already exists on the job, a `PATCH /jobs/{job_id}` with `{"status": "cancelled"}` is more consistent with how `DELETE /posts/{post_id}` drives state (soft delete). However, cancellation has unique side effects (credit release) that justify treating it as an action endpoint. This finding is a minor note, not a defect.

**F-N4 (Minor) — `entitlement` is singular, not plural**

`GET /v1/entitlement` returns a singular resource scoped to the authenticated user — this is correct. Singleton resources (user settings, current user's entitlement) are appropriately singular. No change required; this is a documentation clarification.

**F-N5 (Minor) — `credits/purchase` contains a verb**

`POST /v1/credits/purchase` creates a checkout session to purchase credits. The noun form would be `POST /v1/credit-purchases` or `POST /v1/checkout-sessions`. The current path mixes the resource (`credits`) with the action (`purchase`). This is a design inconsistency given that `POST /v1/subscriptions` uses a clean noun.

```
Current:  POST /v1/credits/purchase
Cleaner:  POST /v1/credit-purchases       (creates a checkout session)
```

**F-N6 (Minor) — Mixed prefix for public endpoint**

`GET /api/public/cards/{username}` uses the `/api` prefix while all other endpoints use `/v1`. This is intentional (public.py comment: "no auth, no versioning, under /api prefix") but creates an inconsistent surface. A fully versioned alternative — `/v1/public/cards/{username}` or `/v1/cards/{username}` — would keep all API paths under a single prefix. If the intent is permanent stability (no versioning needed), this should be documented explicitly as a deliberate design exception.

---

### 2. HTTP Status Codes

**Good practices observed:**

- `POST /analyses` and `POST /posts` return 201.
- `POST /analyses/{id}/generate` returns 202 (async job enqueue).
- `DELETE /auth/account` and `POST /auth/logout` return 204.
- `POST /advisor/nudges/{id}/read` and `DELETE /memories/{id}` return 204.
- 410 Gone is used correctly in `public.py` for deleted accounts.
- 502 Bad Gateway is used for upstream Supabase/Stripe failures.
- 503 Service Unavailable is used for emergency stop and queue depth limits.

**Issues found:**

**F-SC1 (Moderate) — `DELETE /posts/{post_id}` returns 200 instead of 204**

A successful deletion with no response body should return 204. The endpoint currently returns 200 with a JSON body `{"status": "deleted"}` or `{"status": "already_deleted"}`. The "already deleted" case is also wrong — it should return 409 Conflict, not 200.

```python
# posts.py line 177
@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)  # should be 204
```

For the already-deleted case: 200 with a `"status": "already_deleted"` body silently swallows what is semantically a conflict. 409 with a structured error body is the correct response, consistent with how `DELETE /auth/account` handles the same scenario (line 595 in auth.py).

**F-SC2 (Moderate) — `POST /v1/credits/purchase` returns 200 instead of 201**

The endpoint creates a checkout session (a resource). It should return 201 Created. Same issue applies to `POST /v1/subscriptions` when it creates a checkout session.

**F-SC3 (Minor) — `DELETE /subscriptions` returns 200 with a body**

Cancellation at period end is a state mutation confirmed by Stripe, not an immediate deletion. Returning 200 with a body is acceptable here (unlike a true delete). However, the response model has three optional fields (`checkout_url`, `status`, `message`) and only two are populated. The response model is shared with `POST /subscriptions`, which causes ambiguity. These two operations should have distinct response models.

**F-SC4 (Minor) — `POST /auth/login` returns 200 instead of 201**

A successful social login that creates a new user is a resource creation. First-time logins (upsert path) could reasonably return 201 to signal creation vs. 200 for returning users. The current single-status 200 is acceptable as a pragmatic choice for an auth endpoint but is worth noting.

**F-SC5 (Minor) — `POST /v1/jobs/{job_id}/cancel` returns 200 with no `status_code` annotation**

The `@router.post` decorator has no explicit `status_code`. FastAPI defaults to 200, which is correct here since the response carries a body. However, the missing annotation reduces explicitness and OpenAPI documentation quality. All endpoints should declare their `status_code` explicitly.

---

### 3. Error Response Format

**Good practices observed:**

Several endpoints use a structured error body format:
```json
{
  "error": {
    "code": "CONCURRENT_LIMIT",
    "message": "You already have a generation in progress."
  }
}
```

This is a good pattern — machine-readable `code` plus a human `message`.

**Issues found:**

**F-E1 (Significant) — Inconsistent error format across endpoints**

The codebase uses at least three distinct error formats:

Format A — Raw string (used in most endpoints):
```json
"Analysis not found"
```

Format B — Structured with nested `error` object (generation.py, entitlement.py, advisor.py, webhooks.py):
```json
{"error": {"code": "CONCURRENT_LIMIT", "message": "..."}}
```

Format C — Structured with `detail` containing nested dict (auth.py logout):
```json
{"error": {"code": "REVOCATION_FAILED", "message": "..."}}
```

FastAPI's `HTTPException` wraps the `detail` under a `"detail"` key in the response body, so clients receive:
```json
{"detail": "Analysis not found"}
{"detail": {"error": {"code": "...", "message": "..."}}}
```

This means clients must handle two completely different response shapes for errors. A consistent format should be adopted globally and enforced via a custom exception handler or a base error model.

Recommendation — adopt Format B uniformly:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Analysis not found"
  }
}
```

Apply this via a FastAPI exception handler that normalises all `HTTPException` responses, or via a `raise_api_error()` helper that always uses the structured form.

**F-E2 (Moderate) — Missing error codes on plain string errors**

Endpoints in `analyses.py`, `posts.py`, `social.py`, and `users.py` raise `HTTPException` with plain string `detail` values (e.g., `"Post not found"`, `"Not authorized"`). These provide no machine-readable code for clients to act on programmatically. Every error response should carry a `code` string.

**F-E3 (Minor) — Validation errors (422) from Pydantic are not in the structured format**

FastAPI's default `RequestValidationError` handler returns:
```json
{"detail": [{"loc": ["body", "field"], "msg": "...", "type": "..."}]}
```

This is a different shape from the application-level errors. A custom handler should normalise validation errors to match the project's error format.

---

### 4. Pagination

**Good practices observed:**

- Cursor-based pagination is used consistently across all paginated endpoints: `GET /v1/feed`, `GET /v1/posts/{id}/comments`, `GET /v1/users/{username}/history`.
- `has_more` + `next_cursor` envelope is consistent across all three paginated responses.
- The "fetch limit+1 to determine has_more" pattern is correctly applied in all three implementations.
- Composite cursors for multi-sort ordering (trending: `score|created_at|id`) are well-designed and prevent page drift.

**Issues found:**

**F-P1 (Moderate) — Cursor collision risk in timestamp-only cursors**

`GET /v1/posts/{id}/comments` and `GET /v1/users/{username}/history` use a single `created_at` ISO timestamp as the cursor. If two records share the same `created_at` timestamp (possible in high-throughput inserts), the cursor will skip or repeat records. The trending and biggest_improvements strategies correctly use composite cursors (`value|created_at|id`) to avoid this. The same `created_at|id` composite should be applied to the comments and history endpoints.

**F-P2 (Minor) — `GET /v1/advisor/messages` has no pagination**

The conversation history endpoint returns all messages with no limit or cursor. A long conversation context could result in large payloads. A `limit` + cursor parameter should be added consistent with the other list endpoints.

**F-P3 (Minor) — `GET /v1/advisor/nudges` has no pagination**

The nudge feed returns all nudges. Same concern as F-P2.

**F-P4 (Minor) — `GET /v1/memories` has no pagination**

The memory list returns all memories. Same concern.

**F-P5 (Minor) — Default page sizes differ between endpoints**

- `GET /v1/feed`: default 10, max 50
- `GET /v1/posts/{id}/comments`: default 20, max 100
- `GET /v1/users/{username}/history`: default 20, max 100

The variance in limits is reasonable given different use cases. However, the max limit of 100 for comments and history is notably higher than the feed's 50. This should be a deliberate documented decision rather than an undocumented accident.

---

### 5. Request / Response Model Design

**Good practices observed:**

- Request models use Pydantic `Field` with `min_length`, `max_length`, and `pattern` validation: `RegisterRequest`, `CreateCommentRequest`, `CreatePostRequest`.
- Response models are purpose-specific (not raw DB row pass-through).
- `AnalysisDetailResponse` extends `AnalysisResponse` via inheritance — avoids duplication.

**Issues found:**

**F-M1 (Moderate) — `SubscriptionRequest` is an empty model**

`class SubscriptionRequest(BaseModel): pass` on entitlement.py line 189 is vestigial. Either it needs fields or it should be removed entirely (the endpoint takes no body). An empty body should use no body parameter at all, or at minimum a comment explaining why the model is kept for future extensibility.

**F-M2 (Moderate) — `SubscriptionResponse` is overloaded across two operations**

`POST /v1/subscriptions` and `DELETE /v1/subscriptions` both return `SubscriptionResponse`, which has three optional fields: `checkout_url`, `status`, `message`. In practice, the create path populates `checkout_url` and the delete path populates `status` + `message`. These are semantically different resources and should have separate models:

```python
class CreateSubscriptionResponse(BaseModel):
    checkout_url: str

class CancelSubscriptionResponse(BaseModel):
    status: str
    message: str
```

**F-M3 (Moderate) — `recommendations` typed as `list[dict]` in public-facing responses**

`CardResponse.recommendations` and `HistoryEntry.recommendations` are typed `list[dict]`. This means the OpenAPI schema generates `array of object` with no structure. Clients cannot know what fields to expect. A typed `RecommendationItem` model should be used.

**F-M4 (Minor) — `MemoryResponse.content` is typed as `dict` with no schema**

`content: dict` in `MemoryResponse` provides no structure contract. Given that memories have distinct types (`goal`, `user_note`), this should either be a typed union or at minimum documented with an `example`.

**F-M5 (Minor) — Inconsistent ID field naming**

Response models use different naming for ID fields:
- `analysis_id` (AnalysisResponse)
- `post_id` (PostResponse, FeedPostResponse)
- `comment_id` (CommentResponse)
- `report_id` (ReportResponse)
- `job_id` (GenerateResponse, JobStatusResponse)
- `id` (MessageResponse, MemoryResponse, NudgeResponse)

The convention should be uniform. Preferred REST convention is to use `id` in the resource's own representation and only use `{resource}_id` when it is a foreign key reference within another resource's representation.

**F-M6 (Minor) — `UpdateProfileRequest` accepts `avatar_storage_key` as a client input**

`PATCH /v1/users/{username}` accepts `avatar_storage_key` directly from the client. This means a client could point the avatar at an arbitrary storage key they do not own. The upload and storage key assignment should be handled server-side via a dedicated avatar upload endpoint, with the key never being a writable field from the client.

---

### 6. Versioning

**Good practices observed:**

- All application endpoints are mounted under `/v1` via a single `APIRouter(prefix="/v1")` in `main.py`.
- The versioning prefix is applied consistently to all in-product endpoints.
- Webhooks and health checks are intentionally unversioned, which is correct.

**Issues found:**

**F-V1 (Moderate) — `/api/public/cards/{username}` is outside the `/v1` prefix**

The public shareable card endpoint is registered under `/api` (not `/v1`), making it the only non-webhook, non-health endpoint outside the version namespace. This creates two URL spaces for application endpoints:

- `/v1/...` — all standard endpoints
- `/api/public/...` — this single public endpoint

If a v2 of the card format is ever needed, there is no established versioning path (`/api/v2/public/cards/{username}` would be awkward). Moving it to `/v1/public/cards/{username}` is the cleanest fix and introduces no breaking change if it has not been publicly documented yet.

**F-V2 (Minor) — No `Deprecated` markers or sunset headers**

No endpoints currently carry deprecation signals in their OpenAPI metadata (`deprecated=True`) or `Sunset` response headers. As the API matures, the infrastructure to signal deprecation should be established before it is needed.

---

### 7. Rate Limiting

**Good practices observed:**

- Per-IP rate limiting on registration (≥4/hour) and login.
- Per-device-fingerprint rate limiting on registration (≥3/24h).
- Reaction rate limiting (10 per IP per 5 minutes) with Redis.
- Advisor message rate limiting (mentioned in docstring, enforced in service layer).
- All rate limit violations return 429.

**Issues found:**

**F-R1 (Moderate) — Rate limit headers absent from 429 responses**

None of the 429 responses include `Retry-After` or `X-RateLimit-*` headers. RFC 6585 recommends `Retry-After` on 429 responses. Clients have no machine-readable signal for when to retry. The `retry_after` field exists on entitlement error responses (as a JSON body field) but is not present in HTTP headers, which is where HTTP clients and SDKs look for it.

**F-R2 (Moderate) — Reaction rate limit state inconsistency**

In `social.py`, the rate limit check occurs before the Redis INCR, but the rate limit counter increment (`pipe.incr(rate_key)`) happens after the INCR. Between the check and the counter increment, a concurrent request can slip through. The check and counter increment should be atomic, e.g., using a Lua script or a single atomic check-and-increment pattern.

**F-R3 (Minor) — No rate limiting on `GET /v1/feed`, `GET /v1/posts/{id}/comments`, `GET /api/public/cards/{username}`**

Public read endpoints have no rate limiting. These are the highest-traffic endpoints (no auth barrier) and are most susceptible to scraping and abuse. An IP-based limit should be applied.

---

### 8. Idempotency

**Good practices observed:**

- `POST /v1/analyses/{id}/generate` accepts an `idempotency_key` in the request body and returns the existing job if a matching key is found. This is the correct pattern.
- `POST /v1/auth/verify-email` is documented as idempotent (TrialGrantor.grant is idempotent).
- `POST /webhooks/stripe` uses a `processed_webhook_events` deduplication table — correct.
- `POST /v1/advisor/nudges/{id}/read` is documented as idempotent.
- `DELETE /v1/memories/{id}` returns 404 on repeat (not idempotent in the HTTP sense).

**Issues found:**

**F-I1 (Moderate) — `idempotency_key` is in the request body, not a header**

The `idempotency_key` field in `GenerateRequest` lives in the JSON body. The standard practice (used by Stripe, PayPal, Adyen) is to send idempotency keys as a request header (`Idempotency-Key`). This separates business payload from retry semantics and allows middleware/proxies to handle idempotency transparently.

```
Current:  POST /v1/analyses/{id}/generate  body: {"idempotency_key": "..."}
Standard: POST /v1/analyses/{id}/generate  header: Idempotency-Key: <uuid>
```

**F-I2 (Minor) — `DELETE /v1/memories/{id}` returns 404 on second call**

HTTP DELETE is specified as idempotent: a second call to delete the same resource should return 204 (or 200), not 404. The 404 on repeat is technically correct from a "resource not found" perspective but breaks idempotency guarantees. A client retrying a delete after a timeout will receive 404 and cannot distinguish "deletion succeeded (retried)" from "wrong ID". This should return 204 on subsequent deletes of the same resource.

**F-I3 (Minor) — No idempotency support on `POST /v1/posts`**

Creating a post from a job is a non-idempotent operation. If the client retries after a network failure, a duplicate post could be created from the same `glow_up_job_id`. An idempotency check on `glow_up_job_id` (unique constraint: one post per job) would prevent this. The DB likely has this constraint, but the API should return the existing post (200) on a duplicate attempt rather than 409 Conflict.

---

### 9. HATEOAS / Self-Describing Responses

**Overall assessment:** HATEOAS is not implemented. This is a common pragmatic choice for mobile-first APIs and is not necessarily a defect given the project context. However, several specific gaps reduce discoverability:

**F-H1 (Minor) — Job polling requires out-of-band knowledge of the poll URL**

`POST /v1/analyses/{id}/generate` returns a `job_id` but no `href` or `status_url` pointing to `GET /v1/jobs/{job_id}`. Clients must construct this URL themselves. Adding a `status_url` field to `GenerateResponse` eliminates this coupling:

```json
{
  "job_id": "...",
  "status": "queued",
  "status_url": "/v1/jobs/...",
  "estimated_wait_seconds": 30
}
```

**F-H2 (Minor) — No `Location` header on 201 responses**

REST convention: `POST` endpoints that return 201 should include a `Location` header pointing to the newly created resource. This applies to:
- `POST /v1/analyses` → `Location: /v1/analyses/{id}`
- `POST /v1/posts` → `Location: /v1/posts/{id}`
- `POST /v1/advisor/messages` → `Location: /v1/advisor/messages/{id}` (if individual message retrieval is supported)

---

### 10. Query Parameter Conventions

**Good practices observed:**

- `sort` uses descriptive enum values (`newest`, `trending`, `biggest_improvements`).
- `cursor` and `limit` are named consistently across all paginated endpoints.
- `limit` has consistent validation (`ge=1`, `le=N`).

**Issues found:**

**F-Q1 (Minor) — No `sort` parameter on `GET /v1/posts/{id}/comments`**

Comments are returned in ascending `created_at` order with no sort option. A `sort=newest` / `sort=oldest` option would be consistent with the feed's `sort` parameter and expected by users who want to see recent comments first.

**F-Q2 (Minor) — No filtering on `GET /v1/advisor/nudges`**

The nudge feed returns both read and unread nudges. A `?unread=true` filter would reduce payload and client-side filtering. This is consistent with how most notification APIs work.

---

## Summary

### Severity Distribution

| Severity   | Count | Items                         |
|------------|-------|-------------------------------|
| Significant | 1    | F-E1 (inconsistent error format) |
| Moderate   | 12    | F-N1, F-N2, F-N5, F-SC1, F-SC2, F-M1, F-M2, F-M3, F-V1, F-R1, F-R2, F-I1 |
| Minor      | 16    | F-N3, F-N4, F-N6, F-SC3, F-SC4, F-SC5, F-E2, F-E3, F-P1–P5, F-M4–M6, F-V2, F-R3, F-I2–I3, F-H1–H2, F-Q1–Q2 |

### Top Priorities

1. **F-E1 — Inconsistent error format.** The most impactful issue. Mobile clients must currently handle two error shapes depending on which endpoint they call. A single custom exception handler normalising all `HTTPException` and `RequestValidationError` into the `{"error": {"code": "...", "message": "..."}}` shape is a low-effort, high-value fix.

2. **F-SC1 — `DELETE /posts/{post_id}` returns 200 with body.** Should return 204. The "already deleted" case should be 409, consistent with `DELETE /auth/account`.

3. **F-N1, F-N2 — Verbs in paths (`/react`, `/read`).** Two paths violate the resource-naming constraint that REST is built on. These are still early-stage endpoints and should be renamed before any external documentation or SDK is published.

4. **F-P1 — Timestamp-only cursors in comments and history.** Susceptible to data skipping under concurrent writes. Adding `|id` to the cursor is a one-line fix per endpoint.

5. **F-R1 — Missing `Retry-After` headers on 429.** Required for well-behaved clients.

### What Is Working Well

- Versioning is cleanly applied via a single `/v1` prefix in `main.py`.
- Async job pattern (202 + polling) is correctly designed for generation.
- Idempotency on generation (body key) and webhooks (deduplication table) is solid.
- Cursor pagination is consistently applied and the trending composite cursor is well-designed.
- Auth separation (JWT, guest token, Stripe signature) is clear and not mixed.
- 410 Gone for deleted accounts in `public.py` is semantically correct and uncommon.
- Rate limiting covers the highest-risk endpoints (auth, reactions).
- Error propagation from services (HTTPException from pipeline/analysis) keeps the controller thin.
