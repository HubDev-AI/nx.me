# Security Audit

- Target: `feature/story-2-2-auth-social-login` vs `origin/dev`
- Date: `2026-03-17`
- Skill used: `security-sentinel`
- Method: static code review of auth, payment, public, and social surfaces

## Executive Summary

The branch is not ready to be called secure. I found two high-severity abuse paths and three medium-severity auth/session hardening gaps. The most important issues are a spoofable IP rate-limit implementation on auth endpoints and a guest reaction system that trusts arbitrary caller-supplied tokens.

## Risk Matrix

| Severity | Count |
|----------|-------|
| High | 2 |
| Medium | 3 |
| Low | 0 |

## Findings

### High

1. Auth rate limits are bypassable because the code trusts the first `X-Forwarded-For` value from the request.
   Evidence: `app/api/auth.py:93-96` and `app/api/auth.py:378-381` derive `client_ip` from `request.headers.get("x-forwarded-for", "").split(",")[0]`.
   Why this matters: behind a proxy or load balancer, the request header can include attacker-controlled entries. That lets an attacker rotate fake IP values and bypass the registration/login rate limits intended to slow account creation abuse and authentication attacks.
   Recommendation: only trust forwarding headers from verified proxies, or use `request.client.host` unless a trusted proxy middleware normalizes the client IP first.

2. Guest reaction abuse prevention is ineffective because the server accepts any `X-Guest-Token` value and the client token itself is not CSPRNG-grade.
   Evidence: `app/api/social.py:335-340` accepts any `X-Guest-Token` string as identity with no existence check, binding, or format validation. `mobile/lib/guest-session.ts:18-25` generates the token from `Date.now()` and `Math.random()` and hashes the result.
   Why this matters: an attacker can mint unlimited fake guest identities and inflate reactions without creating accounts. The current token generation is also weaker than the repo docs/ADR expect for a durable anonymous identifier.
   Recommendation: generate guest tokens with a cryptographically secure RNG, store only a server-validated token record or token hash, and reject reactions for unknown/unregistered guest tokens.

### Medium

3. Stripe checkout redirect targets are fully user-controlled.
   Evidence: `app/api/entitlement.py:131-145` and `app/api/entitlement.py:191-206` accept arbitrary `success_url` and `cancel_url` strings from the client. Those values are passed straight into Stripe session creation at `app/api/entitlement.py:169-179` and `app/api/entitlement.py:228-235`, then forwarded directly to Stripe in `app/payment/adapters/stripe_adapter.py:44-49`.
   Why this matters: an authenticated attacker can create NXME checkout sessions that bounce users to arbitrary URLs after payment or cancellation. That is an open-redirect style phishing surface attached to a trusted payment flow.
   Recommendation: restrict these URLs to an allowlist of known app/web return URLs, or ignore client input and source them exclusively from server config.

4. Logout fails open when token revocation errors occur.
   Evidence: `app/api/auth.py:508-514` catches all `sign_out` failures, logs them, and still returns `204 No Content`.
   Why this matters: if revocation fails during an incident involving a stolen device or leaked bearer token, the client is told logout succeeded while the token can remain valid until expiry.
   Recommendation: return an error when server-side revocation fails, or clearly separate “local logout” from “revocation confirmed” semantics and require the client to clear state only after a successful revocation response.

5. JWT middleware validates only signature plus `sub`/`exp`, but not issuer, audience, or role constraints.
   Evidence: `app/api/middleware/auth.py:40-58` decodes with `options={"require": ["sub", "exp"]}` and does not enforce `iss`, `aud`, or an allowed `role` set.
   Why this matters: token acceptance is broader than the repo’s documented contract and makes the auth boundary more dependent on implicit upstream guarantees than explicit server checks.
   Recommendation: validate the expected issuer/audience and reject tokens whose role is not appropriate for end-user API access.

## Remediation Roadmap

1. Fix `X-Forwarded-For` handling on auth endpoints first.
2. Replace guest-token generation and add a server-side guest token registry/validation check.
3. Lock Stripe return URLs to server-controlled values.
4. Make logout revocation failure explicit to clients.
5. Tighten JWT claim validation to match the documented contract.

## Notes

- This audit was static only. I did not perform live traffic replay, proxy testing, or dynamic fuzzing.
- I did not find hardcoded secrets in the reviewed application code paths.
