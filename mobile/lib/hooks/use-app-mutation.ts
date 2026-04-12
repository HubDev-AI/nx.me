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
  /**
   * If true and the device is offline, enqueue the mutation for replay on
   * reconnect. When queued, `onSuccess` and `onError` do NOT fire in this
   * session — use `onEnqueue` to show a "queued" toast at the call site.
   * Default: false.
   */
  queueOffline?: boolean;
  /** Required if `queueOffline` is true. Identifies the mutation in the queue. */
  mutationKey?: readonly unknown[];
  /** Fires when a mutation is persisted to the offline queue instead of sent. */
  onEnqueue?: (queued: QueuedMutation) => void;
}

export type AppMutationResult<TData, TVariables> = Omit<
  UseMutationResult<TData, unknown, TVariables>,
  'error' | 'mutate' | 'mutateAsync'
> & {
  appError: AppError | null;
  /**
   * Fires the mutation. Resolves when the work completes (online) or after
   * enqueueing (offline with `queueOffline: true`). Rejects on mutation error.
   */
  mutate: (variables: TVariables) => Promise<void>;
};

export function useAppMutation<TData, TVariables>(
  options: AppMutationOptions<TData, TVariables>,
): AppMutationResult<TData, TVariables> {
  const { queueOffline = false, mutationKey, onEnqueue, mutationFn, ...rest } = options;
  const mutation = useMutation({ ...rest, mutationFn, mutationKey });

  const appError = useMemo(
    () => (mutation.error ? parseApiError(mutation.error) : null),
    [mutation.error],
  );

  const mutate = async (variables: TVariables): Promise<void> => {
    if (queueOffline) {
      let isConnected: boolean | null = true;
      try {
        const netState = await NetInfo.fetch();
        isConnected = netState.isConnected;
      } catch {
        // NetInfo failed — assume online and fall through to mutation.
        isConnected = true;
      }
      if (isConnected === false) {
        if (!mutationKey) {
          throw new Error('queueOffline=true requires mutationKey');
        }
        const queued: QueuedMutation = {
          id: `${String(mutationKey[0])}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          mutationKey,
          variables,
          createdAt: Date.now(),
          replayAttempts: 0,
        };
        mutationQueue.enqueue(queued);
        onEnqueue?.(queued);
        return;
      }
    }
    await mutation.mutateAsync(variables);
  };

  return { ...mutation, appError, mutate };
}
