import { QueryCache, MutationCache, QueryClient } from '@tanstack/react-query';
import * as Sentry from '@sentry/react-native';
import { parseApiError, shouldRetry, type AppError } from './errors';
import { showToast } from './toast';

const MAX_RETRIES = 3;
const BASE_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 15000;

function computeDelay(attempt: number, err: AppError): number {
  if (err.kind === 'rateLimit' && err.retryAfter) {
    return err.retryAfter * 1000;
  }
  return Math.min(BASE_RETRY_DELAY_MS * 2 ** attempt, MAX_RETRY_DELAY_MS);
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
