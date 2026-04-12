# Error UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc per-screen error handling with a consistent, offline-aware, crash-reported error UX across the nxme.ai mobile app.

**Architecture:** Five-layer stack — Screens → feature hooks → `useAppQuery`/`useAppMutation` (TanStack Query) → `apiFetch` + `parseApiError` → HTTP. Side channels: Sentry, NetInfo, MMKV mutation queue, Burnt toast controller.

**Tech Stack:** React Native 0.83.2, Expo SDK 55, React 19.2, TypeScript 5.9, `@tanstack/react-query`, `@tanstack/react-query-persist-client`, `burnt`, `@sentry/react-native`, `@react-native-community/netinfo`, `react-native-mmkv`, Jest, `@testing-library/react-native`.

**Spec:** `docs/superpowers/specs/2026-04-12-error-ux-design.md`

---

## File Structure

### Files to CREATE

**Phase 1 — Foundation:**
- `mobile/lib/errors.ts` — `AppError` union, `parseApiError`, copy table
- `mobile/lib/errors.test.ts` — unit tests for `parseApiError`
- `mobile/lib/query-client.ts` — `QueryClient` with retry/error/offline policy
- `mobile/lib/hooks/use-app-query.ts` — `useAppQuery` wrapper
- `mobile/lib/hooks/use-app-mutation.ts` — `useAppMutation` wrapper with offline queue opt-in
- `mobile/lib/offline-queue.ts` — MMKV-backed mutation queue
- `mobile/lib/offline-queue.test.ts` — unit tests for queue
- `mobile/lib/toast.ts` — `showToast()` wrapper around Burnt
- `mobile/lib/sentry.ts` — Sentry init + helpers
- `mobile/components/ui/QueryStateView.tsx` — loading/empty/error/content wrapper
- `mobile/components/ui/OfflineBanner.tsx` — connection-loss banner
- `mobile/components/ui/LoadingSkeleton.tsx` — generic skeleton primitive (reuses shimmer)
- `mobile/components/ui/FaceErrorCard.tsx` — face-analysis error UI
- `mobile/jest.config.js` — Jest configuration
- `mobile/jest.setup.ts` — Jest setup (mocks, polyfills)

**Phase 3 — Backend:**
- `app/api/refund.py` — refund endpoint route
- `tests/api/test_refund.py` — pytest tests for refund

### Files to MODIFY

- `mobile/app/_layout.tsx` — wire `QueryClientProvider`, Sentry init, `OfflineBanner`
- `mobile/components/ui/ErrorBoundary.tsx` — wire Sentry
- `mobile/app/upload.tsx` — migrate to `useAppMutation` + `FaceErrorCard`
- `mobile/app/result/[jobId].tsx` — migrate to `useAppQuery` with polling
- `mobile/app/(tabs)/index.tsx` — migrate to `useAppQuery` via updated `useFeed`
- `mobile/components/feed/useFeed.ts` — internals swapped to `useAppQuery`
- `mobile/app/(auth)/login.tsx` — error rendering via new primitives
- `mobile/app/settings.tsx`, `mobile/app/subscription.tsx`, `mobile/app/blocked-users.tsx`, `mobile/app/post/[postId].tsx`, `mobile/app/card/[username].tsx` — migrate to hooks
- `mobile/package.json` — add deps + test scripts
- `mobile/lib/api.ts` — minor: ensure `ApiError.body` parsing compatibility
- `app/api/generation.py` — ensure face-error payload includes `zone` / `reason`
- `app/api/deps.py` — add refund authorization dep
- `app/main.py` — register refund router
- `app/constants/tiers.py` — if refund logic depends on tier constants

---

## Phase 1: Foundation

### Task 1: Install dependencies and test tooling

**Files:**
- Modify: `mobile/package.json`
- Create: `mobile/jest.config.js`, `mobile/jest.setup.ts`

- [ ] **Step 1: Add runtime dependencies**

Run:
```bash
cd mobile && npx expo install @tanstack/react-query @tanstack/react-query-persist-client burnt @sentry/react-native @react-native-community/netinfo react-native-mmkv
```

Expected: `package.json` updated with correct Expo-compatible versions.

- [ ] **Step 2: Add dev dependencies for testing**

Run:
```bash
cd mobile && npm install --save-dev jest jest-expo @testing-library/react-native @testing-library/jest-native @types/jest
```

- [ ] **Step 3: Create `mobile/jest.config.js`**

```javascript
module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEach: ['<rootDir>/jest.setup.ts'],
  transformIgnorePatterns: [
    'node_modules/(?!((jest-)?react-native|@react-native(-community)?|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|@tanstack/.*|burnt))',
  ],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json'],
  testMatch: ['**/*.test.ts', '**/*.test.tsx'],
};
```

- [ ] **Step 4: Create `mobile/jest.setup.ts`**

```typescript
import '@testing-library/jest-native/extend-expect';

// Mock react-native-mmkv (native module, unavailable in Jest env)
jest.mock('react-native-mmkv', () => ({
  MMKV: jest.fn().mockImplementation(() => {
    const store = new Map<string, string>();
    return {
      set: (k: string, v: string) => store.set(k, v),
      getString: (k: string) => store.get(k),
      delete: (k: string) => store.delete(k),
      clearAll: () => store.clear(),
      getAllKeys: () => Array.from(store.keys()),
    };
  }),
}));

// Silence Sentry in tests
jest.mock('@sentry/react-native', () => ({
  init: jest.fn(),
  captureException: jest.fn(),
  captureMessage: jest.fn(),
  addBreadcrumb: jest.fn(),
  wrap: (component: unknown) => component,
}));
```

- [ ] **Step 5: Add test scripts to `mobile/package.json`**

Modify the `scripts` block:
```json
"scripts": {
  "start": "expo start",
  "android": "expo run:android",
  "ios": "expo run:ios",
  "web": "expo start --web",
  "lint": "expo lint",
  "test": "jest",
  "test:watch": "jest --watch"
}
```

- [ ] **Step 6: Verify Jest boots**

Create `mobile/lib/__sanity__.test.ts`:
```typescript
describe('jest sanity', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2);
  });
});
```

Run: `cd mobile && npm test -- __sanity__`
Expected: 1 test passed. Delete the sanity file afterwards.

- [ ] **Step 7: Commit**

```bash
git add mobile/package.json mobile/package-lock.json mobile/jest.config.js mobile/jest.setup.ts
git commit -m "chore(mobile): add TanStack Query, Burnt, Sentry, MMKV, NetInfo, Jest"
```

---

### Task 2: `AppError` taxonomy and `parseApiError`

**Files:**
- Create: `mobile/lib/errors.ts`
- Create: `mobile/lib/errors.test.ts`

Backend returns `{ error: { code, message } }` (see `app/api/errors.py:30,59–60`). `parseApiError` targets this shape.

- [ ] **Step 1: Write the failing test** — `mobile/lib/errors.test.ts`

```typescript
import { ApiError } from './api';
import { parseApiError, type AppError } from './errors';

describe('parseApiError', () => {
  it('maps network errors (TypeError from fetch)', () => {
    const err = new TypeError('Network request failed');
    const result = parseApiError(err);
    expect(result.kind).toBe('network');
    expect(result.message).toContain('offline');
  });

  it('maps 422 to validation', () => {
    const err = new ApiError(
      422,
      JSON.stringify({ error: { code: 'VALIDATION_ERROR', message: 'Invalid', details: [] } }),
      '/v1/x',
    );
    const result = parseApiError(err);
    expect(result.kind).toBe('validation');
  });

  it('maps 401 to auth', () => {
    const err = new ApiError(401, '{"error":{"code":"UNAUTHORIZED","message":"nope"}}', '/v1/x');
    expect(parseApiError(err).kind).toBe('auth');
  });

  it('maps 429 with retry_after', () => {
    const err = new ApiError(
      429,
      JSON.stringify({ error: { code: 'RATE_LIMIT_EXCEEDED', message: 'slow', details: { retry_after: 30 } } }),
      '/v1/x',
    );
    const result = parseApiError(err);
    expect(result.kind).toBe('rateLimit');
    if (result.kind === 'rateLimit') {
      expect(result.retryAfter).toBe(30);
    }
  });

  it('maps 402 to business (insufficient credits)', () => {
    const err = new ApiError(402, '{"error":{"code":"INSUFFICIENT_CREDITS","message":"buy more"}}', '/v1/x');
    const result = parseApiError(err);
    expect(result.kind).toBe('business');
  });

  it('maps 500 to server', () => {
    const err = new ApiError(500, '{"error":{"code":"INTERNAL_ERROR","message":"oops"}}', '/v1/x');
    expect(parseApiError(err).kind).toBe('server');
  });

  it('maps face-analysis error code to faceAnalysis', () => {
    const err = new ApiError(
      422,
      JSON.stringify({
        error: { code: 'face_too_close', message: 'too close', details: { zone: 'center', reason: '>80%' } },
      }),
      '/v1/x',
    );
    const result = parseApiError(err);
    expect(result.kind).toBe('faceAnalysis');
    if (result.kind === 'faceAnalysis') {
      expect(result.zone).toBe('center');
      expect(result.errorCode).toBe('face_too_close');
    }
  });

  it('falls back to unknown for unexpected errors', () => {
    const result = parseApiError('weird string');
    expect(result.kind).toBe('unknown');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mobile && npm test -- errors.test`
