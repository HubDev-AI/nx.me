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
