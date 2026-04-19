# Code Review

- Target: `feat/payments-credits-only-engine` vs `origin/dev`
- Date: `2026-04-19`
- Reviewer: `Codex`

## Verification

- Backend: passed with `APP_ENV=test LOG_LEVEL= .venv/bin/ruff format --check app/ tests/ && .venv/bin/ruff check app/ tests/ && .venv/bin/pytest tests/ --tb=short -q`
  Result: `1074 passed, 71 skipped, 1 warning`
- Mobile: `npx expo lint` passed
- Mobile: `npm test -- --runInBand --watchman=false` failed
  Failures:
  - `mobile/app/result/__tests__/[jobId].test.tsx:699`
  - `mobile/app/result/__tests__/[jobId].test.tsx:731`
  - `mobile/app/result/__tests__/[jobId].test.tsx:767`
  Note: this suite is red in an unchanged result-screen delete-overflow area; the current implementation routes through `GlowupOverflowMenu` + deferred `Alert.alert` in `mobile/app/result/[jobId].tsx:435-464`, while the tests still expect the alert to fire directly from the header press.
- Card-web: passed with `npm run lint && npm run build && npm test`
  Note: `next build` logged a sandboxed `fetch failed` warning while generating the sitemap, but the build completed successfully.

## Findings

### High

1. Mobile guest bootstrap does not send `X-Install-UUID`, so the new guest-token theft protection never binds normal app-created guests to a device.

   Evidence:
   - `mobile/lib/guest-session.ts:28-32` creates the guest session with a bare `fetch(...)` and no `X-Install-UUID` header.
   - `app/db/guest.py:77-83` only stores `guest_install_uuid_hash` when `x_install_uuid` is present.
   - `mobile/app/_layout.tsx:94-95` bootstraps guest mode through `getOrCreateGuestToken()`.
   - `tests/test_guest_merge_install_uuid_binding.py:192-207` explicitly documents that unbound guests accept any caller hash.

   Impact:
   - The branch's Unit 10 merge guard does not protect the default mobile guest flow. If a guest token leaks, another device can still merge those guest credits because the guest row was created unbound.

   Recommendation:
   - Create guest sessions through the same install-UUID-aware request path as the other auth endpoints, or attach `X-Install-UUID` in `mobile/lib/guest-session.ts`.

2. Fresh local bootstrap is inconsistent with the new required payments settings, and the backend CI job appears to be missing the same required values.

   Evidence:
   - `app/config/__init__.py:301-304` makes `STRIPE_PRICE_CREDITS_PACK_V1` and `STRIPE_PRICE_PRO_V1` required settings.
   - `scripts/local-env.sh:66-75` writes signup-grant settings but does not emit either required Stripe price ID.
   - `.github/workflows/ci.yml:47-65` sets fingerprint/grant variables for the backend job but does not set the new required Stripe price IDs.

   Impact:
   - A freshly generated local `app/.env` does not satisfy the branch's new config contract.
   - The backend CI job is vulnerable to the same mismatch unless those values are injected elsewhere.

   Recommendation:
   - Add both required Stripe price IDs to `scripts/local-env.sh` and to the backend job environment (or otherwise make the boot path that supplies them explicit in the workflow).

### Medium

3. The mobile Pro-subscribe flow still expects an `"already_subscribed"` success payload, but the backend now returns HTTP 409 `ALREADY_SUBSCRIBED`.

   Evidence:
   - `app/api/entitlement.py:322-334` raises `HTTPException(status_code=409, code="ALREADY_SUBSCRIBED")`.
   - `mobile/lib/hooks/use-purchase-flow.ts:201-206` only handles the case where `createSubscription()` resolves successfully and `response.status === "already_subscribed"`.
   - `mobile/lib/entitlement.ts:65-77` still models that success-payload contract.

   Impact:
   - Already-subscribed users now fall into the generic error path instead of getting the intended refetch + informational toast.

   Recommendation:
   - Either restore the old success response shape or update the mobile client to treat the 409 business error as the already-subscribed path.

## Merge Recommendation

- Do not merge until the two High findings are addressed.
- The Medium client/server contract mismatch should be fixed in the same PR if this branch is meant to ship mobile and backend together.