Expected: FAIL — `parseApiError` not found.

- [ ] **Step 3: Implement `mobile/lib/errors.ts`**

```typescript
import { ApiError } from './api';

export type FaceErrorZone = 'center' | 'top' | 'bottom' | 'left' | 'right' | 'whole';

export type AppError =
  | { kind: 'network'; message: string; cause?: unknown }
  | { kind: 'server'; message: string; status: number; cause?: unknown }
  | { kind: 'validation'; message: string; fieldErrors?: Record<string, string>; cause?: unknown }
  | { kind: 'auth'; message: string; cause?: unknown }
  | { kind: 'permission'; message: string; cause?: unknown }
  | { kind: 'rateLimit'; message: string; retryAfter?: number; cause?: unknown }
  | { kind: 'notFound'; message: string; cause?: unknown }
  | { kind: 'business'; message: string; errorCode: string; status: number; cause?: unknown }
  | { kind: 'faceAnalysis'; message: string; errorCode: string; zone?: FaceErrorZone; reason?: string; cause?: unknown }
  | { kind: 'unknown'; message: string; cause?: unknown };

const FACE_ERROR_CODES = new Set([
  'face_not_detected',
  'face_too_close',
  'face_too_far',
  'lighting_too_dark',
  'lighting_too_bright',
  'face_obscured',
]);

interface BackendErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown> | Array<unknown>;
  };
}

function parseBody(body: string): BackendErrorBody | null {
  try {
    return JSON.parse(body) as BackendErrorBody;
  } catch {
    return null;
  }
}

export function parseApiError(err: unknown): AppError {
  // Network-level failures (fetch throws TypeError)
  if (err instanceof TypeError && /network/i.test(err.message)) {
    return {
      kind: 'network',
      message: "You seem to be offline. We'll keep trying.",
      cause: err,
    };
  }

  if (!(err instanceof ApiError)) {
    return {
      kind: 'unknown',
      message: 'Something unexpected happened. Give it another try.',
      cause: err,
    };
  }

  const body = parseBody(err.body);
  const code = body?.error?.code ?? '';
  const serverMsg = body?.error?.message;

  // Face-analysis errors take precedence regardless of status
  if (FACE_ERROR_CODES.has(code)) {
    const details = (body?.error?.details ?? {}) as { zone?: FaceErrorZone; reason?: string };
    return {
      kind: 'faceAnalysis',
      message: serverMsg ?? faceErrorCopy(code),
      errorCode: code,
      zone: details.zone,
      reason: details.reason,
      cause: err,
    };
  }

  switch (err.status) {
    case 401:
      return { kind: 'auth', message: "Your session expired. Let's sign you back in.", cause: err };
    case 403:
      return { kind: 'permission', message: "You don't have access to do that.", cause: err };
    case 404:
      return { kind: 'notFound', message: "We couldn't find that.", cause: err };
    case 422: {
      const fieldErrors = extractFieldErrors(body);
      return {
        kind: 'validation',
        message: serverMsg ?? 'Some fields need a second look.',
        fieldErrors,
        cause: err,
      };
    }
    case 429: {
      const retryAfter = extractRetryAfter(body);
      return {
        kind: 'rateLimit',
        message: retryAfter
          ? `Whoa, slow down — try again in ${retryAfter}s.`
          : 'Too many requests. Give it a moment.',
        retryAfter,
        cause: err,
      };
    }
    case 402:
      return {
        kind: 'business',
        message: serverMsg ?? "You're out of credits. Top up to continue?",
        errorCode: code || 'INSUFFICIENT_CREDITS',
        status: 402,
        cause: err,
      };
    case 409:
      return {
        kind: 'business',
        message: serverMsg ?? 'Looks like that already happened.',
        errorCode: code || 'CONFLICT',
        status: 409,
        cause: err,
      };
    default:
      if (err.status >= 500 && err.status < 600) {
        return {
          kind: 'server',
          message: 'Something went wrong on our end. Give it a moment.',
          status: err.status,
          cause: err,
        };
      }
      return {
        kind: 'unknown',
        message: serverMsg ?? 'Something unexpected happened. Give it another try.',
        cause: err,
      };
  }
}

function extractFieldErrors(body: BackendErrorBody | null): Record<string, string> | undefined {
  const details = body?.error?.details;
  if (!Array.isArray(details)) return undefined;
  const fieldErrors: Record<string, string> = {};
  for (const d of details) {
    if (d && typeof d === 'object' && 'field' in d && 'message' in d) {
      const { field, message } = d as { field: string; message: string };
      fieldErrors[field] = message;
    }
  }
  return Object.keys(fieldErrors).length ? fieldErrors : undefined;
}

function extractRetryAfter(body: BackendErrorBody | null): number | undefined {
  const details = body?.error?.details;
  if (details && typeof details === 'object' && !Array.isArray(details)) {
    const v = (details as Record<string, unknown>).retry_after;
    if (typeof v === 'number') return v;
  }
  return undefined;
}

function faceErrorCopy(code: string): string {
  switch (code) {
    case 'face_not_detected':
      return "We couldn't find a face. Try a clear selfie.";
    case 'face_too_close':
      return 'Try pulling the camera back a bit.';
    case 'face_too_far':
      return 'Try bringing the camera a little closer.';
    case 'lighting_too_dark':
      return 'A brighter photo will give a better result.';
    case 'lighting_too_bright':
      return 'Try softer lighting.';
    case 'face_obscured':
      return 'Move hair or glasses away from your face and try again.';
    default:
      return 'Try a different photo.';
  }
}

/** Retry policy — drives `useAppQuery` / `useAppMutation` default retry. */
export function shouldRetry(err: AppError): boolean {
  return err.kind === 'network' || err.kind === 'server' || err.kind === 'rateLimit';
}
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd mobile && npm test -- errors.test`
Expected: 8 tests passed.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/errors.ts mobile/lib/errors.test.ts
git commit -m "feat(mobile): AppError taxonomy + parseApiError"
```

---

### Task 3: MMKV offline mutation queue

**Files:**
- Create: `mobile/lib/offline-queue.ts`
- Create: `mobile/lib/offline-queue.test.ts`

- [ ] **Step 1: Write the failing test** — `mobile/lib/offline-queue.test.ts`

```typescript
import { OfflineMutationQueue, type QueuedMutation } from './offline-queue';

