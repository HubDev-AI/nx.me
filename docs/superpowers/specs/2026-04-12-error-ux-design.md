# Error UX Overhaul — Design Spec

**Date:** 2026-04-12
**Status:** Approved, ready for planning
**Scope:** Mobile app (React Native / Expo). Minor backend additions.

---

## Problem

The mobile app lacks consistent, trustworthy error handling. Each screen re-implements its own `loading` / `error` state with ad-hoc messages. Native `Alert.alert` modals interrupt flow. There is no offline awareness, no retry policy, no structured error taxonomy, no crash reporting. Users hit 401/422/409/402/429 and see inconsistent copy, or worse, a white screen on render crashes.

The generation flow is the most acute failure point: face-analysis errors exist server-side but the client ignores the structured payload, credits are consumed on failures without refund, and retry requires re-selecting the photo from scratch.

## Goals

1. One source of truth for error shape, one for error copy, one for error policy.
2. Every async state on every screen renders the same way — loading, empty, error, or content.
3. Offline-aware: the app knows, the user knows, mutations queue for replay.
4. Warm & reassuring tone — no "Oops!", no stack traces, no "Error:" prefix.
5. Crashes reach Sentry with breadcrumbs, not the console.
6. Generation flow gets first-class treatment: face-error guidance, credit refund, retry-in-place.

## Non-Goals

- Localizing error strings (English only; structured so i18n can bolt on later)
- Sentry dashboards / custom alerting
- User-facing queue inspection UI (offline queue replays silently)

---

## Architecture & Data Flow

Five-layer stack:

```
Screen
  └── Feature hook        (useFeed, useGeneration, useProfile...)
        └── useAppQuery / useAppMutation      (TanStack Query wrappers)
              └── apiFetch + parseApiError    (transport + error normalization)
                    └── HTTP
```

Side channels:

- **Sentry** — hooked into `QueryClient` error handler and `ErrorBoundary`.
- **NetInfo** — drives `OfflineBanner` + mutation-queue replay trigger.
- **MMKV queue** — persists mutations while offline; replays on reconnect.
- **Burnt toast controller** — fired from `QueryClient` error hook for rate-limit / background failures.

**Error flow:**

1. `apiFetch` throws `ApiError` (existing class) on non-2xx.
2. TanStack Query catches it, passes to `parseApiError`.
3. `parseApiError` returns a typed `AppError` variant.
4. Default policy (retry / toast / Sentry) applies based on `AppError.kind`.
5. Screen renders via `QueryStateView` using the typed error.

**Principles:**

- No direct `fetch` in screens. All data flows through `useAppQuery` / `useAppMutation`.
- Single `AppError` discriminated union — no ad-hoc error shapes.
- Toasts are side-effects of the query client, not screen logic.
- Mutations queue by default when offline; screens opt out with `queueOffline: false`.

---

## Primitive Components

### `QueryStateView`

Wraps any screen's content with alternate renders:

- `loading` → skeleton (shimmer) matching content shape
- `empty` → illustration + message + optional CTA
- `error` → `AppError`-aware message + retry button
- default → renders children

Props: `{ status, error, onRetry, emptyMessage, skeleton, children }`.

Error copy varies by `AppError.kind` (see Error Taxonomy).

### `OfflineBanner`

28pt fixed bar at safe-area top. Renders only when `useNetInfo().isConnected === false`. No dismiss. Fade in/out. Copy: "You're offline — changes will sync when you're back."

### `AppToast`

Wrapper around Burnt's `toast()`. Three presets: `success`, `warning`, `error`. Screens call `showToast({ kind, message })`; never import Burnt directly.

### `FaceErrorCard`

Generation-specific. Renders when `AppError.kind === 'faceAnalysis'`. Shows a stylised face diagram with the failing zone highlighted, a two-sentence explanation in warm tone, and a "Try a different photo" CTA. Driven by the backend's structured face-error payload.

### `ErrorBoundary` (enhanced)

Existing file, wired to Sentry. Catches render-phase crashes, calls `Sentry.captureException`, renders a full-screen fallback ("Something crashed — tap to reload") instead of a blank white screen.

---

## Error Taxonomy

`AppError` discriminated union in `mobile/lib/errors.ts`:

| kind | trigger | retry? | surface |
|------|---------|--------|---------|
| `network` | no connection, timeout | auto (3×) | inline + offline banner |
| `server` | 500 / 502 / 503 / 504 | auto (3×) | inline |
| `validation` | 422 | never | inline, field-level |
| `auth` | 401 after refresh fail | never | redirect to login |
| `permission` | 403 | never | inline |
| `rateLimit` | 429 | auto w/ Retry-After | toast |
| `notFound` | 404 | never | inline, empty-state style |
| `business` | 402, 409, domain errors | never | inline, actionable CTA |
| `faceAnalysis` | generation face-error | never | `FaceErrorCard` |
| `unknown` | everything else | never | inline + Sentry |

### Copy (warm & reassuring)

- `network`: "You seem to be offline. We'll keep trying."
- `server`: "Something went wrong on our end. Give it a moment."
- `validation`: field-specific — e.g. "This email looks off."
- `auth`: "Your session expired. Let's sign you back in."
- `rateLimit`: "Whoa, slow down — try again in {n}s."
- `business/402`: "You're out of credits. Top up to continue?"
- `business/409`: "Looks like that already happened."
- `faceAnalysis`: zone-specific — e.g. "Try a photo with better lighting."

