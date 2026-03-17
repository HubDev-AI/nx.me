---
id: "2-2-auth-social-login-logout-deletion"
status: complete
created: 2026-03-16
---

# Story: Auth API — Social Login, JWT Validation, Logout & Account Deletion

## User Story

As a registered user, I want to log in with social providers, manage my session, and permanently delete my account, so that I control my data and can access the app securely.

## Acceptance Criteria

- AC-1: Given `POST /login` with a native provider `id_token` (obtained via platform SDK — Google Sign-In / Apple Sign-In), When validated via Supabase `sign_in_with_id_token`, Then a JWT is issued; implicit-flow tokens are rejected with HTTP 401; custom URI scheme redirects are rejected; `id_token` claims (`iss`, `aud`, `exp`, `nonce`) are validated (AC-A9).
- AC-2: Given `POST /logout`, When the request is processed, Then the session is invalidated server-side within ≤1s; subsequent API requests with the invalidated token return HTTP 401; the client navigates to unauthenticated state (AC-FR9).
- AC-3: Given `DELETE /account`, When the request is processed, Then primary storage deletion completes within 72h; the shareable card URL returns HTTP 410; the username is reserved (not reassignable) for 180 days (AC-FR5).
- AC-4: Given a rate-limited IP sending ≥4 account creation attempts per hour, When registration is attempted, Then HTTP 429 is returned (AC-A8 per-IP limit).

## Architecture Guardrails

### Technology Stack

- **Backend:** Python 3.12 + FastAPI
- **Auth:** Supabase GoTrue via supabase-py 2.15.1
- **JWT decode:** PyJWT 2.10.1 (HS256, SUPABASE_JWT_SECRET)
- **Rate limiting:** Redis via redis.asyncio
- **No automated tests** — zero test code written during development

### File Structure for This Story

```
app/
  api/
    middleware/
      __init__.py
      auth.py               # UserClaims TypedDict + validate_jwt(token: str) -> UserClaims
    deps.py                 # UPDATED: get_current_user delegates to validate_jwt
    auth.py                 # UPDATED: POST /login, POST /logout, DELETE /account + per-IP rate limit
  migrations/
    0005_username_reserved_until.sql   # Add username_reserved_until TIMESTAMPTZ to users
  services/
    rate_limiter.py         # UPDATED: check_ip_registration_rate_limit(ip, redis)
```

### Interface Contract

- `validate_jwt(token: str) -> UserClaims` — Location: `api/middleware/auth.py`
- `UserClaims`: TypedDict with `sub: str`, `email: str | None`, `exp: int`, `role: str | None`

## Tasks

- [x] Task 1: Create `app/api/middleware/auth.py` with `UserClaims` + `validate_jwt`; update `deps.py`
- [x] Task 2: Migration `0005_username_reserved_until.sql` + `POST /auth/login` endpoint
- [x] Task 3: `POST /auth/logout` endpoint (server-side session invalidation)
- [x] Task 4: `DELETE /account` endpoint (soft delete + username reservation + auth user deletion)
- [x] Task 5: Per-IP rate limit on `POST /register` (≥4 per hour → HTTP 429)

## Verified Interfaces

- `TrialGrantor.grant(user_id: UUID) -> None` — `entitlement/trial_grantor.py` ✓
- `check_registration_rate_limit(fingerprint: str, redis) -> bool` — `services/rate_limiter.py` ✓
- `get_current_user(authorization, supabase) -> dict` — `api/deps.py` ✓ (to be updated)

## Dev Notes

- `supabase.auth.sign_in_with_id_token({"provider": str, "token": str, "nonce"?: str})` — validates id_token with Supabase GoTrue
- `supabase.auth.admin.sign_out(jwt: str)` — server-side session revocation (≤1s propagation)
- `supabase.auth.admin.delete_user(user_id: str)` — removes from Supabase auth
- Username reservation: `username_reserved_until = deleted_at + 180 days`; registration checks this before allowing username reuse
- Per-IP rate limit key: `reg_ip_limit:{ip}` with 1-hour window, 4-attempt ceiling