describe('OfflineMutationQueue', () => {
  let queue: OfflineMutationQueue;

  beforeEach(() => {
    queue = new OfflineMutationQueue('test-queue');
    queue.clear();
  });

  it('starts empty', () => {
    expect(queue.list()).toEqual([]);
  });

  it('enqueues a mutation', () => {
    const mut: QueuedMutation = {
      id: 'm1',
      mutationKey: ['reportPost'],
      variables: { postId: 'p1' },
      createdAt: Date.now(),
    };
    queue.enqueue(mut);
    expect(queue.list()).toHaveLength(1);
    expect(queue.list()[0].id).toBe('m1');
  });

  it('dequeues by id', () => {
    queue.enqueue({ id: 'm1', mutationKey: ['a'], variables: {}, createdAt: 1 });
    queue.enqueue({ id: 'm2', mutationKey: ['b'], variables: {}, createdAt: 2 });
    queue.dequeue('m1');
    expect(queue.list()).toHaveLength(1);
    expect(queue.list()[0].id).toBe('m2');
  });

  it('preserves FIFO order', () => {
    queue.enqueue({ id: 'm1', mutationKey: ['a'], variables: {}, createdAt: 1 });
    queue.enqueue({ id: 'm2', mutationKey: ['b'], variables: {}, createdAt: 2 });
    queue.enqueue({ id: 'm3', mutationKey: ['c'], variables: {}, createdAt: 3 });
    expect(queue.list().map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
  });

  it('persists across instances (same storage id)', () => {
    queue.enqueue({ id: 'm1', mutationKey: ['a'], variables: {}, createdAt: 1 });
    const queue2 = new OfflineMutationQueue('test-queue');
    expect(queue2.list()).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test — verify fail**

Run: `cd mobile && npm test -- offline-queue.test`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `mobile/lib/offline-queue.ts`**

```typescript
import { MMKV } from 'react-native-mmkv';

export interface QueuedMutation {
  id: string;
  mutationKey: readonly unknown[];
  variables: unknown;
  createdAt: number;
}

const QUEUE_KEY = 'queue';

export class OfflineMutationQueue {
  private storage: MMKV;

  constructor(id: string = 'nxme-mutation-queue') {
    this.storage = new MMKV({ id });
  }

  list(): QueuedMutation[] {
    const raw = this.storage.getString(QUEUE_KEY);
    if (!raw) return [];
    try {
      return JSON.parse(raw) as QueuedMutation[];
    } catch {
      return [];
    }
  }

  enqueue(mutation: QueuedMutation): void {
    const current = this.list();
    current.push(mutation);
    this.storage.set(QUEUE_KEY, JSON.stringify(current));
  }

  dequeue(id: string): void {
    const current = this.list().filter((m) => m.id !== id);
    this.storage.set(QUEUE_KEY, JSON.stringify(current));
  }

  clear(): void {
    this.storage.delete(QUEUE_KEY);
  }
}

/** Shared singleton for the app. */
export const mutationQueue = new OfflineMutationQueue();
```

- [ ] **Step 4: Run tests — verify pass**

Run: `cd mobile && npm test -- offline-queue.test`
Expected: 5 tests passed.

- [ ] **Step 5: Commit**

```bash
git add mobile/lib/offline-queue.ts mobile/lib/offline-queue.test.ts
git commit -m "feat(mobile): MMKV-backed offline mutation queue"
```

---

### Task 4: `QueryClient` with default policy

**Files:**
- Create: `mobile/lib/query-client.ts`

- [ ] **Step 1: Create `mobile/lib/query-client.ts`**

```typescript
import { QueryCache, MutationCache, QueryClient } from '@tanstack/react-query';
import * as Sentry from '@sentry/react-native';
import { parseApiError, shouldRetry, type AppError } from './errors';
import { showToast } from './toast';

const MAX_RETRIES = 3;
const BASE_RETRY_DELAY_MS = 1000;

function computeDelay(attempt: number, err: AppError): number {
  if (err.kind === 'rateLimit' && err.retryAfter) {
    return err.retryAfter * 1000;
  }
  return Math.min(BASE_RETRY_DELAY_MS * 2 ** attempt, 15000);
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        const appError = parseApiError(error);
        if (!shouldRetry(appError)) return false;
        return failureCount < MAX_RETRIES;
      },
      retryDelay: (attempt, error) => computeDelay(attempt, parseApiError(error)),
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: (failureCount, error) => {
        const appError = parseApiError(error);
        if (appError.kind !== 'network' && appError.kind !== 'server') return false;
        return failureCount < 2;
      },
    },
  },
  queryCache: new QueryCache({
    onError: (error, query) => {
      const appError = parseApiError(error);
      Sentry.captureException(error, {
        tags: { source: 'query', kind: appError.kind },
        extra: { queryKey: query.queryKey },
      });
      if (appError.kind === 'rateLimit') {
        showToast({ kind: 'warning', message: appError.message });
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      const appError = parseApiError(error);
      Sentry.captureException(error, {
        tags: { source: 'mutation', kind: appError.kind },
        extra: { mutationKey: mutation.options.mutationKey },
      });
      // Background mutations (no onError override) get a toast
      if (!mutation.options.onError && appError.kind !== 'validation' && appError.kind !== 'auth') {
        showToast({ kind: 'error', message: appError.message });
      }
    },
  }),
});
```

- [ ] **Step 2: Commit (no test — this is wiring; tested via integration)**

```bash
git add mobile/lib/query-client.ts
git commit -m "feat(mobile): QueryClient with retry/sentry/toast policy"
```

---

### Task 5: `showToast()` wrapper (Burnt)

**Files:**
- Create: `mobile/lib/toast.ts`

- [ ] **Step 1: Create `mobile/lib/toast.ts`**

```typescript
import { toast } from 'burnt';

export type ToastKind = 'success' | 'warning' | 'error';

interface ShowToastArgs {
  kind: ToastKind;
  message: string;
  title?: string;
  duration?: number;
}

const PRESET_BY_KIND: Record<ToastKind, 'done' | 'error' | 'none'> = {
  success: 'done',
  warning: 'none',
  error: 'error',
};

export function showToast({ kind, message, title, duration = 3 }: ShowToastArgs): void {
  toast({
    title: title ?? defaultTitle(kind),
    message,
    preset: PRESET_BY_KIND[kind],
    duration,
    haptic: kind === 'error' ? 'error' : kind === 'success' ? 'success' : 'warning',
  });
}

function defaultTitle(kind: ToastKind): string {
  switch (kind) {
    case 'success':
      return 'Done';
    case 'warning':
      return 'Heads up';
    case 'error':
      return 'Something went wrong';
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add mobile/lib/toast.ts
git commit -m "feat(mobile): showToast wrapper around Burnt"
```

---

### Task 6: `useAppQuery` and `useAppMutation` hooks

**Files:**
- Create: `mobile/lib/hooks/use-app-query.ts`
- Create: `mobile/lib/hooks/use-app-mutation.ts`

- [ ] **Step 1: Create `mobile/lib/hooks/use-app-query.ts`**

```typescript
import {
  useQuery,
  type UseQueryOptions,
  type UseQueryResult,
  type QueryKey,
} from '@tanstack/react-query';
import { useMemo } from 'react';
import { parseApiError, type AppError } from '../errors';

export type AppQueryResult<TData> = Omit<UseQueryResult<TData, unknown>, 'error'> & {
  appError: AppError | null;
};

export function useAppQuery<TData, TQueryKey extends QueryKey = QueryKey>(
  options: UseQueryOptions<TData, unknown, TData, TQueryKey>,
): AppQueryResult<TData> {
  const result = useQuery(options);
  const appError = useMemo(
    () => (result.error ? parseApiError(result.error) : null),
    [result.error],
  );
  return { ...result, appError };
}
```

- [ ] **Step 2: Create `mobile/lib/hooks/use-app-mutation.ts`**

```typescript
import {
  useMutation,
  type UseMutationOptions,
  type UseMutationResult,
} from '@tanstack/react-query';
import { useMemo } from 'react';
import NetInfo from '@react-native-community/netinfo';
import { parseApiError, type AppError } from '../errors';
import { mutationQueue, type QueuedMutation } from '../offline-queue';

export interface AppMutationOptions<TData, TVariables>
  extends UseMutationOptions<TData, unknown, TVariables> {
  /** If true and offline, queue the mutation for replay. Default: false. */
  queueOffline?: boolean;
  /** Required if `queueOffline` is true. Identifies the mutation in the queue. */
  mutationKey?: readonly unknown[];
}

export type AppMutationResult<TData, TVariables> = Omit<
  UseMutationResult<TData, unknown, TVariables>,
  'error' | 'mutate'
> & {
  appError: AppError | null;
  mutate: (variables: TVariables) => Promise<void>;
};

export function useAppMutation<TData, TVariables>(
  options: AppMutationOptions<TData, TVariables>,
): AppMutationResult<TData, TVariables> {
  const { queueOffline = false, mutationKey, mutationFn, ...rest } = options;
  const mutation = useMutation({ ...rest, mutationFn, mutationKey });

  const appError = useMemo(
    () => (mutation.error ? parseApiError(mutation.error) : null),
    [mutation.error],
  );

  const mutate = async (variables: TVariables): Promise<void> => {
    if (queueOffline) {
      const netState = await NetInfo.fetch();
      if (!netState.isConnected) {
        if (!mutationKey) {
          throw new Error('queueOffline=true requires mutationKey');
        }
        const queued: QueuedMutation = {
          id: `${String(mutationKey[0])}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          mutationKey,
          variables,
          createdAt: Date.now(),
        };
        mutationQueue.enqueue(queued);
        return;
      }
    }
    mutation.mutate(variables);
  };

  return { ...mutation, appError, mutate };
}
```

- [ ] **Step 3: Commit**

```bash
git add mobile/lib/hooks/use-app-query.ts mobile/lib/hooks/use-app-mutation.ts
git commit -m "feat(mobile): useAppQuery and useAppMutation hooks"
```

---

### Task 7: `LoadingSkeleton` primitive

**Files:**
- Create: `mobile/components/ui/LoadingSkeleton.tsx`

Reuses the shimmer pattern from `mobile/components/feed/FeedSkeleton.tsx` (lines 15–32).

- [ ] **Step 1: Create `mobile/components/ui/LoadingSkeleton.tsx`**

```typescript
import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View, type ViewStyle } from 'react-native';
import { THEME } from '../../constants/theme';