No "Error:" prefix, no stack traces, no exclamation marks, no "Oops!".

### `parseApiError`

Single function. Takes `ApiError | Error | unknown` → returns `AppError`. Handles HTTP status mapping, backend's `{ error_code, message, details }` body, and network error detection.

---

## Screen Migration

Pattern is identical everywhere: remove local `loading/error` state, replace with `useAppQuery` / `useAppMutation`, wrap in `QueryStateView`.

### Feed — `(tabs)/index.tsx`

Already strongest handling. Swap `useFeed` internals for `useAppQuery` with `staleTime: 30s`. Pull-to-refresh maps to `refetch()`. The custom 3-retry backoff in `useFeed.ts` is deleted — TanStack Query owns retry.

### Upload / Generation — `upload.tsx`

Biggest change:

- Inline status-code switch replaced by `parseApiError` + `QueryStateView`.
- `FaceErrorCard` renders when `error.kind === 'faceAnalysis'`.
- Retry-in-place: re-submits the already-selected photo, no picker re-open.
- Credit balance shown below the CTA (so users see cost before submitting).

### Result — `result/[jobId].tsx`

- Polling loop becomes `useAppQuery` with `refetchInterval` driven by job status.
- "Report issue" button triggers refund mutation on the new backend endpoint.
- On refund success: Burnt success toast, optimistic credit-balance update in header.

### Auth screens

- Form errors (wrong password, email taken) move from `Alert` modals to inline field-level text.
- Network failures fall back to an error toast.

### All other screens (analyses list, settings, profile)

Wrap fetch logic in `useAppQuery`. Drop local `isLoading` / `error`. Pass state into `QueryStateView`.

### Migration order

Upload → Result → Feed → Auth → others. Highest user-impact first.

---

## Backend Changes

### 1. Credit refund endpoint

`POST /v1/analyses/{job_id}/refund`

- Idempotent. If job is `failed` or `cancelled` and not already refunded, credit the user's tier balance back.
- Returns `{ refunded: true, new_balance: N }`.
- Owner-only. Already-refunded → 409 with `error_code: "already_refunded"`.

### 2. Structured error responses

Every 4xx/5xx returns `{ error_code: string, message: string, details?: object }`.

Error codes to define: `face_not_detected`, `face_too_close`, `lighting_too_dark`, `insufficient_credits`, `rate_limited`, `job_not_found`, `already_refunded`, `validation_failed`.

### 3. Face-error payload

On face-analysis failure, response includes `{ error_code: "face_too_close", details: { zone: "center", reason: "face occupies > 80% of frame" } }`. Confirm during implementation whether `landmark_extractor` already surfaces this or if we need to add it.

### 4. Auto-refund on worker failure (chosen)

Worker auto-refunds on non-user-caused failures (model timeout, internal error). User-caused failures (bad photo) still require the "Report issue" button. Cleaner UX than purely client-initiated refunds.

---

## Dependencies

New packages:

- `@tanstack/react-query`
- `@tanstack/react-query-persist-client`
- `burnt`
- `@sentry/react-native`
- `@react-native-community/netinfo`
- `react-native-mmkv`

---

## Implementation Phases

### Phase 1 — Foundation (Week 1)

Install deps, build primitives, wire providers. No screen changes.

- Packages installed
- `mobile/lib/errors.ts` — `AppError` + `parseApiError`
- `mobile/lib/queryClient.ts` — retry/error/offline policy
- `useAppQuery` / `useAppMutation` wrappers
- `QueryStateView`, `OfflineBanner`, `AppToast`, `FaceErrorCard` primitives
- `QueryClientProvider` + `SentryInit` + `OfflineBanner` wired into `app/_layout.tsx`
- `ErrorBoundary` wired to Sentry
- MMKV-backed mutation queue + NetInfo replay trigger

**Verification:** dev build runs, `OfflineBanner` appears when airplane mode toggled, Sentry receives test event.

### Phase 2 — Screen migration (Week 2)

One screen per commit: Upload → Result → Feed → Auth → others.

- Replace local state with hooks, wrap in `QueryStateView`, delete inline error handling.
- Upload gets `FaceErrorCard`, retry-in-place, credit balance widget.
- Result gets polling via `refetchInterval` + refund mutation.

**Verification per screen:** manual QA — network off, server 500 via dev toggle, happy path.

### Phase 3 — Backend + polish (Week 3)

- Backend: refund endpoint, structured errors, face-error payload (separate PR, lands first).
- Client: consume new error codes in `parseApiError`.
- Copy review pass across every error string.
- Sentry breadcrumbs tuned (TanStack Query hooks, navigation events).
- All `Alert.alert` error calls removed.
- Network-chaos QA across every screen.

---

## Success Criteria

- Zero screens using raw `fetch` + `useState` for async data.
- Zero `Alert.alert` calls for error display.
- `OfflineBanner` visible within 1s of connection loss.
- Offline mutations replay within 2s of reconnect.
- Render crashes reach Sentry; user sees fallback screen, not white.
- Generation failures auto-refund credits (non-user-caused) or surface actionable UI (user-caused).
- Every error message matches the warm & reassuring tone guide.

---

## Open Questions

- Does `landmark_extractor` already emit enough detail for `FaceErrorCard` zones, or does it need a small addition?
- Are there any existing mutations that must NOT queue offline (e.g. payment intents)? These need `queueOffline: false` explicitly.
