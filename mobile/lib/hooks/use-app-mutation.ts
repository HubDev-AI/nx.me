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