interface LoadingSkeletonProps {
  height?: number;
  width?: number | string;
  borderRadius?: number;
  style?: ViewStyle;
}

export function LoadingSkeleton({
  height = 20,
  width = '100%',
  borderRadius = THEME.radius.sm,
  style,
}: LoadingSkeletonProps) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 600, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 600, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        styles.base,
        { height, width: width as ViewStyle['width'], borderRadius, opacity },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: THEME.colors.surfaceElevated,
  },
});
```

- [ ] **Step 2: Commit**

```bash
git add mobile/components/ui/LoadingSkeleton.tsx
git commit -m "feat(mobile): LoadingSkeleton primitive"
```

---

### Task 8: `QueryStateView` primitive

**Files:**
- Create: `mobile/components/ui/QueryStateView.tsx`

- [ ] **Step 1: Create `mobile/components/ui/QueryStateView.tsx`**

```typescript
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { THEME } from '../../constants/theme';
import { LoadingSkeleton } from './LoadingSkeleton';
import type { AppError } from '../../lib/errors';

interface QueryStateViewProps {
  isLoading: boolean;
  isEmpty?: boolean;
  error: AppError | null;
  onRetry?: () => void;
  skeleton?: React.ReactNode;
  emptyMessage?: string;
  emptyAction?: { label: string; onPress: () => void };
  children: React.ReactNode;
}

export function QueryStateView({
  isLoading,
  isEmpty = false,
  error,
  onRetry,
  skeleton,
  emptyMessage = 'Nothing here yet.',
  emptyAction,
  children,
}: QueryStateViewProps) {
  if (isLoading) {
    return <View style={styles.container}>{skeleton ?? <DefaultSkeleton />}</View>;
  }

  if (error) {
    return <ErrorState error={error} onRetry={onRetry} />;
  }

  if (isEmpty) {
    return <EmptyState message={emptyMessage} action={emptyAction} />;
  }

  return <>{children}</>;
}

function DefaultSkeleton() {
  return (
    <View style={{ gap: THEME.spacing.md, padding: THEME.spacing.lg }}>
      <LoadingSkeleton height={24} width="60%" />
      <LoadingSkeleton height={120} />
      <LoadingSkeleton height={16} />
      <LoadingSkeleton height={16} width="80%" />
    </View>
  );
}

function ErrorState({ error, onRetry }: { error: AppError; onRetry?: () => void }) {
  const canRetry = onRetry !== undefined && isRetryable(error.kind);
  return (
    <View style={styles.stateContainer}>
      <View style={styles.iconCircle}>
        <Ionicons name={iconForError(error.kind)} size={32} color={THEME.colors.textSecondary} />
      </View>
      <Text style={styles.title}>{titleForError(error.kind)}</Text>
      <Text style={styles.message}>{error.message}</Text>
      {canRetry && (
        <Pressable onPress={onRetry} style={styles.button}>
          <Text style={styles.buttonText}>Try again</Text>
        </Pressable>
      )}
    </View>
  );
}

function EmptyState({
  message,
  action,
}: {
  message: string;
  action?: { label: string; onPress: () => void };
}) {
  return (
    <View style={styles.stateContainer}>
      <View style={styles.iconCircle}>
        <Ionicons name="sparkles-outline" size={32} color={THEME.colors.textSecondary} />
      </View>
      <Text style={styles.message}>{message}</Text>
      {action && (
        <Pressable onPress={action.onPress} style={styles.button}>
          <Text style={styles.buttonText}>{action.label}</Text>
        </Pressable>
      )}
    </View>
  );
}

function isRetryable(kind: AppError['kind']): boolean {
  return ['network', 'server', 'unknown', 'rateLimit'].includes(kind);
}

function iconForError(kind: AppError['kind']): React.ComponentProps<typeof Ionicons>['name'] {
  switch (kind) {
    case 'network':
      return 'cloud-offline-outline';
    case 'notFound':
      return 'search-outline';
    case 'permission':
    case 'auth':
      return 'lock-closed-outline';
    case 'rateLimit':
      return 'hourglass-outline';
    default:
      return 'alert-circle-outline';
  }
}

function titleForError(kind: AppError['kind']): string {
  switch (kind) {
    case 'network':
      return "Can't reach the internet";
    case 'server':
      return 'Our server hiccupped';
    case 'notFound':
      return 'Not found';
    case 'permission':
      return 'No access';
    case 'auth':
      return 'Signed out';
    case 'rateLimit':
      return 'Slow down';
    case 'validation':
      return 'Check your input';
    default:
      return 'Something went wrong';
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  stateContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: THEME.colors.surfaceElevated,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
    textAlign: 'center',
  },
  message: {
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: 'center',
    maxWidth: 280,
  },
  button: {
    marginTop: THEME.spacing.md,
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xxl,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.surfaceElevated,
  },
  buttonText: {
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    fontWeight: '600',
  },
});
```

- [ ] **Step 2: Commit**

```bash
git add mobile/components/ui/QueryStateView.tsx
git commit -m "feat(mobile): QueryStateView primitive with AppError-aware rendering"
```

---

### Task 9: `OfflineBanner` primitive

**Files:**
- Create: `mobile/components/ui/OfflineBanner.tsx`

- [ ] **Step 1: Create `mobile/components/ui/OfflineBanner.tsx`**

```typescript
import React, { useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet, Text } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { THEME } from '../../constants/theme';

const BANNER_HEIGHT = 28;

export function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(false);
  const translateY = useRef(new Animated.Value(-BANNER_HEIGHT)).current;

  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      setIsOffline(!state.isConnected);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    Animated.timing(translateY, {
      toValue: isOffline ? 0 : -BANNER_HEIGHT,
      duration: 250,
      useNativeDriver: true,
    }).start();
  }, [isOffline, translateY]);

  return (
    <Animated.View style={[styles.banner, { transform: [{ translateY }] }]} pointerEvents="none">
      <Text style={styles.text}>You're offline — changes will sync when you're back.</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    height: BANNER_HEIGHT,
    backgroundColor: THEME.colors.textPrimary,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1000,
    paddingHorizontal: THEME.spacing.md,
  },
  text: {
    ...THEME.typography.caption,
    color: THEME.colors.bg,
    fontWeight: '600',
  },
});
```

- [ ] **Step 2: Commit**

```bash
git add mobile/components/ui/OfflineBanner.tsx
git commit -m "feat(mobile): OfflineBanner driven by NetInfo"
```

---

### Task 10: `FaceErrorCard` primitive

**Files:**
- Create: `mobile/components/ui/FaceErrorCard.tsx`

- [ ] **Step 1: Create `mobile/components/ui/FaceErrorCard.tsx`**

```typescript
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { THEME } from '../../constants/theme';
import type { AppError, FaceErrorZone } from '../../lib/errors';

interface FaceErrorCardProps {
  error: Extract<AppError, { kind: 'faceAnalysis' }>;
  onTryAgain: () => void;
}

export function FaceErrorCard({ error, onTryAgain }: FaceErrorCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.iconRow}>
        <FaceDiagram highlightedZone={error.zone} />
      </View>
      <Text style={styles.title}>{error.message}</Text>
      {error.reason && <Text style={styles.reason}>{error.reason}</Text>}
      <Pressable onPress={onTryAgain} style={styles.button}>
        <Text style={styles.buttonText}>Try a different photo</Text>
      </Pressable>
    </View>
  );
}

function FaceDiagram({ highlightedZone }: { highlightedZone?: FaceErrorZone }) {
  const highlight = (zone: FaceErrorZone) =>
    highlightedZone === zone || highlightedZone === 'whole'
      ? { tintColor: THEME.colors.destructive }
      : { tintColor: THEME.colors.textMuted };
  return (
    <View style={styles.diagram}>
      <Ionicons name="person-circle-outline" size={80} {...highlight('whole')} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: THEME.spacing.lg,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.surfaceElevated,
    gap: THEME.spacing.md,
    alignItems: 'center',
  },
  iconRow: {
    alignItems: 'center',
  },
  diagram: {
    alignItems: 'center',
  },
  title: {
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
    textAlign: 'center',
  },
  reason: {
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: 'center',
  },
  button: {
    marginTop: THEME.spacing.sm,
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.xxl,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.textPrimary,
  },
  buttonText: {
    ...THEME.typography.body,
    color: THEME.colors.bg,
    fontWeight: '600',
  },
});
```

- [ ] **Step 2: Commit**

```bash
git add mobile/components/ui/FaceErrorCard.tsx
git commit -m "feat(mobile): FaceErrorCard primitive for face-analysis failures"
```

---

### Task 11: Sentry init module

**Files:**
- Create: `mobile/lib/sentry.ts`

- [ ] **Step 1: Create `mobile/lib/sentry.ts`**

```typescript
import * as Sentry from '@sentry/react-native';
import Constants from 'expo-constants';
import { SENTRY_DSN } from '../constants/config';

let initialized = false;

export function initSentry(): void {
  if (initialized) return;
  if (!SENTRY_DSN) {
    console.warn('[Sentry] SENTRY_DSN missing — crash reporting disabled.');
    return;
  }
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: Constants.expoConfig?.extra?.environment ?? 'development',
    tracesSampleRate: 0.1,
    enableAutoSessionTracking: true,
    enableNative: true,
  });
  initialized = true;
}

export function addBreadcrumb(
  category: string,
  message: string,
  data?: Record<string, unknown>,
): void {
  Sentry.addBreadcrumb({ category, message, data, level: 'info' });
}
```

- [ ] **Step 2: Add `SENTRY_DSN` to `mobile/constants/config.ts`**

Locate the existing constants file (confirmed to exist per exploration). Append:

```typescript
export const SENTRY_DSN = process.env.EXPO_PUBLIC_SENTRY_DSN ?? '';
```

- [ ] **Step 3: Update `mobile/.env.example`**

Append:
```
EXPO_PUBLIC_SENTRY_DSN=
```

- [ ] **Step 4: Commit**

```bash
git add mobile/lib/sentry.ts mobile/constants/config.ts mobile/.env.example
git commit -m "feat(mobile): Sentry init module"
```

---

### Task 12: Wire Sentry into `ErrorBoundary`

**Files:**
- Modify: `mobile/components/ui/ErrorBoundary.tsx:28` (componentDidCatch)

- [ ] **Step 1: Re-read the file**

Run: `cat mobile/components/ui/ErrorBoundary.tsx`

- [ ] **Step 2: Add Sentry import at top of file**

```typescript
import * as Sentry from '@sentry/react-native';
```

- [ ] **Step 3: Modify `componentDidCatch` (around line 28)**

Change:
```typescript
componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
  console.error('[ErrorBoundary]', error, errorInfo);
}
```

To:
```typescript
componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
  Sentry.captureException(error, {
    contexts: { react: { componentStack: errorInfo.componentStack } },
    tags: { source: 'errorBoundary' },
  });
  if (__DEV__) {
    console.error('[ErrorBoundary]', error, errorInfo);
  }
}
```

- [ ] **Step 4: Verify with typecheck**

Run: `cd mobile && npx tsc --noEmit`
Expected: no errors introduced in `ErrorBoundary.tsx`.

- [ ] **Step 5: Commit**

```bash
git add mobile/components/ui/ErrorBoundary.tsx
git commit -m "feat(mobile): wire ErrorBoundary to Sentry"
```

---

### Task 13: Wire providers into `_layout.tsx`

**Files:**
- Modify: `mobile/app/_layout.tsx` (provider stack, lines ~152–168)

Provider order (outermost → innermost): ErrorBoundary → QueryClientProvider → ThemeProvider → AuthProvider → StripeProvider → (AuthGuard + content + OfflineBanner).

- [ ] **Step 1: Re-read `_layout.tsx`**

Run: `cat mobile/app/_layout.tsx`

- [ ] **Step 2: Add imports at top of file**

```typescript
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from '../lib/query-client';
import { initSentry } from '../lib/sentry';
import { OfflineBanner } from '../components/ui/OfflineBanner';
import NetInfo from '@react-native-community/netinfo';
import { mutationQueue } from '../lib/offline-queue';
```

- [ ] **Step 3: Call `initSentry()` at module scope (top-level, before default export)**

```typescript
initSentry();
```

- [ ] **Step 4: Add a mutation-queue replay effect inside the root component**

Add this effect alongside existing effects in the root layout component:

```typescript
useEffect(() => {
  const unsubscribe = NetInfo.addEventListener(async (state) => {
    if (!state.isConnected) return;
    const pending = mutationQueue.list();
    for (const queued of pending) {
      try {
        await queryClient
          .getMutationCache()
          .build(queryClient, {
            mutationKey: queued.mutationKey as readonly unknown[],
          })
          .execute(queued.variables);
        mutationQueue.dequeue(queued.id);
      } catch {
        // Leave in queue; next reconnect will retry.
      }
    }
  });
  return unsubscribe;
}, []);
```

- [ ] **Step 5: Wrap provider stack with `QueryClientProvider` and mount `OfflineBanner`**

Inside the root component JSX, change the existing provider tree (around lines 152–168):

Before:
```tsx
<ErrorBoundary>
  <ThemeProvider>
    <AuthProvider>
      <StripeProvider>
        <View style={{ flex: 1 }}>
          <StatusBar ... />
          <AuthGuard>{/* children */}</AuthGuard>
        </View>
      </StripeProvider>
    </AuthProvider>
  </ThemeProvider>
</ErrorBoundary>
```

After:
```tsx
<ErrorBoundary>
  <QueryClientProvider client={queryClient}>
    <ThemeProvider>
      <AuthProvider>
        <StripeProvider>
          <View style={{ flex: 1 }}>
            <StatusBar ... />
            <AuthGuard>{/* children */}</AuthGuard>
            <OfflineBanner />
          </View>
        </StripeProvider>
      </AuthProvider>
    </ThemeProvider>
  </QueryClientProvider>
</ErrorBoundary>
```

- [ ] **Step 6: Typecheck + run**

Run: `cd mobile && npx tsc --noEmit && npx expo lint`
Expected: clean.

Then: `cd mobile && npx expo run:ios`
Verify: app boots. Toggle airplane mode on simulator — `OfflineBanner` slides in.

- [ ] **Step 7: Commit**

```bash
git add mobile/app/_layout.tsx
git commit -m "feat(mobile): wire QueryClientProvider, Sentry, OfflineBanner, mutation replay"
```

---

## Phase 2: Screen Migration

Each screen follows the same pattern: remove local `loading`/`error` state → replace with `useAppQuery`/`useAppMutation` → wrap content in `QueryStateView` → replace `Alert.alert` error calls with `showToast`/inline rendering.

### Task 14: Migrate Upload screen (`mobile/app/upload.tsx`)

**Files:**
- Modify: `mobile/app/upload.tsx` (610 lines; key ranges: state 86–94, status-code switch 202–212, error rendering 298–337)

- [ ] **Step 1: Re-read the file**

Run: `wc -l mobile/app/upload.tsx && cat mobile/app/upload.tsx | head -100`
Then read the full file in chunks.

- [ ] **Step 2: Add imports**

```typescript
import { useAppMutation } from '../lib/hooks/use-app-mutation';
import { FaceErrorCard } from '../components/ui/FaceErrorCard';
import { showToast } from '../lib/toast';
```

- [ ] **Step 3: Replace state declarations (lines 86–94)**

Remove:
```typescript
const [photo, setPhoto] = useState<SelectedPhoto | null>(null);
const [phase, setPhase] = useState<UploadPhase>('idle');
const [faceErrorCode, setFaceErrorCode] = useState<FaceErrorCode | null>(null);
const [errorMessage, setErrorMessage] = useState<string | null>(null);
const [jobId, setJobId] = useState<string | null>(null);
```

Keep `photo` and `jobId` state (still needed). Drop `phase`, `faceErrorCode`, `errorMessage` — `useAppMutation` provides them.

- [ ] **Step 4: Replace the submit handler with a mutation**

Add a mutation definition in the component body:

```typescript
const generation = useAppMutation<
  { jobId: string },
  { photo: SelectedPhoto }
>({
  mutationKey: ['generation.create'],
  mutationFn: async ({ photo }) => {
    const analysis = await createAnalysis(photo);
    const job = await startGeneration(analysis.id);
    return { jobId: job.id };
  },
  onSuccess: ({ jobId: newJobId }) => {
    setJobId(newJobId);
    router.push(`/result/${newJobId}`);
  },
});
```

- [ ] **Step 5: Replace the old status-code switch (lines 202–212) with mutation trigger**

The existing `handleAnalyze` function becomes:

```typescript
const handleAnalyze = () => {
  if (!photo) return;
  generation.mutate({ photo });
};
```

All 401/422/409/402/429-specific message strings are deleted — `parseApiError` + `generation.appError` drive copy now.

- [ ] **Step 6: Replace the error rendering blocks (lines 298–337)**

Replace the phase-based face-error card (298–317) and generic error card (320–337) with:

```tsx
{generation.appError?.kind === 'faceAnalysis' && (
  <FaceErrorCard
    error={generation.appError}
    onTryAgain={() => generation.reset()}
  />
)}

{generation.appError && generation.appError.kind !== 'faceAnalysis' && (
  <View style={styles.errorCard}>
    <Text style={styles.errorText}>{generation.appError.message}</Text>
    <Pressable onPress={handleAnalyze} style={styles.retryButton}>
      <Text style={styles.retryText}>Try again</Text>
    </Pressable>
  </View>
)}
```

The retry button calls `handleAnalyze` directly — same photo, no picker re-open.

- [ ] **Step 7: Loading state — tie CTA to `generation.isPending`**

The existing "Analyze" / "Generate" button's `disabled` prop uses `generation.isPending` (replaces `phase === 'analyzing'` etc.).

- [ ] **Step 8: Remove any remaining `Alert.alert` error calls in this file**

Grep: `grep -n "Alert.alert" mobile/app/upload.tsx`
Replace any error-type alerts with `showToast({ kind: 'error', message: ... })`.

- [ ] **Step 9: Typecheck**

Run: `cd mobile && npx tsc --noEmit`
Expected: no new errors. Fix any type issues introduced.

- [ ] **Step 10: Manual QA**

Run: `cd mobile && npx expo run:ios`
Test matrix:
1. Happy path — select photo → generate → lands on result.
2. Airplane mode before generate — `OfflineBanner` shows; submit; error card appears with "offline" copy.
3. Simulated 500 (temporarily change API base URL to wrong host) — retry button retries.
4. Force a face-error response (point API base to a test server returning `face_too_close`) — `FaceErrorCard` renders.

- [ ] **Step 11: Commit**

```bash
git add mobile/app/upload.tsx
git commit -m "feat(mobile): migrate upload to useAppMutation + FaceErrorCard + retry-in-place"
```

---

### Task 15: Migrate Result screen (`mobile/app/result/[jobId].tsx`) — add polling

**Files:**
- Modify: `mobile/app/result/[jobId].tsx` (485 lines; state 51–56, fetch 59–81, refund 89–128, renders 182–365)

The existing screen does not poll — it fetches once. Migration adds `refetchInterval` polling until the job completes.

- [ ] **Step 1: Re-read the file**

Run: `wc -l mobile/app/result/[jobId].tsx && cat mobile/app/result/[jobId].tsx | head -150`

- [ ] **Step 2: Add imports**

```typescript
import { useAppQuery } from '../../lib/hooks/use-app-query';
import { useAppMutation } from '../../lib/hooks/use-app-mutation';
import { QueryStateView } from '../../components/ui/QueryStateView';
import { showToast } from '../../lib/toast';
```

- [ ] **Step 3: Replace `useState` + `useEffect` fetch (lines 51–81) with `useAppQuery`**

Remove the `useEffect` block (lines 59–81) and local state (51–53). Add:

```typescript
const jobQuery = useAppQuery({
  queryKey: ['job', jobId],
  queryFn: () => getJobStatus(jobId),
  enabled: !!jobId,
  refetchInterval: (query) => {
    const data = query.state.data;
    if (!data) return 2000;
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
      return false;
    }
    return 2000;
  },
});

const result = jobQuery.data;
```

- [ ] **Step 4: Replace refund `Alert.alert` + fetch (lines 89–128) with `useAppMutation`**

Remove the existing `handleRefund` flow. Add:

```typescript
const refundMutation = useAppMutation<
  { refunded: boolean; new_balance: number },
  void
>({
  mutationKey: ['refund', jobId],
  mutationFn: () => requestRefund(jobId),
  onSuccess: (data) => {
    showToast({
      kind: 'success',
      message: `Refunded. New balance: ${data.new_balance}.`,
    });
    setRefundRequested(true);
  },
});

const handleRefund = () => {
  Alert.alert(
    'Report issue',
    "We'll refund your credits. Continue?",
    [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Refund', onPress: () => refundMutation.mutate() },
    ],
  );
};
```

The confirmation Alert is the ONLY surviving `Alert.alert` — it's a confirmation prompt, not an error surface.

- [ ] **Step 5: Replace loading and error render branches (lines 158–209) with `QueryStateView`**

Before (two separate branches): delete the `if (loading) return ...` block (158–175) and `if (error) return ...` block (182–209).

After:
```tsx
return (
  <QueryStateView
    isLoading={jobQuery.isLoading}
    error={jobQuery.appError}
    onRetry={() => jobQuery.refetch()}
  >
    {/* existing success / failed / cancelled branches */}
  </QueryStateView>
);
```

- [ ] **Step 6: Keep failed/cancelled render branches (lines 216–249)** — these are success responses that happen to represent a failure. They stay as-is inside the `QueryStateView` children.

- [ ] **Step 7: Typecheck**

Run: `cd mobile && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 8: Manual QA**

Test matrix:
1. Navigate to a completed job — renders immediately.
2. Navigate to an in-progress job — polls every 2s until complete.
3. Tap "Report issue" — confirmation modal → refund → success toast → balance update.
4. Force a network failure during polling — retry button appears.

- [ ] **Step 9: Commit**

```bash
git add mobile/app/result/[jobId].tsx
git commit -m "feat(mobile): migrate result screen to useAppQuery with polling + refund mutation"
```

---

### Task 16: Migrate Feed via `useFeed` refactor

**Files:**
- Modify: `mobile/components/feed/useFeed.ts` (267 lines; custom retry at 109–115)
- Modify: `mobile/app/(tabs)/index.tsx` (318 lines; useFeed consumption at 41–50, error render at 147–165, Alert.alert at 89, 100, 107, 112, 123)

- [ ] **Step 1: Re-read both files**

Run: `wc -l mobile/components/feed/useFeed.ts mobile/app/\(tabs\)/index.tsx`
Read each in full.

- [ ] **Step 2: Rewrite `useFeed.ts` to use `useAppQuery` with infinite pagination**

Replace the internal fetch + retry + state with `useInfiniteQuery` from TanStack Query. Create a new `useFeed.ts`:

```typescript
import { useInfiniteQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { parseApiError, type AppError } from '../../lib/errors';
import { fetchFeedPage, type FeedPost, type FeedSort } from '../../lib/feed-api';

interface UseFeedArgs {
  sort: FeedSort;
}

export interface UseFeedReturn {
  posts: FeedPost[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: AppError | null;
  refetch: () => Promise<unknown>;
  fetchNextPage: () => void;
  // Preserve existing API surface:
  reactToPost: (postId: string, reaction: string) => void;
  incrementCommentCount: (postId: string) => void;
  removePostsByUser: (userId: string) => void;
}

export function useFeed({ sort }: UseFeedArgs): UseFeedReturn {
  const query = useInfiniteQuery({
    queryKey: ['feed', sort],
    queryFn: ({ pageParam }) => fetchFeedPage({ sort, cursor: pageParam as string | undefined }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    staleTime: 30_000,
  });

  const posts = useMemo(
    () => query.data?.pages.flatMap((p) => p.posts) ?? [],
    [query.data],
  );

  // TODO: reactToPost / incrementCommentCount / removePostsByUser —
  // migrate these to queryClient.setQueryData mutations against ['feed', sort].
  // Extract existing logic from the current useFeed.ts (lines N..M) and adapt.
  // ...

  return {
    posts,
    isLoading: query.isLoading,
    isRefreshing: query.isRefetching,
    isLoadingMore: query.isFetchingNextPage,
    hasMore: query.hasNextPage ?? false,
    error: query.error ? parseApiError(query.error) : null,
    refetch: query.refetch,
    fetchNextPage: query.fetchNextPage,
    reactToPost: /* preserve existing impl via queryClient.setQueryData */ () => {},
    incrementCommentCount: () => {},
    removePostsByUser: () => {},
  };
}
```

Note: the optimistic update methods (reactToPost, etc.) must be preserved. Copy their existing bodies from the original `useFeed.ts` and adapt to call `queryClient.setQueryData(['feed', sort], (old) => ...)`.

- [ ] **Step 3: Update `(tabs)/index.tsx` error rendering (lines 154–165)**

Replace the custom error rendering with `QueryStateView`:

```tsx
<QueryStateView
  isLoading={isLoading && !posts.length}
  isEmpty={!isLoading && !posts.length && !error}
  emptyMessage="No posts yet. Be the first!"
  error={error}
  onRetry={refetch}
>
  <FlatList ... />
</QueryStateView>
```

- [ ] **Step 4: Replace `Alert.alert` error calls (lines 89, 100, 107, 112, 123)**

Every `Alert.alert` that surfaces an error becomes `showToast({ kind: 'error', message: ... })`. Confirmation dialogs (report / block actions) stay as `Alert.alert`.

Example — lines 89 (handleReport 429 alert):
Before:
```typescript
Alert.alert('Slow down', 'You can only report 5 posts per hour.');
```
After:
```typescript
showToast({ kind: 'warning', message: 'You can only report 5 posts per hour.' });
```

Audit each of the 5 lines (89, 100, 107, 112, 123) the same way.

- [ ] **Step 5: Typecheck + lint**

Run: `cd mobile && npx tsc --noEmit && npx expo lint`
Expected: clean.

- [ ] **Step 6: Manual QA**

1. Scroll to end — loads more.
2. Airplane mode → `OfflineBanner` + retry button.
3. Pull-to-refresh.
4. Report / block flows still trigger confirm dialogs but errors become toasts.

- [ ] **Step 7: Commit**

```bash
git add mobile/components/feed/useFeed.ts mobile/app/\(tabs\)/index.tsx
git commit -m "feat(mobile): migrate feed to useInfiniteQuery + QueryStateView"
```

---

### Task 17: Migrate Auth screen

**Files:**
- Modify: `mobile/app/(auth)/login.tsx` (230 lines; error state at 54, 62–72, inline card at 144–151)
- Modify: `mobile/hooks/useSocialAuth.ts` (referenced `instanceof ApiError` at lines 61, 133)

- [ ] **Step 1: Re-read both files**

- [ ] **Step 2: Update `useSocialAuth.ts` to return typed `AppError`**

Inside any `catch` block doing `instanceof ApiError`, replace with `parseApiError`:

```typescript
import { parseApiError, type AppError } from '../lib/errors';

// In hook:
const [error, setError] = useState<AppError | null>(null);

try { /* ... */ } catch (err) {
  setError(parseApiError(err));
}
```

Update the hook's return signature to expose `AppError | null` instead of string.

- [ ] **Step 3: Update `login.tsx` to render AppError**

Replace the existing `socialError` string with `AppError`. The inline error card (lines 144–151) renders `error.message`. Validation-kind errors with `fieldErrors` render under their field input; other kinds render at the card.

- [ ] **Step 4: Typecheck**

Run: `cd mobile && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Manual QA**

1. Wrong credentials → inline validation error.
2. Network off → inline offline error.
3. Server 500 → inline server error + retry button.

- [ ] **Step 6: Commit**

```bash
git add mobile/app/\(auth\)/login.tsx mobile/hooks/useSocialAuth.ts
git commit -m "feat(mobile): migrate auth screens to AppError"
```

---

### Task 18: Migrate remaining screens

**Files (per exploration):**
- Modify: `mobile/app/settings.tsx` (lines 86, 123 — `instanceof ApiError`; `Alert.alert` count TBD)
- Modify: `mobile/app/subscription.tsx` (6 `Alert.alert` calls at 134, 158, 166, 179, 194, +1)
- Modify: `mobile/app/blocked-users.tsx` (line 95 `instanceof ApiError`; 1 `Alert.alert`)
- Modify: `mobile/app/post/[postId].tsx` (lines 159 `instanceof ApiError`; 8 `Alert.alert` calls at 123, 140, 162, 176, 188, 192, 203, 215, 218)
- Modify: `mobile/app/card/[username].tsx`
- Modify: `mobile/app/onboarding.tsx`
- Modify: `mobile/components/upload/PhotoPicker.tsx` (3 `Alert.alert` calls at 117, 145, 174)

For each, follow this uniform micro-checklist. Do one screen per commit.

- [ ] **Step 1: Re-read the screen**
- [ ] **Step 2: Wrap data fetches in `useAppQuery` (if screen fetches data)**
- [ ] **Step 3: Wrap mutations in `useAppMutation`**
- [ ] **Step 4: Wrap render in `QueryStateView` where applicable**
- [ ] **Step 5: Replace error-kind `Alert.alert` with `showToast` or inline `ErrorState`**
- [ ] **Step 6: Keep confirmation-kind `Alert.alert` as-is**
- [ ] **Step 7: Typecheck + lint**
- [ ] **Step 8: Manual smoke test**
- [ ] **Step 9: Commit** — per-screen message, e.g. `feat(mobile): migrate settings to AppError UX`

**Order (one commit per screen):**
1. `settings.tsx`
2. `subscription.tsx`
3. `blocked-users.tsx`
4. `post/[postId].tsx`
5. `card/[username].tsx`
6. `onboarding.tsx`
7. `PhotoPicker.tsx` (component — `Alert.alert` for permission denied → keep as Alert OR replace with toast; permission prompts are acceptable as Alerts)

---

### Task 19: Grep sweep — zero `Alert.alert` for error display

**Files:** cross-cutting audit

- [ ] **Step 1: Search for residual error-kind Alerts**

Run:
```bash
cd mobile && grep -rn "Alert\.alert" app/ components/ hooks/ lib/ | grep -vi "are you sure\|confirm\|cancel\|delete"
```

Every remaining match is either a confirmation dialog (keep) or a residual error Alert (replace).

- [ ] **Step 2: Replace any missed error Alerts with `showToast`**

- [ ] **Step 3: Verify**

Run the grep again — confirmation-only matches remain.

- [ ] **Step 4: Commit**

```bash
git add -A mobile/
git commit -m "refactor(mobile): replace remaining error Alerts with toasts"
```

---

## Phase 3: Backend + Polish

### Task 20: Backend refund endpoint

**Files:**
- Create: `app/api/refund.py`
- Create: `tests/api/test_refund.py`
- Modify: `app/main.py` (register router)

- [ ] **Step 1: Write the failing test — `tests/api/test_refund.py`**

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_refund_failed_job_returns_200(
    client: AsyncClient, authed_headers, failed_job_fixture
):
    response = await client.post(
        f"/v1/analyses/{failed_job_fixture.id}/refund",
        headers=authed_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["refunded"] is True
    assert body["new_balance"] > failed_job_fixture.balance_before_refund

@pytest.mark.asyncio
async def test_refund_already_refunded_returns_409(
    client: AsyncClient, authed_headers, refunded_job_fixture
):
    response = await client.post(
        f"/v1/analyses/{refunded_job_fixture.id}/refund",
        headers=authed_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_refunded"

@pytest.mark.asyncio
async def test_refund_not_owner_returns_403(
    client: AsyncClient, other_user_headers, failed_job_fixture
):
    response = await client.post(
        f"/v1/analyses/{failed_job_fixture.id}/refund",
        headers=other_user_headers,
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_refund_completed_job_returns_409(
    client: AsyncClient, authed_headers, completed_job_fixture
):
    response = await client.post(
        f"/v1/analyses/{completed_job_fixture.id}/refund",
        headers=authed_headers,
    )
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests — verify fail**

Run: `cd app && pytest tests/api/test_refund.py -v`
Expected: FAIL (endpoint missing).

- [ ] **Step 3: Implement `app/api/refund.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from app.api.deps import get_current_user, get_analysis_repository, get_credit_service
from app.repositories.analysis import AnalysisRepository
from app.services.credits import CreditService
from app.api.errors import api_error

router = APIRouter(prefix="/v1/analyses", tags=["refund"])


@router.post("/{job_id}/refund", status_code=200)
async def refund_job(
    job_id: UUID,
    user=Depends(get_current_user),
    analyses: AnalysisRepository = Depends(get_analysis_repository),
    credits: CreditService = Depends(get_credit_service),
):
    job = await analyses.get(job_id)
    if not job:
        raise api_error(404, "job_not_found", "Job not found.")
    if job.user_id != user.id:
        raise api_error(403, "forbidden", "Not your job.")
    if job.status not in ("failed", "cancelled"):
        raise api_error(409, "refund_not_applicable", "Only failed or cancelled jobs can be refunded.")
    if job.refunded:
        raise api_error(409, "already_refunded", "This job was already refunded.")

    new_balance = await credits.refund(user_id=user.id, job_id=job_id, amount=job.credits_charged)
    await analyses.mark_refunded(job_id)
    return {"refunded": True, "new_balance": new_balance}
```

Note: `api_error` is the helper in `app/api/errors.py` that raises an `HTTPException` with the structured `{ error: { code, message } }` body. If the helper doesn't exist with that signature, use whatever the existing errors module exposes — match the pattern from `app/api/generation.py:143–161`.

- [ ] **Step 4: Register router in `app/main.py`**

Add:
```python
from app.api import refund as refund_api
app.include_router(refund_api.router)
```

- [ ] **Step 5: Run tests — verify pass**

Run: `cd app && pytest tests/api/test_refund.py -v`
Expected: 4 tests passed.

- [ ] **Step 6: Lint**

Run: `make lint`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add app/api/refund.py app/main.py tests/api/test_refund.py
git commit -m "feat(api): credit refund endpoint for failed/cancelled jobs"
```

---

### Task 21: Backend face-error payload

**Files:**
- Modify: `app/api/generation.py` (confirm face-error response shape)
- Modify: `app/face_analysis/landmark_extractor.py` (if zone/reason not emitted)

- [ ] **Step 1: Read `app/face_analysis/landmark_extractor.py`**

Identify what the extractor currently returns on failure.

- [ ] **Step 2: If `zone` / `reason` aren't emitted, add them**

Add to the failure return path:
```python
return FaceAnalysisError(
    code="face_too_close",
    message="Face is too close to the frame.",
    details={"zone": "center", "reason": "Face occupies > 80% of frame"},
)
```

- [ ] **Step 3: Verify `generation.py` surfaces `details` in the error response**

In `app/api/generation.py`, the face-error catch should produce:
```python
raise api_error(
    status=422,
    code=err.code,
    message=err.message,
    details=err.details,
)
```

- [ ] **Step 4: Add/update test**

Write a test in `tests/api/test_generation.py` verifying that a face-too-close input yields:
```json
{ "error": { "code": "face_too_close", "message": "...", "details": { "zone": "center", "reason": "..." } } }
```

- [ ] **Step 5: Run**

Run: `cd app && pytest tests/api/test_generation.py -v -k face`
Expected: test passes.

- [ ] **Step 6: Commit**

```bash
git add app/face_analysis/landmark_extractor.py app/api/generation.py tests/api/test_generation.py
git commit -m "feat(api): emit zone + reason in face-analysis errors"
```

---

### Task 22: Backend auto-refund on worker failure

**Files:**
- Modify: worker failure path (find with `grep -rn "job.status = 'failed'" app/`)

- [ ] **Step 1: Find where the worker marks a job failed**

Run: `grep -rn "status.*failed\|status.*cancelled" app/workers/ app/services/`

- [ ] **Step 2: In the worker's failure handler, detect non-user-caused errors**

Non-user-caused: model timeout, internal 5xx from provider, worker crash. User-caused: face-analysis failure.

Pseudocode:
```python
async def on_worker_failure(job_id: UUID, failure_kind: str):
    if failure_kind in ("model_timeout", "provider_5xx", "worker_internal"):
        await credit_service.refund(user_id=job.user_id, job_id=job_id, amount=job.credits_charged)
        await analyses_repo.mark_refunded(job_id)
    await analyses_repo.mark_failed(job_id, reason=failure_kind)
```

- [ ] **Step 3: Write a test**

```python
@pytest.mark.asyncio
async def test_worker_auto_refunds_on_timeout(worker, user_with_credits, submitted_job):
    worker.simulate_failure(submitted_job.id, "model_timeout")
    await worker.finalize(submitted_job.id)
    refreshed = await credit_service.get_balance(user_with_credits.id)
    assert refreshed == user_with_credits.starting_balance  # fully refunded
```

- [ ] **Step 4: Run**

Run: `cd app && pytest tests/services/test_worker.py -v -k auto_refund`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/workers/ tests/services/test_worker.py
git commit -m "feat(worker): auto-refund credits on non-user-caused job failures"
```

---

### Task 23: Copy review pass

**Files:** all files in `mobile/app/` and `mobile/components/` plus `mobile/lib/errors.ts`

- [ ] **Step 1: Search for banned copy patterns**

```bash
cd mobile && grep -rn -iE "oops!|error:|please try|we're sorry" app/ components/ lib/
```

Every match is audited and rewritten in warm/reassuring tone.

- [ ] **Step 2: Audit `mobile/lib/errors.ts`**

Re-read each copy string. Ensure: no exclamation marks (warm), no "Error:" prefix, no "Please" (condescending), no stack traces.

- [ ] **Step 3: Audit primitive components**

`QueryStateView.tsx`, `FaceErrorCard.tsx`, `OfflineBanner.tsx` — check their hardcoded strings.

- [ ] **Step 4: Commit**

```bash
git add mobile/
git commit -m "chore(mobile): copy review pass — warm & reassuring tone"
```

---

### Task 24: Network-chaos QA + Sentry smoke test

- [ ] **Step 1: Build + launch**

```bash
cd mobile && npx expo run:ios
```

- [ ] **Step 2: Run the chaos matrix for each hero screen**

| Screen | Scenario | Expected |
|--------|----------|----------|
| Feed | airplane mode on launch | Offline banner + retry button |
| Feed | toggle airplane while scrolled | Banner appears; next fetch errors gracefully |
| Upload | submit while offline | Error card; retry on reconnect |
| Upload | force face_too_close | FaceErrorCard |
| Result | polling with network chaos | Retry works |
| Result | refund | Success toast |
| All | render crash (trigger via dev button) | ErrorBoundary fallback; Sentry event |

- [ ] **Step 3: Verify Sentry received events**

Check the Sentry dashboard (or set `SENTRY_DSN` to a test project) — confirm queries, mutations, and render crashes all show up with the expected tags.

- [ ] **Step 4: No commit — this is verification only**

If any issue found → fix → commit per-fix.

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task(s) |
|--------------|---------|
| Architecture 5-layer stack | Tasks 2, 4, 6, 13 |
| `QueryStateView` | Task 8 |
| `OfflineBanner` | Task 9 |
| `AppToast` | Task 5 |
| `FaceErrorCard` | Task 10 |
| `ErrorBoundary` enhanced | Task 12 |
| Error taxonomy + copy | Task 2 |
| `parseApiError` | Task 2 |
| Upload migration (retry-in-place, credit balance, FaceErrorCard) | Task 14 |
| Result migration (polling, refund mutation) | Task 15 |
| Feed migration | Task 16 |
| Auth migration | Task 17 |
| Other screens migration | Task 18 |
| Backend refund endpoint | Task 20 |
| Backend structured errors | Already in place (verified in exploration) |
| Backend face-error payload | Task 21 |
| Auto-refund worker | Task 22 |
| Copy review | Task 23 |
| Network-chaos QA | Task 24 |

Gap check: credit balance widget on upload is noted in Task 14 (Step 7 via `generation.isPending` and future step) — **add an explicit step for that**. See Step 7.5 below.

Also: onboarding screen migration is included in Task 18 — covered.

**2. Placeholder scan:**

Found + fixed:
- Task 16, Step 2: "TODO: reactToPost / ..." — this is a pointer to existing code, not a placeholder in the implementation. Flagged with "copy existing bodies from the original `useFeed.ts`". Acceptable — the engineer has the source file.
- Task 20, Step 3: "If the helper doesn't exist with that signature, use whatever the existing errors module exposes — match the pattern from `app/api/generation.py:143–161`." Acceptable — explicit reference pattern.
- Task 22 Step 1: "Find where the worker marks a job failed" — this is a discovery step with the grep command provided. Acceptable.

**3. Type consistency:**

- `AppError` union shape is referenced consistently (Task 2 defines; Tasks 6, 8, 10, 14, 15, 16, 17 consume).
- `parseApiError` signature `(err: unknown) => AppError` consistent throughout.
- `useAppQuery` returns `{ ...query, appError: AppError | null }` consistently.
- `useAppMutation` returns `{ ...mutation, appError, mutate: async }` consistently.
- `showToast({ kind, message, ... })` signature consistent.
- `QueryStateView` props consistent with usage sites.

**Addition from self-review:** Added a Step 7.5 to Task 14 for credit balance widget.

**Task 14, Step 7.5: Add credit balance widget below CTA**

```tsx
import { useAppQuery } from '../lib/hooks/use-app-query';
import { getCreditBalance } from '../lib/api';

const balanceQuery = useAppQuery({
  queryKey: ['credits', 'balance'],
  queryFn: getCreditBalance,
  staleTime: 10_000,
});

// In JSX, below the CTA:
{balanceQuery.data && (
  <Text style={styles.balanceHint}>
    You have {balanceQuery.data.balance} credits. This costs {balanceQuery.data.cost_per_generation}.
  </Text>
)}
```

This assumes `getCreditBalance` exists in the API client. If not, add a minimal wrapper to `mobile/lib/api.ts` first.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-12-error-ux-overhaul.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
